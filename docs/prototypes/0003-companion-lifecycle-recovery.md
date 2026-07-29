# Prototype 0003 — companion lifecycle and durable recovery

## Verdict: `partially passed`

The compound lifecycle contract is **not safe to ship as currently written**.
The independently useful durable-recovery portion passed, but three required
compatibility gates did not:

1. Anki Desktop 26.05 has no documented add-on API for selecting and opening
   another profile. The tested A → B → A path is the non-private AQT path used
   by Anki's own Switch Profile action, but it is not a supported add-on
   contract.
2. Anki 26.05 exposes no native collision-resistant collection UUID. A
   prototype-owned UUID stored in collection config remained stable across
   restart and profile rename, but copy/clone semantics remain a production
   policy problem.
3. `AnkiQt.moveToState("deckBrowser")` closes an unrated Reviewer quickly and
   without mutation, but immediately cleaning up the Reviewer while its
   asynchronous rating is starting leaves a stock callback boundary that
   cannot be proved safe. The backend committed exactly once in the observed
   run, yet `Reviewer.cleanup()` clears `Reviewer.card` before the normal
   completion callback has finished using Reviewer state.

Therefore the answer to the handoff's complete question is **no, not through a
fully supported and proved Anki lifecycle contract**. The prototype did prove
that a companion-owned durable journal can recover one
`reviewTransactionId` exactly once at the tested process boundaries and delay
`ANKIGTA Session` restoration until reconciliation.

This is disposable compatibility evidence, not production ANKIGTA code.

## Prior constraints reused

Prototype 0001's negative result remains binding: rendering or loading an
arbitrary non-top card does not admit it to Anki's scheduler.

Prototype 0002's positive result was reused without repeating its full
scheduling matrix: build an owned rescheduling filtered deck, temporarily
rebuild it as exact X-only, observe X as scheduler-top, answer through Anki,
then rebuild the complete exact-ID session only after transaction
reconciliation.

## Tested environment

Run date: 2026-07-29, Europe/Moscow.

| Component | Observed value |
| --- | --- |
| OS | Windows 11, build family `10.0.26200` |
| Anki Desktop / AQT | 26.05 / 26.05 |
| Upstream source | tag `26.05`, commit `e64c6b1aee3e8d668fb8bbe084beada8e070d985` |
| Python | CPython 3.13.13, 64-bit |
| Qt / PyQt | 6.11.0 / 6.11.0 |
| Scheduler | `anki.scheduler.v3.Scheduler`, version attribute 3 |
| FSRS | enabled for the canonical scenarios |
| Disposable profiles | `ANKIGTA_P0003_A`, `ANKIGTA_P0003_B` |
| Card X / Y | `1785280605920` / `1785280605921` |

Both collections deliberately contain the same numeric X and Y IDs. Their
prototype-owned identities and visible markers are:

| Profile | Collection identity | Marker |
| --- | --- | --- |
| A | `e8294d12-1285-4aac-8273-bdae872f1321` | `COLLECTION-MARKER-A` |
| B | `db9961c9-ca7d-4987-87fc-620d74b54657` | `COLLECTION-MARKER-B` |

## Disposable safety setup

All prototype code, add-on files, journals, screenshots, collection copies and
upstream source are under:

```text
.scratch/0003-companion-lifecycle-recovery-prototype/
```

The harness:

- requires `ANKIGTA_PROTO_0003_ALLOW_DISPOSABLE=YES`;
- requires the exact marker
  `ANKIGTA PROTOTYPE 0003 DISPOSABLE ONLY`;
- rejects an active collection outside the disposable runtime root;
- starts Anki with an isolated `-b` base;
- creates both profiles through `ProfileManager.create`;
- enables FSRS through Anki's deck-configuration operation;
- creates cards and changes scheduling state through Anki APIs;
- creates native Anki backups for A and B;
- closes Anki before producing the common offline baseline;
- gives every destructive scenario a fresh full copy of that baseline;
- uses SQL only for read-only evidence queries;
- never opens the user's normal collection.

One offline copy of A's disposable `collection.anki2` into disposable B was
used only to create the equal-ID collision fixture. Anki was closed, B was
then assigned a distinct config UUID and visible marker through Anki APIs, and
the copy was not used to switch profiles. Full-base copies are likewise test
isolation, not a lifecycle mechanism. No profile file was edited as a product
operation.

Early capture and snapshot-alias artifacts were retained under
`failed-attempts/`; canonical evidence was rerun on fresh copies. This
workspace was not a Git worktree, so a throwaway branch was unavailable; the
prototype stayed isolated under `.scratch/` instead.

## API and lifecycle inventory

| Purpose | Exact mechanism | Classification and boundary |
| --- | --- | --- |
| List profiles | `ProfileManager.profiles()` | Current non-private AQT implementation surface; Qt main thread |
| Stable collection identity | `Collection.get_config()/set_config()` with a prototype UUID | Public non-underscore config surface, but identity is add-on-owned; no native collision-resistant UUID found |
| Switch profile | `AnkiQt.unloadProfile()` → `ProfileManager.load()` → `AnkiQt.loadProfile()` | Current non-private stock AQT path; asynchronous close callback; **not documented as an add-on API** |
| Observe close/open | `gui_hooks.profile_will_close`, `profile_did_open`, `collection_did_load` | Supported add-on hooks on the Qt main thread |
| Observe Reviewer | `reviewer_did_show_question`, `reviewer_did_show_answer`, `reviewer_will_answer_card`, `operation_did_execute` | Supported add-on hooks; rating backend operation is asynchronous |
| Leave Reviewer | `AnkiQt.moveToState("deckBrowser")` | Current non-private AQT state surface; no documented close-Reviewer add-on API; cleanup clears `Reviewer.card` |
| Observe rating commit | `operation_did_execute` plus complete before/after card and `revlog` evidence | Supported hook for observation, but not a transaction-ID-bearing commit receipt |
| Durable journal | sidecar JSON temporary file, file flush + `fsync`, then `os.replace` | Prototype-owned atomic replacement outside Anki profile files; Windows does not provide the directory `fsync` used on POSIX |
| Reconcile | `Collection.get_card()` plus read-only `Collection.db SELECT` evidence | Public card read plus low-level read-only evidence; never treats a `revlog` timestamp as globally unique |
| Exact admission | filtered-deck APIs proved by prototype 0002, then `get_queued_cards()` / `getCard()` / `answerCard()` | Version-sensitive Anki 26.05 surface; X must first be observed scheduler-top |
| Restore session | `empty_filtered_deck()`, `add_or_update_filtered_deck()`, `DeckManager.remove()` | Current non-private/public stock surfaces; allowed only after reconciliation |

The source inventory is captured in
`.scratch/0003-companion-lifecycle-recovery-prototype/evidence/static/api_inventory.json`.
Relevant Anki 26.05 primary source:

- [AQT main/profile lifecycle](https://github.com/ankitects/anki/blob/26.05/qt/aqt/main.py)
- [AQT Reviewer](https://github.com/ankitects/anki/blob/26.05/qt/aqt/reviewer.py)
- [V3 scheduler](https://github.com/ankitects/anki/blob/26.05/pylib/anki/scheduler/v3.py)
- [scheduler base](https://github.com/ankitects/anki/blob/26.05/pylib/anki/scheduler/base.py)
- [filtered-deck UI](https://github.com/ankitects/anki/blob/26.05/qt/aqt/filtered_deck.py)

## Durable Review Transaction model

The journal key is the pair:

```text
(originating collection identity, reviewTransactionId)
```

The value also records `cardId`, requested rating, scheduler invocation count,
the complete before snapshot, the result snapshot when known, and an explicit
unproved boundary when the outcome is unknown. Reusing the transaction ID is
valid only when collection identity, card ID and rating all match.

| Durable state | Meaning and permitted recovery |
| --- | --- |
| `received` | Request and complete before evidence are durable; no admission claimed |
| `admitted` | Owned X-only filtered deck was built and X observed scheduler-top |
| `rating_started` | Scheduler invocation is about to occur or has returned without a later durable state |
| `rating_applied` | Complete card/FSRS/`revlog` delta proves the requested rating |
| `result_persisted` | Exact result is durable and can be returned to an identical retry |
| `session_restored` | Reconciled session was rebuilt/cleaned through the prototype-0002 operations |
| `completed` | Terminal success; profile switch may proceed |
| `outcome_unknown` | Neither application nor non-application is proved; no retry, switch or restoration |

Normal flow:

```text
received → admitted → rating_started → rating_applied
         → result_persisted → session_restored → completed
```

Recovery may move `rating_started → admitted` only after complete evidence
proves non-application. If the evidence proves application, it moves
`rating_started → rating_applied` without another scheduler call. If neither
predicate holds, it moves to `outcome_unknown`, which is a quarantine state,
not an invitation to guess.

Every transition is saved by atomic replacement before the next protected
action. The prototype deliberately does not claim that the `revlog.id`
timestamp identifies a Review Transaction. Reconciliation instead depends on
exclusive coordinator ownership plus exact before/after card, FSRS and full
target-`revlog` deltas.

## Scenario results

| Scenario | Verdict | Result |
| --- | --- | --- |
| S1 — stable identity | `partially passed` | A and B retained distinct prototype UUIDs despite equal card IDs; both survived restart, and B's UUID survived rename to `ANKIGTA_P0003_B_RENAMED`. No native Anki UUID or clone policy was proved. |
| S2 — A → B → A | `partially passed` | Full close/open hook order and identity isolation were observed. The mechanism is stock and non-private, but not a documented add-on switching API. |
| S3 — close unrated Reviewer | `partially passed` | Question and answer cases reached `deckBrowser`, produced no new `revlog`, and left complete card state unchanged. The close surface is version-sensitive and undocumented for add-ons. |
| S4 — close while rating starts | `failed` | UI reached `deckBrowser`; `operation_did_execute` fired; exactly one Good row was committed; session build waited. Clean completion of the stock asynchronous Reviewer callback after cleanup was not proved. |
| S5 — switch while pending | `passed` within tested coordinator/switch surface | Switch was blocked until `completed`; B could not see A's journal; A could query it after return. |
| S6 — crash before scheduler | `passed` | Restart read `admitted`, proved non-application, made exactly one later scheduler call, produced one row and completed. |
| S7 — crash after commit | `passed` for the injected boundary | Restart read `rating_started`, proved application from the complete delta, made no second scheduler call and completed with one row. |
| S8 — crash after durable result | `passed` | Restart returned the saved result, made no second scheduler call, then restored/cleaned the session. |
| S9 — unknown outcome | `passed` | Truthful supported external mutation made the requested outcome unprovable. X alone remained blocked, Y remained queryable, retry count stayed zero, switch was denied and uncertainty remained durable. |
| S10 — retries | `passed` | Identical retry returned the saved result; same ID with a changed card/rating/collection predicate was rejected without mutation. |
| S11 — restore after reconciliation | `passed` | Journal was inspected before deck touch. Only a proved result permitted full rebuild, empty and removal; membership ended empty and cards returned to their home deck with one target row. |
| S12 — invalid/unsafe | `passed` | Wrong identity, stale card, foreign journal, unknown-state switch, normal-deck name collision and FSRS-off environment failed safely. An unrelated normal `ANKIGTA Session` deck was not deleted or repurposed. |

### Identity and switching evidence

The same X ID, `1785280605920`, was observed in A and B with different UUIDs,
markers and card text. The A → B → A timeline contains:

```text
profile_will_close(A)
collection_close_completed(A, collectionIsNone=true)
profile_did_open(B)
profile_will_close(B)
collection_close_completed(B, collectionIsNone=true)
profile_did_open(A)
```

No A journal entry was returned under B's collection identity.

### Reviewer timelines

Screenshots were taken after allowing the WebEngine view to paint. This render
pause is not included in the close latency: latency starts at the actual
`moveToState("deckBrowser")` request.

| Case | State before | State after | Request → `deckBrowser` | Mutation |
| --- | --- | --- | ---: | --- |
| Question shown | `review/question` | `deckBrowser` | 978,100 ns (0.9781 ms) | no row; complete card state identical |
| Answer shown | `review/answer` | `deckBrowser` | 1,172,900 ns (1.1729 ms) | no row; complete card state identical |
| Rating starting | `review/transition` | `deckBrowser` | 1,660,800 ns (1.6608 ms) | exactly one Good row |

For S4, `operation_did_execute` followed the close request by 8,978,600 ns.
Before that event no `ANKIGTA Session` existed. The build began afterward,
then the owned deck was emptied and removed.

The new S4 row was:

| Field | Value |
| --- | ---: |
| card ID | `1785280605920` |
| ease | 3 (Good) |
| interval | 7 |
| previous interval | 0 |
| row delta | 1 |
| repetitions | 1 → 2 |
| final current/home deck | `1785280605918` / `1785280605918` |

This mutation evidence proves one backend application. It does **not** prove
that the normal Reviewer completion callback remains valid after immediate
cleanup; that is why S4 is failed rather than passed.

### Recovery and mutation evidence

| Crash window | Journal on restart | Decision | Scheduler calls before → after | Target `revlog` delta | Final state |
| --- | --- | --- | ---: | ---: | --- |
| Before scheduler call | `admitted` | `proved_unapplied` | 0 → 1 | 1 | `completed` |
| After Anki commit, before durable result | `rating_started` | `proved_applied` | 1 → 1 | 1 | `completed` |
| After durable result | `result_persisted` | `proved_applied` / return saved result | 1 → 1 | 1 | `completed` |
| Ambiguous supported external mutation | `rating_started` | `outcome_unknown` | 0 → 0 | no blind rating row | `outcome_unknown` |

The forced process exits were respectively after durable `admitted`, after
`answerCard()` returned/Anki saved but before `rating_applied` was persisted,
and after durable `result_persisted` but before acknowledgement/restoration.
The canonical pre-touch journal snapshots contain only the states that existed
before recovery:

- `received → admitted`;
- `received → admitted → rating_started`;
- `received → admitted → rating_started → rating_applied → result_persisted`.

No termination was injected inside Anki's atomic backend answer or rebuild
transaction.

## Verifier and reproduction

The verifier is read-only. It reads JSON/PNG/hash evidence, checks scenario
invariants, re-hashes every manifest entry and prints the required verdicts and
unproved boundaries.

From the repository root:

```powershell
$env:PYTHONIOENCODING = 'utf-8'
python .scratch/0003-companion-lifecycle-recovery-prototype/verify_evidence.py
```

Canonical output:

```text
evidence verification result: passed
overall verdict: partially passed
scenario verdicts:
  S1: partially passed — prototype-owned UUID stable/distinct; no native collision-resistant Anki UUID
  S2: partially passed — A→B→A works through stock non-private lifecycle, but no documented add-on switch API
  S3: partially passed — question/answer close without mutation; close call is non-private AQT state surface
  S4: failed — backend commits once and UI closes, but stock async Reviewer callback cannot be proved to complete cleanly after cleanup
  S5: passed within the tested coordinator and version-scoped switch surface
  S6: passed
  S7: passed
  S8: passed
  S9: passed
  S10: passed
  S11: passed
  S12: passed
exact unproved boundaries:
  - No documented supported add-on API was found for programmatic profile selection/open; tested switching is a current non-private AQT surface.
  - No native collision-resistant Anki collection UUID was found; the stable tested identity is add-on-owned collection config with an unresolved copy/clone policy.
  - Immediate normal Reviewer cleanup during its asynchronous rating leaves an unsafe stock callback boundary even though one backend commit was observed.
  - Termination inside Anki's atomic backend answer/rebuild transaction was not injected.
  - revlog has no reviewTransactionId marker; reconciliation proof depends on exclusive ownership plus complete before/delta evidence, never timestamp alone.
```

The full destructive setup is intentionally one-shot and refuses to overwrite
an existing runtime:

```powershell
powershell -ExecutionPolicy Bypass -File .scratch/0003-companion-lifecycle-recovery-prototype/run.ps1
```

Use a new copy of the prototype directory for a clean rerun. The retained
`rerun_*.ps1` files document the fresh-copy evidence corrections made during
this run; they are also covered by the source scan and manifest.

## Evidence and hashes

Primary evidence is under
`.scratch/0003-companion-lifecycle-recovery-prototype/evidence/`.
`hashes.json` contains 48 SHA-256 entries covering prototype source, all
PowerShell runners, fixtures and primary evidence. Runtime collection copies
and the upstream checkout are intentionally excluded.

| Artifact | SHA-256 |
| --- | --- |
| `evidence/hashes.json` itself | `dc4aacd3ab685d84f19b64479b947172d0e22decafcdeb33f52fee725a656fee` |
| `evidence/verifier_output.txt` | `2f0c9c40f045094dae57e38ef8277a4dde1ab77bdc9141d35b351223f1ee7e1a` |
| S1/S2 identity and switch | `988dfcf91aab87738dd118f66b97a013c747cab902082c3006d58c846123f21d` |
| S3 question | `4d9a2cf930a83bdd7ff439178e355a7d3eee6d97e9e2120268650c7df0eabf52` |
| S3 answer | `907c40134c24908bf18d54330bf273934dce8fda4c22cdc74efdbfe58ab9fe23` |
| S4 rating/close | `5f53f70e366bb7d9c11cb6ffbd33b21ad8258131e28dfdf7b13a422549a1662a` |
| S5 pending switch | `2e1aa084d9e103acca748ee9bc01bccc8f046ab1a177d62c951d6c433724efed` |
| S6 recovery | `0b1c8ed24d52c3633eaa5249a8102a9b46251e2e0ba2123021306d77ffec6ce7` |
| S7 recovery | `d87a07e53f62d2e20ee83c7ab32593ef6193dc977755e614f558c5d5beba208b` |
| S8 recovery | `fdcabe3b6f3e9a428f37dbcad08acf3e8c2d2ef18feb6b35501f80d900325cca` |
| S9 unknown | `812c865f04c95f1afe7374e83e44260778b8636ce1edb4bbb476b6b88be32f2d` |
| source scan | `2b0e2e1867a020d36452d3068d07ae0759404fcdc0791376849fb7459dd29d95` |

The source scan covered all executable add-on modules and all PowerShell
runners. It found no SQL write, private queue mutation, custom Scheduler class
or private backend call. The intentional offline disposable collection copy
is separately classified as fixture preparation and marked as not used for
switching.

## Proven and disproven assumptions

Proved for Anki Desktop 26.05 only:

- two profiles can contain the same numeric `cardId`;
- a prototype-owned collection-config UUID can disambiguate them and survive
  restart/profile rename;
- stock close/open hooks expose the tested A → B → A lifecycle order;
- leaving an unrated Reviewer from question or answer state can be fast and
  mutation-free through the tested AQT state surface;
- a durable, collection-scoped journal can prevent duplicate rating at the
  tested crash boundaries;
- identical retry returns a result and conflicting retry fails without
  mutation;
- unknown outcome can quarantine only X without a blind resend;
- owned filtered-deck restoration can wait for reconciliation and return cards
  home without an extra row.

Disproved:

- profile name, folder or collection path alone is a safe collection identity;
- numeric `cardId` identifies a card across profiles;
- a non-private internal method is automatically a supported add-on API;
- UI closure proves an in-flight rating was cancelled;
- closing the Reviewer immediately after rating start is harmless merely
  because the backend later commits once;
- process-local state is sufficient for idempotency;
- persisting only after the scheduler call closes the lost-response window;
- a `revlog` timestamp alone identifies `reviewTransactionId`;
- it is safe to restore `ANKIGTA Session` before reconciliation.

## Exact unproved boundaries

- A documented supported add-on API for programmatic profile selection/open.
- A native collision-resistant Anki collection identity and production
  copy/clone/import policy for an add-on-owned UUID.
- Safe completion of the stock asynchronous Reviewer callback after immediate
  normal cleanup.
- Termination inside Anki's atomic backend answer or filtered-deck rebuild.
- A native Anki commit receipt carrying `reviewTransactionId`; the prototype's
  proof depends on exclusive ownership and complete deltas.
- Any behavior outside Windows, Anki Desktop 26.05, V3 scheduler and FSRS.

## Required specification changes

No production document or ADR was silently changed by this prototype. The
following updates are required before implementation:

- **CONTEXT.md:** replace the unconditional statement that the add-on switches
  to the Bound Anki Collection through a supported mechanism. Treat
  in-process switching as unresolved/version-gated; document a supported
  restart/launch alternative if that becomes the product choice.
- **CONTEXT.md:** replace “always immediately closes” for an already-started
  standard Reviewer rating. The safe contract must either wait for the stock
  Reviewer operation and callback to finish before leaving, or require a new
  proved upstream-supported arbitration mechanism. `ANKIGTA Session` must
  still wait.
- **CONTEXT.md:** specify collection identity as an add-on-owned UUID with an
  explicit copy/clone/import collision policy, or leave it as a proof gate.
- **ADR 0007:** keep Anki authoritative and exact filtered admission, but add
  that normal Reviewer operations cannot be taken over mid-callback.
- **ADR 0008:** record the durable states, collection-scoped key, identical
  retry/conflict rule and `outcome_unknown` quarantine. State that
  `revlog` time alone is insufficient.
- **ADR 0009:** retain stable production collection identity as unresolved;
  profile name/path must not be accepted as a fallback.
- **ADR 0012:** add integration gates for the non-private profile-switch and
  Reviewer-close surfaces, or prohibit relying on them.
- **ADR 0021:** narrow automatic collection switching to a proved supported
  mechanism; preserve a pending/unknown transaction under its originating
  identity.
- **ADR 0022:** change the already-started-rating clause. Immediate visual
  closure plus background completion is not proved safe with the normal
  Reviewer callback in 26.05.
- **Confirmed baseline / preliminary audit:** mark durable journal recovery as
  proved only for the prototype coordinator and tested crash boundaries; mark
  native identity, supported profile switching and immediate in-flight
  Reviewer closure as unresolved/failed gates.

## Follow-up recommendation

A narrower follow-up is justified only if it tests a materially different,
acceptable lifecycle:

1. ask upstream/documentation whether an add-on-supported profile selection
   and Reviewer-leave API exists or can be added;
2. test “finish the normal Reviewer operation and callback, then close” while
   keeping Start Studying visibly pending and delaying session build;
3. define and test the add-on-owned collection UUID's clone/import collision
   policy;
4. optionally test process restart with Anki's supported `-p` profile launch
   instead of in-process switching.

Do not build a follow-up around private queue mutation, monkey-patching
Reviewer completion, direct profile-file switching or a custom scheduler.
