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

**Status:** resolved

- [x] An Anki search expression returns what Anki would return for it
- [x] An expression Anki rejects is reported as rejected, not as no results
- [x] The note/card switch changes what the result rows are
- [x] `Review mode` offers `Allow due` and `Allow all`, and each does what it says
- [x] An existing stored setting migrates to the mode it meant
- [x] The per-map study setting is named for what it controls

## Comments

### 2026-08-04 — implementation

The search form takes an Anki expression and passes it through untouched, with
Anki's notes/cards switch beside it. A note stands for its first card, so
linking still names a card, and a page of notes costs one read per row on the
page. `SearchError` became `search_rejected` with Anki's own sentence, told
apart from a dead link at the gateway by the envelope the companion wrote.

Two defects were found in the path this ticket owns and fixed with it:

- **A search of every deck was thrown away.** `deckFilter: null` decodes to nil
  in MTA, not `false`, and the payload validator admitted only `false` — so the
  whole answer was discarded and reported as `protocol_error` whenever no deck
  was chosen. Ticket 01 verified the unfiltered search at the HTTP endpoint;
  the gateway hop was not covered, and that is where it died.
- **The deck filter was escapable by an `or`.** Anki binds implicit `and`
  tighter than `or`, so a filter plus `tag:verb or tag:noun` returned cards from
  every deck. Unreachable while the panel could only send an empty query.

Two things beyond the literal wording of the ticket, both deliberate:

- **The per-map setting became a row per map.** The ticket asks for a name.
  Built from the schema like everything else, the setting rendered as one
  global switch whose writes went to a stored value nothing reads, so putting
  `This map's entities take part in study` on it would have made the name a
  lie rather than a fix. The plumbing for `mapId` already existed on both sides.
- **`Review mode` overrides ADR 0024's naming.** That ADR names the setting
  `Разрешить досрочное повторение`. Its *behaviour* is unchanged and its default
  still stands: `Allow due` is the default and a Not-due Card is Preview only.
  Only the name is superseded. Flagged rather than silently overridden;
  `docs/design/confirmed-baseline.md` and `docs/design/preliminary-spec-audit.md`
  keep the old name as the historical records they are.

Not done, and why: the ticket's summary line says "the study session says
plainly which cards it will use". Read against the paragraph that expands it
and against the acceptance list, that is delivered by naming the two modes —
not by a new line in the top bar naming the active mode, which the ticket
nowhere describes. Worth raising if the owner meant the latter.

Schema 6 migrates a stored `allowEarlyReview` to the mode it meant, in both
JSON shapes the store has written, and tolerates a database from before the
settings table existed.

Full suite: 1229 passed, 1 skipped. `tests/test_mta_ticket_02.py` (14 tests)
fails on this machine before and after this work — it drives a real MTA server
and the installed build is not the one it expects. Strict mypy: clean.

Standards review: 3 documented-standard findings and 4 smells, of which 5 were
fixed and 2 declined (a shared `"cards"` literal across a wire protocol; one
commit covering the ticket's several parts). Spec review: 4 findings, of which
2 were fixed as real defects and 2 answered above.
