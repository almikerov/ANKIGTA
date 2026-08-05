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

**What a row is called by default is not this ticket.** The owner has since asked
for the Map Editor's own name — `ped (1)`, not `Ped skin 0` — and that is
ticket 07. **Do not ship an id→name table for ped skins**; the earlier plan to do
so is withdrawn. Build the rename overlay and the filter as described above and
leave the default name exactly as it is today; 07 replaces it underneath you.

## Two carried findings, both in these files

`tests/test_panel_page.py::test_saving_lives_with_the_fields_it_saves` reads
`index.html` as text and splits on `'id="inspector"'`, which
`docs/agents/lua-testing.md` forbids by name — rewrite it against behaviour or
delete it. `.inspector-actions` in `styles.css` is dead.

**Done.** The test was rewritten: the harness now parses the real `index.html`
into a tree, so "Save sits inside the editor" is asked of the rendered page
rather than of the file's text. `.inspector-actions` was already gone —
`003a3ee` took it out when the editor became its own column, and the finding
outlived the CSS it was about.

## Found while building this, and left alone

Neither is on the list above and neither was touched.

- **`edf:edfIsRepresentation` fails once per element per snapshot.** The live
  client log carries `panel.lua:468: call: failed to call
  'edf:edfIsRepresentation'` in runs of eight and sixteen, every time F7 is
  opened. The call is inside a `pcall`, so the panel behaves correctly and MTA
  logs the failed export anyway — which buries everything else worth reading in
  that log. It belongs to **02**, which already owns EDF representations and the
  stub that has to know about them.
- **The Next Card Indicator still draws an emphasised sphere at 3.**
  `client/indicator.lua` does `(current.sphereRadius or 3) * emphasis`, so an
  entity that follows the global is emphasised at the shipped default rather
  than at the radius actually in force. Unchanged by this ticket — it read 3
  before too — but it is the same mistake this ticket removed from the panel,
  and **04** owns what ANKIGTA draws into the world.

**Runs beside ticket 02.** That one is almost entirely server-side; the two share
`shared/locale.lua` and `shared/settings.lua`, both of which are tables each side
appends to. **This ticket merges first**, because it rewrites `panel.lua`,
`app.js` and `index.html` wholesale and 02 touches them in about ten lines —
re-applying ten lines onto a finished panel is work; re-applying a rewrite is not.
Do not merge to main yourself.

**It did not stay out of 02's files, and could not have.** "Clearing a field goes
back to inheriting, and does not store a copy" is on the list above, and the only
place a copy can be *not* stored is the store: `map_entity_metadata.radius` is NOT
NULL, so there was nowhere to say "this entity has none". So `server/store.lua`
gains a nullable column beside it, a migration that fills it, and the write and
Change-History paths that carry it; `server/main.lua` gains the three-way answer
(a number, `false` for cleared, absent for "this message is not about the
radius"). 02 will have to rebase over that. The alternative was to tick the line
with a panel that shows inheritance it cannot store.

**And it found `Relink entity` broken on the trunk** while carrying the override
through it. `Store.relinkEntity` handed `historyTransaction` a raw Lua table where
every other caller hands it `historyTarget(...)`; `historySteps` binds that value
straight into a column, so the bind failed, the whole transaction rolled back, and
relinking answered `relink_transaction_failed` every time. Fixed here — a one-line
change and three tests — because the override could not be verified through a path
that never committed. It survived because the only two tests naming relink read
the function's *source text*.

**Blocked by:** 01.

**Status:** built on `claude/panel-surface-rebuild-c2722e`, green, not merged and
not deployed.

Ticked where a test holds the claim. Three are left unticked on purpose: their
words are about how something *appears*, nothing here renders a frame, and
`docs/agents/mta-gta-reference-policy.md` says an observed-runtime item stays
`not run` rather than being marked passed by the seam underneath it.

- [ ] A dropdown opens on a click anywhere on it, not only on the arrow —
      **not run.** The click is held by a test; that the list is then *visible*
      is not, and is the whole reason this ticket exists. See 1 below.
- [x] A choice can be made from it, and the choice reaches the server
- [x] The deck, the Cards/Notes switch and every Settings choice behave alike
- [x] No `<select>` is left on the page
- [ ] A colour can be chosen with a picker that works in the panel as rendered —
      **not run, and not runnable yet.** The picker is built and exercised, but
      nothing in the schema is a colour until ticket 04 adds one, so no colour
      control appears on a deployed panel and there is nothing for a person to
      open. 04 inherits this line.
- [x] An unrelated state push does not close a menu that is open
- [x] Typing in a settings field is not thrown away by an unrelated push
- [x] The entity edit pane is on screen whether or not a row is selected
- [x] With nothing selected it says so, rather than being blank
- [x] A field with no override shows the global value in force
- [x] It is visibly inherited rather than chosen
- [x] Clearing a field goes back to inheriting, and does not store a copy
- [x] A single click on a row points the camera at it
- [x] A client setting turns that off, leaving the click to select only
- [ ] Up and down move the selection, and the selection stays on screen —
      **half not run.** The keys move it and the page asks for the row to be
      scrolled to, both under test; whether the row is then on screen depends
      on a layout no harness here has.
- [x] A renamed row still shows the name it had before
- [x] The filter matches the original name as well as the given one
- [x] No id→name table for ped skins is shipped — ticket 07 owns the default name
- [x] `app.js` is exercised by tests for each of the above
- [x] No test in `tests/test_panel_page.py` asserts on the text of a source file

### What a person still has to look at

Open F7 on a deployed build and check:

1. **A list is visible when it opens** — over the rows below it, not clipped by
   them or by the panel's edge. The whole ticket exists because a list that
   opened could not be seen, and the first build of this one put it back: an
   absolutely positioned list is clipped by any scroller between it and its
   containing block, and `.settings-rows` is one. It is placed against the
   window now and opens upwards where there is no room below. **Look at a choice
   row near the foot of Settings**, which is the case that was broken.
2. The deck list scrolls rather than running off the panel when a collection has
   more decks than fit.
3. The entity pane no longer moves the rest of the column when a row is selected
   or deselected.
4. An inherited radius reads as inherited — the box is dashed and greyed and
   says `following Settings` beside it.
5. Arrowing down a list longer than the panel keeps the selected row in sight.

And two worth *doing* rather than looking at, because they cross into the store.
**Both need an entity with no radius of its own**, and on the owner's database
that is not the same as an entity nobody has touched: the upgrade turns every
radius already stored into an override of itself, and four of the five metadata
rows there carry one. So empty the radius box on whichever row you pick first,
then:

- set the global Activation Zone radius in Settings and confirm that row follows
  it — the box shows the new number, marked as following;
- type a radius on that row, then empty the box again, and confirm it goes back
  to following rather than keeping today's number.
