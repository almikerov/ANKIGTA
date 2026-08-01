# Ticket 16 — Durable Review Transaction recovery manual checklist

Status: not run

The journal, its state machine and every reconciliation branch are covered
automatically, including a real companion restart. What remains needs a live
Anki collection: whether the evidence a production verifier gathers actually
distinguishes an applied rating from an unapplied one.

Use a disposable Anki profile with FSRS enabled and take a native backup first.

## Scenarios

Inject a fault at each window and confirm the recorded decision, the number of
scheduler calls, and the target `revlog` delta:

- Before the scheduler call. Expect the transaction to resend under the same id
  and produce exactly one `revlog` row.
- After Anki commits but before the durable result is written. Expect
  reconciliation to prove application from card, FSRS and `revlog` evidence,
  make no second call, and report `Rating applied`.
- After the durable result but before the response reaches MTA. Expect the
  saved result to be replayed with no second call.
- Kill the companion process, the MTA resource, and the whole MTA server, in
  turn. Confirm each recovers to the same decision.
- Mutate the card externally so the requested outcome becomes unprovable.
  Expect a durable `outcome_unknown`, zero retries, only that card blocked,
  other cards still queryable, and a denied collection switch.
- Terminate inside Anki's atomic answer/rebuild. Confirm the result is either
  reconciled from authoritative evidence or honestly left `outcome_unknown`,
  and that the target `revlog` delta is zero or one — never two.

Then confirm garbage collection removes only completed records that both sides
have acknowledged, and never an `outcome_unknown`.

## Expected evidence

For each scenario record the journal state before and after, `scheduler_calls`,
`resends`, and the full target `revlog` delta.
