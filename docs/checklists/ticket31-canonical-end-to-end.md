# Ticket 31 — canonical end-to-end and card-state manual checklist

Status: not run

The canonical scenario is the spec's primary verification boundary:

> Map Entity → Spatial Link → verified Map Editor Save → Activation Zone →
> question → answer → rating → reconciled Anki result → updated next target

Every part of it is covered by automated tests at its own seam, and the world
polling that joins them was written for this ticket. What no automated check
can do is walk a player into a zone and watch a card open, so this pass is the
one that turns those seams into a scenario.

Run on the certified matrix (`docs/release/supported-versions.md`), on an
installation made by following `docs/operations/installation.md`.

## Before starting

- Make an Anki deck with a card in each state you will need: new, learning,
  relearning, due review, a review that is not due yet, one suspended, one
  buried. Note each card's id, interval and FSRS state before you begin.
- Keep a second copy of the collection, or take an Anki backup. This pass rates
  real cards.

## Scenarios

### The canonical scenario, once, slowly

1. In Map Editor, place an object. In F7, link it to a card. Confirm the link
   reads `Pending Map Save` and that the entity does **not** appear in the HUD
   counters, gets no Activation Zone, and is not marked.
2. Save the map with Map Editor's own Save. Confirm ANKIGTA notices the file
   change on its own and the link becomes active without you pressing anything.
   If it does not, press `Проверить ещё раз` and say which happened.
3. Press `Начать обучение`. Confirm the counters appear and that a filtered
   deck named `ANKIGTA Session` now exists in Anki.
4. Walk towards the object. Confirm the card opens after the configured delay
   and not before, and that walking out of the zone before the delay elapses
   cancels it.
5. Reveal the answer. Rate it. Confirm the window behaves as `Close after
   rating` is set.
6. In Anki, confirm exactly one new `revlog` row for that card and that its
   interval and FSRS state moved the way Anki's own reviewer moves them for the
   same rating.
7. Confirm the HUD counters changed and that the Next Card Indicator now points
   at a different target, or at nothing if there is nothing left.

### Every card state

For each of new, learning, relearning, due review:

- Confirm the card counts in the right HUD bucket, gets an Activation Zone, can
  be opened by walking into it, and can be rated with all four buttons across
  repeated runs.

For a not-due card:

- With `Режим повторения` on `Только подошедшие`: confirm it is not counted, has
  no zone, is never marked, and opens as Preview only with no rating buttons.
- On `Все`: confirm it counts in `Early`, gets a zone, and rates through Anki
  with the early-review warning shown.

For suspended and buried:

- Confirm they are listed in F7 with their status, are absent from the
  counters, get no zone and are never marked, and open as Preview only.
- Unsuspend one in Anki. Confirm it returns to the ordinary flow after the
  state refresh, with no restart.

For `Card missing`:

- Delete a linked card in Anki. Confirm F7 keeps the Map Entity and the old
  link record, marks it `Card missing`, excludes it from counters, zone and
  marker, and offers `Replace card`.
- Create a new card in Anki. Confirm ANKIGTA does **not** match it
  automatically.

For `Entity missing`:

- Remove a linked entity from the map outside ANKIGTA. Confirm the state is
  `Entity missing` rather than a destroyed Runtime Instance, that the card
  relationship survives, and that `Relink entity` moves the link, the name, the
  Entity Tag, the radius and `Show radius` onto an unlinked entity — including
  one in another loaded map or another interior.
- Confirm the operation previews the change, removes the old missing record,
  and is undone completely by Undo.

### The world moving underneath

- Bind a card to a vehicle. Drive it away from where it was authored and
  confirm the zone and the marker are where the vehicle *is*.
- Destroy it. Confirm the zone and the marker disappear, the countdown cancels,
  and the Spatial Link is still in F7.
- Walk far enough away that it unstreams and come back. Confirm it works again
  with no restart.
- With a card open, unload the map, destroy the entity and change dimension.
  Confirm the open card survives all three and that everything recalculates
  after it closes.

### The marker

- Set the Next Card Indicator to each of its three modes and confirm exactly
  those three exist: sphere and minimap, minimap only, nothing. Confirm the
  default is nothing.
- Link one card to several entities. Confirm only the nearest reachable one is
  marked, and that entering a different interior or dimension moves the mark to
  a reachable entity or removes it.
- Stand where a permanent `Show radius` sphere and the temporary next-card
  sphere coincide. Confirm one emphasised sphere is drawn rather than two, and
  that the entity's radius did not change.

### Timing, felt rather than measured

- With the automatic delay at zero, walk into a zone and note how long the card
  takes to appear. It is polled every 250 ms, so up to a quarter of a second is
  expected — write down whether it reads as immediate or as a lag.
- With the delay at its default of one second, confirm the countdown feels like
  a second rather than like a second and a quarter.
- Drive through a zone at speed with the speed gate at 30 km/h. Confirm 20 km/h
  opens and 60 km/h does not, reading the game's own speedometer. This is the
  only check on the velocity-to-km/h conversion.

## Expected evidence

Per scenario: the machine and version details; the card ids with their before
and after interval, due date, FSRS state and `revlog` rows read out of Anki
itself; the F7 state of each entity; and, for the timing scenarios, the
stopwatch and speedometer readings.

Where a rating produced two `revlog` rows, or none, stop and record the whole
sequence: that is the failure this pass exists to catch.
