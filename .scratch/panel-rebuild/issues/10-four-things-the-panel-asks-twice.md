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

## Settings sits beside the list, not on top of it

The Settings screen grew with every ticket in this wave and now covers the Map
Entity list. That is the wrong shape twice over: the list is what the panel is
for, and a setting is usually changed *while looking at* what it affects.

It goes to the left of the entity list, as its own column — the way the card
editor already does it. The panel widens for it the same way
(`EDITOR_WIDTH_SHARE` in `client/panel.lua`), rather than a third column being
fitted inside the old width and every column left cramped.

## `Apply to all` sits on the field's row

It is under the field it belongs to, so each setting takes two rows and the
screen above is twice as tall as it needs to be — which is half of why Settings
now covers the list. On the row, beside the field.

**Blocked by:** None. Runs beside ticket 09, which is server-side; they share
`shared/locale.lua` and nothing else.

**Status:** ready-for-agent

- [ ] One `Restore global` control clears an override, everywhere one can be set
- [ ] `Follow Settings` is gone from the drawn menus and from the colour picker
- [ ] An override cleared this way follows the global again, and does not store
      a copy of today's value
- [ ] `Activation key` is set by pressing a key
- [ ] A key ANKIGTA already answers to is refused, with the reason, on the press
- [ ] A key MTA cannot name is refused rather than stored
- [ ] The globally set key and a per-link key are both set this way
- [ ] Settings is a column beside the entity list, not over it
- [ ] The entity list stays readable while Settings is open
- [ ] The panel widens for it rather than narrowing the other columns
- [ ] `Apply to all` is on the same row as the field it applies
- [ ] `app.js` is exercised by tests for each of the above
