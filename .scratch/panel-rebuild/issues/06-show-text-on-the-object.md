# 06 — Show text: a Text Label on the Map Entity

**What to build:** a third Review Mode in which a linked Map Entity carries a
**Text Label** — a line from its card's note, drawn in the world — instead of
opening the review surface.

Reported item 16. Decided in a grilling session; the reasoning that does not
belong in a ticket is in ADR 0029, and `Text Label` is in the glossary.

**It stays its own ticket** while everything else in this wave was merged into
something bigger. It is a whole Review Mode with an ADR behind it — three
settings, a fallback rule, caching, wrapping, a draw cap — and folding it into
ticket 04's rebuild would make one ticket nobody finishes in a sitting.

**Nothing is presented and nothing is rated.** The card cannot be opened or
answered in this mode. ADR 0027 lets a *badly* presented card still be rated —
the player saw it. Here there is no presentation at all, and rating what was never
shown would write a repetition that did not happen. The panel says so where the
mode is chosen, rather than leaving the player to assume their reading counted.

**No ANKIGTA Session.** No filtered deck, no Exact Card Admission, no Review
Transaction, no progress counters. The label comes from the Spatial Link directly
and shows whether or not the card is due.

**Three things the player sets, each globally and again per link** — the same
shape the Activation Zone radius already has:

- **the note field** to show;
- **the colour**, chosen freely; a dark outline is always drawn, so a colour
  picked in daylight is still legible at night;
- **the size**.

The colour picker is ticket 03's and the colour rule kind is ticket 04's. Use
both; do not add a third way to choose a colour.

**When a field is missing or wordless.** The chosen field may not exist on this
note type, and a field holding only `<img>` or `[sound:]` has no words once the
markup is stripped. Both fall through to the first field that does have words. The
panel's row shows when a label is falling back, so an object showing something
other than what was asked reads as such rather than as correct.

**What is drawn.** Wrapped by words to a line limit, ellipsis past it — a silent
truncation reads as a whole answer. Turned to face the player: a label you have to
walk around is not a glance. A cap on how many labels are drawn at once, nearest
first; a cap applied quietly reads as "that is all there is".

**When it is visible.** One global distance setting, its own — not the Activation
Zone radius, which stays about opening cards and is unused in this mode. Not
affected by the speed threshold either: a label covers nothing and demands
nothing, and reading one while driving past is the point. It still sits under
ticket 04's outer draw-distance rule, which is a ceiling on everything drawn
rather than a second answer to this question.

**Where the text lives.** Cached in ANKIGTA's own store when the Spatial Link is
made, refreshed on connecting to the companion and when a note is saved through
the inspector. Anki stays authoritative (ADR 0017); this is a copy for display and
never a source of truth.

**Review Protection and Mute world do not apply** in this mode. There is no review
surface to protect and no review to be quiet for.

**It shares an entity with ticket 05's key prompt.** Both are text drawn on a Map
Entity, and one entity never shows both at once. 05 lands first and has no Text
Label to collide with, so this ticket owns the rule and the test for it.

**Reference, not a merge.** This was built once, on
`claude/show-text-on-object-51bd31`, starting at commit `f60905b`. That branch
merged the old trunk into itself twice and so carries tickets 06 and 07 of the
first wave with it; it is not being merged. Read it — `git show f60905b` — and
take what survives. It was never run by anyone, so nothing in it is evidence.

**Carried finding:** the card row's `label` key collides with **Text Label**,
which is a different thing entirely. Rename it here, where the collision starts to
matter.

**Blocked by:** 01, 03, 04, 05.

**Status:** done, not yet looked at in game

Manual pass: `docs/checklists/panel-rebuild-06-show-text.md`, `not run`. Every
item below is covered by an executed test except the two the harness cannot
reach, which are marked.

- [x] `Review mode: Show text` draws a Text Label on every linked entity in range
- [x] The review surface never opens and no rating is possible in this mode
- [x] The panel states that reading does not rate, where the mode is chosen
- [x] Field, colour and size each have a global default and a per-link override
- [ ] A dark outline keeps any chosen colour legible against a night sky and a
      white wall — **the outline is drawn and asserted; whether it is legible
      is a frame, and stays on the manual list**
- [x] A missing or wordless field falls through to the first field with words
- [x] A falling-back label is identifiable as such in the panel
- [x] Long text wraps by words to the line limit and ends in an ellipsis
- [x] Labels face the player — drawn in screen space at the projected point, so
      there is no orientation to get wrong; asserted from four sides
- [x] The label cap is applied nearest-first and the number dropped is reported
- [x] Labels show at the global distance regardless of speed
- [x] Labels are drawn with Anki closed, from the cache
- [x] Editing the note in the inspector updates the label
- [x] No filtered deck, admission or Review Transaction happens in this mode
- [x] An entity never shows a Text Label and ticket 05's key prompt at once
- [x] The card row's `label` key no longer collides with **Text Label** — it is
      `sortField` now, the name Anki and the companion both use

## What this ticket decided that the ticket did not say

**An entity cannot ask for "the first field with words".** Every override in
this resource is a NULL column, which is what makes ticket 05's sweep able to
clear them without a list — so an empty `Text Label field` on a row is the
override being cleared, not an override whose value is "". A player who wants
one object to fall through while the global names a field cannot say so. The
alternative was a spelling of "nothing of its own" that only these three
settings used, which is the shape 05 spent a ticket removing.

**`Text Label distance` stops at 150 m** because that is `world_marks.lua`'s
draw distance, and a setting that reads as saved and changes nothing is a
control arguing with the thing that obeys it. The two numbers are pinned
together by a test rather than by one file reading the other.

## Carried findings

- **`Follow Settings` on the *corona* colour has been broken since 05.** The
  picker sends `false` and the server's `proposed` only recognises `"inherit"`,
  so the write is refused as `settings.error.not_a_color`, the override stays,
  and the player is told "The entity was not changed: Enter a colour as
  #rrggbb". Reproduced on the server harness, not inferred.
  `tests/test_panel_page.py::test_a_colour_can_be_handed_back_to_settings`
  asserts the broken payload, so both it and `app.js` move together. One word
  in `app.js` and one line in that test. Ticket 06's own colour picker sends
  `"inherit"` and works; not fixed here because it is 05's control.
- **`%s`, `%a` and `%d` in Lua patterns answer about the C locale.** In a
  Windows-1252 one `isspace(0xA0)` is true, and 0xA0 is the last byte of many
  UTF-8 characters — `%s+` collapsing whitespace ate it and handed the renderer
  half a character. Fixed in `shared/text_label.lua` by writing every class out;
  nothing else in the resource does character-class work on user text today,
  but the next thing that does should know.
