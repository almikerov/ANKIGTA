# 01 — English only

**What to build:** one string table, in English, and none of the machinery that
existed to have two.

ANKIGTA has a Russian table beside the English one, a language the code decides
between, and a read of the Windows locale to decide it with. All three go. What
is left is a flat table where each string has one key and one value.

**Why this one is first.** It touches every user-facing string in the resource,
and every ticket after it adds strings. Run it last and eight tickets each write
their strings twice, into a table that then loses half of what they wrote. Run
it first and they each write one.

**Reference, not a merge.** This was built once already, on
`claude/english-only-panel-usability-ead8e9`, and merged into the old trunk as
`848ee04`. It is not on this trunk and is not being merged onto it — but it is
worth reading before starting, because it found things the table alone does not
show. Read it with `git show 848ee04` and decide what still applies.

**What the table is for.** Strings live in `shared/locale.lua` and not at their
call sites, so a sentence is never stranded in the middle of a module and a
missing string is found by a test rather than by a player reading `f7.pickEntity`
off a button. That does not change here.

**What does not go through the table:** card text, user-given Map Entity names,
Entity Tags and Anki Tags. Those are the user's own words.

**Blocked by:** None.

**Status:** ready-for-agent

- [ ] `shared/locale.lua` holds one table, and every key has one value
- [ ] No setting selects a language, and none is stored
- [ ] Nothing reads the Windows locale — `getLocalization` is never called
- [ ] No script in the resource compiles a Cyrillic string constant, the string
      table included
- [ ] Every surface still renders: a string in the table that no control ever
      receives fails a test
- [ ] A key looked up but absent from the table fails a test rather than
      reaching a player
- [ ] `String Table` in CONTEXT.md describes one table and no language choice
