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

**The Runtime Instance column goes**, and its meaning moves into the link
column: an entity whose element is gone or not streamed says so there, so a
missing object still reads as missing rather than as an ordinary row.

**The selection is visible**, and double-clicking a row points the camera at
that entity the way the prior resource did — distinct from Teleport, which
moves the player.

**The lists refresh themselves** when entities or cards change, rather than
waiting for the panel to be closed and reopened.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Each object appears exactly once with the Map Editor running
- [ ] Elements in the editor's deleted dimension are not offered
- [ ] Only entities of the current map are listed
- [ ] A card linked to another map names that map on the card, in the danger colour
- [ ] An entity can be renamed, and the name survives a restart
- [ ] The sub-line reads as coordinates and a location, not as identifiers
- [ ] A gone or unstreamed entity says so in the link column
- [ ] The selected row is visibly the selected row
- [ ] Double-click points the camera at the entity without moving the player
- [ ] Linking, unlinking or adopting updates both lists without reopening F7
