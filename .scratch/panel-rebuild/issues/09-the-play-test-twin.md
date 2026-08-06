# 09 — Linking during a play-test

**What to build:** an object the player is pointing at is linkable, even when
the editor is play-testing the map it lives in.

Reported item: `The entity was not changed: editor_play_test_map` on Link.

## Both copies exist at once, and the player is standing in the wrong one

Measured on the owner's running server with `editor_test` running. Every
authored element exists **twice**:

```
object (vgsSstairs04_lvs) (2)  ->  owner=editor_main  dimension=200
object (vgsSstairs04_lvs) (2)  ->  owner=editor_test  dimension=0
vehicle (Sentinel) (1)         ->  owner=editor_main  dimension=200
vehicle (Sentinel) (1)         ->  owner=editor_test  dimension=0
```

`editor_main` holds the map being edited, in the editor's working dimension.
`editor_test` holds the play-test copy, in dimension 0 — which is where the
player is while testing, and so is the copy they are pointing at.

`World.owningResource` walks the element's ancestors and answers `editor_test`,
`isPlayTestResource` says yes, and adoption refuses. **The refusal is correct
about the element and wrong about the intention.** The player is editing a map,
pressed Test, is looking at their object, and wants to link it.

## What ticket 02 already decided, applied one place further

02's follow-up settled that **a map is its identity, not the name of the
resource it loads from**: one document answers to `editor_dump` while unsaved,
`editor_test` while play-testing, and its own name afterwards, while the
`ankigtaMapId` written inside it never changes. Row matching was moved onto
identity. The *adoption* path was not.

The same rule finishes it: a play-test element is not a different entity, it is
the same entity seen from inside the test. It carries the same `id` and its
document carries the same `ankigtaMapId` as the working copy. Adopt against the
identity, and record the entity against the map that owns it — not against
`editor_test`, which will be rewritten on the next Test press.

**Refusing is still right where there is nothing else.** A play-test whose
document carries an identity no working copy answers to has no other copy to
adopt against, and a link made there would still point at something that stops
existing. That case keeps `editor_play_test_map`, and the reason should say
which of the two situations it is.

## The message, separately

`The entity was not changed: editor_play_test_map` puts a machine token in front
of a player. Whatever this ticket decides the behaviour is, the refusal a person
reads should be a sentence.

## What was read to build the fixture, and where

`mta-gta-reference-policy.md` asks for provenance where a source observation
decides something. Three did, and all three are in the harness rather than in
the resource.

Stock Map Editor, `[editor]/editor_main.zip` (zip entries dated 2026-06-13
12:55), read 2026-08-06T12:13Z:

- `server/saveloadtest_server.lua` —
  `sha256 45d0ac0e67f1063b614d1130c152ae27f27fb335b2acbaa34bf42add60fab375`.
  Test is `saveResourceCoroutine(TEST_RESOURCE, true, …)`: the ordinary save
  with `test = true`. And `createElementAttributesForSaving` writes the `id`,
  the EDF data fields, and **every** element data key `getMapElementData`
  hands it — which is why a stamp ANKIGTA wrote with plain `setElementData`
  reaches the play-test copy.
- `server/dumpxml.lua` —
  `sha256 d344369b874f636d3822bed03a3692365d9c9ac9c57d626f8055103501c0e6de`.
  `getMapElementData` drops the keys prefixed `me:` and `edf:`, so `me:ID`
  does not travel. `dumpMap` skips representations and anything parked in
  `DESTROYED_ELEMENT_DIMENSION`.

MTA source reference, read 2026-08-06T12:25Z:

- `Shared/mods/deathmatch/logic/luadefs/CLuaElementDefsShared.cpp` —
  `sha256 67c52e06d27778fd8d323cc22732076f770fb8e8ce35781c84f43f1c48fde544`.
  `GetElementData` falls through to `lua_pushboolean(luaVM, false)`, so a key
  that is not set answers **`false`**, never nil. It also reads the parent
  chain by default (`inherit = true`), which the harness still does not model.

## Found on the way, not fixed here

- **Adoption still writes a resource name where a map identity belongs.** 02's
  follow-up moved row *matching* onto identity; `adoptionRecord` still sets
  `mapId = resourceName`. So a map whose document carries an `ankigtaMapId`
  unequal to its current resource name refuses the first link on it —
  `preparePendingMapSave` compares the identity element against the row's
  `map_id` and answers `persistent_map_identity_conflict`. Reproducible
  outside a play-test, which is why it is not this ticket: give
  `editor_with_map_open` a `map_identity` in
  `tests/test_map_editor_play_test_twin.py` and every link on that map fails.
  The owner's `editor_dump.map` carries no identity today, so nobody is
  hitting it yet — 0ee572a records a day when it did.
- **`Locale.reasons` covers the panel's paths, not the store's plumbing.**
  Every code `server/main.lua`, `server/map_identity.lua`, `server/world.lua`
  and `server/teleport.lua` return — the four modules a notice comes out of —
  is worded, along with the store codes a panel button can surface. The
  seventy-odd left are backup, migration, connection-config and SQLite
  internals; the recovery window has words of its own for the ones it shows,
  and if one of the rest ever reaches a notice it is shown as a code, with
  `missing_reason` in the debug log to say so.
- **`getElementData` inherits by default in MTA and not in the harness.**
  `CLuaElementDefsShared.cpp` reads the parent chain unless told otherwise, so
  in the game an EDF representation inherits its element's `ankigtaEntityId`
  even where nothing wrote one on it. The harness answers per element. Nothing
  here depends on the difference; something will.
- **Two maps can hand the editor the same element id.** `object (crate) (1)`
  is generated from the type and an ordinal, so a play-test of one map and a
  map open in the editor can collide on a name with no identity to tell them
  apart, and the walk would take the wrong object. Left alone deliberately:
  the editor suspends its own interface for the length of a test
  (`startWhenLoaded` returns early and `onClientRender` does nothing while
  `g_in_test` is set — `editor_main/client/main.lua`,
  `sha256 550cbcb838158e7f9e8565e406fea987a991a3784ed7fb3eb27ba49ba9039c20`,
  read 2026-08-06T13:10Z), so a map cannot be opened without stopping the
  test, which stops `editor_test` with it. The obvious second discriminator is
  wrong and was measured to be wrong: on the owner's server the play-test's
  Sentinel stands 80 m from the editor's, because somebody drove it, so
  matching on the transform would refuse every vehicle a test was used on.

**Blocked by:** None.

**Status:** done, unmerged — branch `claude/play-test-twin-c7c8a4`

- [x] An object linked while the editor is play-testing is adopted, not refused
- [x] It is recorded against the map that owns it, not against `editor_test`
- [x] The same object linked outside a play-test gives the same Map Entity
- [x] Linking the working copy and the play-test copy does not make two rows
- [x] A play-test document whose identity no working copy answers to is still
      refused, and says why in words a player can read
- [x] No refusal shown to a player is a bare token — every code the four
      modules a notice comes out of can return, and the store codes a button
      can surface. What is left is named under "Found on the way".
- [x] The stubs know that a play-test duplicates every element into another
      resource and dimension, so this cannot pass in tests and fail in the game
- [ ] **not run:** the same, in the game. Nothing here was deployed — the
      branch is left for the main chat to merge and deploy. What to look at:
      with a map open in the editor and Test pressed, aim at an object, pick a
      card and press Link. It should be taken in and say `Pending Map Save`
      rather than `The entity was not changed: editor_play_test_map`; stopping
      the test and saving with the editor's own Save should turn it into an
      Active Spatial Link on a row whose map is the map being edited.
