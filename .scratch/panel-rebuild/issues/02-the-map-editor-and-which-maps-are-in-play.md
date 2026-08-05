# 02 — The Map Editor, and which maps are in play

**What to build:** four things ANKIGTA gets wrong about the stock Map Editor.
They are one ticket because they are one misunderstanding — the editor keeps a
world beside the world, and ANKIGTA reads it as if it were the only one.

## Nothing can be linked

Every object is refused with `entity_runtime_not_unique`. The check counts every
element carrying the Map Entity's id and demands exactly one, but the editor
keeps its own EDF representation beside the real element, so inside the editor
there are always two and the count is never one. The panel already knows this and
steps around it when it resolves a row to a live element; the link path does not.

The same check only ever looks at objects, so a vehicle, a ped or a marker cannot
be linked through it at all — and all four are Map Entity types.

This is the reason to do this ticket early: linking is what ANKIGTA is for, and
today it cannot be done in the place it is done.

## Teleport lands in the wrong place

Finding a row in the world is the reason Teleport exists, and the editor is where
a player is most likely to be looking for one. The editor works in a dimension of
its own and the entity records carry the authored one, so Teleport has to put the
player next to the copy actually in front of them, not next to the one the record
describes.

**And the crash.** The owner reported the game crashing on teleport. There is no
dump from that day and the client logs show no trace, so this ticket does not
promise a fix — it owns getting a reproduction, because it is already in this
code. Drive it from the live server with the reaction stream running (`mark`,
then `since`), then look in `C:\Games\MTA San Andreas 1.6\MTA\dumps\public`. If it
reproduces, file it with the diagnosis attached; if not, say so and say what was
tried.

### It did not reproduce

Driven against the deployed build on 2026-08-05, with `mark`/`since` running
throughout and the owner's player restored afterwards:

- 5 teleports through `exports.ankigta:teleportPlayerToMapEntity`, one per
  stored Map Entity;
- 15 rapid repeats to the one entity that has a live instance, resetting the
  player to dimension 0 between each;
- one teleport while occupying a vehicle, and one out of interior 3;
- one through the whole client→server path (`ankigta:teleportToEntity` from the
  client), and then 12 more of those on a 250 ms timer with F7 open and the
  focus camera held, alternating the player's dimension between 0 and 200.

The client stayed reachable throughout, `since` reported no error from any
resource, and `MTA\dumps\public` is still empty. The only dump on the machine is
`private\client_..._20260723_0046.dmp`, from 2026-07-23 — not the reported day.

What it did reproduce is the wrong-place symptom, exactly: teleport to
`editor_dump / object (vgsSstairs04_lvs) (1)` put the player in **dimension 200**,
the editor's working dimension, from dimension 0. Every other stored entity
refused with `invalid_target`, because `Store.getMapEntity` never selected the
authored coordinates — so teleport to an entity with no Runtime Instance could
not work at all. Both are fixed and tested here.

## The editor's scratch maps are not the player's

`editor_dump` and `editor_test` are what the editor calls the throwaway resources
it dumps into and play-tests from. They ended up in ANKIGTA's store as maps, and
an entity adopted out of a play-test is a Spatial Link pointing at a copy that
stops existing when the test does.

This is not hypothetical. A read of the owner's live store on 2026-08-05 found
**every stored Map Entity on one or the other** — nothing has been adopted from a
real map at all:

```
('editor_test', 'ped (1)',                       'ped')
('editor_test', 'object (sw_hedstones) (1)',     'object')
('editor_test', 'vehicle (Clover) (1)',          'vehicle')
('editor_test', 'vehicle (Glendale Damaged) (1)','vehicle')
('editor_dump', 'object (vgsSstairs04_lvs) (1)', 'object')
```

Not adopting from them again is the fix. What to do about the ones already stored
is a decision, and it is not deletion: a Map Entity carries a link the player made
deliberately and may have made against an object they still have. Report them as
what they are and let the player decide — the entity list already knows how to say
a Map Entity is missing and how to relink it.

**ADR 0025 stays.** The editor is used as it ships and nothing is written into its
resources. Knowing which of its resources are scratch is reading it, not changing
it.

## Loaded is what decides, not a switch

The scratch maps became visible because Settings offers a row per map, named by
whatever the map is called in the store. That switch goes: the map that is running
gives the set of cards, and `Review mode` chooses within it. Two questions, in
that order, and only the second is the player's to answer twice.

**It cannot simply be deleted, because it is currently the only thing narrowing
anything.** Study walks every stored Spatial Link and takes every one whose card
is live, so a map that is nowhere in the world contributes its cards just the
same. Removing the switch alone would widen study to every map ANKIGTA has ever
seen.

So the rule it stood in for becomes the actual rule: a Map Entity takes part when
its map is loaded. Which maps those are is a question the panel already answers,
to scope the Map Entity list to the map in front of the player; study asks the
same question of the same answer rather than growing a second one that can
disagree with it.

The session's card set, the counters and the spatial candidates each narrow by
that answer, taken from one place. Text Labels do not exist on this trunk yet —
ticket 06 builds them, and it inherits this rule rather than growing its own.

**Almost all of this is server-side.** `includeInStudy` lives in
`server/settings_store.lua`, `server/store.lua` and `server/main.lua`; teleport is
`server/teleport.lua`. The client carries three references to `includeInStudy` in
`panel.lua` (the per-map settings row it draws) and about seven lines of teleport
wiring across `panel.lua` and `app.js`. Ticket 03 rewrites those two files, so
keep this ticket's touch on them to the minimum the work actually needs.

**Unloading a map still removes nothing.** A Spatial Link is not the map, and
loading the map again brings the link back exactly as it was.

**Blocked by:** 01.

**Status:** ready-for-agent

- [x] A card links to an object while the Map Editor is open
- [x] An editor representation is not counted as a second copy of an entity
- [x] A genuine duplicate is still refused, and the refusal says which
- [x] A vehicle, a ped and a marker can each be linked
- [x] The stub the uniqueness check runs against knows about EDF representations,
      so this cannot pass in tests and fail in the game
- [x] Teleport moves the player to the entity while the Map Editor is open
- [x] Teleport still works outside the editor, into the right dimension
- [x] The teleport crash is either reproduced and filed with a diagnosis, or
      reported as not reproducing, with what was tried
- [x] An entity is not adopted while an editor scratch resource owns it
- [x] Working in the Map Editor normally still adopts from the map being edited
- [x] Entities already stored against a scratch map are identifiable as such
- [x] The player is told, rather than having rows silently deleted — the row
      turns `Entity missing` and offers Relink, and carries a reason; see
      "Found on the way" for why nothing renders the reason yet
- [x] A Spatial Link made against one can be relinked or removed deliberately
- [x] Nothing is written into any editor resource
- [x] Settings offers no per-map row, and no way to exclude a map
- [x] A Map Entity on a loaded map is in play; one on an unloaded map is not
- [x] Loading that map again brings its links back untouched
- [x] The session's card set, the counters and the spatial candidates all narrow
      by the same answer, taken from one place
- [x] A database holding stored per-map preferences opens without complaint, and
      stops carrying them
- [x] `Active Map Set` in CONTEXT.md no longer mentions the switch — it names
      it only to say it is abolished, which is how CONTEXT.md retires a term
      (see `String Table` on `Localization`)

## Found on the way, and left for whoever owns the file

**Nothing renders `guidanceKey`.** `panel.lua` puts it in the page state and
`app.js` and `index.html` never read it — so `guidance.saveWithEditor`,
`guidance.retrySave`, `guidance.cardMissing`, `guidance.copyBlocked`,
`f7.guidance.notAdopted` and this ticket's `guidance.editorScratchMap` are all
written and never shown. A scratch row therefore says `Entity missing` and
offers Relink, which is the state and the action, but not the reason. Ticket 03
rewrites both files and should render it once for all six.

**`zone_marks.lua:254`** repeats `attempt to call field 'selection'` in
`clientscript.log`. Ticket 04's file.

**`client/settings_store.lua`** still discards stored `language` and
`drawRadius` on every start — settings that no longer exist, left from before
ticket 01.

**Four orphan files sit in the deployed resource**, on disk and undeclared by
its own `meta.xml`: `client/text_labels.lua`, `client/zone_marks.lua`,
`server/text_labels.lua`, `shared/text_label.lua`. They are inert — MTA never
loads them — but this is the shape the wave was called for
(`spec.md`: "`zone_marks.lua` ended up sitting in the deployed folder undeclared
by its own `meta.xml` — on disk, never loaded, for days"). Whoever deploys next
should sweep the directory rather than copy over it.

## What this ticket touched that it was not asked for

Three, each because a checklist item could not otherwise be met:

- **`Store.relinkEntity` passed a bare table as its Change History target**,
  which SQLite cannot bind, so every relink failed with a transaction error.
  Only source-text tests covered relink, so nothing had ever run it. Needed for
  *A Spatial Link made against one can be relinked*.
- **`Store.getMapEntity` never selected the authored coordinates**, so teleport
  to an entity with no Runtime Instance answered `invalid_target` — reproduced
  live on four of the owner's five stored entities. Needed for *Teleport still
  works outside the editor*.
- **`me:ID` dropped as a gate in the two Pick Entity prepare paths as well as
  the Link path**, because it is the same mistake: `assignID` writes it only
  when the editor has to invent an id.

## What a person still has to look at

Every item above is met at the highest programmatic seam, in
`tests/test_map_editor_and_maps_in_play.py`. Four of them end in something only
a person can see, and those are **not run**:

- **F7 → pick a row → Link, inside the open Map Editor.** Expect a Pending Map
  Save row rather than `entity_runtime_not_unique`. The link only becomes an
  Active Spatial Link after the editor's own Save, which is the same manual step
  it always was.
- **The Teleport button, in the editor and out of it.** Expect to arrive beside
  the copy in front of you, in the dimension you were looking at.
- **Settings.** Expect no map names, no heading above them, and no `No map is
  loaded` line — just the flat list of settings.
- **A row stored against `editor_dump`/`editor_test`.** Expect `Entity missing`
  with the scratch-map guidance, Relink offered, and nothing gone from the list
  on its own.

The owner's live database holds five such rows (`editor_test` ×4,
`editor_dump` ×1) and no Spatial Link at all, so the fourth is what the panel
will show first on the next deploy.
