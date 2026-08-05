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

**Status:** done. Automated proof: `tests/test_activation_by_key.py`, plus the
page's own half in `tests/test_panel_page.py`. What needs a person to look at a
frame — whether the prompt is *readable*, and whether it flickers — is
`docs/checklists/panel-rebuild-05-activation-by-key.md`, which is `not run`.

- [x] `Activation type` offers `Automatic` and `Key`, globally and on a link
- [x] `Automatic` behaves exactly as it does today, delay and speed included
- [x] In `Key`, standing in the zone and pressing the key opens the card
- [x] In `Key`, standing in the zone alone never opens the card
- [x] In `Key`, the activation delay does not gate the press
- [x] An entity offering a card shows `<KEY> to view` while the player is in its
      zone, and stops when they leave
- [x] The prompt names the key that is actually bound
- [x] The prompt obeys the draw distance from ticket 04
- [x] Whether the prompt is drawn is decidable from outside the draw call, so
      ticket 06 can suppress it without reaching into this one
- [x] `Activation key` is settable globally and on a link
- [x] A key ANKIGTA already uses is refused with a reason
- [x] Nothing about admission or rating changes: the card opens the one way in
- [x] Every global setting a link can override offers the bulk control
- [x] A setting that gains an override later gains the control without being
      added to a list
- [x] Using it makes every link follow the global for that setting
- [x] Changing the global afterwards moves those links again
- [x] Other settings' overrides are untouched
- [x] It names how many links it will change, and asks first
- [x] It is one Change History entry, and one Undo puts every override back

## What was decided along the way

**`Show corona` gained a global.** The ticket names it among the settings the
bulk control covers, and clearing an override means "follow the global" — so
there had to be one for it to follow. It ships off, which is what every entity
already was, and the per-entity answer became three-way: on, off, or following.
That third state is why the wire says `"inherit"` where it used to say `false`:
`false` is a value `Show corona` can hold, so it cannot also be how a field says
it holds nothing.

**In `Key`, the speed threshold does not gate the press either.** The ticket's
conclusion names only the delay, but the reason it gives covers both — a press
carries the certainty they exist to wait for — and the default threshold is
zero, so gating on it would mean the prompt saying `E to view` while walking and
E doing nothing. The gate still short-circuits the zone walk whenever nothing in
the world can be offering, which is the optimisation ticket 22 measured.

**One spelling for "nothing of its own".** Every override is a NULL-able column
now, `corona_color` and `corona_opacity` included — they said it with `''` and
`-1`, and a sweep that clears overrides everywhere would have needed to know
which spelling each column used. That is the list this ticket exists to avoid.

**"Links" here means Map Entity.** The prose above counts "links"; the control
counts Map Entity, because an entity carries its own answer whether or not a
card was ever hung on it, and a Spatial Link is what hangs one. The number the
question names is what the sweep will really change.

**An override reaching the client was the missing half.** The watched set the
activation rules read is rebuilt only when Anki is next asked, so an entity told
to open by a key went on opening by itself until that happened — and a sweep
that put every entity back on `Automatic` left every client still waiting for a
press. Editing an override, clearing them everywhere, and undoing either now go
through `invalidateStudyDependents`, which is the seam link, unlink, replace and
relink already used. Undo did not go through it before this either.

## Found next door, not fixed

- `map_entity_metadata` now carries four inert columns: `radius`, `show_radius`,
  `corona_color`, `corona_opacity`. Each was the answer before the override
  column beside it, and SQLite cannot drop a column from a table other tables
  cascade from without rebuilding it — which is the procedure
  `rebuildMapEntities` already follows for `map_entities`, and its own ticket.
- `client/panel/app.js` still carries ticket 03's per-map branches (`heading`,
  `note`, `settingClass`'s `per-map`, `mapId` on the wire). Inert since 02
  removed per-map settings; noted in that merge and still there.
- `tests/test_mta_ticket_09.py`, `test_mta_ticket_10.py` and
  `test_mta_ticket_24.py` assert over the *source text* of Lua files, which
  `docs/agents/lua-testing.md` forbids by name. All three had to be edited here
  to follow a refactor rather than a behaviour change, which is the cost that
  rule names.
