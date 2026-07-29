# Handoff: companion lifecycle and durable recovery prototype

## Purpose

Continue in a **new chat** and build disposable prototype 0003 answering:

> Can the companion add-on use supported Anki mechanisms to switch the Bound Anki Collection, close the standard Anki Reviewer immediately, and durably complete one Review Transaction exactly once after process restart before restoring `ANKIGTA Session`?

This is a compatibility and recovery prototype, not production implementation. It must report a negative or partial result instead of hiding an unsupported operation behind private APIs.

## Read first

- `AGENTS.md`
- `CONTEXT.md`
- `docs/design/confirmed-baseline.md`
- `docs/design/preliminary-spec-audit.md`
- `docs/prototypes/0001-exact-card-idempotent-review.md`
- `docs/prototypes/0002-filtered-deck-fsrs-admission.md`

Relevant decisions:

- `docs/adr/0003-gate-a-real-filtered-deck-behind-a-prototype.md`
- `docs/adr/0007-make-the-companion-add-on-the-review-coordinator.md`
- `docs/adr/0008-make-ratings-idempotent.md`
- `docs/adr/0009-scope-card-links-to-anki-collections.md`
- `docs/adr/0012-limit-v1-to-tested-anki-on-windows-with-fsrs.md`
- `docs/adr/0017-keep-anki-authoritative-for-study-data.md`
- `docs/adr/0021-pause-when-the-bound-anki-collection-changes.md`
- `docs/adr/0022-make-anki-and-ankigta-study-modes-exclusive.md`

Treat the old `ANKIGTA_SPEC.md` only as preliminary material. Current context, ADRs, confirmed baseline and measured prototype evidence take precedence.

## Prior evidence that must constrain this prototype

Prototype 0001 established on Anki Desktop 26.05, V3 scheduler and FSRS:

- a rendered non-top card cannot be answered through `Scheduler.answerCard()`;
- scheduler-top cards can be rated;
- in-process identical retry and lost-response reconciliation can work;
- process-restart durability and production collection identity were not proved.

Prototype 0002 established in the same environment:

- an owned rescheduling filtered deck can admit exact X through X-only rebuild;
- X must be observed scheduler-top before rating;
- rating and defined cleanup/recovery boundaries can preserve FSRS and avoid extra `revlog`;
- exact-ID order does not control scheduler-top;
- termination inside Anki's atomic backend rebuild was not injected;
- durable production Review Transaction journaling and stable production collection identity remain open.

Do not repeat the complete state/rating matrix from prototype 0002. Reuse its proven admission mechanism only where necessary to exercise durable lifecycle recovery.

## Scope

Test one companion lifecycle contract with three inseparable parts:

1. **Bound collection identity and profile switching**
   - distinguish two disposable Anki profiles/collections even when test card IDs are deliberately equal;
   - switch A → B → A through an acceptable Anki mechanism;
   - keep unfinished transactions scoped to their originating collection.
2. **Exclusive study surface**
   - close the standard Reviewer immediately from question and answer states;
   - preserve an unrated card;
   - let an already-started Anki rating finish exactly once in the background;
   - delay creation/restoration of `ANKIGTA Session` until the previous Anki operation is settled.
3. **Durable Review Transaction recovery**
   - persist transaction state across forced process termination;
   - acknowledge an already-applied rating without replay;
   - resend only when non-application is proved;
   - never blindly resend an unknown outcome;
   - restore the filtered deck only after reconciliation.

Do not test:

- MTA HTTP transport or server-side Lua;
- CEF rendering/isolation;
- Map Editor persistence;
- AnkiWeb synchronization;
- automatic add-on installation/update;
- final production API or SQLite schema;
- the full prototype 0002 scheduling matrix.

## Non-negotiable constraints

- Windows, Anki Desktop 26.05, V3 scheduler and FSRS.
- Use at least two disposable Anki profiles and fresh disposable collection copies for destructive scenarios.
- Anki remains the only scheduler and the only writer of scheduling state and `revlog`.
- No direct SQL writes.
- No private scheduler queue mutation.
- No custom scheduler or interval calculation.
- No direct opening, copying or modification of another profile's collection files as the switching mechanism.
- Read-only database inspection is evidence only and must not be presented as a production API.
- Prototype code and runtime data stay under `.scratch/0003-companion-lifecycle-recovery-prototype/`.
- Do not modify production ANKIGTA code.
- Every relied-on Anki surface must be classified as public/documented, supported add-on surface, current non-private implementation surface, or private/unsupported.
- If a required behavior needs private or unsupported internals, mark that criterion failed or conditional.

## Safety setup

1. Record exact Anki/AQT/Python/Qt versions, scheduler mode and FSRS state.
2. Create disposable profiles `ANKIGTA_P0003_A` and `ANKIGTA_P0003_B`.
3. Create native Anki backups and offline baseline copies before mutations.
4. Use a fresh baseline copy for each forced-termination scenario.
5. Give each profile a distinct collection marker and profile name.
6. Create controlled cards with known scheduling state and `revlog`.
7. Deliberately arrange at least one same numeric `cardId` across A and B if this can be done safely in disposable data; otherwise record why and prove collision resistance with the strongest controlled substitute.
8. Add a prototype ownership marker for its filtered deck and journal.
9. Require an explicit disposable-runtime safety marker before the harness runs.
10. Preserve failed attempts separately from canonical evidence.

## Required test data

Create the minimum data needed:

- Profile A with scheduler-top Card A-X and another card A-Y.
- Profile B with Card B-X and B-Y.
- A-X and B-X should share the same numeric `cardId` where safely reproducible, while their collection identities differ.
- At least one due review card with FSRS memory state for rating scenarios.
- A normal user deck in each profile.
- An owned `ANKIGTA Session` filtered deck where admission/recovery requires it.
- A standard Reviewer state with question shown.
- A standard Reviewer state with answer shown.
- A scenario where a rating callback/operation has begun but lifecycle switching is requested before the caller receives completion.

For every mutable card capture:

- profile and collection identity;
- card ID, note ID, current deck and original deck;
- scheduling fields and FSRS memory state;
- relevant `revlog` rows;
- Reviewer state;
- filtered-deck ownership/membership;
- durable transaction journal state.

## Supported API inventory

Identify and classify the exact mechanism used to:

- list or identify available profiles;
- obtain stable collection identity;
- switch the currently open profile/collection;
- detect collection close/open completion;
- detect standard Reviewer question/answer/rating states;
- close or leave the standard Reviewer immediately;
- determine when an already-started standard Anki rating is committed;
- persist and atomically advance the Review Transaction journal;
- reconcile journal state with actual Anki state after restart;
- perform exact-card admission using the already-proved filtered-deck mechanism;
- empty/rebuild/remove an owned `ANKIGTA Session`.

Do not call a mechanism “supported” merely because it exists in an internal object. Record lifecycle hooks, thread restrictions, transaction boundaries and version sensitivity.

## Durable transaction model to exercise

The disposable prototype must define explicit persisted states equivalent to:

- `received`
- `admitted`
- `rating_started`
- `rating_applied`
- `result_persisted`
- `session_restored`
- `completed`
- `outcome_unknown`

Names may differ, but every state transition, durable write boundary and recovery action must be documented.

The journal key must include:

- `reviewTransactionId`;
- originating collection identity;
- `cardId`;
- requested rating;
- enough before/after evidence to distinguish an already-applied rating from a provably unapplied request without guessing.

The prototype must not claim that `revlog` timestamp alone is a globally unique transaction marker unless proved.

## Required scenarios

### S1 — Stable identity across two profiles

1. Open profile A and record its proposed collection identity.
2. Open profile B and record its identity.
3. Prove A and B remain distinct even for equal numeric card IDs.
4. Restart Anki and prove both identities remain stable.
5. Rename a disposable profile if the selected identity is expected to survive profile rename; prove the result or explicitly narrow the guarantee.
6. Show that collection display name or filesystem path alone is not silently treated as stable identity unless proved.

### S2 — Supported A → B → A switching

1. Begin in A with no open Reviewer and no pending transaction.
2. Switch to B using the candidate supported mechanism.
3. Observe collection-close and collection-open completion.
4. Verify no A card or transaction is read as B data.
5. Switch back to A and verify identity and state.
6. Prove no direct profile-file access or process corruption.

If supported in-process profile switching is unavailable, record the exact supported alternative and whether it requires an Anki restart. Do not invent a hidden file-based switch.

### S3 — Close an unrated standard Reviewer

Run separately with:

- question shown;
- answer shown.

For each:

1. Snapshot card state and `revlog`.
2. Request `Начать обучение`.
3. Close the standard Reviewer immediately through the tested mechanism.
4. Prove the card was not rated and scheduling state did not change.
5. Prove Anki reached a neutral state before building the prototype filtered deck.

### S4 — Close Reviewer while a rating is already starting

1. Open a fresh due card in the standard Reviewer.
2. Instrument the supported rating lifecycle sufficiently to observe start and completion without mutating private scheduler queues.
3. Begin one rating.
4. Request immediate Reviewer closure before the caller receives completion.
5. Prove the Reviewer UI closes immediately.
6. Prove the Anki operation finishes exactly once.
7. Prove no `ANKIGTA Session` build starts until completion is observed.
8. Prove exactly one expected `revlog` and correct FSRS state.

If the rating operation is synchronous and the requested interleaving cannot exist, prove that fact and define the closest real lifecycle boundary instead of simulating a false race.

### S5 — Profile switch requested during a pending transaction

1. Start in A.
2. Create a pending prototype Review Transaction for A-X.
3. Request switch to B.
4. Prove B does not open until A's transaction reaches a reconciled terminal state.
5. Prove no A journal entry is visible under B identity.
6. Complete the switch, then return to A and verify the result remains queryable.

### S6 — Crash before scheduler call

1. Persist the transaction request.
2. Terminate the disposable process before the scheduler call.
3. Restart on the same disposable profile.
4. Prove non-application.
5. Automatically continue/send the rating once through supported admission.
6. Prove one `revlog` and one terminal journal result.

### S7 — Crash after applied rating but before response/result persistence

1. Admit A-X through the proven X-only filtered-deck mechanism.
2. Apply one rating through Anki.
3. Force termination after Anki commit but before the response/result is durably recorded.
4. Restart.
5. Prove the rating is detected as already applied.
6. Return/reconstruct the result without a second scheduler call.
7. Prove exactly one `revlog`.

If this exact crash window cannot be deterministically injected, report the strongest proven boundary and leave the criterion unproved.

### S8 — Crash after durable result

1. Apply a rating and persist its result.
2. Terminate before client acknowledgement or session restoration.
3. Restart and repeat the same `reviewTransactionId`.
4. Prove the saved result is returned.
5. Prove no second `revlog`.
6. Restore/clean the filtered deck only after reconciliation.

### S9 — Unknown outcome

Create or simulate only through a truthful lifecycle boundary a state where the journal cannot yet prove applied or unapplied.

Verify:

- no blind scheduler retry occurs;
- only the affected card remains blocked;
- additional reconciliation attempts are observable;
- other safe cards may remain usable if the collection lifecycle permits;
- profile switching and filtered-deck restoration do not erase the uncertainty.

Do not fabricate “proof” by comparing only a mutable due value or approximate time.

### S10 — Identical and conflicting retries after restart

1. Repeat the same `reviewTransactionId`, collection identity, card ID and rating after restart.
2. Prove the prior result is returned without mutation.
3. Repeat the ID with a different card, collection or rating.
4. Prove a conflict is returned without scheduling mutation.

### S11 — Restore filtered deck only after reconciliation

For the recovery cases above:

1. Start with an owned `ANKIGTA Session`.
2. Leave it populated across a forced termination.
3. Restart and inspect the journal before touching the deck.
4. Reconcile the transaction.
5. Empty/rebuild through the prototype-0002-supported operations.
6. Prove every card has correct home deck, filtered membership and scheduling state.

### S12 — Invalid and unsafe operations

Prove safe failure for:

- wrong collection identity;
- stale `cardId`;
- transaction journal belonging to another profile;
- switch request while reconciliation remains genuinely unknown;
- unrelated user deck named `ANKIGTA Session`;
- missing or unavailable supported profile-switch hook;
- missing or unavailable supported Reviewer-close hook;
- FSRS disabled or unsupported Anki environment.

No scenario may delete or repurpose an unrelated user deck.

## Success criteria

Overall verdict is `passed` only if all are proved:

1. Profiles A and B have stable, distinct collection identities that disambiguate equal card IDs.
2. A → B → A switching uses an acceptable Anki lifecycle mechanism without direct profile-file manipulation.
3. Question-side and answer-side Reviewer closure is immediate and creates no rating.
4. An already-started standard Anki rating finishes exactly once despite immediate UI closure.
5. `ANKIGTA Session` is never created/restored before the prior rating operation or Review Transaction is reconciled.
6. Profile switching waits for the originating collection's pending transaction.
7. A crash before scheduler invocation results in exactly one later application.
8. A crash after Anki commit does not result in a second application.
9. Identical retry after restart returns the same result; conflicting retry is rejected without mutation.
10. Unknown outcome never causes blind resend.
11. Recovery remains scoped by collection identity.
12. Filtered-deck restoration leaves no stranded card or extra `revlog`.
13. No direct SQL write, private queue mutation, custom scheduler or direct profile-file switching is used.
14. Evidence is machine-verifiable and reproducible from disposable setup.

Use `partially passed` if independently useful portions are proved but any required lifecycle mechanism or crash boundary remains unproved. Use `failed` if the central safe lifecycle contract cannot be built from acceptable Anki mechanisms.

## Required evidence

Capture:

- exact environment and profile setup;
- collection identity values before/after restart and switching;
- equal-card-ID collision evidence or documented substitute;
- lifecycle event timeline for profile close/open and Reviewer close;
- UI state before and immediately after Reviewer closure;
- journal contents at every durable boundary;
- scheduler invocation count;
- `revlog` deltas and complete target card/FSRS state;
- filtered-deck membership and home-deck restoration;
- process termination point and restart observations;
- structured result for every scenario;
- source scan for forbidden SQL writes, private queue mutation and direct profile-file manipulation;
- SHA-256 manifest for prototype source and primary evidence.

Provide a read-only verifier that validates the structured evidence and prints:

- evidence verification result;
- scenario verdicts;
- overall verdict;
- exact unproved boundaries.

## Assumptions forbidden without proof

- Profile name, profile folder or collection path is a stable collection identity.
- Two profiles cannot contain the same numeric `cardId`.
- Opening another profile is a supported add-on operation merely because an internal method exists.
- Closing Reviewer UI proves an in-flight rating was cancelled.
- A started rating can be safely interrupted or replayed.
- A `revlog` timestamp uniquely identifies one Review Transaction.
- Process-local memory is sufficient for idempotency.
- Writing the result after the scheduler call closes the lost-response window.
- The same `reviewTransactionId` may be reused in another collection.
- It is safe to rebuild `ANKIGTA Session` before transaction reconciliation.
- Immediate UI closure means filtered-deck build may also begin immediately.
- Prototype 0002 proved durable restart journaling.
- Behavior on Anki 26.05 applies to another version.

## Expected repository artifact

Write the canonical report to:

```text
docs/prototypes/0003-companion-lifecycle-recovery.md
```

It must include:

- verdict: `passed`, `failed` or `partially passed`;
- tested environment and disposable safety setup;
- API inventory and stability classification;
- explicit durable transaction state model;
- scenario-by-scenario results;
- measured timelines and mutation evidence;
- verifier instructions and output;
- evidence hashes;
- proven and disproven assumptions;
- unproved crash/lifecycle boundaries;
- required changes to CONTEXT, ADRs and confirmed baseline;
- whether a narrower follow-up prototype is justified.

Keep disposable code and runtime data under:

```text
.scratch/0003-companion-lifecycle-recovery-prototype/
```

Do not present prototype code as production ANKIGTA.

## Suggested skills

- **Required:** `/prototype`
- **Optional for official Anki API investigation:** `/research`
- **After completion:** `/handoff` back to the main design chat, then `/grill-with-docs`

Do not invoke `/implement`, `/to-spec` or `/to-tickets`.

## Exact prompt for the new prototype chat

Open a new chat in the same ANKIGTA workspace and send:

```text
/prototype

Используй handoff:
docs/handoffs/0003-companion-lifecycle-recovery-prototype.md

Создай одноразовый prototype 0003 и проверь единый lifecycle-контракт:
может ли companion add-on через поддерживаемые механизмы Anki безопасно
переключать Bound Anki Collection, немедленно закрывать стандартный Reviewer
и после перезапуска завершать один reviewTransactionId ровно один раз до
восстановления `ANKIGTA Session`.

Перед началом прочитай все источники истины из handoff и учти фактические
результаты prototypes 0001 и 0002. Не повторяй полную scheduling-матрицу 0002.

Используй Windows, Anki Desktop 26.05, V3 scheduler, FSRS, минимум два
disposable профиля и свежие копии для разрушительных сценариев. Полностью
выполни safety setup, required scenarios, success criteria и evidence
requirements из handoff.

Запрещены production-код ANKIGTA, прямые SQL-записи, private queue mutation,
собственный scheduler, прямое изменение файлов профилей, а также исследование
MTA HTTP, CEF, Map Editor и AnkiWeb sync.

Если переключение профиля, немедленное закрытие Reviewer или точное crash-window
невозможно доказать через приемлемый Anki API, зафиксируй failed либо partially
passed и точную границу доказанного. Не создавай скрытый обход.

Сохрани канонический отчёт в:
docs/prototypes/0003-companion-lifecycle-recovery.md

Добавь read-only verifier, структурированные evidence и SHA-256 manifest.
Прототипный код и runtime оставь только под:
.scratch/0003-companion-lifecycle-recovery-prototype/
```
