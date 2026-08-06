# Panel rebuild

Fourteen things the owner asked for after running the panel, plus what four
parallel branches left unfinished, folded into eight tickets.

They are grouped by the file set they open, not by how they were reported. Two
tickets that read the same 2000 lines of `app.js` are one ticket; a ticket small
enough to feel tidy still costs a merge, a deploy and a trip into the game.

## Why this exists as a second wave

The first wave ran four lines at once — the Card Picker, the world marks, the
single string table and Show text. Each was fine on its own branch. Together
they did not join: `panel.lua`, `app.js`, `index.html`, `locale.lua` and two
test modules all conflicted, `panel.lua` was not even mergeable as text, and
`zone_marks.lua` ended up sitting in the deployed folder undeclared by its own
`meta.xml` — on disk, never loaded, for days.

The owner judged those features by playing the game, and the game was running a
build two tickets behind the trunk. So "English only" and "the zone follows its
object" both read as not done when they were merged, green and unreachable.

Hence the rule this wave is built on: **one ticket at a time, deployed and
looked at before the next one starts.** The trunk is now the build the owner
actually runs.

## What that cost, and what it did not

Tickets 06 and 07 of the first wave are no longer on the trunk. They are not
gone: they remain on their own branches and as parents of the trunk commit that
superseded them, so a ticket here that wants to read what they did has
`git show`. Where that is worth doing, the ticket says so.

Their *behaviour* is respecified here rather than merged, because the owner
never saw either one and specifying from a report nobody has checked is how the
first wave got its shape.

## The owner's list, and where each item went

| # | What the owner asked for | Ticket |
|---|---|---|
| 24 | Activation key, global and per link | 05 |
| 25 | Activation type: by key or by zone | 05 |
| 26 | `<KEY> to view` on an entity in key mode | 05 |
| 27 | "Apply to all" beside every overridable global | 05 |
| 28 | Teleport works in the Map Editor | 02 |
| 29 | Drop language support, English only | 01 |
| 30 | Dropdowns only open on the arrow | 03 |
| 31 | A drawn zone has no distance at which it stops | 04 |
| 32 | `editor_dump`/`editor_test`, and no map switch | 02 |
| 33 | `entity_runtime_not_unique` — nothing links | 02 |
| 34 | Zones do not follow their objects until F7 | 04 |
| 35 | The entity edit pane should always be visible | 03 |
| 36 | A field inheriting a global should show its value | 03 |
| 37 | `Draw always` becomes `Show corona` | 04 |
| 38 | Markers are ordinary Map Entities, renamable | 07 |
| 39 | A row is named `ped (1)`, the way the editor names it | 07 |
| 40 | `Draw radius` belongs beside `Show corona` | 08 |
| 41 | The map shows ANKIGTA's objects, coloured by state | 08 |
| 42 | UI Scale is the first setting | 08 |
| 43 | Corona opacity reads `0.60000002` | 08 |
| 44 | Settings should not outlive the window it was opened in | 08 |

**07 turned out to be the cheapest of the seven.** The editor's name for an
entity is already its `entity_id` in ANKIGTA's own store — `ped (1)`,
`marker (corona) (1)`, `object (sw_hedstones) (1)` — verified against the live
database. The panel derives a name from the model number instead of showing the
one it holds. No schema change, no migration.

Two more, carried from the previous wave and not in the owner's numbered list:
the Map Entity list's ergonomics (single-click camera, arrow keys, a renamed
entity still showing its original name) are in **03**; `Review mode: Show text`
is **06**.

## Carried findings

Small things found by review and by the live server, too small to be tickets.
Each belongs to whichever ticket next opens the file; the ticket that does is
named where it is obvious.

- `companion/ankigta_companion/cards.py` carries a raw U+00A0 inside a
  `.replace()` that `str.split()` already handles.
- ~~The card row's `label` key collides with the glossary's **Text Label**,
  which is a different thing entirely. Ticket 06.~~ Done in 06: it is
  `sortField`, the name Anki and the companion both use.
- `Follow Settings` on the *corona* colour picker has been broken since 05: the
  page sends `false` where the server only recognises `"inherit"`, so clearing
  it is refused as `settings.error.not_a_color` and the override stays. Found
  and reproduced by 06, which owns the other colour picker on that pane and
  sends the right word. Whichever ticket next opens `app.js` — one word there
  and one line in `tests/test_panel_page.py`.
- `.inspector-actions` in `styles.css` is dead. Ticket 03.
- `tests/test_panel_page.py::test_saving_lives_with_the_fields_it_saves` reads
  `index.html` as text and splits on `'id="inspector"'`, which
  `docs/agents/lua-testing.md` forbids by name. Ticket 03.
- `app.js` still carries ticket 03's per-map branches — `heading`, `note`,
  `settingClass`'s `per-map`, `mapId` on the wire — inert since 02 removed
  per-map settings. Whichever ticket next opens the file.
- `tests/test_mta_ticket_09.py`, `test_mta_ticket_10.py` and
  `test_mta_ticket_24.py` assert over the *source text* of Lua files, the same
  thing the finding above names. Ticket 05 had to edit all three to follow a
  refactor rather than a behaviour change.
- `map_entity_metadata` carries four inert columns after 05 — `radius`,
  `show_radius`, `corona_color`, `corona_opacity` — each superseded by the
  override column beside it. Dropping them means rebuilding a table other
  tables cascade from, which is its own ticket.

## Not in this wave

**The teleport crash.** The owner reported the game crashing on teleport. No
dump exists from that day and the client logs show no trace. It has no
diagnosis, so it cannot have an acceptance criterion. Ticket 02 owns getting a
reproduction, because it is already in teleport's code; if it reproduces, it
becomes its own ticket with a real diagnosis behind it.
