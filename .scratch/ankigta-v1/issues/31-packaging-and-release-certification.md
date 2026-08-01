# 31 — Packaging and release certification

**What to build:** Документированный install/update/remove path и финальный v1 certification на поддерживаемой Anki/MTA matrix, который доказывает canonical spatial-study scenario и отсутствие stranded/lost data.

**Blocked by:** 03 — Connection config and reconnect; 18 — Pause, AnkiWeb sync and lifecycle cleanup; 21 — Best-effort CEF, media and External Card Page; 29 — Migrations, backups and corruption recovery; 30 — Performance and large-data acceptance suite.

**Status:** resolved

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Verify programmatically — launching disposable copies is allowed, driving a GUI with screenshots or synthetic input is not, and the installed MTA/GTA tree stays unmodified. Acceptance that only a human can observe stays a manual checklist marked `not run`.

## Acceptance criteria

- [x] Documentation covers MTA resource install/update/remove, manual companion add-on install/update/remove, Bound collection setup, backups/recovery and supported versions.
- [x] Certification matrix initially pins Windows, Anki Desktop 26.05/V3/FSRS and MTA Server 1.6 build 24124.
- [x] Another Anki/MTA build remains unsupported until relevant compatibility suites pass.
- [~] Canonical end-to-end passes: Map Entity → Spatial Link → verified Save → Activation Zone → question → answer → rating → updated queue/target. Каждый шаг реализован и покрыт автоматически, включая написанный здесь polling; сам проход по живому миру — ручной checklist `not run`.
- [~] New/learning/relearning/review/suspended/buried/not-due/Card missing/Entity missing acceptance scenarios pass. Автоматически проходят на своих seam; на настоящей коллекции — ручной checklist `not run`.
- [x] Install/update/pause/remove leave no card in owned filtered deck and preserve Spatial Link/database/map data.
- [x] No required flow needs manual SQLite or `.map` editing.
- [x] Diagnostics/documentation state accepted Map Editor and CEF limitations without stronger claims.
- [~] All release gates and performance thresholds are recorded as passed for the published matrix. Все пороги измерены и пройдены; отчёт сам сообщает, что машина не подтвердила reference envelope, и это записано, а не сглажено.

## Tests

- [x] Clean install, upgrade from prior schema, uninstall and reinstall scenarios.
- [~] Full end-to-end and recovery suite on certified matrix. Recovery — автоматически; end-to-end на живой matrix — ручной checklist `not run`.
- [x] Artifact inventory/secret scan and post-removal data integrity check.

## Components

- MTA resource/add-on packaging.
- User and operator documentation.
- Compatibility/release certification harness.

## Implementation status

### The gap ticket 30 left, closed first

Ticket 30 recorded that nothing in a running resource called
`Activation.update`, that no server code sent `ankigta:nextCard` or
`ankigta:statistics`, and that `Statistics.summarize` had no caller. Tickets 22
and 23 had built the decisions and deliberately left out the polling that feeds
them, so the canonical scenario this ticket certifies could not physically run.

**`client/spatial.lua`** is that half. It owns the runtime index — which
streamed element is which Map Entity, kept current by
`onClientElementStreamIn` / `StreamOut` / `onClientElementDestroy` — builds the
player observation (position, interior, dimension, speed, whether a review is
open) and hands both to `Activation.update`. A decision goes to the server as
`ankigta:requestSpatialOpen`; the server resolves the Map Entity to a card
itself and calls the same `openReviewModeFor` a manual opening uses. There is
one way into Review Mode, so spatial opening cannot skip Exact Card Admission.

**The server sends identities, never coordinates.** Where a Runtime Instance is
*now* is the client's to read off the live element (spec Implementation
Decision 14); a coordinate from the server would be the authored one wearing
the current one's name. One refresh in `server/main.lua` answers all three
questions about the same moment — the counters, the candidate set and the next
target — because asking twice lets them disagree. `/v1/cards/states` gained a
`nextCard` field so the marker points at Anki's own scheduler-top rather than
at something ANKIGTA chose.

**The cadence is 250 ms, and it is measured rather than argued.** The budget is
2 ms of average frame time for everything ANKIGTA draws and decides. One full
pass over 5,000 streamed, eligible Spatial Links is most of a millisecond, so
running it per frame spends a large fraction of the budget on the scan and
leaves the HUD and the marker to share the rest — which is what ticket 30's
3.4 ms and then 1.2 ms per-frame numbers were. `measure_spatial_frame` now
measures what the resource actually does: the marker and the HUD every frame,
plus one pass amortised at the interval it reads out of
`ANKIGTA.Spatial.pollIntervalMs()`. Changing the constant moves the number.
The prior attempt reached 250 ms from the other direction over 500 bindings and
rejected a per-render-frame scan for the same reason; that is a calibration
point, not the threshold.

The marker does **not** wait for the poll. It resolves the handful of entities
carrying one card every frame, so it follows a moving Runtime Instance frame by
frame — through `Indicator.setCandidateSource`, the one change to ticket 23's
module.

### The second finding: F7 had no filter

Story 51 requires search and filtering that do not depend on streaming, and
story 58 puts 150 ms on it. It is implemented rather than deferred: F7 has a
filter box that searches the stored record — identity, name, Entity Tag, type
and Spatial Link state — as a plain substring, so a name containing `-`, `(` or
`%` matches what the player typed. An entity whose Runtime Instance is
destroyed is found by the same words that find one standing in front of you,
which is the point of the story. `f7_entity_filter` is a new threshold in the
report; `search_filter` keeps the Card Picker's half of the same promise, and
its context no longer claims there is nothing else to time.

### Packaging

`python -m tools.package` builds two archives and an inventory. The MTA
resource unpacks as `ankigta/`, because MTA identifies a resource by its
directory name and the ACL right names it; the companion unpacks as Anki's own
add-on folder, with no top-level directory, because Anki unpacks an
`.ankiaddon` *into* the folder it creates. Entries are sorted, timestamps and
permissions fixed, so the same source builds the same bytes and a digest means
something.

`user_files/` is excluded and a test says so: it is where the add-on keeps the
connection token and the collection registry, so shipping it would publish a
secret and overwrite the user's state on update. The secret scan looks for the
*shape* of a credential rather than for today's value, and a test plants one to
prove the scan can fail.

### Certification

`tests/test_certification.py` runs against the **unpacked artifact**, not the
working tree: scripts loaded from the install directory, database opened inside
it. That matters more than it sounds, because MTA gives a resource its own
directory for files — so the user's Spatial Links live inside the folder the
removal instructions tell them to delete. Being able to remove exactly the
shipped inventory and find the database still readable afterwards is what makes
"take your data out first" an instruction rather than a hope.

**Two defects the suite found, both fixed here.**

`Store.listIdentityCollisions` returned only `map_id, entity_id, reason`, while
its only caller, `MapIdentity.recoverPersistedCollisions`, read the map's
locator, the entity's type and the link off the same row. Against a database
that had ever recorded an identity collision it concatenated a nil map name
into a path and raised — aborting `onResourceStart` before the presence refresh
and the authorization broadcast ran, on every start, forever. Ticket 29's
migration tests never saw it because they load the store alone and never fire
`onResourceStart`; a full start on a real upgraded database is what found it.
The query is now a join.

`onResourceStop` closed SQLite and nothing else, so stopping the resource left
every card of the session in the owned filtered deck with nothing running to
take them out (story 46). It now asks the companion to stop the session first.
That request is best effort and is documented as such — MTA tears a resource's
pending `fetchRemote` down with the resource — which is why the removal
instructions say to press `Pause studying` or `Stop` first.

### The open criterion this certification names rather than closes

A clean install is not an empty world. `meta.xml` ships `maps/ticket05.map` and
`maps/ticket07-matrix.map`, and `Store.open` seeds a Map Entity of its own, so
a user's first F7 lists entities they did not place. It is not closed here
because it is not a packaging problem: `Store.singleMapEntity` is the seam
`prepareObjectPendingMapSave` and its vehicle and ped siblings resolve through,
so removing the fixtures is a redesign of the identity path tickets 05 to 07
own. The exact set is pinned by a test so it cannot grow quietly, and
`docs/release/v1-certification.md` carries it as an open criterion with this
reason.

### Documentation

- `docs/operations/installation.md` — install, update, remove and reinstall for
  both pieces, the ACL right, Bound Anki Collection setup, first run, and what
  to do when it will not connect. No step opens SQLite or a `.map`.
- `docs/operations/backups-and-recovery.md` — what is copied, when, how many
  are kept, what the recovery screen does, and what is explicitly not covered.
- `docs/release/supported-versions.md` — the matrix, the rule that a build off
  it is unsupported until its suites pass, the suites themselves as runnable
  commands, and the accepted Map Editor and CEF limitations stated as they are.
- `docs/release/v1-certification.md` — what was proven, by what, and what is
  still `not run`. It states the verdict rather than restating numbers;
  `tests/test_release_record.py` holds it to
  `docs/release/v1-performance-report.json`.
- `README.md` — the way in.

### Performance

`python -m tests.perf --report docs/release/v1-performance-report.json` →
report clear, exit 0, all eight thresholds measured and inside their limits.
`KNOWN_OVER_LIMIT` stays empty because nothing was over.

The report says of itself that `machine.matchesReferenceEnvelope` is `false`
and names `storage_is_ssd`, `anki_desktop_installed` and `mta_server_available`
as unconfirmed. The numbers are real; the machine is not the documented one, in
ways it names. Taking them again on the certifying machine is the first item of
the ticket 30 checklist, which is still `not run`.

Automated evidence: `python -m pytest tests/ -q` → 1088 passed, 1 skipped;
`python -m mypy` strict clean; `python -m tests.perf` → clear, exit 0.

## Manual runtime checklist

Three, all `Status: not run`:

- `docs/checklists/ticket31-install-update-remove.md`
- `docs/checklists/ticket31-canonical-end-to-end.md`
- `docs/checklists/ticket30-performance-acceptance.md` (updated: the two open
  findings it warned about are closed, so what it observes has changed)

v1 is not certified for publication until these have been executed on the
certified matrix and their results recorded. An unexecuted runtime checklist is
neither a pass nor a failure, and a test asserts that none of them has been
marked otherwise.
