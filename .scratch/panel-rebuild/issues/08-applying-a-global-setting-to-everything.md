# 08 — Applying a global setting to everything

**What to build:** a way to say "and the ones I already made, too".

A global setting governs every link that has not been told otherwise, so a new
link follows it by existing. What has no answer today is the link that *was* told
otherwise, months ago, and should now go back to following along. The only way
back is to open each one and clear it by hand, which is not a way back at all
once there are more than a few.

So each global setting a link can override gets a control beside it that clears
that override everywhere.

**Clearing, not copying.** After it, every link *follows* the global — so changing
the global again moves them all again. The alternative, writing today's value into
every link as its own override, would look identical for about a minute and then
quietly stop tracking. Following is what the player means by "bring the old ones
into line", and it is what an empty override already means everywhere else —
ticket 03 made that visible in a single link's field; this does it to all of them
at once.

**Driven by which settings have overrides, not by a list.** The set is already
growing — the Activation Zone radius, the corona's colour and opacity and
`Show corona` from ticket 04, the activation type and key from ticket 07, and the
Text Label settings from ticket 09 — and a hand-written list is a list that will
be missing the next one. A setting that gains an override gains this control by
gaining the override.

**It says what it will do before it does it.** Clearing overrides across a world
is not undoable by pressing it again, so it names how many links it is about to
change and asks. It is a single entry in Change History either way: one decision,
one undo.

**Blocked by:** 07 — the control has to cover the activation type and key too,
and building it first would mean coming back to add them.

**Status:** ready-for-agent

- [ ] Every global setting a link can override offers the control
- [ ] A setting that gains an override later gains the control without being
      added to a list
- [ ] Using it makes every link follow the global for that setting
- [ ] Changing the global afterwards moves those links again
- [ ] Other settings' overrides are untouched
- [ ] It names how many links it will change, and asks first
- [ ] It is one Change History entry, and one Undo puts every override back
