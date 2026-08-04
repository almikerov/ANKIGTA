# 03 — Every control the panel owns is drawn in the page

**What to build:** the panel's own controls, made to work the way the panel is
rendered — and made to say what they are showing.

**A dropdown opens and can be chosen from.** Today clicking anywhere but the
arrow shows nothing, and that is true of every `<select>` on the page: the deck,
the Cards/Notes switch, and every choice row in Settings.

The first guess was that the rows are rebuilt on every state push and take the
open popup with them. That is worth fixing on its own but it is not this. A
`<select>` opens a **native** popup, and the panel has nowhere to put one: MTA
blits CEF's popup surface only while it fits inside the browser rectangle and
drops it whole otherwise, so the list vanishes exactly when it grows. The page
is rendered offscreen into a game window; an `<input type="color">` hit the same
wall and became a text field with a swatch. A dropdown needs the same answer —
the list is drawn inside the page, in HTML, like every other part of this panel.

Every one of them, not only the broken-looking ones. Two dropdowns where one is
native and one is drawn would look and behave differently for no reason a player
could name. There is already one drawn list to follow: the deck picker's
`.picklist` / `#deck-menu`.

**The edit pane does not come and go.** The pane that edits the selected entity
is hidden until a row that has one is selected, so the right-hand side of the
panel jumps as the player moves down the list. It stays on screen, and says why
it is empty when it is.

**A field that inherits a global shows the global.** An override left unset is
drawn as an empty box today, on the reasoning that empty means "whatever
Settings says". It does not read that way: it reads as no value. The field shows
the value that is actually in force, and shows that it is inherited rather than
chosen — and clearing it goes back to following.

This is the half of the same idea that ticket 08 completes: this one is one link
reading its inherited value, that one is every link being put back to inheriting
at once.

**Two carried findings, both in this ticket's files.**
`tests/test_panel_page.py::test_saving_lives_with_the_fields_it_saves` reads
`index.html` as text and splits on `'id="inspector"'`, which
`docs/agents/lua-testing.md` forbids by name — rewrite it against behaviour or
delete it. `.inspector-actions` in `styles.css` is dead.

**Why third.** Settings cannot be operated at all today, and tickets 04, 05, 07
and 08 each add a setting that has to be judged on that screen.

**Blocked by:** 01.

**Status:** ready-for-agent

- [ ] A dropdown opens on a click anywhere on it, not only on the arrow
- [ ] A choice can be made from it, and the choice reaches the server
- [ ] The deck, the Cards/Notes switch and every Settings choice behave alike
- [ ] No `<select>` is left on the page
- [ ] An unrelated state push does not close a menu that is open
- [ ] Typing in a settings field is not thrown away by an unrelated push
- [ ] The entity edit pane is on screen whether or not a row is selected
- [ ] With nothing selected it says so, rather than being blank
- [ ] A field with no override shows the global value in force
- [ ] It is visibly inherited rather than chosen
- [ ] Clearing a field goes back to inheriting, and does not store a copy
- [ ] `app.js` is exercised by tests for each of the above
- [ ] No test in `tests/test_panel_page.py` asserts on the text of a source file
