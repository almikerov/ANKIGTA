# Ticket 21 — Best-effort CEF manual checklist

Status: not run

This is the ticket that most needs a human. Prototype 0006 could not verify
fidelity without launching the MTA client, and neither can any check here: the
whole promise is "best effort in stock CEF", which only an eye can judge.

## Scenarios

Render each prototype 0006 corpus group and compare side by side with Anki
Desktop, recording differences rather than expecting equality:

- plain and Unicode text; Anki front/back CSS; layout, fonts, pseudo-elements
  and animation; safe JavaScript; script-heavy templates.
- local media with relative, escaped and Unicode filenames; side audio.

Then:

- Confirm nothing in the card HTML, CSS, JavaScript or media references is
  deliberately stripped or truncated on the way to CEF.
- Break a card template, a script and a media reference in turn. Confirm each
  shows a warning and that Again/Hard/Good/Easy stay enabled and working.
- Reference an external HTTPS image. Confirm stock MTA domain permissions govern
  it and that denying the domain does not break rating.
- Make the card navigate its main frame away. Confirm the External Card Page
  appears, the outer Review Mode and rating bar remain usable, and
  `Вернуться к карточке` returns to the correct side with a fresh capability.
- Confirm `Вернуться к карточке` is optional — a player who ignores it can still
  rate.
- From card JavaScript, attempt a privileged `window.mta` call. Confirm the stub
  exists (prototype 0006) but no privileged dispatch succeeds.
- Attempt `window.open` from card JavaScript. Confirm the popup stays blocked.
  Do **not** treat system-browser handoff or downloads as supported.
- Mute card audio with world audio on, and the reverse. Confirm the two are
  independent.

## Expected evidence

Per corpus group: screenshot, DOM dump and computed styles from MTA CEF beside
Anki Desktop, plus whether the rating controls remained enabled.
