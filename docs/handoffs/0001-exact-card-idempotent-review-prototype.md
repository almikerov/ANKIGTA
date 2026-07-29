# Handoff: exact-card, exactly-once Anki review prototype

## Purpose

Continue in a **new chat** and build a disposable prototype answering one question:

> Can the ANKIGTA companion add-on open one exact Anki Card even when Anki's scheduler would select another card next, then apply Again/Hard/Good/Easy exactly once when the same `reviewTransactionId` is submitted repeatedly?

This is a proof, not production implementation. Do not implement the MTA resource, F7, CEF UI, filtered-deck lifecycle, map persistence or other ANKIGTA features.

## Current state

- The repository contains design documents only; production code does not exist.
- Repository configuration is recorded in `AGENTS.md` and `docs/agents/`.
- The old external `ANKIGTA_SPEC.md` is preliminary material and is **not** a source of truth.
- The product interview is complete enough to begin technical proof-gates.
- This is prototype 1. Filtered-deck + FSRS compatibility is prototype 2 and must remain separate.

## Read before working

Authoritative domain and baseline:

- `CONTEXT.md`
- `docs/design/confirmed-baseline.md`
- `docs/design/preliminary-spec-audit.md`

Relevant accepted decisions:

- `docs/adr/0002-use-server-side-lua-as-the-anki-gateway.md`
- `docs/adr/0007-make-the-companion-add-on-the-review-coordinator.md`
- `docs/adr/0008-make-ratings-idempotent.md`
- `docs/adr/0009-scope-card-links-to-anki-collections.md`
- `docs/adr/0012-limit-v1-to-tested-anki-on-windows-with-fsrs.md`
- `docs/adr/0017-keep-anki-authoritative-for-study-data.md`
- `docs/adr/0019-restrict-ankigta-to-the-mta-admin.md`

Read for boundary awareness, but do not test it in this prototype:

- `docs/adr/0003-gate-a-real-filtered-deck-behind-a-prototype.md`
- `docs/adr/0010-isolate-card-content-from-the-mta-bridge.md`

## Constraints that must remain true

- Anki is the only owner of scheduling.
- The companion add-on is the sole coordinator of a Review Transaction.
- The add-on must not implement its own scheduler.
- MTA must never apply the same rating through a second path.
- Card identity is `collection identity + cardId`, not `cardId` alone.
- Ratings are idempotent by `reviewTransactionId`.
- Target platform is Windows with FSRS and an explicitly recorded, tested Anki Desktop version.
- Anki Desktop, the companion add-on and MTA Server are intended to run on the same computer.
- One MTA Admin uses one local Anki collection.
- No production ANKIGTA code should be created during this prototype.

## Safety requirements

Use a disposable Anki profile or a disposable copy of a collection. Never run rating experiments against the user's real collection.

Before the first mutation:

1. Record the exact Anki Desktop version, Python/Qt versions exposed by Anki, scheduler mode and FSRS configuration.
2. Create or select a disposable profile.
3. Export or otherwise back up that disposable profile.
4. Record the initial card rows and review-log rows needed to prove later mutations.
5. Ensure no normal Anki review session is open.

Do not:

- edit Anki's SQLite database directly to simulate a successful rating;
- claim success from mocked scheduler behavior;
- rely on undocumented behavior without identifying the exact API and tested version;
- test with the user's real learning history;
- leave test cards in an unexpected filtered deck;
- silently change scheduler options or FSRS parameters.

## Required test data

Create a disposable deck with at least:

- **Card X** — the exact card requested by `collection identity + cardId`;
- **Card Y** — a card that Anki's scheduler selects before X;
- a note/card suitable for testing a missing or stale `cardId`;
- enough scheduling state to expose all rating choices that Anki genuinely permits for X.

Record:

- collection identity;
- note IDs and card IDs;
- deck IDs;
- queue/type/due values before testing;
- scheduler-selected next card before opening X;
- rendered question and answer for X;
- permitted answer buttons and intervals for X;
- scheduling and review-log state after each mutation.

The prototype must demonstrate that Y is scheduler-next while X is the explicitly opened card. Do not merely assume this from insertion order.

## Minimum prototype contract

The disposable add-on/prototype may expose an internal test interface equivalent to:

```text
openExactCard(collectionIdentity, cardId)
rateCard(reviewTransactionId, collectionIdentity, cardId, rating)
getReviewTransaction(reviewTransactionId)
getNextCard()
```

The exact transport is not important in this prototype. Focus on Anki behavior and transaction semantics. Do not design the final public HTTP API yet.

`openExactCard` must return enough evidence to identify X, show its current question/answer render and list the rating choices Anki currently permits.

`rateCard` must use Anki's scheduler/reviewer facilities rather than manually calculating or writing scheduling fields.

The idempotency store may be prototype-quality, but the result must survive at least a simulated lost response within the running prototype. Clearly state whether process-restart durability was proved or remains unproved.

## Required scenarios

### S1 — Exact card differs from scheduler-next

1. Ask Anki which card is next and prove that it is Y.
2. Call `openExactCard` for X.
3. Prove that the returned card is X, not Y.
4. Capture X's current render, scheduler state and permitted ratings.
5. Confirm that merely opening X does not create a review-log entry or change its schedule.

### S2 — One successful rating

1. Generate transaction ID `T1`.
2. Rate X with one permitted rating, initially `Good` unless Anki says it is unavailable.
3. Prove that exactly one review-log entry was created for X.
4. Prove that X's scheduling state changed through Anki.
5. Return the committed transaction result, X's new state and Anki's new next card.

### S3 — Identical retry

1. Submit the exact same `T1`, card identity and rating again.
2. Return the previously committed result.
3. Prove that no additional review-log entry exists and scheduling did not change a second time.

### S4 — Conflicting retry

1. Submit `T1` again with a different rating or card identity.
2. Reject it as a transaction conflict.
3. Prove that neither card changed.

### S5 — Lost response

1. Use a new transaction ID `T2`.
2. Apply a permitted rating successfully but simulate loss of the response before the caller receives it.
3. Query `getReviewTransaction(T2)`.
4. Prove that the caller can distinguish `applied` from `not applied` without resubmitting a rating.
5. Retry `T2` and prove that no duplicate review occurs.

### S6 — Invalid identity and stale card

Verify explicit non-mutating failures for:

- wrong collection identity;
- missing/stale `cardId`;
- card from another disposable profile/collection;
- rating not currently permitted by Anki.

### S7 — All four ratings

Using fresh disposable cards or a reset disposable profile, exercise Again, Hard, Good and Easy wherever Anki genuinely exposes them. Do not force a button that the scheduler does not permit. Record any state where fewer than four choices are valid.

## Success criteria

The prototype passes only if all are demonstrated with observed evidence:

1. `collection identity + cardId` uniquely identifies X.
2. X opens while scheduler-next is Y.
3. Current question/answer render and allowed rating choices are obtained.
4. The first request for a transaction changes X exactly once.
5. An identical retry returns the same committed result without a second review.
6. A conflicting reuse of the transaction ID is rejected without mutation.
7. A lost response can be reconciled unambiguously.
8. The result contains X's actual post-rating state and Anki's next card.
9. No custom scheduling algorithm is implemented.

If any criterion fails, report failure plainly. Do not hide it behind a proposed production workaround.

## Evidence to capture

For every scenario, capture:

- exact commands or add-on actions;
- input identifiers and rating;
- returned structured result;
- scheduler-next before and after;
- relevant card scheduling fields before and after;
- count and identity of review-log entries before and after;
- exceptions, warnings and Anki logs;
- whether the behavior uses a public, internal or undocumented Anki API.

Screenshots are optional; machine-readable logs and database/API observations are preferred. Reading the database for evidence is allowed; writing it to manufacture results is not.

## Assumptions that must not be accepted without proof

- An arbitrary card can be reviewed safely outside normal scheduler selection.
- Constructing or switching reviewer state has no side effects.
- Anki exposes the same four ratings in every card state.
- Rendered question/answer can be obtained without advancing scheduler state.
- AnkiConnect alone provides every required operation.
- An internal Anki API found in one version is stable across supported versions.
- `cardId` is globally unique across collections.
- Retrying a rating is safe without a transaction journal.
- A scheduler-next query after rating X is equivalent to normal Reviewer behavior.
- Rating X while Y is next does not corrupt learning/relearning state.
- Process restart durability exists merely because in-process retries work.

## Expected repository artifact

Save findings to:

```text
docs/prototypes/0001-exact-card-idempotent-review.md
```

The findings document must include:

- verdict: `passed`, `failed` or `partially passed`;
- tested versions and disposable-profile setup;
- scenario-by-scenario results;
- evidence and reproducible commands;
- exact Anki APIs used and their stability status;
- discovered constraints;
- unanswered questions;
- ADRs or baseline statements supported, contradicted or requiring revision;
- whether a second prototype iteration is needed.

Disposable prototype code should live under a clearly marked scratch/prototype directory and must not be presented as production ANKIGTA code.

## Suggested skills

- **Required:** `/prototype`
- **Optional if official API behavior must be investigated:** `/research`
- **After completing the prototype:** `/handoff` back to the main design chat

Do not invoke `/implement`, `/to-spec` or `/to-tickets` in the prototype chat.

## Exact prompt for the new prototype chat

Send the following in a new chat opened in the same ANKIGTA workspace, with this handoff file attached or referenced:

```text
/prototype

Используй приложенный handoff
docs/handoffs/0001-exact-card-idempotent-review-prototype.md.

Создай одноразовый технический прототип, отвечающий только на вопрос:
может ли companion add-on открыть точную Anki Card, когда scheduler-next —
другая карточка, и применить оценку ровно один раз при повторной отправке
одного reviewTransactionId.

Полностью соблюдай safety requirements, required scenarios и success criteria
из handoff. Используй только disposable Anki profile или копию коллекции.
Сначала зафиксируй версии и наблюдаемый критерий успеха. Не начинай
производственную реализацию ANKIGTA и не исследуй filtered deck в этом прототипе.

Запусти проверки, собери доказательства и сохрани итог в
docs/prototypes/0001-exact-card-idempotent-review.md.
Если нужное поведение невозможно или зависит от нестабильного внутреннего API,
зафиксируй это как результат, а не обходи ограничение недоказанным допущением.
```

