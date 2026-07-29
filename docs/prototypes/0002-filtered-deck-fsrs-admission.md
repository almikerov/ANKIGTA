# Prototype 0002 — filtered-deck FSRS admission

## Verdict: `passed`

Yes. On the tested Anki Desktop 26.05 environment, a real rescheduling
filtered deck named `ANKIGTA Session` can legitimately turn a selected non-top
Card X into Anki's scheduler-top card:

1. build the normal session and observe Anki's actual scheduler-next;
2. empty/reconfigure the same filtered deck to an exact X-only `cid:` search;
3. observe X from `Scheduler.get_queued_cards()` before rating;
4. render and rate that scheduler-admitted card through Anki;
5. rebuild the full exact-ID session afterward.

Anki accepted Again, Hard, Good and Easy only after X was observed
scheduler-top. Each rating produced exactly one target `revlog` row. Across 20
fresh-copy comparisons (five card states × four ratings), post-cleanup card
state, FSRS memory state and semantic `revlog` fields matched the corresponding
ordinary/early-review control within the declared time tolerance.

This result is version-scoped. It does not authorize rating a non-top card
directly, private queue mutation, custom scheduling, or transferring the
prototype harness into production.

## Question and prior failure

Prototype 0001 proved that loading/rendering an arbitrary X does not admit it:
when scheduler-next was Y, `Scheduler.answerCard(X, rating)` failed with
`not at top of queue` before mutation.

Prototype 0002 did not repeat that rejected operation and did not inspect or
mutate private queue internals. It tested whether stock filtered-deck
operations change the admission state first.

## Tested environment

Run date: 2026-07-29, Europe/Moscow.

| Component | Observed value |
| --- | --- |
| Anki Desktop | 26.05 |
| AQT | 26.05 |
| Python | CPython 3.13.13, 64-bit |
| Qt / PyQt | 6.11.0 / 6.11.0 |
| Scheduler | `anki.scheduler.v3.Scheduler`; version attribute 3 |
| Legacy scheduler schema value | 2, as expected for V3 |
| FSRS before setup | disabled in the fresh disposable profile |
| FSRS during all rating scenarios | enabled explicitly through Anki |
| FSRS health check | enabled |
| Prototype collection identity | `cd98f6d0-6c35-4466-997d-0bd8b86432ba` |
| Platform/base | Windows, isolated `-b` base below the prototype runtime |

The fresh profile did not have FSRS enabled. The harness recorded that state,
enabled FSRS through `DeckManager.update_deck_configs` with
`fsrs_reschedule=False`, and re-read the setting before creating test data.

The tested Default preset used:

- learning steps: 1m, 10m;
- relearning step: 10m;
- new cards/day: 1;
- reviews/day: 9999;
- new/review mix: new first;
- maximum answer time: 60 seconds;
- FSRS desired retention and parameters as exposed in the complete captured
  deck configuration.

The complete configuration is in `evidence/baseline_metadata.json`.

## Disposable safety setup

All mutations occurred under:

```text
.scratch/0002-filtered-deck-fsrs-admission-prototype/runtime/
```

The harness:

- required `ANKIGTA_PROTO_0002_ALLOW_DISPOSABLE=YES`;
- verified the active collection path was below that runtime root;
- refused to run while Anki's normal Reviewer was open;
- created a fresh disposable profile and test collection;
- recorded scheduler, FSRS and deck options before scenario mutations;
- created a native Anki backup;
- closed Anki and made an offline copy of the full disposable base;
- made a fresh copy of that same baseline for every state/rating comparison;
- used Anki APIs for every scheduling/deck mutation;
- used SQL only for read-only evidence;
- never opened or copied the user's normal Anki profile.

The source verifier rejects direct database writes, `_backend` calls, scheduler
field assignment, private queue references and a custom `Scheduler` class.

## Required test data

The baseline contains unique notes and cards with rendered question/answer
evidence and complete card/revlog state.

| Role | Note ID | Card ID | Original deck ID |
| --- | ---: | ---: | ---: |
| X, new | 1785274116665 | 1785274116667 | 1785274116652 |
| new card beyond original daily limit | 1785274116669 | 1785274116669 | 1785274116652 |
| excluded from active set | 1785274116670 | 1785274116670 | 1785274116652 |
| Y, new | 1785274116672 | 1785274116672 | 1785274116671 |
| available learning | 1785274116674 | 1785274116674 | 1785274116673 |
| available relearning | 1785274116676 | 1785274116676 | 1785274116675 |
| due review with FSRS state | 1785274116678 | 1785274116678 | 1785274116677 |
| future/not-due review with FSRS state | 1785274116679 | 1785274116679 | 1785274116678 |
| suspended | 1785274116681 | 1785274116681 | 1785274116680 |
| buried | 1785274116683 | 1785274116683 | 1785274116682 |

Learning/relearning/review states were produced through legitimate scheduler
answers and `set_due_date()` during disposable test-data setup, never through
SQL or direct scheduler-field writes. The comparison baseline begins after
those setup operations, so their setup `revlog` rows are separated from
scenario deltas.

## Supported API inventory

| API | Prototype use | Stability classification |
| --- | --- | --- |
| `gui_hooks.profile_did_open` | wait for a loaded disposable profile | supported add-on hook |
| `Collection.add_note()` | create disposable cards | public/documented add-on surface |
| `DeckManager.update_deck_configs()` | explicitly enable/disable FSRS for disposable scenarios | public Python wrapper; protobuf request is version-sensitive |
| `Scheduler.get_or_create_filtered_deck()` | create/get `ANKIGTA Session` configuration | current non-private implementation surface; upstream says new code should prefer it |
| `Scheduler.add_or_update_filtered_deck()` | save configuration and build/rebuild exact `cid:` membership | current non-private implementation surface used by stock AQT filtered-deck UI |
| `Scheduler.rebuild_filtered_deck()` | rebuild an unchanged filtered-deck configuration | current non-private implementation surface used by stock AQT |
| `Scheduler.empty_filtered_deck()` | Pause/cleanup and return cards to home decks | current non-private implementation surface used by stock AQT |
| `DeckManager.remove()` | normal Stop removal after emptying | current public/non-private deck surface |
| `Scheduler.get_queued_cards()` | observe scheduler-next without advancing it | current non-private V3 method; documented in source as idempotent |
| `Scheduler.getCard()` | obtain the observed top card with timer started | supported legacy add-on surface; version-sensitive |
| `Card.question()` / `Card.answer()` | render scheduler-admitted and Preview-only cards | public/documented add-on surface |
| `Scheduler.answerButtons()` / `nextIvlStr()` | expose allowed ratings and interval labels | supported legacy surface; version-sensitive |
| `Scheduler.answerCard()` | submit Again/Hard/Good/Easy to Anki | supported legacy surface; delegates to V3 backend and enforces scheduler-top |
| `Scheduler.set_due_date()`, `suspend_cards()`, `bury_cards()` | create disposable state variants | current non-private scheduler surfaces; setup only |
| `Collection.create_backup()` | native pre-scenario backup | public collection surface |
| `Collection.db` `SELECT` methods | primary evidence only | low-level/undocumented for product use; excluded from the product path |

The filtered-deck APIs are acceptable for this pinned compatibility result
because they are non-underscore methods used by Anki's own AQT operations.
They are not promised as a stable cross-version protocol. ADR 0012's version
pin and integration test gate remain mandatory.

Relevant upstream primary sources:

- [Anki 26.05 scheduler base](https://github.com/ankitects/anki/blob/26.05/pylib/anki/scheduler/base.py)
- [Anki 26.05 V3 scheduler](https://github.com/ankitects/anki/blob/26.05/pylib/anki/scheduler/v3.py)
- [Anki 26.05 filtered-deck UI](https://github.com/ankitects/anki/blob/26.05/qt/aqt/filtered_deck.py)
- [Anki 26.05 scheduling operations](https://github.com/ankitects/anki/blob/26.05/qt/aqt/operations/scheduling.py)
- [Anki Manual: filtered decks](https://docs.ankiweb.net/filtered-decks.html)

## Scenario results

### S1 — normal exact-ID session: passed

The input contained 11 references and 9 unique card IDs. X and Y were each
duplicated. Seven eligible cards entered. Suspended and buried cards were the
only requested cards excluded; the card outside the active set did not enter.

The build:

- created a real dynamic deck named `ANKIGTA Session`;
- had rescheduling enabled;
- used exact `cid:` searches;
- created no `revlog`;
- placed each admitted card under the session deck while preserving its home
  deck in Anki's original-deck field.

Exact-ID input ordering did not control scheduler-top. In the broad mixed-state
session, the available learning card became scheduler-top, even though Y was
the first search term. This is a disproven assumption and a required product
constraint: the Next Card Indicator must always follow Anki's observed
scheduler-next.

### S2 — admit non-top exact X: passed

For the required two-new-card normal session:

- scheduler-next before manual selection was Y (`1785274116672`);
- X (`1785274116667`) was present but non-top;
- the harness emptied/reconfigured the same owned session to X-only using
  `add_or_update_filtered_deck()`;
- scheduler-next after admission was X;
- X rendered successfully and exposed Again, Hard, Good and Easy;
- S2 itself did not submit a rating.

This is the supported admission mechanism that prototype 0001 lacked.

### S3 — rate admitted X: passed

On four fresh baseline copies, X was admitted X-only and then rated Again,
Hard, Good or Easy. Every case:

- observed X scheduler-top first;
- called Anki's scheduler once;
- created exactly one new X `revlog` row;
- recorded complete post-rating card and FSRS state;
- created no non-target rating or non-target card-state change.

Durable `reviewTransactionId` idempotency remains outside this prototype, as
required by the handoff. The result proves scheduler admission and one
coordinator call, not a production journal.

### S4 — ordinary Reviewer/scheduler comparison: passed

The matrix used a fresh control copy and fresh experiment copy for each case:

| State | Ratings compared | Result |
| --- | --- | --- |
| new X | Again, Hard, Good, Easy | 4/4 equivalent |
| learning | Again, Hard, Good, Easy | 4/4 equivalent |
| relearning | Again, Hard, Good, Easy | 4/4 equivalent |
| due review | Again, Hard, Good, Easy | 4/4 equivalent |
| future review | Again, Hard, Good, Easy | 4/4 equivalent to supported early-review control |

For new, learning, relearning and due-review controls, the target was made
legitimately top in its original deck and answered through Anki's normal
scheduler path. For future review, which cannot be ordinary original-deck
scheduler-next, the control was a separate stock rescheduling early-review
filtered deck.

Compared exactly:

- card type/queue/interval/factor/reps/lapses/steps;
- home/current deck after cleanup;
- FSRS stability, difficulty, desired retention and decay;
- custom data other than the answer timestamp;
- `revlog.ease`, `ivl`, `lastIvl`, `factor` and `type`.

Defined tolerances:

- intraday `due` and FSRS last-review timestamps: at most 10 seconds between
  sequential process runs;
- card `mod`/`usn`, `revlog.id` and measured answer time were treated as
  expected process-time metadata, not scheduling divergences.

Observed intraday differences were 3–4 seconds. No unexplained scheduling
difference remained.

### S5 — new cards and limits: passed

The original X deck had `new.perDay=1`. Its ordinary queue exposed X and did
not expose `NEW_LIMIT_EXTRA`. An exact filtered-deck request for both cards
admitted and queued both.

Therefore filtered-deck construction bypassed the original new-card daily
limit in the tested version. Rebuilding the unchanged session preserved the
same two-card membership, order and counts.

Product implication: `Total` for `ANKIGTA Session` must be based on the actual
unique available filtered membership, not ordinary deck daily limits.

### S6 — learning and relearning lifecycle: passed

Learning and relearning targets were each tested on a fresh copy:

1. build full session;
2. rebuild X-only for the state target;
3. observe it top and rate Good;
4. rebuild the full session;
5. empty the session.

Both created one `revlog` row, occurred exactly once after the full rebuild,
retained scheduler-controlled steps/due values, and returned to the correct
home deck. No card was stranded and no duplicate presentation was introduced.

### S7 — suspended and buried: passed

Exact `cid:` requests admitted neither suspended nor buried cards. Their
states were byte-equivalent before and after build/cleanup. Both questions and
answers could still be rendered in explicit Preview-only mode; no rating
choices or scheduler call were exposed.

### S8 — future/not-due review: passed for explicit early review

Anki 26.05 allowed the future review card into a rescheduling filtered deck,
made it scheduler-top, and exposed four ratings. For all four ratings, the
`ANKIGTA Session` result matched a separate supported early-review filtered
deck control under the S4 comparison rules.

Product rule: a future review may be rated only when the product explicitly
chooses this tested early-review behaviour and first observes the card
scheduler-top. Otherwise it remains Preview only. Ordinary original-deck
availability must not be inferred.

### S9 — rebuild full session after manual X: passed

Starting from Y top in the two-new-card session, X was admitted and rated Good,
then the complete current active set was rebuilt.

- X occurred once, not twice;
- Y remained present;
- the existing learning card remained present;
- no card was lost or stranded;
- scheduler-next after the full rebuild was the available learning card, which
  is correct Anki priority and not an input-order failure.

### S10 — Pause and normal Stop: passed

Two build/empty cycles restored every card's scheduling state and home deck.
Normal Stop then emptied and removed the filtered deck. No card retained a
non-zero original-deck field and `ANKIGTA Session` no longer existed.

### S11 — leftover-session recovery: passed for defined windows

The disposable Anki process was forcibly terminated with `os._exit()`:

| Window | X rows after recovery | Duplicate | Stranded |
| --- | ---: | --- | ---: |
| before rating | 0 | no | 0 |
| after committed Good | 1 | no | 0 |
| immediately after full rebuild returned | 1 | no | 0 |

On restart the harness detected the leftover deck, reconciled the known
transaction result before cleanup, submitted no replacement rating, emptied
and rebuilt using supported operations, then emptied/removed the session.

Not proved: termination inside the backend's atomic rebuild transaction. The
harness could deterministically terminate immediately after the operation
returned, but did not inject a crash into Anki internals.

### S12 — invalid and conflicting inputs: passed

The following failed without card mutation:

- wrong collection identity;
- stale card ID;
- card outside the active set;
- rebuild while a rating transaction was open;
- unsupported Anki version;
- FSRS disabled in an actual disposable copy;
- collision with a normal user deck named `ANKIGTA Session`.

Duplicate input IDs were accepted only after stable de-duplication. The
unrelated colliding deck remained normal, retained its name and contents, and
was neither deleted nor repurposed.

## Proven and disproven assumptions

Proven for Anki Desktop 26.05 on the tested Windows/FSRS configuration:

- an X-only rescheduling filtered-deck rebuild can legitimately admit exact X;
- Anki accepts its rating after X is observed scheduler-top;
- exact `cid:` membership is unique;
- empty/rebuild preserves tested new, learning, relearning and review
  lifecycles;
- filtered rating matches ordinary scheduler/FSRS behaviour for the tested
  state/rating matrix;
- suspended/buried requests remain unavailable and Preview-only;
- supported early review of a future card is equivalent through
  `ANKIGTA Session`;
- recovery at the three defined transaction boundaries creates no duplicate
  rating and strands no card.

Disproven:

- exact-ID search order necessarily determines scheduler-top;
- a broad session with Y first necessarily shows Y before an available
  learning card;
- filtered construction respects the original new-card daily limit;
- merely requesting suspended/buried IDs admits them.

Still forbidden/unproved:

- rating an arbitrary non-top card directly;
- behaviour on any Anki version other than 26.05;
- a stable production collection-identity source;
- durable production `reviewTransactionId` journaling;
- a crash injected inside Anki's rebuild transaction;
- treating low-level SQL reads as a production API.

## Product fallbacks

- If exact X cannot be observed scheduler-top after supported admission: do not
  rate; Preview only.
- Suspended or buried: Preview only; never unbury/unsuspend implicitly.
- Unsupported Anki version, V3 absent, or FSRS disabled: block session creation
  and ratings; Preview may remain available.
- Wrong collection identity, stale/outside-active card, open rating
  transaction, or session-name collision: reject without mutation.
- Future/not-due review: rate only under the explicit tested early-review rule;
  otherwise Preview only.
- Leftover session with an unknown transaction result: reconcile the
  transaction before empty/rebuild or offering another rating.

## ADR and baseline impact

- **ADR 0003**: compatibility gate passes for the exact tested environment.
  `ANKIGTA Session` may remain the preferred mechanism, guarded by a
  version-pinned integration test.
- **ADR 0007**: strengthened. The companion add-on has a supported admission
  sequence before coordinating the scheduler answer. It still must never
  answer an arbitrary non-top card.
- **ADR 0008**: unchanged in scope. One-call rating and restart reconciliation
  boundaries worked, but the production durable idempotency journal remains a
  separate requirement.
- **ADR 0012**: strengthened. The relied-on filtered-deck methods are
  non-private but version-sensitive; v1 must remain pinned to tested Windows,
  Anki and FSRS combinations.
- **ADR 0017**: supported. Anki alone changed scheduling data and `revlog`.
- **Confirmed baseline**: replace the unconditional non-top Preview-only rule
  with a conditional rule: Preview-only unless the tested supported
  filtered-deck admission first makes exact X scheduler-top. The indicator and
  counts must follow observed Anki state, not input ordering.

## Reproduction and verification

Fresh complete run:

```powershell
powershell -ExecutionPolicy Bypass -File .scratch/0002-filtered-deck-fsrs-admission-prototype/run.ps1
```

On a completely fresh base, Anki 26.05 may show its one-time interface-language
dialog despite `-l en`. Keep English (United States) selected and press OK; the
remaining copied bases run without interaction.

Read-only verification:

```powershell
$env:PYTHONIOENCODING='utf-8'
python .scratch/0002-filtered-deck-fsrs-admission-prototype/verify_evidence.py
```

Observed verifier summary:

```json
{
  "verification": "passed",
  "overallVerdict": "passed",
  "answer": "yes: supported X-only rebuild made non-top X scheduler-top; Anki rated it once; tested FSRS/lifecycle results matched controls",
  "limitation": "termination inside the atomic backend rebuild transaction was not controllable; immediately-after-return recovery was proved"
}
```

The initial run exposed two harness assumptions: the broad mixed-state session
correctly prioritized a learning card over Y, and recovery metadata initially
asked a filtered deck for a normal deck preset. Both initial artifacts are
preserved under `failed-attempts/`; the canonical evidence was regenerated
from fresh baseline copies after correcting the harness. Neither correction
changed Anki scheduling state directly.

## Primary evidence hashes

All 69 manifest entries are verified by `evidence/hashes.json`.

| Artifact | SHA-256 |
| --- | --- |
| add-on `__init__.py` | `617b1419ceb41c9e6cbc6629aca961f42d9b267582917c12dd58f9027d1543d1` |
| pure admission guards | `cfabba736bd9f38389ff74eadd23a94f24938ce36b2f98418c6c225b092e9e5a` |
| read-only verifier | `0f839d4eb0897935dc730769e4d654dde10a7144e7a787c274cd6a0574f20d03` |
| core scenarios | `2a312a3c8609bd3e401dd94534188140c6389c0b2a8e98ae5324560087ae4d73` |
| representative X/Good experiment | `a0081818ee2394b44b54a85465dc8aa6a59d5c9e8209c20269e8952ef8d0bfe8` |
| learning lifecycle | `88f58de0a761d8b8416ac608a275258c4041689edcc6c3f726405a2a9ee93d26` |
| relearning lifecycle | `6d8f3126d8e6225e249f96771190e880b04a58eeb09d36698294b6d4d2c0d24b` |
| X rebuild lifecycle | `507cff683539af9ffc5b9b49b5f2b356a949d658a4c3fe5fa56a4f34a75fb5e8` |
| recovery before rating | `29d22f44b11ef4015ea24cc8475860d4b8d18eca931f0e5ac282f446884cf637` |
| recovery after rating | `61833150fce65aee02c2e54648fe43ad40f5d677026665b5358dc780ba10e4dd` |
| recovery after rebuild | `8f5123b12d705250d1432a9427bbc68137ca8777af0809f974745d2dd1620c7a` |
| hash manifest itself | `1828799bea18502a3ecdb02dbbed0f14c7c2b3b583a3f4ccb79a159413229838` |
| verifier output | `8ab0fde3605dc0bca91e17982d1ad8debe1fdd2de5c0a48a00582cb980f54ae7` |

## Is another prototype iteration justified?

Not for the narrow Anki 26.05 admission question: it is answered `yes`.

A new compatibility iteration is justified only for another Anki version or a
materially different FSRS/deck configuration. Production collection identity,
durable Review Transaction journaling, UI/transport and implementation remain
separate gates and must not be folded into this throwaway prototype.

The workspace is not a Git repository, so the disposable prototype could not
be captured on the throwaway branch requested by the prototype workflow. Its
source, failed attempts, runtime copies and primary evidence remain isolated
under `.scratch/0002-filtered-deck-fsrs-admission-prototype/`.
