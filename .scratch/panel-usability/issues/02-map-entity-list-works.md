# 02 — The Map Entity list shows what is here, once, readably

**What to build:** the left column becomes usable. It lists the objects of the
map the player is actually on, each exactly once, described the way a person
would describe them, and it keeps itself current.

Covers the reported items 0, 1, 2, 2.5, 3, 7, 19 and 20.

**Every object appears once.** Objects currently appear twice. The candidate
scan has no `edfIsRepresentation` guard while `validatePickEntity` does, and
with the `editor` resource running every editor-managed object exists twice —
the real element and the editor's representation. The Map Editor also parks
deleted elements in the working dimension plus one; the prior resource knew
this and skipped them.

**Only this map.** Entities belonging to other maps are not listed at all. A
*card* linked to an entity on another map is still shown in the Card Picker,
with that map's name on the card in the danger colour, so a link that points
somewhere else is visible rather than silently missing.

**A row a person can read.** The player can give any entity a name of their
own — cosmetic only, it changes no identity and no stored key. The line beneath
carries the XYZ position and, where it fits, the name of the game location. The
map/entity pair is not on the row: it is an identifier, not a description.

**The Runtime Instance column and warning go.** A row remains usable from its
stored Map Entity identity and authored position even when no Runtime Instance
is currently streamed near the player.

**The selection is visible**, and double-clicking a row points the camera at
that entity the way the prior resource did — distinct from Teleport, which
moves the player.

**The lists refresh themselves** when entities or cards change, rather than
waiting for the panel to be closed and reopened.

**Blocked by:** None — can start immediately.

**Status:** resolved

- [x] Each object appears exactly once with the Map Editor running
- [x] Elements in the editor's deleted dimension are not offered
- [x] Only entities of the current map are listed
- [x] A card linked to another map names that map on the card, in the danger colour
- [x] An entity can be renamed, and the name survives a restart
- [x] The sub-line reads as coordinates and a location, not as identifiers
- [x] A gone or unstreamed Runtime Instance adds no warning to the row
- [x] The selected row is visibly the selected row
- [x] Double-click points the camera at the entity without moving the player
- [x] Linking, unlinking or adopting updates both lists without reopening F7

## Comments

Implemented the current-map entity list, representation/deleted-dimension
suppression, durable cosmetic names, readable position/location rows, foreign
map card warnings, camera focus with restoration, and event-driven list
refreshes.

The live development client exposed an incremental-reload failure in which the
new `panel.lua` arrived before the new shared entity-type module. That stopped
the script at load time and left F7 unbound. The panel now installs the same
canonical entity-type values as a reload-safe fallback, covered by a regression
test that loads the panel before the new shared script.

After live review, the Runtime Instance availability warning was removed rather
than moved into the link column. Camera focus now uses an unstreamed Runtime
Instance when present and falls back to the stored authored position when the
client has no element at all.

Verification: 190 passed, 1 skipped across the ticket's affected Lua/UI test
modules. The full repository suite was started but exceeded the 120-second
command budget without a verdict. The stock MTA CEF/readability observation
check remains explicitly `not run` in
`docs/checklists/panel-usability-02-map-entity-list.md`.
