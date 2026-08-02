# 05 — Show text: the card is 3D text on the object

**What to build:** a third Review Mode in which approaching a linked entity
draws the card as text in the world, on the object, instead of opening the CEF
review surface.

Reported item 16. This is a new way to study, not a rename.

**What it is for.** The review surface is a window: it takes the cursor, covers
the world and has to be dismissed. Text on the object is a glance. Walking past
a linked object and reading it is a different act from sitting down to answer
it, and this mode is the first one.

**What has to be decided while building it, not before.** Which side of the
card is shown, and whether the other side is reachable at all. Whether reading
text can rate a card — and if it cannot, say so rather than letting the player
assume their reading counted. How much text is drawn before it stops being
readable at a distance, and what happens to a card longer than that. Whether
the text turns to face the player. What Review Protection and the world-mute
setting mean in a mode with no review surface to protect or mute.

Answer these in the ticket, in the code, with the reason next to the answer.
Rating is the one that must not be guessed at: a card the player believes they
answered and that the scheduler never saw is worse than no mode at all.

**Blocked by:** 04 — the mode is the third value of the setting that ticket
creates.

**Status:** ready-for-agent

- [ ] `Review mode: Show text` draws the card's text on the linked entity
- [ ] The CEF review surface never opens in this mode
- [ ] Whether a card can be rated in this mode is decided, implemented and stated on screen
- [ ] Text too long to read at a distance is handled deliberately, not clipped by accident
- [ ] Leaving the entity's zone removes the text
- [ ] What Review Protection and the world mute mean here is decided and written down
