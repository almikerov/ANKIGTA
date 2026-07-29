# 30 — Performance and large-data acceptance suite

**What to build:** Повторяемый release benchmark на подтверждённом reference hardware/data envelope для F7, search, spatial/HUD frame time, card/rating latency и session rebuild.

**Blocked by:** 18 — Pause, AnkiWeb sync and lifecycle cleanup; 21 — Best-effort CEF, media and External Card Page; 22 — Activation Zone and automatic opening; 23 — Next Card Indicator and statistics; 24 — Pick Entity; 25 — Teleport and Runtime Instance lifecycle; 26 — Review Protection and client restoration; 27 — Settings and localization; 28 — UI Scale and layout; 29 — Migrations, backups and corruption recovery.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Fixture contains 10,000 Map Entity, 5,000 Spatial Link and 100,000 Anki cards without eager CEF loading.
- [ ] F7 available ≤2 s; search/filter ≤150 ms.
- [ ] Pick Entity, Activation Zone and HUD add ≤2 ms average frame time.
- [ ] Card Picker first page, card open and rating confirmation ≤1 s for 95% local requests.
- [ ] Full 5,000-link session rebuild ≤5 s while UI remains responsive/progress visible.
- [ ] Measurements run on documented Windows 4-core/16 GiB/SSD environment with MTA+Anki.
- [ ] Exceeding reference volume warns/may slow down but never truncates or corrupts persisted data.
- [ ] Results are reproducible, versioned and block release on threshold failure.

## Tests

- [ ] Automated dataset generator and repeatable benchmark runner.
- [ ] Warm/cold/restart runs with p95 and frame-time reporting.
- [ ] Over-limit integrity test.

## Components

- End-to-end benchmark harness.
- F7/search/spatial/session instrumentation.
- Performance report/verifier.

