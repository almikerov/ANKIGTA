# Ticket 17 — Reviewer arbitration manual checklist

Status: not run

The state machine and every refusal are covered automatically against a fake
Reviewer. What remains is confirming that the real AQT surface behaves as
prototype 0003 measured — `moveToState("deckBrowser")` is not a documented
add-on API, so it must be re-checked on the pinned build.

Use a disposable Anki profile with FSRS enabled and take a native backup first.

## Scenarios

- With an ANKIGTA Session running, start ordinary review in Anki. Confirm
  ANKIGTA pauses, the owned filtered deck is emptied and removed, and every
  card returns to its home deck.
- Repeat with an unproven ANKIGTA transaction outstanding. Confirm the handover
  is refused until reconciliation, and that the filtered deck is not cleaned.
- Leave a standard question, then a standard answer, via ANKIGTA's session
  start. Confirm Anki reaches `deckBrowser`, creates no `revlog` row, and leaves
  complete card state byte-identical.
- Press a rating in the standard Reviewer and immediately request an ANKIGTA
  session. Confirm `Завершаем оценку Anki…` appears, the Reviewer is untouched,
  and the session is created only after the stock callback completes.
- Repeat, but let the callback hang. Confirm ANKIGTA keeps waiting, never forces
  cleanup, never starts a session, and never cancels the operation.
- End ordinary review normally. Confirm ANKIGTA does **not** resume by itself.
- Run against an Anki build outside the supported pin. Confirm arbitration is
  blocked with a clear message rather than attempted.

## Expected evidence

Per scenario: the AQT state before and after, the `revlog` delta, complete card
state before and after, and whether a filtered deck existed at each step.
