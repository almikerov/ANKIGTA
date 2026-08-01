# Ticket 13 — Eligibility manual checklist

Status: not run

The policy, the queue mapping and the warnings are covered automatically. What
remains is confirming against a live Anki collection that the queue values mean
what `anki.consts` says they do, and that early review really matches Anki's own
early-review behaviour.

Use a disposable Anki profile with FSRS enabled and take a native backup first.

## Scenarios

- Build a card in each queue: new, learning, day-learn/relearn, due review,
  future review, suspended, sibling-buried and manually buried. Confirm ANKIGTA
  classifies each as the tests expect, especially that a **manually buried**
  card is Unavailable rather than a due review.
- Confirm suspended and buried cards keep their Spatial Link, remain visible in
  F7, can be previewed, and never appear in the session, the queue, activation
  zones or markers.
- With early review off, open a future review card. Confirm Preview only, no
  rating controls, and that it drives no automatic study.
- Turn early review on and rate the same card each of the four ways. Compare
  card state, FSRS parameters and `revlog` against the same rating performed
  through a supported early-review filtered deck in Anki itself.
- Suspend and bury cards with early review on. Confirm the setting does not
  override either.
- Set a source deck's new-card limit to 1 and link three new cards. Confirm all
  three enter the session, all are rateable, and those beyond the limit carry
  the warning.
- Suspend a card that is already in a running session, then refresh. Confirm it
  leaves the queue without breaking the session.

## Expected evidence

Per card: queue value, `due`, resulting ANKIGTA state, whether rating controls
appeared, and the `revlog` delta where a rating was made.
