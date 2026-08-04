# 02 — Linking and teleport, while the Map Editor is open

**What to build:** the two things a player does from the panel — connect a card
to a thing, and go and look at the thing — made to work in the place they are
actually done.

**Nothing can be linked at all.** Every object is refused with
`entity_runtime_not_unique`. The check counts every element carrying the Map
Entity's id and demands exactly one, but the stock editor keeps its own EDF
representation beside the real element, so inside the editor there are always
two and the count is never one. The panel already knows this and steps around it
when it resolves a row to a live element; the link path does not.

The same check only ever looks at objects, so a vehicle, a ped or a marker
cannot be linked through it at all — and all four are Map Entity types.

**Teleport lands in the wrong place.** Finding a row in the world is the reason
Teleport exists, and the Map Editor is where a player is most likely to be
looking for one. The editor works in a dimension of its own and the entity
records carry the authored one, so Teleport has to put the player next to the
copy that is actually in front of them, not next to the one the record
describes.

**And the crash.** The owner reported the game crashing on teleport. There is no
dump from that day and the client logs show no trace, so this ticket does not
promise a fix — it owns getting a reproduction, because it is already in this
code. Drive it from the live server with the reaction stream running (`mark`,
then `since`), then look in `C:\Games\MTA San Andreas 1.6\MTA\dumps\public`. If
it reproduces, file it with the diagnosis attached; if it does not, say so and
say what was tried.

**Why second.** Linking is the thing ANKIGTA is for, and today it cannot be done
where it is done. Everything after this is judged by a player who can link.

**Blocked by:** 01 — it adds a refusal string, and the table should be one table
by then.

**Status:** ready-for-agent

- [ ] A card links to an object while the Map Editor is open
- [ ] An editor representation is not counted as a second copy of an entity
- [ ] A genuine duplicate is still refused, and the refusal says which
- [ ] A vehicle, a ped and a marker can each be linked
- [ ] Teleport moves the player to the entity while the Map Editor is open
- [ ] Teleport still works outside the editor, into the right dimension
- [ ] The stub the uniqueness check runs against knows about EDF
      representations, so this cannot pass in tests and fail in the game
- [ ] The teleport crash is either reproduced and filed with a diagnosis, or
      reported as not reproducing, with what was tried
