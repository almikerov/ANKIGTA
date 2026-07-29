# 23 — Next Card Indicator and statistics

**What to build:** HUD, Next Card Indicator и уникальные `Total/New/Learning/Due/Early`, согласованные с наблюдаемым Anki state и текущим Active Map Set.

**Blocked by:** 13 — Early, unavailable and daily-limit behavior; 22 — Activation Zone and automatic opening.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Statistics count unique Anki Card Identity, not number of Spatial Link.
- [ ] `Total` is union of `New`, `Learning`, `Due`, `Early`; Early always visible and zero when disabled/empty.
- [ ] Suspended/Buried/Card missing/Pending Map Save/excluded maps do not count.
- [ ] Counts refresh after Anki notification, link/map/session changes and completed review without reimplementing scheduler.
- [ ] Indicator modes exactly: sphere+minimap, minimap only, nothing; default nothing and no sphere-only mode.
- [ ] Multiple entities for next card mark only nearest eligible entity.
- [ ] Temporary sphere does not alter/create Activation Zone; overlap renders one emphasized/pulsing sphere.
- [ ] Indicator obeys current runtime availability/world context while queue remains global.

## Tests

- [ ] Scheduler-state/statistics matrix and duplicate-link tests.
- [ ] Active Map Set and status refresh tests.
- [ ] Real-MTA indicator mode, nearest target and overlap visual behavior tests.

## Components

- Companion statistics query.
- Server aggregation/next-target selection.
- MTA Statistics HUD, Minimap Blip and sphere renderer.

