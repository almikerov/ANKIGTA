# 08 — Five corrections, and what the map shows

**What to build:** four things the owner found wrong after using tickets 03, 04
and 05, and one thing the map does not do yet. One ticket because four of them
are the panel's own surface — the same `app.js` / `index.html` / `panel.lua` /
`settings.lua` — and the fifth is the only other thing that draws where the
player is looking.

## `Draw radius` belongs beside `Show corona`, not in Settings

Ticket 04 pulled the two apart correctly — one is a way of looking and the other
is a property of the entity — and then left them on different screens. In use
that is the wrong seam: both answer "what do I see around this row", both are
reached while a row is selected, and walking to Settings to turn one on and back
to the list to turn the other on is two journeys for one decision.

`Draw radius` stays the client's own and stays a way of looking. It moves to the
entity pane, beside `Show corona`.

## The map says which objects are ANKIGTA's

A toggle: show every Map Entity ANKIGTA knows on the map. Today only the Next
Card Indicator puts anything there — `createBlip(x, y, z, 41)` in
`client/indicator.lua`, one blip, for one card.

Three states, three colours, because the question the map answers is not "where
are my objects" but "which of them are ready":

- **connected** — the entity has a Spatial Link and its card is available;
- **disconnected** — the entity is known but has no usable link;
- **next card** — the one the scheduler chose, where the Next Card Indicator is
  set to show it at all.

Where an entity is both the next card and connected, next card wins: it is the
more specific answer and it is the one the player is looking for.

This is a toggle of its own, not a fourth value of `indicatorMode`. That setting
answers "how is the *next card* marked" and has three values about one entity;
this answers "is the rest of the world marked at all".

**Blips are cheap but not free.** MTA's blip limit is not the marker limit that
ticket 04 ran into, but a world with hundreds of entities is a map with hundreds
of blips. Say what happens past a sensible number rather than discovering it.

## UI Scale is the first setting

It is currently second from last, above `uiPlacement`. It is the setting a player
reaches for first — before anything else can be read comfortably, the interface
has to be a readable size — and on a panel that now has a lot of rows it is at
the bottom of a scroll.

## Corona opacity reads as `0.60000002`

Not a wrong value: a wrong *rendering* of the right one. `0.6` has no exact
single-precision representation, and MTA writes a Lua number to JSON as a
single-precision float. The repository already documents the same behaviour from
the other side — see `_card_id_or_none` in
`companion/ankigta_companion/http_server.py`, which exists because a card id
arrives as `1784032937016.0`.

```
0.6  -> float32 -> 0.6000000238418579
0.5  -> float32 -> 0.5
0.55 -> float32 -> 0.550000011920929
```

So the fix is not to retreat to `0.5`, which only hides it for one value while
`0.55` and every other two-decimal setting keeps the tail. The setting's rule
already declares its precision — `numeric(0, 1, nil, 2)` — and a value shown to
the player should be shown at the precision its own rule states. Round at the
boundary, once, for every numeric setting rather than for this one.

The owner said `0.5` would be acceptable if the tail cannot be removed. It can,
so the default stays `0.6`.

## Settings does not outlive the window it was opened in

Open Settings, close F7, press F7 again: Settings is still there. The panel
should open where it always opens — on the list.

This is the same shape ticket 04 settled for the drawn zone: what outlives the
window is the *answer* (the settings the player changed), not the screen they
changed it on. A window that reopens where it was left is a window whose state
the player has to notice and undo before doing the thing they opened it for.

**Blocked by:** None — 03, 04 and 05 are all on the trunk.

**Status:** ready-for-agent

- [ ] `Draw radius` is in the entity pane beside `Show corona`
- [ ] It is still the client's own, and still about the selected row
- [ ] It is gone from Settings, and from `Settings.order`
- [ ] A toggle shows every known Map Entity on the map
- [ ] Connected, disconnected and next card are three different colours
- [ ] An entity that is both the next card and connected reads as next card
- [ ] The toggle is independent of `indicatorMode`, and neither breaks the other
- [ ] What happens past a large number of entities is stated and tested
- [ ] `UI Scale` is the first row in Settings
- [ ] Corona opacity reads `0.6`, not `0.60000002`
- [ ] Every numeric setting is shown at the precision its own rule declares
- [ ] The default is still `0.6`
- [ ] Closing F7 with Settings open and reopening lands on the list
- [ ] The settings themselves are unchanged by that — only the screen resets
