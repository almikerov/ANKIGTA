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

**Status:** built on `claude/map-editor-row-naming-55c9af`, green, not merged and
not deployed.

- [x] A row's default name is its `entity_id`, as the editor wrote it
- [x] Two peds of one skin read as `ped (1)` and `ped (2)`
- [x] A marker has a name, from the same place as every other type
- [x] A marker can be renamed and carries the same per-link settings as the rest
- [x] No schema change and no migration: the value is already stored
- [x] An entity whose `entity_id` is not an editor name still reads honestly
- [x] A given name still replaces the default, and the original is still shown
- [x] The filter matches a ped by its skin number
- [x] The filter matches a skin name where one can be had — **vacuously, and
      checked as such.** MTA has no name for a ped skin: `CModelNames` holds the
      object table, vehicles 400–610 and the clothes tables and no peds at all,
      so there is none to be had. `test_mta_has_no_name_for_a_ped_skin_to_be_
      searched_by` asserts both MTA calls refuse a skin, so this is a measured
      absence rather than an omission. Objects and vehicles do have names, and
      the filter matches those.
- [x] No skin id→name table is shipped for the purpose of naming rows
- [x] Nothing is written into any editor resource

Every line above is held by a test. The two that are about what a person *sees*
— the panel's list and the editor's list saying the same words, side by side —
are `not run`: nothing here renders a frame, and
`docs/agents/mta-gta-reference-policy.md` says an observed-runtime item stays
`not run` rather than being ticked by the seam underneath it.
`docs/checklists/panel-rebuild-07-map-editor-row-naming.md` is that pass, and it
starts by putting five things in the editor, because the owner's database is
empty.

## What it turned out to be

The display half was the smaller half.

`modelName` in `client/panel.lua` became `editorName`, which returns
`mapEntity.entityId` and derives nothing. What the model can still say went into
`modelSearchTerms`, which the **filter** reads and the row never does: the skin
number, and the name MTA can put to a car or an object. The rename overlay 03
built is untouched — only what "the name it had before" *is* has changed.

The other half was not display. **`Store.adoptMapEntity` listed `object`,
`vehicle` and `ped` by hand** — the one place in the resource where a marker was
not a Map Entity. The schema's CHECK has admitted markers since version 5, the
world scan finds them, Pick Entity offers them and the spatial poll follows
them; adoption refused, so a marker could be pointed at, offered as `Not
adopted`, and never taken in. Naming one was impossible because there was no row
to write the name on. That gate now reads `ANKIGTA.EntityTypes.supported`.

So this ticket does change the store's behaviour, and the owner should know it:
**a marker will now get a row in the live database where before it could not.**
There is no migration and no schema change — `map_entities` already accepts one.
A marker has no model at all (`getElementModel` answers `false`, measured on the
running server), and the NOT NULL `model` column stores that as 0.

Two doubles in `tests/lua/sandbox.py` were made faithful along the way:
`getElementModel`/`getElementRotation` answer `false` for a marker the way the
real server does, and `getVehicleNameFromModel` exists at all. The provenance for
each — MTA source files, the stock editor's `IDhandler.lua`, and the live
measurements — is recorded in the checklist above.

**One near miss worth naming.** The first build guarded the search terms with
`model > 0`, meaning to say "a marker has no model". Skin **0 is CJ**, and it is
the skin every ped in the ticket's own store dump wears — so that guard made
exactly those peds unfindable by their number. It is keyed on the type now, and
`test_skin_zero_is_a_skin_like_any_other` holds it.

## Found while building this, and left alone

Neither is on the list above, and neither was touched.

- **The `.map` read-back does not know about markers.** `readBackSavedMap` and
  `readMapFileIdentities` in `server/map_identity.lua` walk `<object>`,
  `<vehicle>` and `<ped>` children only, and `recoverPersistedCollisions`
  iterates the same three by hand. A card linked to a marker *while the map is
  open in the editor* goes to `Pending Map Save` and the read-back can never
  verify it, because the saved `<marker>` is not counted. This gap predates the
  ticket — `test_every_map_entity_type_can_be_linked` reaches it today with a
  seeded row — but adoption refusing markers is what made it unreachable through
  the product, and this ticket removes that. It belongs to **02**, which owns
  map identity and the editor.
- **`me:ID` is still read in nine places.** `server/main.lua:402`,
  `server/map_identity.lua:735` and `:1017`, `server/store.lua:2636`, `:2665`
  and `:2909`, `server/world.lua:327` and `:401`, and `client/panel.lua:495`.
  This ticket established that `id` is the key that is actually there and
  `me:ID` is only on the editor's own EDF representation, so most of those reads
  answer for one case out of eleven. None of them is the display, so none was
  touched. Each is an identity *match*, which is a different question from what
  a row is called.
