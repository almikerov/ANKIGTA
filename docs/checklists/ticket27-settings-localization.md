# Ticket 27 — Settings and localization manual checklist

Status: not run

Authority, defaults, validation, persistence, restart recovery, the locale
fallback and the runtime switch are covered automatically — including a restart
of each side against a real database and a real settings file, and including
rendering F7, the Study window, the connection windows and the counter HUD in
both languages and reading the control texts back. What needs a human is the
settings UI itself, how the two languages *look* once CEGUI lays them out, and
the behaviour of a real MTA client's private file directory.

## Scenarios

- Open the settings panel from the F7 window, then again from inside Review
  Mode with a card open. Review Mode blocks F7, so its own button is the only
  way in; confirm the panel opens over the card, that closing it returns the
  card to its previous state, and that rating still works afterwards.
- Change every server-owned setting (radius, delay, speed, early review,
  include in study) and restart the resource. Confirm each persists and appears
  in Change History, and that Undo restores it.
- Change every client-owned setting (indicator mode, protection, controls,
  close after rating, card audio, world muting, UI scale, language) and restart
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
  readable localized reason and that the stored value is unchanged — nothing
  should be silently clamped.
- On a Russian Windows locale, start with language `auto`. Confirm Russian.
  On any other locale, confirm English.
- Switch language while F7, the Card Picker, the Study window and Review Mode
  are open. Confirm every label changes without restarting the resource and
  without losing state — the selected row, the deck filter text and the open
  card all survive the rebuild.
- Confirm no Russian label is clipped by a control sized for the English one:
  the automated tests read the text, not the pixels.
- Confirm card text, Map Entity names you typed, Entity Tags and Anki Tags stay
  exactly as entered in both languages.
- Confirm stored values (setting keys, link states, identifiers) are unchanged
  by switching language — check the database before and after.

## Expected evidence

Screenshots of the settings UI in both languages, the database rows for each
setting before and after restart, and the rejection message shown for each
invalid input.
