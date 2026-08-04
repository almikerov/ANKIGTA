# 05 — Opening a card by pressing a key, and applying a global to everything

**What to build:** a second way for a card to open, and a way to make every link
that was told otherwise go back to following the global.

They are one ticket because the second exists to cover the first. Building the
bulk control before the settings it has to cover would mean coming back to add
them, and building the settings without it would leave two more overrides with no
way back.

## Two ways in, and the entity says which

`Activation type` is `Automatic` — what happens today, the card opens by itself
once the Activation Zone and its delay are satisfied — or `Key`, where standing in
the zone offers the card and pressing the key takes it. Global, and overridable on
the link, the same shape the Activation Zone radius has.

`Key` is not a slower `Automatic`. The delay and the speed threshold exist because
a card that opens by itself has to be sure the player meant to be there; a card
that opens because the player pressed a key has that certainty from the press. So
in `Key` the delay does not apply — the offer stands for as long as the player is
in the zone.

**An offered card says so.** An entity in `Key` mode carries `<KEY> to view` while
the player is inside its zone, naming the key that is actually bound. A key nobody
can discover is a key nobody presses, and this is the whole of how it is
discovered. It is drawn facing the player and legible over anything, and it obeys
ticket 04's draw distance rather than inventing a second one.

**Which key.** `Activation key` is global and overridable on the link too, so one
object can be the odd one out without moving everything else. The prompt names
whatever it is set to. A key already bound to something ANKIGTA owns is refused
with a reason rather than quietly shadowing it.

**A Text Label is the other thing drawn on an entity**, and one entity shows only
one of them. Text Labels do not exist yet — ticket 06 builds them — so that rule
cannot be tested here and 06 owns it. What this ticket owes 06 is a prompt it is
possible to suppress: the decision about whether to draw is reachable from
outside, not buried in the draw call.

## And the ones I already made

A global setting governs every link that has not been told otherwise, so a new
link follows it by existing. What has no answer today is the link that *was* told
otherwise, months ago, and should now go back to following along. The only way
back is to open each one and clear it by hand, which is not a way back at all once
there are more than a few.

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
`Show corona` from ticket 04, the activation type and key from this one, and the
Text Label settings from ticket 06 — and a hand-written list is a list that will
be missing the next one. A setting that gains an override gains this control by
gaining the override.

**It says what it will do before it does it.** Clearing overrides across a world
is not undoable by pressing it again, so it names how many links it is about to
change and asks. It is a single entry in Change History either way: one decision,
one undo.

**Blocked by:** 01, 03, 04.

**Status:** ready-for-agent

- [ ] `Activation type` offers `Automatic` and `Key`, globally and on a link
- [ ] `Automatic` behaves exactly as it does today, delay and speed included
- [ ] In `Key`, standing in the zone and pressing the key opens the card
- [ ] In `Key`, standing in the zone alone never opens the card
- [ ] In `Key`, the activation delay does not gate the press
- [ ] An entity offering a card shows `<KEY> to view` while the player is in its
      zone, and stops when they leave
- [ ] The prompt names the key that is actually bound
- [ ] The prompt obeys the draw distance from ticket 04
- [ ] Whether the prompt is drawn is decidable from outside the draw call, so
      ticket 06 can suppress it without reaching into this one
- [ ] `Activation key` is settable globally and on a link
- [ ] A key ANKIGTA already uses is refused with a reason
- [ ] Nothing about admission or rating changes: the card opens the one way in
- [ ] Every global setting a link can override offers the bulk control
- [ ] A setting that gains an override later gains the control without being
      added to a list
- [ ] Using it makes every link follow the global for that setting
- [ ] Changing the global afterwards moves those links again
- [ ] Other settings' overrides are untouched
- [ ] It names how many links it will change, and asks first
- [ ] It is one Change History entry, and one Undo puts every override back
