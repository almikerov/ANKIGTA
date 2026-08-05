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

**Status:** built on `claude/panel-rebuild-04-world-marks`, green, not merged
and not deployed.

## What the stored `coronaOpacity` turned out to be worth: nothing

The owner's database holds `coronaOpacity` = **0.2**, and the shipped default is
0.6. Left alone, the moment this ticket named the key again that leftover would
have become the value in force — a corona faint enough to read as the feature
not working, on the first build that has the feature.

A value whose schema was deleted is not a preference; it is a leftover of a
build nobody kept, at a default nobody chose. So schema **8** retires it: one
`DELETE` of that one key, behind the migration gate that takes a verified copy
of the database first. `test_migrations.py` holds both halves — that the row
goes and the default is what the server then acts on, and that a value the
owner sets *after* the upgrade survives every later start, because this is a
one-off about one leftover and not a rule that eats the setting.

One key rather than "everything the schema does not know": a blanket sweep
would also delete a setting a *newer* build stored, which this one has no
business reading, let alone removing.

## What is in the world, and where it stops

`client/world_marks.lua` is the one module. Everything drawn goes through a
door on it — `sphere` for a zone, `beam` for the Next Card Indicator's mark —
and the door is where the distance is checked, so a mark added later inherits
the rule by drawing through one rather than by remembering to ask. The corona
is a marker element rather than something drawn per frame, so for that one the
same rule takes it out of the world instead of skipping a draw.

**The distance is 150 metres, from the camera.** Far enough to see a corona
from across a street or a plaza — a GTA San Andreas block is on the order of a
hundred — and well inside MTA's own streaming, so it is ANKIGTA's rule and not
a race with the streamer: markers stream within 600 units and objects within
500 (`CClientManager.cpp`). From the camera rather than the player because the
panel flies the camera to a row while the player stays put, and it does that in
order to look at the mark.

Asked once per mark rather than once per line: a sphere is forty-eight
segments, and testing each would draw the near half of a mark whose centre is
out of range — an arc hanging in the air, which is worse than either answer.

**The zone is drawn only while F7 is open**, and the corona is the one that is
not. The first build here had the zone outliving the panel — "the player sizes
a zone, closes F7 and walks the edge of it" — which was carried over from the
reference branch's own comment rather than from this ticket, and the owner
corrected it: the zone is an answer about the row being worked on, and with the
window shut there is no row being worked on. What outlives F7 is the *answer*
— the setting stays on, the selection is not cleared — so reopening puts the
same zone straight back without anyone reselecting anything. Told rather than
polled at both edges, so the sphere goes with the window rather than a quarter
of a second later.

## Two things changed that the ticket did not name

Both fell out of adding two columns to one table, and both are worth knowing
about at the merge.

- **`Store.relinkEntity` writes the metadata row in one statement.** It was an
  `INSERT OR IGNORE` followed by an `UPDATE`, which had to be kept saying the
  same thing; a column added to one and not the other survives a relink only
  when the target row happened not to exist yet. It is now the same
  `INSERT OR REPLACE` every other write path uses.
- **A per-entity value is validated before it is normalized.** The old order
  handed whatever arrived over the wire straight to the rule's own conversion,
  which is harmless for a number and not for a colour: `string.lower` on a
  boolean is an error rather than a refusal, so a client sending `true` would
  have taken the handler down instead of being told no.

## Found while building this

- **`Show corona` is silently capped at 32 by MTA.**
  `CClientMarker::IsLimitReached` is `m_uiStreamedInMarkers >= 32`, and
  `StreamIn` asks it, so the thirty-third corona within streaming range is an
  element that exists and is never drawn — no error, no log line. The distance
  rule above bounds how many can be near at once but not to 32. Nothing here
  reaches that number; a player who marks a warehouse full of objects would.
  Worth a ticket of its own: what to do when the world asks for more marks than
  the engine will draw, and how to say so.
- **The Next Card Indicator's mark is a beam, not a sphere.** The code calls it
  a sphere throughout and draws `dxDrawMaterialLine3D` — a vertical band whose
  *width* is the radius. Ticket 03's finding is fixed (it drew every entity
  following the global at three metres), but the naming is still wrong and the
  shape is still a band standing in for a sphere. Whichever ticket next opens
  `client/indicator.lua`.

Ticked where a test holds the claim. The rest are the things nothing here can
see: `docs/agents/mta-gta-reference-policy.md` says an item that needs a person
to look at a frame stays `not run` rather than being marked passed by the seam
underneath it.

- [x] A mark follows its object as the object moves
- [x] A mark is drawn without F7 having been opened first
- [x] A mark goes when the thing it marks is destroyed
- [x] Nothing is drawn past a stated distance
- [x] That distance is one rule, in one place, for every drawn mark
- [x] `Draw always` is gone, from the code and from the string table
- [x] `Draw radius` draws the selected row's zone and is the client's own —
      on screen while F7 is, per the owner; the setting and the selection
      outlive the window, the drawing does not
- [x] `Show corona` is stored on the entity
- [x] A corona is sized by the Activation Zone it stands for
- [x] Corona colour and opacity each have a global and a per-link override
- [x] Opacity defaults to 0.6
- [ ] A colour is chosen with a picker that works in the panel as rendered —
      **not run**, and inherited from ticket 03 for the same reason it was left
      there. The picker is executed against the real page in Node — it opens,
      offers swatches, takes a typed hex, refuses half a code and hands the
      colour back to Settings — and there is now a colour in the schema, so a
      control finally appears on a deployed panel. Whether the surface it opens
      is *visible* over a page rendered into a game window is the one thing no
      harness here can see.
- [x] A stored colour that fails its own rule falls back rather than drawing
      black
- [x] The stub the drawing runs against resizes and attaches the way MTA does

### What a person still has to look at

Deploy and open F7. What no test here can see is whether any of this is on
screen at all.

1. **Tick `Show corona` on a row and walk away from it.** The corona should
   stand on the thing, at the width of its Activation Zone, and go out at about
   150 metres — not blink, and not hang in the air after the object itself has
   gone.
2. **Look at a corona on something that moves** — a vehicle. It should keep up
   with it rather than trailing or staying behind.
3. **Change `Corona colour` in Settings** and confirm every corona that has no
   colour of its own changes with it, and one that does stays put.
4. **Open the entity's own colour picker** and check that the surface it opens
   is visible over the panel rather than clipped — this is ticket 03's
   unchecked line, and this is the first build on which there is anything to
   open.
5. **Turn on `Draw the selected row's radius`** and step down the list: the
   sphere should move to whichever row is selected, be the size the row's box
   says, and go the moment F7 closes — then be back on the same row when F7
   opens again.
6. **The opacity in force after the upgrade is 0.6**, not the 0.2 the database
   was carrying. If a corona looks nearly invisible on the first run, the
   migration did not happen and the server log will say why.
