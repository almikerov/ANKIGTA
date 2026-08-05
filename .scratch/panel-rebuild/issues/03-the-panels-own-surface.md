# 03 — The panel's own surface

**What to build:** everything the panel does badly as a piece of interface. One
ticket because it is one file set — `app.js`, `index.html`, `styles.css`,
`panel.lua` — and doing it in two passes means reading all of it twice and
merging the halves.

## Every control is drawn in the page

Clicking a dropdown anywhere but the arrow shows nothing, and that is true of
every `<select>` on the page: the deck, the Cards/Notes switch, and every choice
row in Settings.

The first guess was that the rows are rebuilt on every state push and take the
open popup with them. That is worth fixing on its own but it is not this. A
`<select>` opens a **native** popup, and the panel has nowhere to put one: MTA
blits CEF's popup surface only while it fits inside the browser rectangle and
drops it whole otherwise, so the list vanishes exactly when it grows. The page is
rendered offscreen into a game window; an `<input type="color">` hit the same wall
and became a text field with a swatch. A dropdown needs the same answer — the list
is drawn inside the page, in HTML, like every other part of this panel.

Every one of them, not only the broken-looking ones. Two dropdowns where one is
native and one is drawn would look and behave differently for no reason a player
could name. There is one drawn list to follow already: the deck picker's
`.picklist` / `#deck-menu`.

**A colour is chosen the same way.** Ticket 04 needs a colour picker and ticket 06
needs another; both are the same problem as the dropdown and get the same answer
here, once, rather than twice later.

## The edit pane does not come and go

The pane that edits the selected entity is hidden until a row that has one is
selected, so the right-hand side of the panel jumps as the player moves down the
list. It stays on screen, and says why it is empty when it is.

## A field that inherits a global shows the global

An override left unset is drawn as an empty box today, on the reasoning that empty
means "whatever Settings says". It does not read that way: it reads as no value.
The field shows the value actually in force, shows that it is inherited rather
than chosen, and clearing it goes back to following.

## The list stops fighting the player

**One click points the camera.** Focusing a row is a double-click today and the
single click before it only selects. But selecting a row and looking at it are the
same intention almost every time: the reason to select a row is to decide
something about the thing it names, and that decision needs the thing on screen.
So a click does both — and because "almost every time" is not "every time", a
client setting turns it off.

**The list answers the arrow keys.** A list reachable only by pointing gets slower
the longer it is, and this one is meant to grow. Up and down move the selection;
the selection stays in view as it moves. This is what makes the setting above
worth having and what makes it necessary: arrowing through fifty rows with the
camera flying to each is not a way to read a list.

**A renamed Map Entity still says what it was.** The cosmetic name replaces the
model name, which is the point — but it also hides the only thing connecting the
row to what the player sees in the Map Editor. The row shows the original
alongside the given name, and the filter matches either.

**A ped is not `Ped skin N`.** Objects and vehicles read as themselves because MTA
can name them; peds read as a number because it cannot. Checked against the MTA
source: `CModelNames` holds the object table and the vehicle names for 400–610 and
no ped table at all, and no MTA API names a skin. A real name means shipping our
own id→name table.

## Two carried findings, both in these files

`tests/test_panel_page.py::test_saving_lives_with_the_fields_it_saves` reads
`index.html` as text and splits on `'id="inspector"'`, which
`docs/agents/lua-testing.md` forbids by name — rewrite it against behaviour or
delete it. `.inspector-actions` in `styles.css` is dead.

**Runs beside ticket 02.** That one is almost entirely server-side; the two share
`shared/locale.lua` and `shared/settings.lua`, both of which are tables each side
appends to. **This ticket merges first**, because it rewrites `panel.lua`,
`app.js` and `index.html` wholesale and 02 touches them in about ten lines —
re-applying ten lines onto a finished panel is work; re-applying a rewrite is not.
Do not merge to main yourself.

**Blocked by:** 01.

**Status:** ready-for-agent

- [ ] A dropdown opens on a click anywhere on it, not only on the arrow
- [ ] A choice can be made from it, and the choice reaches the server
- [ ] The deck, the Cards/Notes switch and every Settings choice behave alike
- [ ] No `<select>` is left on the page
- [ ] A colour can be chosen with a picker that works in the panel as rendered
- [ ] An unrelated state push does not close a menu that is open
- [ ] Typing in a settings field is not thrown away by an unrelated push
- [ ] The entity edit pane is on screen whether or not a row is selected
- [ ] With nothing selected it says so, rather than being blank
- [ ] A field with no override shows the global value in force
- [ ] It is visibly inherited rather than chosen
- [ ] Clearing a field goes back to inheriting, and does not store a copy
- [ ] A single click on a row points the camera at it
- [ ] A client setting turns that off, leaving the click to select only
- [ ] Up and down move the selection, and the selection stays on screen
- [ ] A renamed row still shows the name it had before
- [ ] The filter matches the original name as well as the given one
- [ ] A ped row reads as a name rather than as a skin number
- [ ] A skin with no name falls back to something honest, not to a wrong name
- [ ] The ped table is data, checked by a test, not a chain of `if`s
- [ ] `app.js` is exercised by tests for each of the above
- [ ] No test in `tests/test_panel_page.py` asserts on the text of a source file
