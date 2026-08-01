# Ticket 14 — Exact Card Admission manual checklist

Status: not run

This checklist covers acceptance only a human can observe against a live Anki
profile. Automated checks verify the coordinator contract, the refusal paths and
the control operations; what remains is confirming that Anki 26.05 still behaves
the way prototype 0002 measured.

Use a disposable Anki profile with FSRS enabled, and take a native backup first.

## Scenarios

- With a full session built and Y scheduler-next, select linked card X in the
  world. Confirm the owned `ANKIGTA Session` deck rebuilds to X only, that Anki
  then reports X as scheduler-next, and that X exposes Again/Hard/Good/Easy.
- Confirm no `revlog` row is created by the admission itself, before any rating.
- Rate the admitted X once. Confirm exactly one new `revlog` row for X, correct
  FSRS state, and no change to any other card.
- After the rating, confirm the full session membership is rebuilt: X appears
  once, Y remains, the learning card remains, and nothing is stranded in the
  filtered deck.
- Request admission for a suspended card and for a buried card. Confirm neither
  enters the deck, both remain byte-identical, and both can still be previewed
  without any rating control.
- Request admission for a future/not-due review card with early review disabled,
  then enabled. Confirm the first is Preview only and the second is rated
  through Anki's own early-review path.
- Force a case where Anki does not place X on top after the X-only rebuild.
  Confirm the card opens Preview only, no scheduler answer is attempted, and the
  full membership is restored rather than left X-only.
- Kill Anki between admission and rating, restart, and confirm no duplicate
  rating and no stranded deck.

## Expected evidence

For each scenario record the collection identity, card ID, `type`, `queue`,
`due`, `ivl`, `factor`, `reps`, `lapses`, FSRS memory state and the relevant
`revlog` rows, before and after.
