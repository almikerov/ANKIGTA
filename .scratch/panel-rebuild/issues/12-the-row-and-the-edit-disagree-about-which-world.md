# 12 — The row and the edit disagree about which world you are in

**What to build:** a row the panel offered stays editable, whichever copy of the
map the player is standing in when they edit it.

Found on the owner's running server on 2026-08-06, in their own workflow: they
made a map in the editor, saved it as `dum`, put an object in it, and tried to
edit that object's settings. The server answered

```
entity_element_not_found     map=dum entity=object (CJ_SKIP_Rubbish) (1)
entity_metadata_unresolved   map=dum entity=object (CJ_SKIP_Rubbish) (1)
                             reason=map_entity_not_found
```

Nothing was stored, so nothing was written — the edit was simply refused.

## One authored object, three elements

Measured live. Three elements answer to `object (CJ_SKIP_Rubbish) (1)`:

| owner | dimension | `edf:creatorResource` |
|---|---|---|
| `editor_main` | 200 | `editor_main` |
| `editor_test` | 0 | — |
| `dum` | 0 | — |

The editor's copy is the **EDF representation**. The other two are the
play-test's and the saved map's.

## Why the edit cannot find any of them

`elementByAdoptionName` (`server/main.lua:1841`) accepts an element only when

```lua
owningResource(element) == context.candidateOwner
    and not isEditorRepresentation(element)
```

Standing in the editor's working dimension, `World.currentMapContext` answers
`candidateOwner = EDITOR_RESOURCE`, which is `"editor_main"`
(`server/world.lua:41`). So inside the editor those two conditions exclude each
other: the only `editor_main`-owned element **is** the representation, and the
representation is rejected. The real element belongs to `dum`.

**The candidate walk that offered the row has the same filter**
(`server/main.lua:451`) — which is how the row existed at all: it was built
under a *different* context, when the player was in the map's world and
`candidateOwner` was `dum`. The row was offered in one world and edited in
another.

## This is the same root cause a third time

Ticket 02's follow-up: *"one map document answers to three different strings at
once, and ANKIGTA kept picking the wrong one."* Ticket 09: adoption during a
play-test. Both were fixed by matching **map identity** rather than resource
name — and the context already carries the identities, as `context.mapIds`
(`World.mapIdsForOwner`).

`elementByAdoptionName` and the candidate walk never look at `mapIds`. They are
the two places the move to identity did not reach.

So this ticket is not "add `dum` to the list". It is: those two filters ask the
same question the rest of the resource now asks, and the answer stops depending
on which copy the player happens to be standing in. If after that a
`candidateOwner` is still needed anywhere, say what it is still deciding.

## What it must not break

Ticket 02 bought the representation filter with real breakage — the editor's own
EDF copy counted as a second entity and refused every link with
`entity_runtime_not_unique`. Widening the owner test must not widen that: a
representation is still not an entity, and a genuine duplicate is still refused
with a reason.

## What the running server said when it was asked

Two things above are not what the live world holds, measured on it before any
code was written.

**The editor's copy is not the EDF representation.** `edf:rep` is `false` on
all three copies of `object (CJ_SKIP_Rubbish) (1)`; the `editor_main` one
carries `edf:creatorResource`, which is a different key and not what
`isEditorRepresentation` reads. So the representation filter never refused
anything here, and editing from inside the editor's own dimension already
worked. The representation filter is still needed and is still there — it is
just not what this defect was.

**What refused was the tie.** `dum` and `editor_test` are both running
resources of type `map`, and both hold a copy of the map the editor has open.
Read as two maps the player could be standing in, they score equally in the
ordinary world — and a tie is answered by not guessing, so standing in the
map's own world there was no current map at all. Nothing was offered there and
nothing could be edited there.

Which of the two worlds the owner was standing in when the edit was refused is
not recorded, so this is the mechanism rather than a replay of their click.
Both worlds are acceptance criteria above, and both are held by tests now.

So the answer is one question rather than two, and the two filters now ask it
literally: `World.belongsToContext` is the whole of what either walk tests, and
the context carries `owners` — every resource holding a copy of this map: the
editor's own, the one a Test press writes out, the resource the map is saved
as, and anything else carrying its identity.

`candidateOwner` was deciding nothing that survives the question being asked
properly, so it is gone rather than kept beside `owners`.

`workingDimension` now stands wherever the editor has a map open, not only in
the editor's own world: the walk can meet the editor's own copies from either
world now, and a parked element is in the bin whichever world it is seen from.

**A third site was touched, and it had to be.** `World.instanceInFrontOf` is
what says which of several copies is the one in front of the player, and it
counted a play-test copy standing beside the map it is a test of as a genuine
duplicate — because the editor runs a test in the ordinary world, which is
where the saved map runs too, so the player's dimension cannot tell those two
apart. It is one entity seen twice, which is ticket 09's own statement, so it
is answered there rather than worked around in each of the two filters. A
duplicate that is not a play-test copy is still refused, and now says which
thing and how many of it, in the shape the link path already refuses in.

Which copy the *offer* describes is the same question, so it is asked there
too: the copies share a position but not a dimension, and a row's dimension is
what the map draws its blip in. Offered from whichever copy the walk met first,
a row described the world the player was not in.

## Found on the way, not fixed here

- Two maps that carry no ANKIGTA identity at all still cannot be told apart
  where one of them is a leftover `editor_test` of a map the editor has since
  closed. That is the same gap `World.enduring` already names and declines to
  close, for the same reason: the editor cannot open a map while a test runs,
  so a *running* test is a test of the open map.

**Blocked by:** None.

**Status:** done, unmerged and not deployed — branch
`claude/row-edit-world-disagree-958189`. Automated proof:
`tests/test_map_editor_saved_map_copies.py`, with ticket 09's
`tests/test_map_editor_play_test_twin.py` and ticket 02's
`tests/test_map_editor_and_maps_in_play.py` green beside it. Nothing below has
been looked at in the game.

- [x] An object in a map saved under its own name can have its settings edited
      from the editor
- [x] The same object can be edited while standing in the map's own world
- [x] A row the panel offers is editable without moving the player first
- [x] Both filters resolve by map identity, not by which copy owns the element
- [x] An EDF representation is still never an entity
- [x] A genuine duplicate is still refused, and says which
- [x] Linking during a play-test still works — ticket 09's tests stay green
- [x] The stub the walk runs against carries all three copies of one authored
      object, so this cannot pass in tests and fail in the game
