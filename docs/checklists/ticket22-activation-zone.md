# Ticket 22 — Activation Zone manual checklist

Status: not run

The decision core — eligibility, nearest-target selection, countdown,
cancellation, speed gate and interior/dimension scoping — is covered
automatically. What remains is everything that needs a world: moving entities,
streaming, and how the timing actually feels.

## Scenarios

- Walk into an object's zone and wait. Confirm the card opens after the delay,
  and that the zone visualisation matches the configured radius.
- Repeat with a vehicle and with a ped. Confirm the zone follows the moving
  Runtime Instance rather than its authored position.
- Drive the linked vehicle away while standing still. Confirm the countdown
  cancels as the zone leaves you.
- Destroy the Runtime Instance mid-countdown. Confirm the countdown cancels, no
  card opens, and the Spatial Link survives — check F7 still lists it.
- Let the entity unstream by walking far away and back. Confirm no card opens
  while it is unstreamed and that it works normally once it returns.
- Stand where two zones overlap. Confirm the nearest wins, and that moving
  between them restarts the countdown rather than opening instantly.
- Set the speed gate to 0 and drive slowly through a zone. Confirm nothing opens
  until a complete stop. Then set it to 30 and confirm 20 km/h opens and
  60 km/h does not.
- Enter an interior and a different dimension containing a linked entity.
  Confirm activation happens only in the matching interior and dimension, and
  that changing either mid-countdown cancels it.
- With a card open, change dimension, unload the map, and destroy the entity.
  Confirm the open card survives all three and that activation recalculates
  correctly after it closes.
- Confirm a Pending Map Save, Entity missing, suspended, buried and
  study-excluded link never auto-open.

## Expected evidence

Per scenario: player position, interior, dimension and speed; the entity's live
position and radius; whether a countdown started; and whether a card opened.
