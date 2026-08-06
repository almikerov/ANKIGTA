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

Not a wrong value: a wrong *rendering* of the right one.

**Measured on the owner's running server, not guessed.** The first guess was
MTA's JSON, and it was wrong — `toJSON(0.6)` writes `0.6` and reads back as a
double. What loses the precision is **every server→client hop**: MTA packs a
non-integer Lua number as a 32-bit float on the wire. Both paths do it:

```
triggerClientEvent  0.6  -> 0.60000001999999997
                    0.55 -> 0.55000000999999998
                    0.25 -> 0.25
setElementData      0.6  -> 0.60000001999999997
```

`0.25` survives because a power-of-two fraction is exact in single precision.
`0.5` survives for the same reason — which is the whole of why retreating to it
would appear to work. It would hide the tail for one value while `0.55`, `0.1`
and most other two-decimal settings kept it, and every server-owned numeric
setting crosses that wire.

So the setting's rule already declares its precision — `numeric(0, 1, nil, 2)` —
and a value shown to the player is shown at the precision its own rule states.
Round at the boundary, once, for every numeric setting rather than for this one.

The owner offered `0.5` as a fallback if the tail could not be removed. It can,
so the default stays `0.6`.

Related, and not the same thing: `_card_id_or_none` in
`companion/ankigta_companion/http_server.py` exists because a card id reaches
the add-on as `1784032937016.0`. Same family — a number that changed shape in
transit — different hop.

## Settings does not outlive the window it was opened in

Open Settings, close F7, press F7 again: Settings is still there. The panel
should open where it always opens — on the list.

This is the same shape ticket 04 settled for the drawn zone: what outlives the
window is the *answer* (the settings the player changed), not the screen they
changed it on. A window that reopens where it was left is a window whose state
the player has to notice and undo before doing the thing they opened it for.

**Blocked by:** None — 03, 04 and 05 are all on the trunk.

**Status:** done. Automated proof: `tests/test_map_blips.py` for the map,
`tests/test_settings_ui.py` for the precision, `tests/test_panel.py` for the
section and the order, `tests/test_panel_page.py` for the pane, and
`tests/test_settings_and_locale.py` for the schema rules behind all four. What
needs a person to look at a frame, a radar or a map is
`docs/checklists/panel-rebuild-08-five-corrections-and-the-map.md`, which is
`not run`.

- [x] `Draw radius` is in the entity pane beside `Show corona`
- [x] It is still the client's own, and still about the selected row
- [x] It is gone from Settings, and from `Settings.order`
- [x] A toggle shows every known Map Entity on the map
- [x] Connected, disconnected and next card are three different colours
- [x] An entity that is both the next card and connected reads as next card
- [x] The toggle is independent of `indicatorMode`, and neither breaks the other
- [x] What happens past a large number of entities is stated and tested
- [x] `UI Scale` is the first row in Settings
- [x] Corona opacity reads `0.6`, not `0.60000002`
- [x] Every numeric setting is shown at the precision its own rule declares
- [x] A setting whose value crossed the wire still compares equal to the one
      the player chose, so a redraw does not read as an edit
- [x] The default is still `0.6`
- [x] Closing F7 with Settings open and reopening lands on the list
- [x] The settings themselves are unchanged by that — only the screen resets

## What the three states look like, and why the next card is a sprite

Three states, three colours, one blip per entity — and the next card's is the
sprite-41 blip the Next Card Indicator has always made, now carrying the
next-card colour with it.

GTA draws the sprite in place of the colour where a blip has one
(`CMarkerSA::SetColor`: "Sets the color of the marker when MARKER_SPRITE_NONE is
used"), so on screen the next card is told apart by its sprite and the other two
by their colour. The colour is set anyway so that what a state looks like is one
table with three entries rather than a rule split across two modules, and the
sprite is the stronger mark — which is right for the one entity the player is
being sent to.

`indicatorMode` decides whether that mark exists at all; the toggle decides
whether anything else is on the map. Where both are on, the map puts nothing on
top of the indicator's mark.

## Past a sensible number: 64, nearest first

GTA San Andreas has 175 radar trace slots in total — `MAX_MARKERS` in
`game_sa/CRadarSA.h`, an array `CRadarSA` fills once and hands out of — shared
with the game's own icons and every other resource. `CRadarSA::GetFreeMarker`
answers NULL once they are gone and nothing reports it:
`CClientRadarMarker::CreateMarker` leaves the blip with no trace behind it, so
the element exists, `isElement` says yes, and there is nothing on the radar.
Worse, `CClientRadarMarkerManager::OrderMarkers` destroys and re-creates every
trace in ordering order whenever the list changes, so which blips lose is decided
by ordering rather than by anything the player did.

So ANKIGTA draws at most 64, the nearest to the player, and says so.
`Indicator.mapBlipLimit()` is the number, and `tests/test_map_blips.py` holds it
to a range as well as taking it from the module.

## The shape the indicator draws

`sphere_and_minimap` named a shape nothing ever drew: the mark is
`dxDrawMaterialLine3D`, a standing bar as wide as the Activation Zone's radius.
The value, the plan's fields and the words are `beam` now; **the shape is
unchanged** — what it should look like is the owner's to judge and nobody has
asked for another. A value stored under the old name is carried across by
`Settings.normalize`, so an indicator somebody had turned on does not go quietly
back to `none`.

## Found beside it, not fixed here

- `Indicator.refresh` writes `setElementInterior` and `setElementDimension` onto
  the next card's blip on **every frame**. On a blip that is not a value write:
  `CClientRadarMarker::SetDimension` goes through `RelateDimension`, which asks
  the manager to re-order — destroying and re-creating every radar trace on the
  client, the game's own and every other resource's included — whether or not the
  dimension is different. So with the Next Card Indicator on, the whole radar is
  re-cut sixty times a second. Predates this ticket; the map blips added here
  guard against exactly this and the indicator's own blip does not. One `if`
  and one remembered value, in `client/indicator.lua`.
- `docs/design/confirmed-baseline.md` still calls the indicator's mark a sphere.
  It is a record of what was confirmed in the interview rather than living
  documentation, so it is left as it stands; `CONTEXT.md` is the glossary and is
  updated here.
