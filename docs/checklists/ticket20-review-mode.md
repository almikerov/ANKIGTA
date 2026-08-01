# Ticket 20 — Minimal Review Mode manual checklist

Status: not run

The state machine, transaction discipline, input capture and restoration are
covered automatically in the Lua harness. What remains is everything a person
has to look at: whether the card is legible, whether the buttons are where the
eye expects them, and whether focus behaves as described.

## Scenarios

- Open a linked card in game. Confirm the question renders in the CEF surface,
  the only control is `Показать ответ`, and no rating button is reachable yet.
- Reveal the answer. Confirm the answer renders and Again/Hard/Good/Easy appear
  **outside** the CEF surface, drawn by the resource — a card whose HTML mimics
  the rating bar must not be clickable as one.
- Rate the card. Confirm exactly one `revlog` row and that the modal closes when
  `Close after rating` is on, for all four ratings including Again.
- With `Close after rating` off, confirm the card stays open, shows the result,
  and further clicks submit nothing.
- Press `Esc` before rating: closes with no rating. Press `Esc` while a rating
  is in flight: refuses to close.
- While the modal is up, press F7, E, the number keys and +/−. Confirm no
  ANKIGTA game action fires and no weapon is switched or vehicle entered.
- Alt+Tab away and back. Confirm the card neither closes nor rates, and that the
  first click after returning only restores focus.
- Open the card with the cursor already visible and with `action` already
  disabled by another resource. Close it and confirm both come back as they
  were, rather than being reset to ANKIGTA's defaults.
- Kill the companion mid-rating. Confirm the card stays open and reports that
  the outcome is unknown rather than claiming success or failure.
- Stop the resource with a card open. Confirm the cursor, controls, camera and
  radio channel are restored.

## Expected evidence

Screenshots of question and answer states, the `revlog` delta per rating, and a
before/after capture of cursor state, control states, camera target and radio
channel around open and close.
