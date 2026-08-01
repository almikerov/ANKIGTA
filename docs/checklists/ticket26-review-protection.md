# Ticket 26 — Review Protection manual checklist

Status: not run

Snapshot capture and restoration are covered automatically for every exit path.
What needs a human is damage coverage: which sources of harm MTA's damage-proof
flag actually stops.

## Scenarios

- Open a card on foot and have another player shoot you. Confirm no health is
  lost, that health is **not** restored to full, and that the world keeps
  running around you.
- Repeat in a vehicle. Confirm neither the player nor the occupied vehicle takes
  new damage.
- Repeat with fire, drowning, falling and explosions. Record which are actually
  covered; do not assume.
- Confirm another player standing nearby gets no protection of their own, and
  that a passenger in your protected vehicle benefits only because the vehicle
  does.
- Enable Review Protection with Disable player controls off, and the reverse.
  Confirm the two are genuinely independent.
- Have another resource make the player damage-proof, then open and close a
  card. Confirm the player is still damage-proof afterwards.
- Force a CEF failure, a disconnect and a resource stop while a card is open.
  Confirm cursor, controls, camera, audio and protection all return to their
  captured values, and that nothing is left stuck.

## Expected evidence

Per scenario: health and armour before/during/after, damage-proof state of
player and vehicle before and after, cursor and control states, and which damage
sources were tested.
