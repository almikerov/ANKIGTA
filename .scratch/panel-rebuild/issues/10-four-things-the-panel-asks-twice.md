# 10 — Four things the panel asks twice

**What to build:** four corrections to controls tickets 03, 04 and 05 built.
One ticket: the same `app.js` / `index.html` / `styles.css` / `panel.lua`, and
three of the four are the same complaint — a control that takes two motions
where it should take one.

## `Follow Settings` becomes one `Restore global`

An override is cleared in two different ways today: a `Follow Settings` entry
inside each drawn menu, and a `picker-clear` button beside the colour. Two
spellings of one idea, and the menu entry makes "stop having an opinion" look
like one of the values a setting can hold.

One button beside the field, named for what it does. It is the single-entity
half of the sweep ticket 05 built; the two should read as the same action at
two scales, not as two unrelated controls.

## `Activation key` is bound, not chosen

It is a dropdown over every key MTA can name. A player who wants `E` scrolls a
list of a hundred entries looking for it, and the list is the wrong shape for
the question anyway: the answer is a key, and the way a person says which key
is to press it.

So: a control that listens for the next key and takes it. The refusal ticket 05
built stays — a key ANKIGTA already answers to is still refused with a reason,
now at the moment it is pressed. `Settings.bindableKeys` stays as what a
captured key is validated against, so a key MTA cannot name is refused rather
than stored.

## The settings panel sits beside the list, not on top of it

> **Which panel.** Built as the *Settings screen* first, which was wrong: the
> owner meant the pane that edits the selected Map Entity. The Settings screen
> is back exactly as it was, and what follows describes the pane.

The entity pane grew with every ticket in this wave and now covers the Map
Entity list. That is the wrong shape twice over: the list is what the panel is
for, and these fields are changed *while looking at* the row they belong to.

It goes to the left of the entity list, as its own column — the way the card
editor already does it, so the window is wider rather than a third column being
fitted inside the old width and every column left cramped. Unlike the editor's
it never folds away: a row is selected in order to be edited, so the pane that
edits it has nothing to wait for.

## `Apply to all` sits on the field's row

It is under the field it belongs to, so each setting takes two rows and the
screen above is twice as tall as it needs to be. On the row, beside the field.

## `Show radius` is a checkbox

Two states, offered as a button reading `On` or `Off` — a control whose state
has to be read as a word before it can be understood. A tick is the one control
every player already knows. Nothing else on the pane can be one: every other
field there has a third answer, "whatever Settings says".

**Blocked by:** None. Runs beside ticket 09, which is server-side; they share
`shared/locale.lua` and nothing else.

**Status:** done, not yet deployed

- [x] One `Restore global` control clears an override, everywhere one can be set
- [x] `Follow Settings` is gone from the drawn menus and from the colour picker
- [x] An override cleared this way follows the global again, and does not store
      a copy of today's value
- [x] `Activation key` is set by pressing a key
- [x] A key ANKIGTA already answers to is refused, with the reason, on the press
- [x] A key MTA cannot name is refused rather than stored
- [x] The globally set key and a per-link key are both set this way
- [x] The entity pane is a column beside the entity list, not over it
- [x] The entity list stays readable while the pane is open
- [x] The panel is wider for it rather than the other columns narrowing
- [x] The pane never folds away
- [x] The Settings screen is exactly the screen it was
- [x] `Show radius` is a checkbox
- [x] `Apply to all` is on the same row as the field it applies
- [x] `app.js` is exercised by tests for each of the above

## What only a person can see

The harness runs `app.js` in Node against the real `index.html` parsed into a
tree, so "this control exists, in this part of the page, and sends this action"
is checked. It does not lay anything out, so these stay for the deploy:

- Three columns abreast — the pane, the list, the cards — and four with the
  editor out, at 1580 and 2117, on the owner's resolution.
- `Restore global` beside nine fields down a 400-wide column without the rows
  wrapping badly.
- `Apply to all` landing in the row's third grid column rather than under the
  field. The harness has no layout engine, so what a test can see is that the
  control is appended straight after the field rather than after the sentence
  that belongs below it; the column it lands in is the stylesheet's.

The first of these was asked for on the running server and could not be
answered: `mcp__mta-agent-devtools__status` reports `clientReachable: false`
with no player connected, and the server is not running this build. Both are
needed — the branch deployed and the owner in game — and neither is this
chat's to arrange. **Still unchecked live.**

## Found while doing it, not fixed

- **The `key_in_use` refusal cannot be reached with `F7` in the running game.**
  The panel never calls `guiSetInputMode("no_binds")`, so MTA keeps firing
  `bindKey` handlers while the page has focus: pressing `F7` into the capture
  control closes the panel rather than arriving as a press. The refusal is
  right and is tested — it reads the reserved list rather than naming `F7`, so
  it holds for whatever the list gains — but the one key on it today can only
  be refused in a test. `escape`, the other one, cancels the capture on purpose.
  Fixing it means deciding what every game bind does while the panel is open,
  which is its own ticket.
- The number, text and colour boxes on the entity pane still take an emptied
  value as "follow Settings again", beside the new button that says the same
  thing. Kept: emptying a box has to mean *something*, and the hints
  (`f7.radiusClearHint` and its two neighbours) already promise it. It is one
  idea with two spellings, which is the shape this ticket was about.
- `test_ui_layout.py`'s placement tests opened the panel through the Settings
  door, so they were measuring whichever window that door happened to show.
  Changed here to open it by its key, because the change is this ticket's.
- The per-map leftovers this ticket was told to clean out of `app.js` —
  `heading`, `note`, `settingClass`'s `per-map`, `mapId` on the wire — were
  already gone. Ticket 03 removed them and left the tests that hold them gone.
- **UI Scale has almost no headroom left for the panel.** It is 1580 wide, and
  `Layout.size` fits every surface inside the screen — so on 1920 a scale past
  about 1.2 does nothing to it. It still scales the HUD and Review Mode. The
  alternative was squeezing the three columns instead of widening the window,
  which is the thing this ticket forbids, so the trade is deliberate; whether
  1.2 is enough headroom is the owner's call and would be its own ticket.
- **A drag was remembered at one position and drawn at another** whenever the
  panel was wider than its declared width. `Layout.moveTo` clamps and stores
  against the width the layout was told; the browser is drawn at whatever
  `panelRect` works out. With the editor open — the only case before this — the
  two differed by half the extra width, so grabbing the bar made the panel jump.
  Fixed here rather than filed, because making the pane's column permanent would
  have made it the normal case: the pane's room is in the panel's *declared*
  width, and only the editor's share is added on top. Ticket 11 rewrites both
  halves of this and should know the trap is there.
