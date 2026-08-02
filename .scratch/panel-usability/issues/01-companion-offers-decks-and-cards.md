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

**Status:** ready-for-agent

- [ ] With Anki connected, the deck picker lists the collection's decks
- [ ] A search with no deck filter returns cards
- [ ] The cause is named in the commit message, not just the fix
- [ ] A test fails without the fix and passes with it
- [ ] Where no honest test seam exists, that is written down rather than faked
