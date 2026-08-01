# Ticket 15 — One rating through MTA manual checklist

Status: not run

Automated checks cover the coordinator, the gateway's request and settlement
paths, and every refusal. What remains is confirming the end-to-end effect on a
live Anki collection, which only a human can observe.

Use a disposable Anki profile with FSRS enabled and take a native backup first.

## Scenarios

- With a session running and a card admitted, submit each of Again, Hard, Good
  and Easy from MTA on a fresh baseline copy. For each, confirm exactly one new
  `revlog` row for that card, correct FSRS state, and no change to any other
  card.
- Confirm the MTA status shows the confirmed terminal result, and that the full
  session membership is rebuilt only after it arrives.
- Double-click a rating button. Confirm one `revlog` row, one HTTP request, and
  that the second click reports the same `reviewTransactionId`.
- Stop the companion between the request and its response. Confirm MTA reports
  `outcome_unknown`, does not claim success or failure, does not rebuild the
  session, and blocks further ratings until reconciliation.
- Return a malformed body and an HTTP 500 from a stub companion. Confirm both
  settle as `outcome_unknown` rather than as a failed rating.
- Compare the resulting card state, FSRS parameters and `revlog` against the
  same rating performed in Anki's own Reviewer on an identical baseline.

## Expected evidence

For each scenario record the collection identity, card ID, `reviewTransactionId`,
`type`, `queue`, `due`, `ivl`, `factor`, `reps`, `lapses`, FSRS memory state and
the relevant `revlog` rows, before and after.
