# 01 — The companion offers decks and cards again

**What to build:** F7 with Anki running and connected shows decks in the deck
picker and cards in the Card Picker. Today it offers neither, so nothing about
linking, searching or studying can be judged.

Start by finding out why. The panel, the gateway and the companion each have a
place this can fail, and guessing at it has cost this project several rounds
already. The dev control channel (`tools/devserver`) can ask the running server
directly; the companion's own logs say what it answered.

Whatever the cause turns out to be, the fix carries a test at the seam that was
blind to it. Four bugs in a row in this project lived in the gap between real
MTA and its test doubles, and a fifth living in the gap between the companion
and its own is the same mistake wearing different clothes.

**Blocked by:** None — can start immediately.

**Status:** resolved

- [x] With Anki connected, the deck picker lists the collection's decks
- [x] A search with no deck filter returns cards
- [x] The cause is named in the commit message, not just the fix
- [x] A test fails without the fix and passes with it
- [x] Where no honest test seam exists, that is written down rather than faked

## Comments

### 2026-08-03 — implementation

The live companion search returned 934 cards but reported `deck.name = null`
and no deck list. Anki 26.05 returns `DeckNameId` records with `id` and `name`
attributes; the companion only recognised mappings, tuples and dictionaries.
The tuple-shaped test double hid that production API shape.

The agreed public seam was `POST /v1/cards/search`. The HTTP contract test was
red with an empty `decks` result before the fix and green after it. The
disposable real-Anki 26.05 harness then exercised the same endpoint against
`mw.col.decks.all_names_and_ids()`: it returned every collection deck, named
every returned card's deck and returned cards for an unfiltered search. The
evidence is under
`.scratch/panel-usability-ticket-01-anki-integration-runtime/evidence/`.

Cause-naming commit: `d143a0a fix(companion): accept Anki DeckNameId records`.
The devserver probe syntax repair is covered by an executable Lua 5.1 command
test. Target tests: 12 passed; strict mypy: passed; 308 baseline-independent
tests: passed. The full suite was run once, but the repository baseline fails
before this change because `MtaSandbox` calls the absent
`_install_export_globals`; that unrelated failure remains outside this ticket.

Standards review: 0 findings. Spec review: 0 findings.
