# Ticket 27 — Settings and localization manual checklist

Status: not run

Authority, defaults, validation, the locale fallback and the runtime switch are
covered automatically. What needs a human is the settings UI itself and how the
two languages actually look in it.

## Scenarios

- Change every server-owned setting (radius, delay, speed, early review,
  include in study) and restart the resource. Confirm each persists and appears
  in Change History, and that Undo restores it.
- Change every client-owned setting (indicator mode, protection, controls,
  close after rating, card audio, world muting, UI scale, language) and restart
  the client. Confirm each persists per machine and does **not** appear in
  Change History.
- Set a manual connection port and token on each side. Confirm the override is
  local to that side, survives restart, is excluded from Change History, and
  that the previous token value is never displayed.
- Type an out-of-range radius, an off-step radius, a three-decimal delay, a
  negative speed and a non-numeric value. Confirm each is rejected with a
  readable localized reason and that the stored value is unchanged — nothing
  should be silently clamped.
- On a Russian Windows locale, start with language `auto`. Confirm Russian.
  On any other locale, confirm English.
- Switch language while F7 and Review Mode are open. Confirm every label
  changes without restarting the resource and without losing state.
- Confirm card text, Map Entity names you typed, Entity Tags and Anki Tags stay
  exactly as entered in both languages.
- Confirm stored values (setting keys, link states, identifiers) are unchanged
  by switching language — check the database before and after.

## Expected evidence

Screenshots of the settings UI in both languages, the database rows for each
setting before and after restart, and the rejection message shown for each
invalid input.
