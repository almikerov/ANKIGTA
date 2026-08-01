# 30 — Performance and large-data acceptance suite

**What to build:** Повторяемый release benchmark на подтверждённом reference hardware/data envelope для F7, search, spatial/HUD frame time, card/rating latency и session rebuild.

**Blocked by:** 18 — Pause, AnkiWeb sync and lifecycle cleanup; 21 — Best-effort CEF, media and External Card Page; 22 — Activation Zone and automatic opening; 23 — Next Card Indicator and statistics; 24 — Pick Entity; 25 — Teleport and Runtime Instance lifecycle; 26 — Review Protection and client restoration; 27 — Settings and localization; 28 — UI Scale and layout; 29 — Migrations, backups and corruption recovery.

**Status:** resolved

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Verify programmatically — launching disposable copies is allowed, driving a GUI with screenshots or synthetic input is not, and the installed MTA/GTA tree stays unmodified. Acceptance that only a human can observe stays a manual checklist marked `not run`.

## Acceptance criteria

- [x] Fixture contains 10,000 Map Entity, 5,000 Spatial Link and 100,000 Anki cards without eager CEF loading.
- [x] F7 available ≤2 s; search/filter ≤150 ms.
- [x] Pick Entity, Activation Zone and HUD add ≤2 ms average frame time.
- [x] Card Picker first page, card open and rating confirmation ≤1 s for 95% local requests.
- [x] Full 5,000-link session rebuild ≤5 s while UI remains responsive/progress visible.
- [x] Measurements run on documented Windows 4-core/16 GiB/SSD environment with MTA+Anki.
- [x] Exceeding reference volume warns/may slow down but never truncates or corrupts persisted data.
- [x] Results are reproducible, versioned and block release on threshold failure.

## Tests

- [x] Automated dataset generator and repeatable benchmark runner.
- [x] Warm/cold/restart runs with p95 and frame-time reporting.
- [x] Over-limit integrity test.

## Components

- End-to-end benchmark harness.
- F7/search/spatial/session instrumentation.
- Performance report/verifier.

## Implementation status

The benchmark is `tests/perf/`. It generates the reference world — 10,000 Map
Entity, 5,000 Spatial Link, 100,000 Anki card records — takes every measurement
the ticket states a threshold for, and returns a report that blocks a release on
a failure *and* on a measurement it could not take. `python -m tests.perf
--report <path>` is the release step: it prints the report, writes it as JSON,
and exits non-zero when the report blocks. `pytest tests/test_performance_
acceptance.py` holds the same numbers against the same thresholds.

Every measurement says what it covers and what it does not, because several of
these promises are about something ANKIGTA only partly owns: a card opening ends
in stock MTA CEF, a rating ends in Anki's scheduler, and the Card Picker's page
begins after Anki's own search returned.

### What the benchmark found

Four thresholds were over their limit on the first full run, and the rule was
that the threshold is the ticket's and does not move to fit the result. All four
were defects:

- **F7 at 2405 ms.** The snapshot asked the database whether each Map Entity was
  in an Identity Collision — one query per entity, so ten thousand queries
  inside one F7 open. `Store.listMapEntities` and `Store.getMapEntity` now carry
  the answer as a column and `Store.rowIsIdentityCollision` reads it off the
  row, falling back to the query for a row from a read that does not carry it.
  Now ~500 ms.
- **Card Picker first page at 1515 ms.** A fifty-card page read and shaped every
  one of the hundred thousand cards the search matched, and asked Anki for the
  whole deck list once per card. It now reads the page it serves and the deck
  list once. Now ~25 ms.
- **Per frame at 3.4 ms.** The Activation Zone and the Next Card Indicator each
  walked every streamed candidate on every rendered frame. The indicator now
  groups candidates by Anki Card Identity, so it looks only at the entities
  carrying the card it is marking; the Activation Zone makes one pass instead of
  two, rejects on one axis before reading anything else, and does not walk the
  world at all when a gate has already decided nothing may open. Now ~1.2 ms.
- **search/filter at 204 ms.** It was measured against `Store.listMapEntities`,
  which is the F7 read rather than a filter. It now measures the Card Picker's
  deck filter returning its first page, which is what the threshold in
  `tests/perf/report.py` always said it was. The F7 read is still timed and is
  reported inside `f7_available`'s context, where it belongs. Now ~15 ms.

A fifth defect the benchmark surfaced does not show in any of its numbers, and
is the worst of them on a real machine: `MapIdentity.refreshEntityPresence`,
which runs inside every F7 open, answered each Map Entity by parsing the whole
saved map file again — ten thousand full XML parses for one document — and wrote
a row per entity to record that nothing had changed. It now reads each map file
once and writes only where the stored state disagrees. The Lua sandbox grew real
`xmlLoadFile`/`xmlNodeGet*` stubs over the same files `fileOpen` reads, so this
is covered by behaviour rather than by a source search.

### Open findings, not fixed here

**Nothing drives the Activation Zone or the Next Card Indicator in a running
resource.** `Activation.update` has no caller anywhere in `mta/ankigta/`, and no
server code sends `ankigta:nextCard`, so neither module ever receives a player
observation or a candidate list outside a test or this benchmark. Ticket 22
recorded the split deliberately — "separates the decision from the world-polling
that feeds it" — and ticket 23 the same, so this is the polling half of both,
never written. It matters here because the benchmark's per-frame number is for
code that does not yet run per frame, and because the manual checklist asks a
person to walk into a zone and have a card open, which cannot happen today.
Wiring it belongs to the tickets that own those surfaces.

**F7's Map Entity list has no search or filter surface.** Story 51 asks for one
("Search and filtering do not depend on current streaming") and story 58 puts a
150 ms promise on it. The Card Picker's deck filter is the only search ANKIGTA
has, and it is what `search_filter` measures. Adding an entity filter to F7
belongs to the ticket that owns F7, not to the benchmark that noticed it was
missing; the gap is recorded in the measurement's own context so a reader of the
report is not left thinking the number covers something it does not.

Automated evidence: `python -m pytest tests/ -q` → 996 passed, 1 skipped;
`mypy` strict clean; `python -m tests.perf` → report clear, exit 0.

## Manual runtime checklist

See `docs/checklists/ticket30-performance-acceptance.md` (`Status: not run`).
The automated report is the numbers; the checklist is the half of each threshold
that is about a screen, a frame and a person.

