# Ticket 30 — Performance and large-data acceptance manual checklist

Status: not run

The benchmark is automated and is the release gate: `tests/perf/` generates the
reference world — 10,000 Map Entity, 5,000 Spatial Link, 100,000 Anki cards —
takes every measurement the ticket states a threshold for, and emits a report
that blocks a release on a failure *and* on a measurement it could not take.
The over-limit run is automated too, and reports the state every file was left
in rather than that nothing raised.

What no automated check can reach is the half of each threshold that is about a
screen, a frame and a person: whether the window is usable when it appears,
whether the game still feels smooth, whether progress is visible while a
rebuild runs, and whether a card that took 900 ms felt instant or felt late.
The numbers below are the automated ones; the point of this pass is to find out
whether they describe the experience.

Run every scenario on the documented environment — Windows, 4 cores, 16 GiB,
SSD, with MTA and Anki Desktop installed — and write the machine down.

Take the automated numbers on the same machine, in the same session, before or
after the pass:

```bash
python -m tests.perf --report .scratch/ticket30-report.json
```

It prints one line per threshold, writes the evidence as JSON, and exits
non-zero if anything blocks the release.

Two things to know before starting. Both were open findings on ticket 30 and
were closed by ticket 31, so what this pass observes is different from what the
original text described:

- **The Activation Zone and the Next Card Indicator are driven now.**
  `client/spatial.lua` polls the world every 250 ms, feeds `Activation.update`
  a player observation and a candidate list, and asks the server to open the
  card through the ordinary Review Mode path; the server sends the candidate
  set, the HUD counters and `ankigta:nextCard`. The scenarios below that ask
  for a card to open by walking into a zone now have something to observe.
- **F7 has a Map Entity filter.** It searches the stored record — identity,
  name, Entity Tag, type and Spatial Link state — and does not depend on
  streaming. The 150 ms promise in story 58 covers it and the Card Picker's
  deck filter; the benchmark measures them as `f7_entity_filter` and
  `search_filter`.

Because the scan no longer runs on every rendered frame, the per-frame number
this pass compares against is the amortised one: `spatial_frame` in the report
is the marker and the HUD every frame plus one full pass every 250 ms, and
`pollMsMax` in its context is what a single full pass costs.

## Scenarios

### The reference world

- Load the generated reference map and confirm F7 lists 10,000 Map Entity with
  5,000 of them linked. Time from pressing F7 to the list being scrollable and
  legible, by stopwatch. Confirm it is inside two seconds and that the window
  is not merely present but usable — the grid populated, the buttons live.
- Type a deck name into the Card Picker filter and press Search. Time to the
  first page. Confirm the wait reads as immediate rather than as a pause you
  notice.
- Type into F7's own Map Entity filter and press Filter over the same ten
  thousand entities. Time it by stopwatch, and confirm the grid repopulates
  without the window going blank. The automated number excludes CEGUI
  repopulating the rows, which is the part only this pass can see.
- Scroll the F7 list from top to bottom. Confirm scrolling stays smooth and no
  row renders blank while it catches up.
- Confirm no card is rendered by any of the above: nothing loads CEF until a
  card is actually opened.

### 500+ links while watching frame time

- Stand in a part of the map with at least 500 linked entities streamed in.
  Turn on the frame-time display (`showfps` or the client's own counter) and
  write down the frame time with ANKIGTA's HUD and Next Card Indicator on.
- Turn the Next Card Indicator to `none` and the HUD off, and write it down
  again. The difference is ANKIGTA's cost. Confirm it is under 2 ms on average
  and that no single frame stutters visibly when the nearest entity changes.
- Repeat while driving through the same area at speed, so the nearest candidate
  changes every frame.
- Enter Pick Entity in the same place and sweep the camera across the entities.
  Confirm the highlight keeps up and the frame time does not step up while the
  mode is active.

*The prior attempt polled 500 bindings on a 250 ms timer and rejected a
per-render-frame full-map scan for this reason. If our frame time is much worse
than theirs, the polling shape is the first thing to look at — but their
numbers are a calibration point, not our threshold.*

### Restart the resource with a review open

- Open a card through spatial activation. While it is open, restart the ANKIGTA
  resource from the server console (`restart ankigta`).
- Confirm, in this order and each one by hand: player controls are usable
  again; the cursor is back to the game's own state; the player is no longer
  frozen; card audio has stopped and game-world sound is back at its normal
  level; and no card surface is left drawn over the world.
- Confirm no rating was recorded for the card that was open — check the card in
  Anki, not only ANKIGTA's own report.
- Repeat with the player inside a vehicle, and confirm Review Protection was
  lifted from both the player and the vehicle.

### A bound entity that moves

- Bind a card to a moving door, a lift, or a vehicle that is driven.
- Stand where the *authored* position is and confirm nothing activates once the
  entity has moved away.
- Follow the entity to its current position and confirm the Activation Zone is
  there — the radius follows the live Runtime Instance, not the authored point.
- Ride the lift or the vehicle with the zone around you and confirm the
  countdown behaves as it does on foot rather than restarting each frame.

### Destroy and recreate a bound entity

- With a card bound to an object, destroy that object at runtime. Confirm F7
  reports Entity missing and that the Spatial Link is still listed.
- Recreate the object with the same element ID. Confirm the binding resolves
  again on its own, or that Relink entity offers it — and say which happened.
- Confirm no second link was created and that the card is still counted once.

### Over the reference volume

- Load a world past the reference volume — more than 10,000 Map Entity or more
  than 5,000 Spatial Link. Confirm the server log carries one
  `volume_over_reference` line and that ANKIGTA keeps working rather than
  refusing.
- Work normally for a while: link, unlink, undo, redo, open cards, rate.
- Stop the server, and confirm every link made during that session is still
  there on the next start. Confirm `backups/` holds whole copies and that the
  database passes `PRAGMA integrity_check`.

### Cold, warm and restart

- Reboot, then start MTA and Anki and time the first F7 open. Write it down as
  the cold number.
- Open and close F7 five more times. Write down the warm numbers.
- Restart the resource and time the first F7 open after the restart.
- Confirm the cold number is the worst of the three and that none of them is a
  surprise.

### Session rebuild

- Start a session over all 5,000 links. Confirm progress is visible the whole
  time, that it advances rather than sitting at one number, and that the
  interface answers a click while it runs.
- Cancel a rebuild halfway. Confirm it stops promptly and leaves no filtered
  deck behind in Anki.

## Expected evidence

Per scenario: the machine (CPU, RAM, disk, OS build), the MTA and Anki
versions, the stopwatch numbers, the frame-time readings with and without
ANKIGTA drawing, the server log lines, and the automated report from the same
machine (`tests/perf` writes it as JSON) so the hand-timed numbers and the
measured ones can be read side by side.

Where a hand-timed number disagrees with the automated one, the hand-timed
number is the one that matters: the thresholds are about what the player
experiences, and the automated measurement only covers the part of that
ANKIGTA owns.
