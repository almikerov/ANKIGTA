# 27 — Settings and localization

**What to build:** Полный пользовательский settings path с authority по компонентам, validation/defaults и переключаемым Russian/English UI.

**Blocked by:** 03 — Connection config and reconnect; 12 — Full ANKIGTA Session; 20 — Minimal Review Mode; 22 — Activation Zone and automatic opening.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Server owns world/study settings and Change History; client owns presentation/input/audio; add-on owns listener/token/Anki internals.
- [ ] Manual connection overrides remain side-local and excluded from Change History.
- [ ] Radius, delay, speed, early-review policy, indicator, pause, protection and Close after rating use confirmed defaults/ranges.
- [ ] Invalid numeric input is rejected with localized reason, not silently clamped.
- [ ] Russian and English ship as UTF-8 resources; Russian Windows locale defaults Russian, otherwise English.
- [ ] Language switches without resource restart.
- [ ] Missing translation falls back to English and logs diagnostics.
- [ ] Card text, user Map Entity names, Entity Tag and Anki Tag are never automatically translated.
- [ ] Stable stored technical values do not change with language.

## Tests

- [ ] Authority/persistence/restart tests for every setting.
- [ ] Validation boundary and default migration tests.
- [ ] Localization completeness, runtime switch and fallback tests.

## Components

- Server/client/add-on settings stores.
- F7/Review Mode settings UI.
- UTF-8 localization system.

