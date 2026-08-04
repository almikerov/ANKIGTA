# 05 — Show text: a Text Label on the Map Entity

> **Superseded.** This wave ran four lines in parallel and they did not join.
> The work continues one ticket at a time under `.scratch/panel-rebuild/`, where
> this ticket is `09-show-text-on-the-object.md`. Do not start from this file.

**Status:** superseded

**What to build:** a third Review Mode in which a linked Map Entity carries a
**Text Label** — a line from its card's note, drawn in the world — instead of
opening the review surface.

Reported item 16. Decided in a grilling session; the reasoning that does not
belong in a ticket is in ADR 0029, and `Text Label` is in the glossary.

**Nothing is presented and nothing is rated.** The card cannot be opened or
answered in this mode. ADR 0027 lets a *badly* presented card still be rated —
the player saw it. Here there is no presentation at all, and rating what was
never shown would write a repetition that did not happen. The panel says so
where the mode is chosen, rather than leaving the player to assume their
reading counted.

**No ANKIGTA Session.** No filtered deck, no Exact Card Admission, no Review
Transaction, no progress counters. The label comes from the Spatial Link
directly and shows whether or not the card is due.

**Three things the player sets, each globally and again per link** — the same
shape the Activation Zone radius already has:

- **the note field** to show;
- **the colour**, chosen freely; a dark outline is always drawn, so a colour
  picked in daylight is still legible at night;
- **the size**.

The settings schema has no colour rule kind yet; this adds one.

**When a field is missing or wordless.** The chosen field may not exist on this
note type, and a field holding only `<img>` or `[sound:]` has no words once the
markup is stripped. Both fall through to the first field that does have words.
The panel's row shows when a label is falling back, so an object showing
something other than what was asked reads as such rather than as correct.

**What is drawn.** Wrapped by words to a line limit, ellipsis past it — a
silent truncation reads as a whole answer. Turned to face the player: a label
you have to walk around is not a glance. A cap on how many labels are drawn at
once, nearest first; a cap applied quietly reads as "that is all there is".

**When it is visible.** One global distance setting, its own — not the
Activation Zone radius, which stays about opening cards and is unused in this
mode. Not affected by the speed threshold either: a label covers nothing and
demands nothing, and reading one while driving past is the point.

**Where the text lives.** Cached in ANKIGTA's own store when the Spatial Link
is made, refreshed on connecting to the companion and when a note is saved
through the inspector. Anki stays authoritative (ADR 0017); this is a copy for
display and never a source of truth.

**Review Protection and Mute world do not apply** in this mode. There is no
review surface to protect and no review to be quiet for.

**Blocked by:** 04 — the mode is the third value of the setting that ticket
creates.

**Status:** ready-for-agent

- [ ] `Review mode: Show text` draws a Text Label on every linked entity in range
- [ ] The review surface never opens and no rating is possible in this mode
- [ ] The panel states that reading does not rate, where the mode is chosen
- [ ] Field, colour and size each have a global default and a per-link override
- [ ] A dark outline keeps any chosen colour legible against a night sky and a white wall
- [ ] A missing or wordless field falls through to the first field with words
- [ ] A falling-back label is identifiable as such in the panel
- [ ] Long text wraps by words to the line limit and ends in an ellipsis
- [ ] Labels face the player
- [ ] The label cap is applied nearest-first and the number dropped is reported
- [ ] Labels show at the global distance regardless of speed
- [ ] Labels are drawn with Anki closed, from the cache
- [ ] Editing the note in the inspector updates the label
- [ ] No filtered deck, admission or Review Transaction happens in this mode
