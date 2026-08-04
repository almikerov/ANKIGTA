# 07 — Opening a card by pressing a key

**What to build:** a card can be opened by walking up to a Map Entity and
pressing a key, instead of by walking up to it and waiting.

**Two ways in, and the entity says which.** `Activation type` is `Automatic` —
what happens today, the card opens by itself once the Activation Zone and its
delay are satisfied — or `Key`, where standing in the zone offers the card and
pressing the key takes it. Global, and overridable on the link, the same shape
the Activation Zone radius has.

`Key` is not a slower `Automatic`. The delay and the speed threshold exist
because a card that opens by itself has to be sure the player meant to be there;
a card that opens because the player pressed a key has that certainty from the
press. So in `Key` the delay does not apply — the offer stands for as long as the
player is in the zone.

**An offered card says so.** An entity in `Key` mode carries `<KEY> to view`
while the player is inside its zone, naming the key that is actually bound. A key
nobody can discover is a key nobody presses, and this is the whole of how it is
discovered. It is drawn facing the player and legible over anything, and one
entity never shows both this and a Text Label at once.

**Which key.** `Activation key` is global and overridable on the link too, so one
object can be the odd one out without moving everything else. The prompt names
whatever it is set to. A key already bound to something ANKIGTA owns is refused
with a reason rather than quietly shadowing it.

**A Text Label is the other thing drawn on an entity, and one entity shows only
one of them.** Text Labels do not exist yet — ticket 09 builds them — so that
rule cannot be tested here and 09 owns it. What this ticket owes 09 is a prompt
it is possible to suppress: the decision about whether to draw is reachable from
outside, not buried in the draw call.

**Blocked by:** 01, 03, 04 — 04 because the prompt is drawn into the world and
inherits that ticket's draw-distance rule rather than inventing a second one.

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
      ticket 09 can suppress it without reaching into this one
- [ ] `Activation key` is settable globally and on a link
- [ ] A key ANKIGTA already uses is refused with a reason
- [ ] Nothing about admission or rating changes: the card opens the one way in
