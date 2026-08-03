# Panel usability 02 — Map Entity list, manual runtime checklist

Status: not run

The executable Lua tests cover map scoping, duplicate suppression, durable
renaming, distant camera movement without player movement, and refresh events.
Stock MTA CEF rendering and the readability of its visual
states still require a human observation pass. Use a disposable test map, not
an owner's map.

## List and selection

- Open the disposable map in Map Editor and press F7.
- Confirm each real Map Entity appears once, while editor representations and
  Map Entities deleted into working dimension + 1 do not appear.
- Confirm every row shows its cosmetic name plus XYZ and the GTA location;
  map/entity identifiers and a separate Runtime Instance column are absent.
- Select two different rows in turn. Confirm only the current row has the
  selected treatment and that it remains legible at 1280×720 and 1920×1080.

## Links and foreign maps

- With Anki and the companion connected, link one visible card to an entity on
  the current map and another card to an entity on a second disposable map.
- Return to the first map and open F7. Confirm the second card remains in the
  Card Picker even when it is absent from the current search page, and shows
  the second map's readable name in the danger colour. A current-map card must
  not carry that warning label.
- Stream an entity out, then remove one from the running disposable map.
  Confirm neither state adds a Runtime Instance warning to the row and no
  separate runtime column appears.

## Rename, camera, and live refresh

- Rename an entity, close F7, restart `ankigta`, and reopen F7. Confirm the new
  name survives and its existing card link is unchanged.
- Record the player's XYZ, double-click a row, and confirm the camera points at
  the entity while the player's XYZ does not change. Close F7 and confirm the
  prior camera target/matrix is restored.
- Reopen F7, select the same row, and press Teleport. Confirm F7 closes first
  and the player is then moved to the Map Entity.
- Link, unlink, and adopt an editor Map Entity. After each action, confirm both
  the entity list and Card Picker update without closing or reopening F7.

## Expected evidence

- Screenshots at 1280×720 and 1920×1080 showing selection, the foreign-map
  danger label, and unavailable text in the link column.
- Before/after player XYZ for both a nearby and a distant-row double-click, plus
  a note that the camera restored after closing F7.
- A short action log for rename/restart and link/unlink/adopt stating whether
  either list needed an F7 reopen.

## MTA source seam record

Read at 2026-08-03T17:49:26+03:00 from the repository's read-only local MTA
source reference. No version marker was available in the individually read
files.

- `Shared/mods/deathmatch/logic/luadefs/CLuaUtilDefs.cpp`, SHA-256
  `923ABF206A7BEFB07A3DDB9198F1F86679366E2052641E23FD1B58ED18E41145`:
  six numeric arguments and one numeric return for
  `getDistanceBetweenPoints3D`.
- `Client/mods/deathmatch/logic/luadefs/CLuaWorldDefs.cpp`, SHA-256
  `46EECDD67A4CFF2D692A9FDAC0771B9163FAD55E8FEFE9023A6B940AB88EC6E7`:
  XYZ plus optional cities-only flag and a string return for `getZoneName`.
- `Client/mods/deathmatch/logic/luadefs/CLuaCameraDefs.cpp`, SHA-256
  `C01BB5FB4725D64BB4E1A040624637B2EF58B2106ADF4F4989644092CB17AB9F`:
  camera matrix/target/interior getters and the matrix/interior setter
  signatures used by the focus-and-restore harness.
