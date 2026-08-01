# 31 — Packaging and release certification

**What to build:** Документированный install/update/remove path и финальный v1 certification на поддерживаемой Anki/MTA matrix, который доказывает canonical spatial-study scenario и отсутствие stranded/lost data.

**Blocked by:** 03 — Connection config and reconnect; 18 — Pause, AnkiWeb sync and lifecycle cleanup; 21 — Best-effort CEF, media and External Card Page; 29 — Migrations, backups and corruption recovery; 30 — Performance and large-data acceptance suite.

**Status:** ready-for-agent

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Verify programmatically — launching disposable copies is allowed, driving a GUI with screenshots or synthetic input is not, and the installed MTA/GTA tree stays unmodified. Acceptance that only a human can observe stays a manual checklist marked `not run`.

## Acceptance criteria

- [ ] Documentation covers MTA resource install/update/remove, manual companion add-on install/update/remove, Bound collection setup, backups/recovery and supported versions.
- [ ] Certification matrix initially pins Windows, Anki Desktop 26.05/V3/FSRS and MTA Server 1.6 build 24124.
- [ ] Another Anki/MTA build remains unsupported until relevant compatibility suites pass.
- [ ] Canonical end-to-end passes: Map Entity → Spatial Link → verified Save → Activation Zone → question → answer → rating → updated queue/target.
- [ ] New/learning/relearning/review/suspended/buried/not-due/Card missing/Entity missing acceptance scenarios pass.
- [ ] Install/update/pause/remove leave no card in owned filtered deck and preserve Spatial Link/database/map data.
- [ ] No required flow needs manual SQLite or `.map` editing.
- [ ] Diagnostics/documentation state accepted Map Editor and CEF limitations without stronger claims.
- [ ] All release gates and performance thresholds are recorded as passed for the published matrix.

## Tests

- [ ] Clean install, upgrade from prior schema, uninstall and reinstall scenarios.
- [ ] Full end-to-end and recovery suite on certified matrix.
- [ ] Artifact inventory/secret scan and post-removal data integrity check.

## Components

- MTA resource/add-on packaging.
- User and operator documentation.
- Compatibility/release certification harness.
