# Panel rebuild 07 — a row is called what the Map Editor calls it

Status: not run

This checklist requires a separately authorized MTA runtime. It is not executed
by repository implementation or review work. Everything a machine can answer is
already answered by `tests/test_panel_map_entity_list.py` and
`tests/test_f7_entity_filter.py`; what is left here is what needs a person to
have the Map Editor and F7 open side by side and compare two lists of words.

**The owner's database is empty — zero Map Entity.** So the first three steps
are what puts anything in it. Nothing below can be checked against rows that are
already there.

## The two lists agree

1. Open the Map Editor and place **two peds of the same skin**, one **object**,
   one **vehicle** and one **marker**. The editor's own list calls them `ped
   (1)`, `ped (2)`, `object (<model>) (1)`, `vehicle (<model>) (1)` and `marker
   (corona) (1)`.
2. Leave the editor and open F7. Each of the five is offered as `Not adopted`,
   under exactly the name the editor gave it. **The marker is one of them** —
   before this ticket it read `Unnamed Map Entity`.
3. Name one of them, or give it a radius, so it is taken into the store. It
   keeps the same name in the list.
4. The two peds read as two different rows — `ped (1)` and `ped (2)`, not `Ped
   skin 0` twice.
5. The object's and the vehicle's rows carry the model name **inside** the
   editor's id, because that is where the editor put it. Nothing says `Infernus`
   on its own line.

## A marker is an ordinary Map Entity

6. Select the marker. The edit pane fills the way it does for an object: a name,
   a radius, `Show corona`, a corona colour and opacity, an activation type and
   key.
7. Rename it. The row shows the new name, with `originally marker (corona) (1)`
   under it.
8. Give it a radius and turn its corona on. A corona appears on the marker in
   the world, and the Activation Zone works when you walk into it.
9. Link a card to it and confirm the card opens.

## Searching still finds what the row no longer says

10. Type the **skin number** of one of the peds into `Search Map Entity`. That
    ped is found. (MTA has no name for a ped skin at all — there is no ped table
    in `CModelNames` — so the number is the only handle, and no lookup table is
    shipped to invent one.)
11. Type the **model name** of the object or the vehicle — `Infernus`, or
    whatever the editor put in its id. It is found.
12. Type the name you gave the marker in step 7. It is found. Type `marker
    (corona) (1)`. It is found too.

## Nothing else moved

13. Confirm the Map Editor's own list is unchanged: the ids it shows are the ids
    it showed before, and no ANKIGTA field has appeared in its property pane.
14. Save the map from the editor and reload the server. The rows come back under
    the same names.
15. Read `clientscript.log` after opening F7 on a map with peds and markers in
    it. There is **no** `Expected valid model ID` warning — a name derived from
    the model produced one per ped per snapshot.

## What to record

For each step: what you did, what you saw, and — where it did not match — a
screenshot and the matching lines from `clientscript.log` and `server.log`.

## MTA source seam record

Read at 2026-08-06T01:40:36+03:00 from the repository's read-only local MTA
source reference. No version marker was available in the individually read
files. These settle which model names MTA can be asked for, and what asking
about one it cannot answer costs — which is what `modelSearchTerms` in
`client/panel.lua` and the sandbox doubles are built on.

- `Client/mods/deathmatch/logic/CModelNames.cpp`, SHA-256
  `F1892D490314AE9835A014C13FC16E4FF96B35C18E64D68D4D219B108E23525D`:
  `InitializeMaps` fills `ms_ModelIDNameMap` from `bigFOTable` (objects), from
  `CVehicleNames` for 400–610, and from the clothes tables. **No peds.** So MTA
  has no name for a ped skin, and the row cannot be headed by one.
- `Client/mods/deathmatch/logic/luadefs/CLuaEngineDefs.cpp`, SHA-256
  `7C2801BCFECE19DBC6DB6DBAFF4A364BF3DFEB2F4CAAFF540ED3839B22FEE5BF`:
  `EngineGetModelNameFromID` returns `false` for an id `CModelNames` does not
  hold **and** calls `LogCustom` with `Expected valid model ID at argument 1`.
  That is the warning-per-ped-per-snapshot, and the reason only object and
  vehicle are asked.
- `Client/mods/deathmatch/logic/luadefs/CLuaVehicleDefs.cpp`, SHA-256
  `C4E1B8BC2B944A99007AB26CB0F3CF7519717D5171322DAE575662403C46B17F`, and
  `Client/mods/deathmatch/logic/CVehicleNames.cpp`, SHA-256
  `22EB108BF6D5CF67C5B9A986090571D00C243D8D0B15923331BD3B1405BF46C6`:
  `getVehicleNameFromModel` indexes `VehicleNames[model - 400]`, answers `false`
  outside the range, and logs nothing for an id it does not know. That is the
  `getVehicleNameFromModel` double in `tests/lua/sandbox.py`.

## Stock Map Editor seam record

Read at 2026-08-06T01:40:36+03:00 from the owner's installed stock Map Editor,
read-only, extracted to the OS temporary directory and deleted afterwards. This
is where the name a row is now headed by comes from.

- `[editor]/editor_main.zip!server/IDhandler.lua`, SHA-256
  `1BDD0519551E9D8F0189C848692F561D04E123CA80AE3F0E1CDE921BB6324B3A`:
  `assignID` builds `<type> (<named category values>) (<n>)` — hence `ped (1)`,
  `object (sw_hedstones) (1)`, `marker (corona) (1)` — and writes it four ways
  at once: `setElementID`, and element data `id`, `me:ID` and `me:autoID`. The
  `setElementID` is the one ANKIGTA's adoption reads, and MTA fills the same
  element id from the `<ped id="...">` of a saved `.map`, which is why the name
  survives the editor being closed.
- `[editor]/editor_main.zip!server/synchronization.lua`, SHA-256
  `503E594FD49C204BB9280DB932D9018117C493FAD50E5E83E33AE0DB71EED1EE`:
  `syncID` keeps all four in step when the player renames an element, so the
  element id never falls behind what the editor's list shows.

## Live-server measurements

Taken through `tools/devserver/` on the owner's running server on 2026-08-06,
and each one is a test in this repository rather than a note:

- `getElementModel(marker)` → `false`, `getElementRotation(marker)` → `false`,
  `getElementID(marker)` → `""` for a script-created marker. Pinned by the
  `getElementModel` / `getElementRotation` doubles in `tests/lua/sandbox.py`.
- `setElementID(element, id)` does **not** put anything in
  `getElementData(element, "id")`; the editor writes both separately. This is
  what makes `getElementID` — not the `id` element data — the thing adoption can
  read from a `.map`-loaded element with no editor open.
