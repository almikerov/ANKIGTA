# 04 — What ANKIGTA draws into the world

**What to build:** the marks ANKIGTA puts into the game world, as one module
with one rule about distance — replacing `Draw always`, which answered the wrong
question.

**A mark follows the thing it marks.** A zone is drawn where its target was when
the panel last spoke to the server, so it stays behind when the object moves and
sits in the air when the object is gone. It follows, by being attached to the
element or by reading its position per frame.

**And it exists before F7 does.** Nothing is drawn at all until the panel has
been opened once, because the entity snapshot is only sent in answer to F7 being
pressed. A mark that is a property of the world does not wait for a window.

**`Draw always` goes; `Show corona` replaces it.** `Draw always` was a per-link
switch that made the drawn radius permanent, which confused two different
things. Pull them apart:

- **`Draw radius`** is a way of *looking*: while it is on, the selected row's
  Activation Zone is drawn. It is the player's own, it belongs to the client, and
  it says nothing about the entity.
- **`Show corona`** is a property of *the entity*: a corona marker standing where
  the thing stands, sized to its Activation Zone, visible from across a street
  with nothing open. Stored on the entity, so it is the same for anyone looking.

A corona has a colour and an opacity, each with a global default and an override
on the link — the shape the Activation Zone radius already has. **Opacity
defaults to 0.6.** The colour picker is ticket 03's; use it rather than building
a second way to choose a colour.

**One distance, for everything drawn.** A drawn mark has no distance at which it
stops, so it is still hanging in the air long after its object has dropped its
LOD and gone. One rule, applied wherever anything is drawn, so a mark added
later inherits it instead of repeating it.

**Reference, not a merge.** This was built once, on `claude/ticket-06-f8ae21`,
and merged into the old trunk as `00faa13` — `client/zone_marks.lua`, 560 lines,
with 872 lines of tests. It is not on this trunk. It is the best available answer
to several of the questions above and reading it will save real time:
`git show 00faa13`. Take from it what survives scrutiny; it was never run by
anyone, so nothing in it is evidence.

**The owner's store already holds a `coronaOpacity`.** After ticket 01 deployed,
the live server logged `discarded_stored_setting: coronaOpacity
(settings.error.unknown)` — some earlier build wrote it and the current schema
does not know it, so the store throws it away every start, correctly. The moment
this ticket adds the setting back, that stored value stops being discarded and
becomes the value in force — whatever it happens to be, not 0.6. Decide what a
stored value from a schema that no longer existed is worth, and say so; do not
let it silently outrank the new default.

**Blocked by:** 01, 03 — it adds three settings, and Settings has to be operable
to judge them.

**Status:** ready-for-agent

- [ ] A mark follows its object as the object moves
- [ ] A mark is drawn without F7 having been opened first
- [ ] A mark goes when the thing it marks is destroyed
- [ ] Nothing is drawn past a stated distance
- [ ] That distance is one rule, in one place, for every drawn mark
- [ ] `Draw always` is gone, from the code and from the string table
- [ ] `Draw radius` draws the selected row's zone and is the client's own
- [ ] `Show corona` is stored on the entity
- [ ] A corona is sized by the Activation Zone it stands for
- [ ] Corona colour and opacity each have a global and a per-link override
- [ ] Opacity defaults to 0.6
- [ ] A colour is chosen with a picker that works in the panel as rendered
- [ ] A stored colour that fails its own rule falls back rather than drawing
      black
- [ ] The stub the drawing runs against resizes and attaches the way MTA does
