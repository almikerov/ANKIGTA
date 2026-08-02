# 04 — Finding cards the Anki way, and choosing which ones count

**What to build:** the Card Picker searches the way Anki searches, and the
study session says plainly which cards it will use.

Covers the reported items 11, 15 and 18.

**Search takes an Anki expression.** `deck:Spanish tag:verb -is:suspended` and
the rest of what Anki understands, passed through rather than reinterpreted.
The companion already builds a query out of a phrase and a deck filter; this
lets a written expression through instead, and says clearly when Anki rejects
one. Beside it, a switch between showing notes and showing cards, as Anki has.

**`Allow early review` becomes `Review mode`**, with `Allow due` and `Allow
all`. The current setting is a boolean whose name describes neither of its
states: `Allow due` uses only cards the scheduler says are due, `Allow all`
takes them whether they are due or not. A third mode, `Show text`, is ticket 05
and is deliberately not part of this one.

**`Maps included in study` gets a name that says what it is** — whether the
entities of a map take part in the study session at all.

**Blocked by:** 01 — nothing here can be seen while the picker offers no cards.

**Status:** ready-for-agent

- [ ] An Anki search expression returns what Anki would return for it
- [ ] An expression Anki rejects is reported as rejected, not as no results
- [ ] The note/card switch changes what the result rows are
- [ ] `Review mode` offers `Allow due` and `Allow all`, and each does what it says
- [ ] An existing stored setting migrates to the mode it meant
- [ ] The per-map study setting is named for what it controls
