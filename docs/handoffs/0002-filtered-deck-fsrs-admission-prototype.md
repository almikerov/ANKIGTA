# Handoff: filtered-deck FSRS admission prototype

## Purpose

Continue in a **new chat** and build disposable prototype 0002 answering:

> Can a real rescheduling filtered deck named `ANKIGTA Session` legitimately make an exact selected Anki Card scheduler-top, allow Anki to rate it, and preserve normal FSRS scheduling and card lifecycle?

This prototype follows the failed exact-card experiment. It must test whether filtered-deck admission solves that failure through supported Anki behavior. It is not production implementation.

## Current state and prior evidence

Read these first:

- `AGENTS.md`
- `CONTEXT.md`
- `docs/design/confirmed-baseline.md`
- `docs/design/preliminary-spec-audit.md`
- `docs/prototypes/0001-exact-card-idempotent-review.md`

Relevant decisions:

- `docs/adr/0003-gate-a-real-filtered-deck-behind-a-prototype.md`
- `docs/adr/0007-make-the-companion-add-on-the-review-coordinator.md`
- `docs/adr/0008-make-ratings-idempotent.md`
- `docs/adr/0009-scope-card-links-to-anki-collections.md`
- `docs/adr/0012-limit-v1-to-tested-anki-on-windows-with-fsrs.md`
- `docs/adr/0017-keep-anki-authoritative-for-study-data.md`

Prototype 0001 established on Anki Desktop 26.05, V3 scheduler and FSRS:

- exact Card X can be loaded and rendered while scheduler-next is Y;
- `Scheduler.answerCard(X, rating)` fails with `not at top of queue`;
- the failure occurs before card or `revlog` mutation;
- scheduler-top controls accept Again/Hard/Good/Easy;
- in-process identical retry, conflicting retry and lost-response reconciliation work for scheduler-top cards;
- process-restart durability and production collection identity remain unproved.

Do not rerun prototype 0001 or probe private queue internals. Prototype 0002 must make X scheduler-top through a real filtered deck or report failure.

## Scope

Test two related filtered-deck behaviors:

1. **Normal session queue** — `ANKIGTA Session` contains the exact unique card-ID set for active Spatial Link, and Anki chooses its next card.
2. **Manual exact-card admission** — while Y is scheduler-next, the user selects linked Card X in the world. Test whether supported filtered-deck operations can make X legitimately scheduler-top, rate it once, then restore/rebuild the full session without damaging other cards.

The prototype may test rebuilding the one `ANKIGTA Session` deck to X-only and then rebuilding the full set, if this can be done through supported Anki APIs. It must not assume that approach is safe before measuring its effects on learning cards and scheduling.

Do not test:

- MTA HTTP transport;
- CEF rendering isolation;
- Map Editor ID persistence;
- final companion HTTP API shape;
- production SQLite schema;
- UI implementation.

## Non-negotiable constraints

- Use a disposable Anki profile or disposable copies only.
- Anki remains the only scheduler.
- Use a real filtered deck with rescheduling enabled.
- Never write scheduling fields or `revlog` through SQL.
- Never mutate Anki's private scheduler queue.
- Never implement custom card ordering or interval calculation outside supported filtered-deck options.
- Do not interpret preview behavior as a successful scheduler review.
- Do not transfer prototype code into production.
- Record the exact tested Anki/AQT/Python/Qt versions and FSRS configuration.
- Observe whether FSRS is enabled; do not assume a fresh profile enables it.

## Safety setup

Before mutations:

1. Create a disposable Anki base/profile.
2. Explicitly record scheduler mode, FSRS state and deck options.
3. Enable FSRS only in the disposable profile if needed, recording before and after.
4. Create a native Anki backup.
5. Close Anki and make an offline copy of the disposable base.
6. Use a fresh copy of the same baseline for each rating/state comparison.
7. Ensure no normal Reviewer is open while the harness changes filtered decks.

The harness must refuse to run outside its disposable runtime directory unless an explicit safety variable is present.

SQL may be used only for read-only evidence. Source verification must detect direct database writes and forbidden scheduler-field mutation.

## Required test data

Create original decks and cards sufficient to exercise:

- at least two new cards X and Y with Y normally scheduler-next;
- due review cards with known FSRS memory state;
- an available learning card;
- an available relearning card;
- a suspended card;
- a buried card;
- a future/not-due review card;
- cards excluded from the exact active card-ID set;
- duplicate references in the input set, proving that the filtered-deck set is unique.

For each card record before and after:

- collection identity used by the prototype;
- note ID, card ID, original deck ID and current deck ID;
- `type`, `queue`, `due`, `ivl`, `factor`, `reps`, `lapses`;
- original-deck/original-due fields used by filtered decks;
- FSRS memory state/custom data exposed by the tested version;
- relevant `revlog` rows;
- rendered question/answer and available rating choices where applicable.

## Supported API requirement

The prototype must identify the exact Anki API used to:

- create/get `ANKIGTA Session`;
- configure it as a rescheduling filtered deck;
- build/rebuild it from exact card IDs;
- empty it and return cards to original decks;
- ask Anki for scheduler-next;
- obtain question/answer and allowed ratings;
- submit an answer through Anki;
- detect and recover a leftover session after restart.

For every API, classify it as public/documented, supported add-on surface, current non-private implementation surface, or undocumented/private. A result that requires private queue mutation fails.

## Required scenarios

### S1 — Build the normal session from exact IDs

1. Supply an input set containing X, Y, several state variants and duplicate IDs.
2. Create/rebuild `ANKIGTA Session` with rescheduling enabled.
3. Prove that only unique eligible requested cards entered.
4. Prove original deck identity is retained by Anki.
5. Ask Anki for scheduler-next and record the observed card.
6. Prove that building the deck alone creates no `revlog`.

### S2 — Admit non-top exact X

1. Prove the normal session's scheduler-next is Y.
2. Select X explicitly.
3. Using only supported filtered-deck operations, attempt to make X scheduler-top.
4. Prove scheduler-next is now X before rating.
5. Render X and obtain allowed ratings.
6. If X cannot legitimately become scheduler-top, stop the rating attempt and record failure without mutation.

### S3 — Rate admitted X

On a fresh baseline copy for each rating exposed by Anki:

1. Admit X through the successful S2 mechanism.
2. Apply Again, Hard, Good or Easy through Anki's scheduler.
3. Prove exactly one `revlog` entry is created.
4. Record X's complete post-rating scheduling state.
5. Prove no non-target card was rated or had scheduling fields unexpectedly changed.

This prototype may reuse the in-process idempotency control from prototype 0001 only as evidence that the admitted card is rated once. Durable idempotency remains outside this prototype.

### S4 — Compare with ordinary Reviewer

For each card state and tested rating:

1. Start from equivalent disposable baseline copies.
2. In the control copy, make the same card legitimately scheduler-top in its original deck and rate it through normal Anki Reviewer/scheduler behavior.
3. In the experiment copy, rate it through `ANKIGTA Session`.
4. Compare card state, FSRS memory state and `revlog`.
5. Explain every difference. Time-dependent differences require defined tolerances; unexplained scheduling differences fail the gate.

### S5 — New cards and limits

Verify:

- whether filtered-deck construction respects or bypasses new-card limits;
- whether requested new cards unavailable under normal limits enter;
- their permitted ratings and post-rating states;
- whether session rebuild changes their order or counters unexpectedly.

Do not decide desired product behavior from assumptions; report actual Anki behavior.

### S6 — Learning and relearning

For available learning and relearning cards:

1. Build the normal session.
2. Record their current steps and availability.
3. Rebuild the session before rating.
4. Admit/rate a target where supported.
5. Rebuild the full session afterward.
6. Empty/pause the session.
7. Prove steps, due times and original-deck return remain consistent with normal Anki behavior.

Any stranded card, lost step, duplicate presentation or unexplained due change fails the gate.

### S7 — Suspended and buried

Verify that suspended and buried cards:

- do not become scheduler-admitted merely because their IDs were requested;
- do not receive ratings;
- do not get silently unsuspended or unburied;
- retain their state through rebuild and cleanup;
- can still be loaded for Preview only without mutation.

### S8 — Future/not-due cards

Attempt supported admission of a future/not-due review card with rescheduling enabled.

Record:

- whether Anki permits inclusion;
- whether it becomes scheduler-top;
- which rating choices are offered;
- how the result compares with a normal supported early/custom-study review;
- whether FSRS state changes equivalently.

If no safe equivalent exists, the correct product result is Preview only.

### S9 — Rebuild after manual X review

1. Begin with the full active card-ID set and Y scheduler-next.
2. Admit and rate X.
3. Rebuild `ANKIGTA Session` from the full current set.
4. Ask Anki for its new next card.
5. Prove X is not incorrectly duplicated and Y/learning cards were not lost.
6. Verify statistics/counts against the actual unique available set.

### S10 — Pause and normal stop

1. Populate `ANKIGTA Session`.
2. Empty it as Pause studying would.
3. Prove every card returns to the correct original deck with correct scheduling state.
4. Rebuild and repeat.
5. On normal stop, empty and remove the temporary deck.
6. Prove no card remains stranded under the temporary deck.

### S11 — Leftover session recovery

1. Populate `ANKIGTA Session`.
2. Terminate the disposable Anki process without normal cleanup at defined points:
   - before a rating;
   - after a committed rating;
   - during or immediately around a rebuild where reproducible.
3. Restart on the same disposable base.
4. Detect the leftover deck.
5. Reconcile any known transaction result before cleanup.
6. Empty/rebuild through supported operations.
7. Prove no duplicate `revlog`, stranded card or lost learning state.

If exact crash timing cannot be controlled, state which recovery windows were and were not proved.

### S12 — Invalid and conflicting inputs

Verify non-mutating failures for:

- wrong collection identity;
- stale card ID;
- card ID outside the active set;
- duplicate input IDs;
- an existing user deck named `ANKIGTA Session` that is not owned by the prototype;
- attempts to rebuild while a rating transaction is open;
- unsupported Anki version or FSRS disabled.

The prototype must not delete or repurpose an unrelated user deck with the same name.

## Success criteria

The overall gate passes only if:

1. A real rescheduling filtered deck is created and controlled through an acceptable Anki API.
2. The exact requested set is represented without duplicate cards.
3. Non-top X can be made scheduler-top through supported filtered-deck operations.
4. Anki accepts X's rating only after X is observed scheduler-top.
5. Exactly one expected `revlog` entry is created.
6. For supported card states, filtered-deck results match ordinary Reviewer/FSRS behavior within documented tolerances.
7. New, learning, relearning and review cards retain correct lifecycle across admission, rating, rebuild and cleanup.
8. Suspended and buried cards are never silently admitted or mutated.
9. Future/not-due behavior is either proved equivalent to supported Anki early review or explicitly rejected to Preview only.
10. Rebuilding the full session after manual X does not lose, duplicate or corrupt other cards.
11. Pause/stop returns every card to its correct original deck.
12. Tested leftover-session recovery creates no duplicate rating and strands no card.
13. No direct SQL writes, private queue mutation or custom scheduler is used.

Any unexplained scheduling divergence, stranded card, duplicate `revlog`, private queue dependency or inability to admit X makes the overall verdict `failed` or `partially passed`, with the failed criterion named explicitly.

## Evidence requirements

Capture:

- exact Anki/AQT/Python/Qt versions and FSRS configuration;
- exact filtered-deck configuration before every build;
- input card-ID sets and resulting membership/order;
- scheduler-next before and after exact-card admission;
- full relevant card state before and after;
- `revlog` deltas;
- original-deck return state;
- normal Reviewer control results;
- restart/recovery observations;
- structured scenario results;
- source scan proving absence of forbidden database writes and private queue mutation;
- SHA-256 hashes for primary evidence and prototype source.

Provide a read-only verifier that checks the structured evidence and prints the overall verdict.

## Assumptions forbidden without proof

- A filtered deck containing X necessarily makes X scheduler-top.
- Exact-ID search preserves supplied ordering.
- Rebuilding a filtered deck is harmless to learning/relearning cards.
- Rescheduling filtered-deck review is equivalent to ordinary Reviewer under FSRS.
- New-card limits behave as product design expects.
- Suspended/buried cards are automatically excluded from exact-ID searches.
- Future/not-due review is safe merely because Anki allows inclusion.
- Emptying or deleting a filtered deck always restores every original field.
- A leftover filtered deck can be rebuilt safely before transaction reconciliation.
- The temporary deck name is always available and owned by ANKIGTA.
- Behavior observed on Anki 26.05 applies to another version.
- Read-only SQL evidence is a supported production API.

## Expected repository artifact

Write the canonical result to:

```text
docs/prototypes/0002-filtered-deck-fsrs-admission.md
```

It must include:

- verdict: `passed`, `failed` or `partially passed`;
- exact tested environment and disposable safety setup;
- scenario-by-scenario results;
- supported API inventory and stability classification;
- comparison with ordinary Reviewer;
- reproducible commands;
- evidence hashes and verifier output;
- proven and disproven assumptions;
- impact on ADR 0003, 0007, 0008, 0012 and the confirmed baseline;
- explicit product fallbacks for states that cannot be safely rated;
- whether another iteration is justified.

Keep disposable code and runtime data under:

```text
.scratch/0002-filtered-deck-fsrs-admission-prototype/
```

Do not present that code as production ANKIGTA.

## Suggested skills

- **Required:** `/prototype`
- **Optional for official API/behavior investigation:** `/research`
- **After the prototype:** `/handoff` back to the main design chat

Do not invoke `/implement`, `/to-spec` or `/to-tickets`.

## Exact prompt for the new prototype chat

Open a new chat in the same ANKIGTA workspace, attach or reference this handoff, and send:

```text
/prototype

Используй handoff
docs/handoffs/0002-filtered-deck-fsrs-admission-prototype.md.

Создай одноразовый prototype 0002 и ответь только на вопрос: может ли настоящая
rescheduling filtered deck `ANKIGTA Session` штатно сделать выбранную exact
Card X scheduler-top, позволить Anki принять её оценку и сохранить корректное
поведение FSRS.

Учти подтверждённый провал prototype 0001. Не повторяй попытку оценить non-top
Card напрямую и не исследуй private queue internals. Полностью выполни safety
setup, required scenarios, success criteria и evidence requirements из
handoff. Используй только disposable Anki profiles/copies.

Не исследуй MTA HTTP, CEF или Map Editor и не создавай production-код.
Запрещены direct SQL writes, private queue mutation и собственный scheduler.

Сохрани канонический результат в
docs/prototypes/0002-filtered-deck-fsrs-admission.md, добавь read-only verifier
и машинно-проверяемые evidence. Если хотя бы один критический критерий не
выполнен, зафиксируй failed или partially passed без недоказанного обхода.
```

