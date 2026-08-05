# 07 — A row is called what the Map Editor calls it

**What to build:** a Map Entity's default name is the name the Map Editor gave
it, not a name ANKIGTA invents from a model number.

Reported items 38 and 39. They arrived as two and are one fix.

## What is wrong

Place two peds and both rows read `Ped skin 0`. The name is derived from the
model, so two of the same model are two rows with the same name and nothing
tells them apart. The Map Editor, standing right there, calls them `ped (1)` and
`ped (2)`.

The same derivation is why a **marker** has no name at all. `entityLabel` in
`client/panel.lua` starts with `tonumber(mapEntity.model)` and gives up when
there is not one; a marker has no model, so every marker row is
`Unnamed Map Entity`. Markers are otherwise a supported type everywhere —
`shared/entity_types.lua`, the world scan, `pick_entity.lua`,
`spatial.lua`, and the database's own CHECK constraint all list them. Naming is
the whole of what is missing.

## The name already exists — it just is not kept

The editor writes its element id into element data under `me:ID`, and
`server/map_identity.lua:575` already reads it: `editorElementId =
getElementData(objectElement, "me:ID")`. It is used transiently, to match a
pending save back to its authored node, and then dropped. `map_entities` has no
column for it.

So the work is: keep it, and use it.

**Read, do not derive.** A counter of our own would produce `ped (1)` and
`ped (2)` that agree with the editor right up until an entity is deleted and
another added, after which they disagree silently and the player trusts the
wrong one. ADR 0025 stands: reading the editor's element data is reading, not
writing.

**An entity adopted with no editor id still needs a name.** Fall back to what
happens today — the model name for an object or vehicle — and to something
honest for the rest. A fallback that looks like an editor id would be a lie
about where the name came from.

## A ped is not named by its skin, but is still found by it

Do **not** ship an id→name table for skins. The row says `ped (1)`; the skin
does not appear in it.

The skin stays a **search** criterion: filtering by the skin number finds the
ped. If a name for the skin can be had at all, that is a second search
criterion — but it is not what the row is called. This supersedes the earlier
plan to name peds from a shipped table.

## A marker is an ordinary Map Entity

Named like the rest, renamed like the rest, and carrying the same per-link
settings as the rest. Nothing about a marker should need a special case in the
panel once it has a name.

## What ticket 03 already did

03 built the rename overlay: a given name replaces the default, the row still
shows what it was called before, and the filter matches either. That mechanism
does not change — this ticket changes what "what it was called before" *is*.

**Blocked by:** 02, 03 — 02 owns `store.lua` and the migration lands there; 03
owns the row and the filter.

**Status:** ready-for-agent

- [ ] The editor's element id is persisted with the Map Entity
- [ ] A database written before this opens, migrates, and keeps its entities
- [ ] A row's default name is the editor's id: `ped (1)`, `object (4)`
- [ ] Two entities of the same model read as two different rows
- [ ] A marker has a name, and it comes from the same place as every other type
- [ ] A marker can be renamed, and carries the same per-link settings as the rest
- [ ] An entity with no editor id still gets an honest name, not a fake one
- [ ] A given name still replaces the default, and the original is still shown
- [ ] The filter matches a ped by its skin number
- [ ] The filter matches a skin name where one can be had
- [ ] No skin id→name table is shipped for the purpose of naming rows
- [ ] Nothing is written into any editor resource
