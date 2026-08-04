# Ticket 27 — Settings and the string table manual checklist

Status: not run

Authority, defaults, validation, persistence and restart recovery are covered
automatically — including a restart of each side against a real database and a
real settings file, and including rendering F7, the Study window, the
connection windows and the counter HUD and reading the control texts back.
What needs a human is the settings UI itself, how the words *look* once CEGUI
lays them out, and the behaviour of a real MTA client's private file directory.

Ticket 07 removed the language setting, so the two-language steps are gone from
this list; the guard that nothing outside the string table holds a Cyrillic
constant is automatic and covers the whole resource.

## Scenarios

- Open the settings panel from the F7 window, then again from inside Review
  Mode with a card open. Review Mode blocks F7, so its own button is the only
  way in; confirm the panel opens over the card, that closing it returns the
  card to its previous state, and that rating still works afterwards.
- Change every server-owned setting (radius, delay, speed, early review,
  include in study) and restart the resource. Confirm each persists and appears
  in Change History, and that Undo restores it.
- Change every client-owned setting (indicator mode, protection, controls,
  close after rating, card audio, world muting, UI scale) and restart
  the client. Confirm each persists per machine — the file is
  `@ankigta-settings.json` in the client's private resource directory — and
  does **not** appear in Change History.
- Set a manual connection port and token on each side. Confirm the override is
  local to that side, survives restart, is excluded from Change History, and
  that the previous token value is never displayed.
- Hand-edit `connection-manual.json` to carry `"overrideSide": "client"`.
  Confirm the server reports a foreign override rather than adopting the port.
- Type an out-of-range radius, an off-step radius, a three-decimal delay, a
  negative speed and a non-numeric value. Confirm each is rejected with a
  readable reason and that the stored value is unchanged — nothing should be
  silently clamped.
- On a Russian Windows locale, confirm every surface is still in English and
  that no language can be chosen anywhere in the settings panel.
- Confirm no label is clipped by the control it sits in: the automated tests
  read the text, not the pixels.
- Confirm card text, Map Entity names you typed, Entity Tags and Anki Tags stay
  exactly as entered, including when they are not in English.

## Expected evidence

Screenshots of the settings UI, the database rows for each setting before and
after restart, and the rejection message shown for each invalid input.
