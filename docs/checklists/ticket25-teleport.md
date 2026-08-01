# Ticket 25 — Teleport manual checklist

Status: not run

Snapshot resolution, the state race, passenger handling and both ADR
prohibitions are covered automatically. What needs a human is what teleport
looks like when it lands.

## Scenarios

- Teleport to a linked object, a linked vehicle and a linked ped in turn.
  Confirm you arrive at the live position each time.
- Move a linked vehicle, then teleport. Confirm you arrive at where it is now,
  not where it was authored.
- Destroy a linked entity, then teleport. Confirm you arrive at the authored
  map position, interior and dimension.
- Teleport to an entity inside an interior and to one in a non-zero dimension.
  Confirm position, interior and dimension all match — a mismatch here is the
  failure this ticket exists to prevent.
- Teleport into water, into open air, into a solid object and into a vehicle's
  interior. Confirm each is permitted and nothing is relocated to a "safe"
  spot (ADR 0005).
- Teleport while driving with a passenger aboard. Confirm the vehicle, the
  driver and every passenger arrive together in the same interior and
  dimension.
- Destroy a linked entity and confirm F7 still lists its Map Entity and Spatial
  Link, and that ANKIGTA does **not** recreate it (ADR 0004).
- Have the map or another resource recreate it with the same persistent ID.
  Confirm availability returns and teleport uses the live position again.

## Expected evidence

Per scenario: the entity's live and authored position/interior/dimension, the
player's position/interior/dimension after arrival, and for vehicles the same
for every occupant.
