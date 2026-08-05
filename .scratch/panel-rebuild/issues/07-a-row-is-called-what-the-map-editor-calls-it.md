# 07 — A row is called what the Map Editor calls it

**What to build:** show the name ANKIGTA already stores, instead of deriving a
worse one from the model number.

Reported items 38 and 39. They arrived as two and are one fix, and the fix is
smaller than either of them sounds.

## The name is already in the database

Checked against the owner's running server and a copy of the live store. Every
Map Entity's `entity_id` **is** the Map Editor's own name for it:

```
('editor_test', 'ped (1)',                       'ped',     0)
('editor_test', 'object (sw_hedstones) (1)',     'object',  12961)
('editor_test', 'vehicle (Clover) (1)',          'vehicle', 542)
('editor_dump', 'object (vgsSstairs04_lvs) (1)', 'object',  8615)
('editor_test', 'vehicle (Glendale Damaged) (1)','vehicle', 604)
```

The editor publishes it as element data under the key **`id`** — every element
carries one, `marker (corona) (1)` included — and adoption already copies it into
`ankigtaEntityId` and stores it. Nothing needs to be captured, migrated or added
to the schema.

**`me:ID` is not the key.** Only the editor's own EDF representation carries
`me:ID`, and only sometimes: of eleven elements in the running world, one had it.
`server/map_identity.lua:575` reads `me:ID`, which is why it works transiently and
for one case. If this ticket touches that read at all, `id` is the key that is
actually there.

## What is wrong is only the display

`entityLabel` in `client/panel.lua` starts from `tonumber(mapEntity.model)` and
builds a name out of the model:

- two peds of the same skin become `Ped skin 0` twice, telling nothing apart,
  while the editor beside them says `ped (1)` and `ped (2)`;
- a **marker** has no model at all, so it falls straight through to
  `Unnamed Map Entity` — even though the editor calls it `marker (corona) (1)`
  and markers are a supported type everywhere else in the resource
  (`shared/entity_types.lua`, the world scan, `pick_entity.lua`, `spatial.lua`,
  and the database's own CHECK constraint).

Show `entity_id`. Both defects go at once, for every type.

## A ped is not named by its skin, but is still found by it

Do **not** ship an id→name table for skins. The row says `ped (1)`; the skin does
not appear in it. This supersedes the plan ticket 03 originally carried.

The skin stays a **search** criterion: filtering by the skin number finds the ped.
If a name for the skin can be had at all, that is a second search criterion — but
it is not what the row is called.

Note what the editor already does for the types MTA can name: `object
(sw_hedstones) (1)` and `vehicle (Clover) (1)` carry the model name inside the id.
So showing `entity_id` keeps the model name where one exists and drops it where
none does, which is the behaviour asked for without a rule of our own.

## A marker is an ordinary Map Entity

Named like the rest, renamed like the rest, carrying the same per-link settings as
the rest. Once it has a name, nothing about a marker should need a special case.

## What ticket 03 already did

03 built the rename overlay: a given name replaces the default, the row still
shows what it was called before, and the filter matches either. That mechanism
does not change — this ticket changes what "what it was called before" *is*.

**Blocked by:** 03 — it owns `panel.lua`'s row and the filter, and this edits the
same function. No longer blocked by 02: there is no migration.

**Status:** ready-for-agent

- [ ] A row's default name is its `entity_id`, as the editor wrote it
- [ ] Two peds of one skin read as `ped (1)` and `ped (2)`
- [ ] A marker has a name, from the same place as every other type
- [ ] A marker can be renamed and carries the same per-link settings as the rest
- [ ] No schema change and no migration: the value is already stored
- [ ] An entity whose `entity_id` is not an editor name still reads honestly
- [ ] A given name still replaces the default, and the original is still shown
- [ ] The filter matches a ped by its skin number
- [ ] The filter matches a skin name where one can be had
- [ ] No skin id→name table is shipped for the purpose of naming rows
- [ ] Nothing is written into any editor resource
