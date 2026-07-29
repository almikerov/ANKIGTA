# 22 — Activation Zone and automatic opening

**What to build:** Пространственное открытие linked card внутри физической Activation Zone с per-entity radius, global delay/speed gate и движущейся Runtime Instance.

**Blocked by:** 08 — Card Picker and first Spatial Link; 20 — Minimal Review Mode.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] New Map Entity copies current global radius default 3 m; range 0.5–50 m, step 0.5 m, invalid/zero rejected without clamping.
- [ ] Activation Zone follows live moving Runtime Instance and disappears on destruction without deleting link.
- [ ] Global delay defaults 1 sec, accepts 0–60 with two decimals; leaving all eligible zones cancels countdown.
- [ ] Nearest eligible entity is recalculated during countdown.
- [ ] Vehicle speed gate is always active, defaults 10000 km/h; zero requires complete stop.
- [ ] Spatial activation occurs only in current interior/dimension; changing either cancels pending opening.
- [ ] Already open Review Mode survives world-context/map/runtime/link changes and recalculates afterward.
- [ ] Pending/missing/unavailable/excluded links never auto-open.

## Tests

- [ ] Real-MTA moving vehicle/ped/object and destruction tests.
- [ ] Radius/delay/speed boundary and nearest-target race tests.
- [ ] Interior/dimension change and review-in-progress tests.

## Components

- Server spatial eligibility/index.
- MTA client Activation Zone visualization/detection.
- Automatic-open coordinator.
- Review Mode integration.

