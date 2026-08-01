# Ticket 19 — Read-only card content manual checklist

Status: not run

The capability contract, budgets, denials and headers are covered automatically.
What remains needs the real MTA CEF browser, which no automated check here can
stand in for — prototype 0006 explicitly could not verify fidelity without it.

## Scenarios

- Render each corpus group from prototype 0006 in stock MTA CEF and compare
  against Anki Desktop: plain and Unicode text, Anki front/back CSS, layout,
  fonts, pseudo-elements, animation, safe JavaScript, local media, relative,
  escaped and Unicode filenames, side audio, script-heavy templates.
- Confirm a card requesting an external subresource does not gain access to
  anything on the control port.
- Confirm the `window.mta` stub present in every CEF context (prototype 0006
  finding) cannot reach a privileged operation from card JavaScript.
- Let a capability expire while the card is open. Confirm the page stops being
  served and the failure is visible as a warning, not a crash.
- Open a second card while the first is still displayed. Confirm the first
  capability stops working immediately.
- Render a card whose media is missing. Confirm the placeholder appears and the
  rating controls still work.

## Expected evidence

Per corpus group: screenshot, DOM dump and computed styles from MTA CEF beside
the same card in Anki Desktop, plus the endpoint's request log showing request
count and unique bytes for that render.
