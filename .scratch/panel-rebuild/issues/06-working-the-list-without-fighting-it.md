# 06 — Working the list without fighting it

**What to build:** four things the Map Entity list asks of the player that it
should not.

**One click points the camera.** Focusing a row is a double-click today, and the
single click before it only selects. But selecting a row and looking at it are
the same intention almost every time: the reason to select a row is to decide
something about the thing it names, and that decision needs the thing on screen.
So a click does both — and because "almost every time" is not "every time", a
client setting turns it off for the player working down a list without wanting
the camera to chase them.

**The list answers the arrow keys.** A list of rows reachable only by pointing at
them gets slower the longer it is, and this one is meant to grow. Up and down
move the selection through the rows; the selection stays in view as it moves.
This is what makes the setting above worth having, and what makes it necessary:
arrowing through fifty rows with the camera flying to each is not a way to read a
list.

**A renamed Map Entity still says what it was.** The cosmetic name replaces the
model name in the row, which is the point — but it also hides the only thing
connecting the row to what the player sees in the Map Editor. The row shows the
original alongside the given name, and the filter matches either: searching for
the model name of a thing you renamed six months ago should find it, because the
model name is what you still remember it by.

**A ped is not `Ped skin N`.** Objects and vehicles read as themselves because
MTA can name them; peds read as a number because it cannot. This was checked
against the MTA source: `CModelNames` holds the object table and the vehicle
names for 400–610 and no ped table at all, and no MTA API names a skin. A real
name means shipping our own id→name table, which is what this asks for. It
belongs here because it is the same question as the one above — what a row is
called — and because a row nobody can identify is the reason the rest of this
ticket exists.

**Blocked by:** 01 — it adds a setting label and a column heading.

**Status:** ready-for-agent

- [ ] A single click on a row points the camera at it
- [ ] A client setting turns that off, leaving the click to select only
- [ ] Up and down move the selection through the list
- [ ] The selected row stays on screen as the selection moves
- [ ] A renamed row still shows the name it had before
- [ ] The filter matches the original name as well as the given one
- [ ] A ped row reads as a name rather than as a skin number
- [ ] A skin with no name in the table falls back to something honest, not to a
      wrong name
- [ ] The table is data, checked by a test, not a chain of `if`s
