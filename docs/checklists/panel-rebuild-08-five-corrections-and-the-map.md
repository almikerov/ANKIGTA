# Panel rebuild 08 — five corrections, and what the map shows

Status: not run

This checklist requires a separately authorized MTA runtime. It is not executed
by repository implementation or review work. Everything a machine can answer is
already answered by `tests/test_map_blips.py`, `tests/test_settings_ui.py`,
`tests/test_panel.py`, `tests/test_panel_page.py` and
`tests/test_settings_and_locale.py`; what is left here is what needs a person to
look at a frame, a radar, or a map.

The owner's database is empty — zero Map Entity — so **steps 6 onwards need
objects placed in the Map Editor and linked first.** Three is enough: one linked
to a card, one adopted but unlinked, and one linked to a card that is then
deleted from Anki.

## `Draw radius` beside `Show corona`

1. Open F7 and select a row. `Draw radius` is on the entity pane, immediately
   beside `Show corona`, and reads `On`/`Off` rather than naming an action.
2. Turn it on. The selected row's Activation Zone appears in the world, the same
   sphere it drew when the setting was in Settings.
3. Move down the list. The sphere follows the selection.
4. Close F7. The sphere goes. Open F7 again: it is back, on the same row, with
   nothing reselected and nothing re-ticked.
5. Open Settings. There is no `Draw radius` row anywhere in it.
6. With no row selected, `Draw radius` is still usable — it is yours, not the
   row's — while the boxes beside it are greyed out.

## The map says which objects are ANKIGTA's

7. Open Settings and turn on `Show every Map Entity on the map`. Press F11 for
   the full map, and look at the minimap.
8. The object with a live link is one colour, the one with no usable link is
   another, and the two are told apart at a glance — on the minimap as well as
   on the big map, and against both the water and the city.
9. Turn `Next Card Indicator` to `Minimap only`. The entity the scheduler chose
   carries the Next Card mark, and does **not** also carry a second dot.
10. Break that entity's link (delete its card in Anki, or Unlink it). Its mark
    becomes the disconnected colour, and the next card mark moves to whatever
    the scheduler chose instead.
11. Turn `Next Card Indicator` to `No marker`. The rest of the entities stay on
    the map; only the next card's mark goes.
12. Turn `Show every Map Entity on the map` off with the indicator still on
    `Minimap only`. Only the next card is marked, exactly as before this ticket.
13. Turn both off. The map is as it was.
14. Walk a few hundred metres. The colours do not flicker or swap as you move,
    and blips do not blink in and out at the edge of a step.

### Past a sensible number

ANKIGTA draws at most **64** entity blips, the nearest to you. GTA has 175 radar
slots in total (`MAX_MARKERS`, `game_sa/CRadarSA.h`), shared with the game's own
icons and every other resource, and `CRadarSA::GetFreeMarker` answers with
nothing rather than complaining once they are gone. The cap and the nearest-first
choice are `tests/test_map_blips.py`'s; what a person has to judge is whether a
map with 64 dots on it is still readable.

15. If a map with more than 64 linked objects is available, load it and confirm
    the map is still legible — that the dots do not merge into a smear — and
    that walking across the map swaps which ones are shown without visible
    stutter.
16. Confirm the game's own map icons (shops, saves, pickups) are still there
    with ANKIGTA's blips on screen.

## UI Scale is the first setting

17. Open Settings. `UI scale` is the first row, above `Companion port`, with no
    scrolling.

## Corona opacity reads `0.6`

18. Open Settings with a fresh install, or after `Reset UI layout`. `Corona
    opacity (0–1)` reads `0.6` — not `0.60000002`.
19. Type `0.55` into it and press Tab. It reads `0.55`, and still reads `0.55`
    after the panel redraws (walk about with F7 open; a car streaming in is
    enough to cause a redraw).
20. Do the same for `Activation delay (s)` with `1.35`, and for `Open cards when
    speed lower than:` with `12.34`.
21. Give one entity its own corona opacity of `0.55` on the entity pane. It
    reads `0.55` there too, and the corona in the world matches what the two
    other entities show at `0.6`.

## Settings does not outlive the window

22. Open F7, open Settings, close F7 with F7 or with Escape. Press F7 again: the
    panel is on the Map Entity list.
23. Do it again after changing a setting. The setting you changed is still
    changed — only the screen reset.
24. Repeat with the panel closed by Pick Entity rather than by F7: it comes back
    where Pick Entity left off, and not on Settings.

## The mark over the next card

25. Set `Next Card Indicator` to `Beam and minimap`. The words say beam, and what
    stands over the entity is the standing bar it has always been — nothing
    about the shape changed with the name.
26. If `Next Card Indicator` had been set to `Sphere and minimap` before this
    build, confirm it is still marking the next card after the update rather
    than having gone quiet.

## What to record

For each step: what you did, what you saw, and — where it did not match — a
screenshot and the matching lines from `clientscript.log` and `server.log`.
