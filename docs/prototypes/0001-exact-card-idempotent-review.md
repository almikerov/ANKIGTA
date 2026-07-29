# Prototype 0001: exact-card, idempotent Anki review

## Verdict

`failed`

On Anki Desktop 26.05 with the V3 scheduler and FSRS, a companion add-on can
load and render an exact Card X while Anki reports Card Y as scheduler-next.
It cannot submit a rating for X through the tested scheduler API while Y
remains at the top of the queue: `Scheduler.answerCard(X, Good)` raises
`anki.errors.InvalidInput: not at top of queue`.

The failure occurs before a card or `revlog` mutation. It is therefore safe,
but it means the minimum contract and success criteria are not met.

The prototype did **not** bypass the restriction by editing SQLite, changing
queue fields, implementing a scheduler, using a filtered deck, or relying on a
non-reproducible internal side effect.

## Question fixed before testing

Can an add-on running inside Anki open one exact Anki Card when the scheduler
would select another Card next, then apply Again/Hard/Good/Easy exactly once
when the same `reviewTransactionId` is submitted repeatedly?

The pre-recorded observable success criterion was:

- scheduler-next is Y;
- `openExactCard()` returns and renders X;
- opening X does not change X or create `revlog`;
- the first T1 rating request creates exactly one X `revlog` row;
- identical retry returns the committed result without mutation;
- conflicting retry is rejected;
- a lost response can be reconciled;
- all four ratings are exercised where Anki exposes them.

The criterion is recorded in
`.scratch/0001-exact-card-idempotent-review-prototype/README.md`.

## Tested environment

Test date: 2026-07-28, Europe/Moscow.

| Component | Observed value |
| --- | --- |
| OS | Microsoft Windows 11 Pro, 10.0.26200, build 26200, AMD64 |
| Anki executable | file/product version 26.5 |
| Anki runtime | 26.05 |
| AQT | 26.05 |
| Embedded Python | CPython 3.13.13, MSC v.1944, 64-bit |
| Qt | 6.11.0 |
| PyQt | 6.11.0 |
| Scheduler | `anki.scheduler.v3.Scheduler`; `version=3`; legacy scheduler version 2 |
| FSRS | enabled explicitly on the disposable profiles before test data/reviews |
| FSRS parameters | no parameter vector supplied or changed; built-in defaults remained in use |
| Main window state before testing | `deckBrowser`, not normal Reviewer |

The fresh Anki 26.05 profile initially reported FSRS disabled. Before any test
data or rating, this fact was written to
`versions_before_test_data.json`. FSRS was then explicitly enabled only in the
disposable profile through
`DeckManager.update_deck_configs(fsrs=True, fsrs_reschedule=False)`. The full
before/after configuration is in `fsrs_enablement_main.json`; this was not a
silent option or parameter change.

## Disposable setup and safety

All collections used by the prototype live under:

```text
.scratch/0001-exact-card-idempotent-review-prototype/runtime/
```

The add-on refuses to run unless the collection path is below this runtime
directory and `ANKIGTA_PROTO_ALLOW_DISPOSABLE=YES` is present.

Two separate disposable collections were created:

| Role | Collection identity | Deck ID | Relevant Card ID |
| --- | --- | ---: | ---: |
| Main | `08698941-aa22-4a95-ba5b-bb427c8d3604` | `1785270730720` | Y `1785270730726`; X `1785270730728` |
| Foreign | `807cfca5-862a-460a-b42b-6113f8bce8bf` | `1785270830480` | foreign `1785270830483` |

The collection identity is a prototype-owned UUID tied to the disposable
collection. A stable production derivation of Anki collection identity was not
proved here.

Before the first rating:

1. exact runtime versions, scheduler mode, FSRS state and deck configuration
   were recorded;
2. the disposable deck and eight fresh cards were created through Anki
   collection APIs;
3. initial `cards` and `revlog` rows were recorded;
4. scheduler-next was observed, not inferred;
5. Anki's public `Collection.create_backup()` created
   `backup-2026-07-28-23.32.10.colpkg`;
6. with Anki closed, the whole disposable base was copied to
   `runtime/main-base-offline-copy-before-rating`;
7. the core probe and every rating control used separate copies of that
   pre-rating base.

The user's real collection was never loaded by the prototype add-on. The
already-running real Anki window was closed while it was on the deck list, then
all launches used an explicit `-b` disposable base.

SQL was used only for evidence reads. A source scan found no calls to
`db.execute`/`db.executemany` and no `INSERT`, `UPDATE cards` or `DELETE`
statements. No filtered-deck operation is present.

## Test data

The main disposable deck contained fresh Basic cards:

| Logical name | Note ID | Card ID | Initial due position |
| --- | ---: | ---: | ---: |
| Y | `1785270730726` | `1785270730726` | 1 |
| X | `1785270730728` | `1785270730728` | 2 |
| LostResponse | `1785270730729` | `1785270730729` | 3 |
| Again | `1785270730730` | `1785270730730` | 4 |
| Hard | `1785270730731` | `1785270730731` | 5 |
| Good | `1785270730733` | `1785270730733` | 6 |
| Easy | `1785270730734` | `1785270730734` | 7 |
| InvalidRating | `1785270730735` | `1785270730735` | 8 |

Every initial card had `type=0`, `queue=0`, `ivl=0`, `reps=0`; the initial
collection-wide `revlog` was empty.

## Scenario results

### S1 — exact card differs from scheduler-next: passed

Observed scheduler-next:

```json
{
  "cardId": 1785270730726,
  "counts": {"new": 8, "learning": 0, "review": 0},
  "state": {"type": 0, "queue": 0, "due": 1, "ivl": 0, "reps": 0}
}
```

`openExactCard(collectionIdentity, 1785270730728)` returned X, not Y, with:

- question render containing `PROTOTYPE Card X question`;
- answer render containing both question and
  `PROTOTYPE Card X answer`;
- Card X state `type=0`, `queue=0`, `due=2`, `ivl=0`, `reps=0`;
- Again `<1m`, Hard `<6m`, Good `<10m`, Easy approximately `9–10d`.

The exact Card ID differed from scheduler-next. Byte-for-byte card scheduling
fields and the empty X `revlog` were unchanged by opening/rendering.

### S2 — one successful rating of non-top X: failed

Input:

```json
{
  "reviewTransactionId": "T1",
  "collectionIdentity": "08698941-aa22-4a95-ba5b-bb427c8d3604",
  "cardId": 1785270730728,
  "rating": "Good"
}
```

The add-on loaded X, started the same in-memory card timer used by Reviewer, and
called Anki's scheduler. Anki returned:

```text
anki.errors.InvalidInput: not at top of queue
```

After the error:

- scheduler-next remained Y;
- X remained `type=0`, `queue=0`, `due=2`, `ivl=0`, `reps=0`;
- Y remained unchanged;
- X `revlog` remained empty;
- `getReviewTransaction("T1")` returned `status=not_applied`.

A second identical submission in the clean core-probe copy returned the same
Anki error and again caused no database mutation.

One earlier exploratory disposable base produced an inconsistent observation:
after a prior `not at top of queue`, a later same-process submission applied
Good to X. The behavior was not reproduced from the clean pre-rating copy.
That diagnostic is preserved in
`evidence/diagnostics/attempt-05-postcondition.json`. It is evidence that an
exception must not be assumed to leave undocumented scheduler state suitable
for blind retry; it is not a supported solution.

### S3 — identical retry after committed T1: blocked

There is no committed T1 for X in the clean core probe, so the required S3
precondition does not exist. Repeating the failed T1 did not mutate X, but it
also could not return a committed result.

Control result, limited to scheduler-top Y: after a successful commit, an
identical retry returned the same stored result and did not change the card or
`revlog`.

### S4 — conflicting retry: blocked for X; passed in control

Because X/T1 never committed, the required post-commit conflict test cannot be
performed for the exact non-top card.

In every scheduler-top control, reusing the committed transaction ID with a
different rating returned `transaction_conflict` and did not mutate the card.
This validates the prototype journal logic, not arbitrary-card schedulability.

### S5 — lost response: blocked for non-top X; passed in control

A lost response cannot be simulated after a successful exact-card mutation
because the scheduler does not allow that mutation.

In the scheduler-top Good control:

1. Anki applied Good and created one `revlog` row.
2. The harness stored the committed result, then deliberately withheld it.
3. `getReviewTransaction("CONTROL-Good")` returned `status=applied`.
4. Retrying returned the same committed result.
5. No second `revlog` row or schedule change occurred.

This proves only in-process reconciliation. Process-restart durability was not
tested and must not be inferred.

### S6 — invalid identity and stale card: passed

All cases failed explicitly and without mutation:

| Case | Result |
| --- | --- |
| wrong collection identity for X | `wrong_collection_identity` |
| stale Card ID `1785271730734` | `card_missing` |
| foreign collection identity + foreign Card ID | `wrong_collection_identity` |
| unsupported rating `Excellent` | `rating_not_permitted` |

The prototype checked collection identity before looking up a local numeric
Card ID. No heuristic replacement was attempted.

### S7 — all four ratings: passed only as scheduler-top controls

Each rating used a fresh copy of the pre-rating disposable base. In every
control, Y was proven scheduler-next and was rated once.

| Rating | `revlog.ease` | `revlog.ivl` | Post card state | Retry/conflict |
| --- | ---: | ---: | --- | --- |
| Again | 1 | -60 | `type=1`, `queue=1`, `reps=1` | no second mutation |
| Hard | 2 | -330 | `type=1`, `queue=1`, `reps=1` | no second mutation |
| Good | 3 | -600 | `type=1`, `queue=1`, `reps=1` | no second mutation; lost response reconciled |
| Easy | 4 | 9 | `type=2`, `queue=2`, `ivl=9`, `reps=1` | no second mutation |

Each control created exactly one new `revlog` row. These controls distinguish
the exact-card/top-of-queue restriction from a broken FSRS setup, rating
mapping, or transaction journal.

## Success criteria

| Criterion | Result | Evidence |
| --- | --- | --- |
| `collection identity + cardId` identifies X | partially passed | prototype UUID validation worked; production collection identity remains unproved |
| X opens while scheduler-next is Y | passed | Y `1785270730726`; X `1785270730728` |
| current render and allowed ratings obtained | passed | question, answer and four interval labels captured |
| first T1 changes X exactly once | **failed** | `not at top of queue`; no mutation |
| identical retry returns committed X result without a second review | **failed / blocked** | no committed X result exists |
| conflicting committed T1 reuse is rejected without mutation | **failed / blocked for X** | passed only in scheduler-top controls |
| lost response can be reconciled unambiguously | **failed / blocked for X** | passed only in an in-process scheduler-top control |
| result contains X post-rating state and Anki next card | **failed** | no supported X rating committed |
| no custom scheduler | passed | all scheduling mutations were delegated to Anki |

The handoff states that the prototype passes only if all criteria are observed.
Therefore the correct verdict is `failed`, not `partially passed`.

## APIs used and stability

| API | Use | Status in tested Anki |
| --- | --- | --- |
| `gui_hooks.profile_did_open` | wait for a loaded disposable profile | supported add-on hook |
| `Collection.add_note()` and deck APIs | create disposable test data | public Python API |
| `DeckManager.get_deck_configs_for_update()` / `update_deck_configs()` | observe and explicitly enable FSRS | public Python wrapper over protobuf; version-specific request shape |
| `Scheduler.get_queued_cards(fetch_limit=1)` | observe scheduler-next | current non-underscore V3 method; source calls it idempotent |
| `Collection.get_card()` | load exact Card ID | public Python API |
| `Card.question()` / `Card.answer()` | render exact question and answer | documented add-on API |
| `Scheduler.answerButtons()` / `nextIvlStr()` | exposed ratings and interval labels | legacy helper surface; not suitable as a long-term stable contract |
| `Card.start_timer()` | satisfy Reviewer/scheduler answer precondition | non-underscore method, but the precondition is not expressed by `answerCard()` |
| `Scheduler.answerCard(card, ease)` | delegate rating to Anki | documented legacy spelling; enforced top-of-queue and rejected X |
| `Collection.create_backup()` | native pre-rating backup | public collection method |
| `Collection.db` SELECT queries | read card/revlog evidence | evidence-only low-level read; not part of the product path |

Relevant upstream primary sources:

- [Anki add-on docs: the `anki` module](https://addon-docs.ankiweb.net/the-anki-module.html)
- [Anki 26.05 V3 scheduler source](https://github.com/ankitects/anki/blob/26.05/pylib/anki/scheduler/v3.py)
- [Anki 26.05 Reviewer source](https://github.com/ankitects/anki/blob/26.05/qt/aqt/reviewer.py)
- [Anki 26.05 deck-config protobuf](https://github.com/ankitects/anki/blob/26.05/proto/anki/deck_config.proto)
- [Anki manual: isolated base folder with `-b`](https://docs.ankiweb.net/files.html)

The required exact-card scheduling behavior is not available through the
tested public/legacy scheduler surface. A solution would need a supported way
to make X the scheduler's legitimate top card or would depend on internal queue
manipulation. This prototype did not test or endorse such manipulation.

## Evidence and reproducible commands

Disposable source and evidence:

```text
.scratch/0001-exact-card-idempotent-review-prototype/
├── README.md
├── run.ps1
├── verify_evidence.py
├── addon/__init__.py
└── evidence/
    ├── initial_state_before_backup.json
    ├── main_metadata.json
    ├── foreign_metadata.json
    ├── fsrs_enablement_main.json
    ├── native_backup.json
    ├── offline_base_copy_complete.json
    ├── core_probe_results.json
    ├── control_again.json
    ├── control_hard.json
    ├── control_good.json
    ├── control_easy.json
    └── diagnostics/
```

Fresh one-command run:

```powershell
powershell -ExecutionPolicy Bypass -File .scratch/0001-exact-card-idempotent-review-prototype/run.ps1
```

On a completely fresh Anki base, Anki may ask twice to confirm the interface
language for each newly created base. No collection choice or rating is
performed through that UI.

Read-only evidence verification:

```powershell
$env:PYTHONIOENCODING='utf-8'
python .scratch/0001-exact-card-idempotent-review-prototype/verify_evidence.py
```

Observed verifier output:

```text
verification: passed
coreVerdict: failed: arbitrary non-top card rejected
schedulerNext: 1785270730726
openedExactCard: 1785270730728
Again/Hard/Good/Easy: one revlog each; retryMutated=false; conflictMutated=false
processRestartDurability: not proved
```

Primary evidence SHA-256:

| File | SHA-256 |
| --- | --- |
| add-on `__init__.py` | `A8BC5060D71FF104534D18C8939854025F6F2809D805598D59F8563A69E79063` |
| `core_probe_results.json` | `11EBACA12E1A8F1EAB6F02DA149E77A1688DA6A8E2B59E302B7FE729BB2EC2F9` |
| `control_again.json` | `4512DA5B9BEE5D40A5565C107EEFF03F7B248D63E3DB4C2DAC19311C9B4186BE` |
| `control_hard.json` | `2BA5DB952D1FB466A7AFF343B76B6C1559C77CA288E309522C9D45695416439C` |
| `control_good.json` | `72C8B08920FE59E8B6BDDEED0375E926EFDF8233460F984E24434BCF7FA5AEEC` |
| `control_easy.json` | `2C185036A799CA5BFEEC9FBF9EE3340E09D9454B467112A7F6DCCB07C647D990` |
| `initial_state_before_backup.json` | `27A9FE7142CE9350C7A1C2FFAC842B8A4DF3EA81E00F2D3260CD113DD355461A` |

The workspace directory is not a Git repository, so the prototype could not be
captured on a throwaway Git branch. It remains explicitly isolated under
`.scratch/`.

## Discovered constraints

1. Rendering an arbitrary Card and rating it are separate capabilities.
   `get_card()` plus `question()`/`answer()` works without advancing it.
2. In Anki 26.05, the tested scheduler answer path requires the Card to be at
   the top of Anki's queue.
3. A scheduler exception must not be followed by assumptions about private
   in-memory queue state. The non-reproducible diagnostic makes this especially
   important.
4. Idempotency can prevent duplicate scheduler calls only after the coordinator
   has an unambiguous committed result. It cannot make an unsupported first
   scheduler operation valid.
5. An in-memory transaction journal is sufficient for simulated lost-response
   reconciliation in one process, but not for restart durability.
6. Anki 26.05's fresh profile did not start with FSRS enabled in this
   environment; the exact configuration must be observed and recorded.
7. A production-quality stable Anki collection identity still needs a separate
   decision/proof.

## ADR and baseline impact

- **ADR 0007** (`companion add-on` as sole Review Transaction coordinator):
  ownership remains sound, but the statement that it can apply a rating to an
  arbitrary exact Card through Anki's scheduler is contradicted for Anki 26.05
  unless X is first made scheduler-top by a separately supported mechanism.
- **ADR 0008** (idempotent ratings): supported by the scheduler-top controls,
  but durable storage and crash recovery remain unproved.
- **ADR 0009** (collection-scoped card links): supported at the coordinator
  validation boundary; the actual production collection-identity source is
  still open.
- **ADR 0012** (pin tested Windows/FSRS Anki versions): strongly supported;
  this behavior is version- and API-sensitive.
- **ADR 0017** (Anki authoritative): supported. The prototype did not calculate
  schedules or write scheduling fields.
- **ADR 0003** (filtered-deck gate): neither supported nor contradicted; filtered
  decks were intentionally not tested.
- **Confirmed baseline, early review rule**: on Anki 26.05, a non-top exact Card
  must be treated as Preview only unless a separate prototype proves a
  supported Anki mechanism that legitimately makes it scheduler-top.

## Unanswered questions

- Is there a documented, supported Anki API in a later tested version that
  admits an exact Card into the active scheduler queue without custom queue
  mutation?
- What production mechanism supplies a durable collection identity?
- What durable journal and transaction states safely distinguish committed,
  rejected and unknown outcomes across process restart?
- Does the separately gated filtered-deck mechanism make X legitimately
  scheduler-top without changing normal FSRS behavior? This belongs only to
  prototype 2.

## Is another iteration needed?

Do not iterate on this same prototype by probing private queue internals. For
Anki 26.05, the question has been answered: the tested supported path fails.

A new exact-card iteration is justified only if:

1. a newer pinned Anki version exposes a documented supported API for the
   operation; or
2. the architecture changes so X is legitimately scheduler-top before rating.

The already-planned filtered-deck/FSRS compatibility prototype remains a
separate proof gate and must not retroactively convert this result into a pass.

