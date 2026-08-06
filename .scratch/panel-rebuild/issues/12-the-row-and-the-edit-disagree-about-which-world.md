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

**Blocked by:** None.

**Status:** ready-for-agent

- [ ] An object in a map saved under its own name can have its settings edited
      from the editor
- [ ] The same object can be edited while standing in the map's own world
- [ ] A row the panel offers is editable without moving the player first
- [ ] Both filters resolve by map identity, not by which copy owns the element
- [ ] An EDF representation is still never an entity
- [ ] A genuine duplicate is still refused, and says which
- [ ] Linking during a play-test still works — ticket 09's tests stay green
- [ ] The stub the walk runs against carries all three copies of one authored
      object, so this cannot pass in tests and fail in the game
