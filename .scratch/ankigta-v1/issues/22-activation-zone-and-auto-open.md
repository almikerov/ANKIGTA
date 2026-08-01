# 22 — Activation Zone and automatic opening

**What to build:** Пространственное открытие linked card внутри физической Activation Zone с per-entity radius, global delay/speed gate и движущейся Runtime Instance.

**Blocked by:** 08 — Card Picker and first Spatial Link; 20 — Minimal Review Mode.

**Status:** resolved

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Verify programmatically — launching disposable copies is allowed, driving a GUI with screenshots or synthetic input is not, and the installed MTA/GTA tree stays unmodified. Acceptance that only a human can observe stays a manual checklist marked `not run`.

## Acceptance criteria

- [x] New Map Entity copies current global radius default 3 m; range 0.5–50 m, step 0.5 m, invalid/zero rejected without clamping.
- [x] Activation Zone follows live moving Runtime Instance and disappears on destruction without deleting link.
- [x] Global delay defaults 1 sec, accepts 0–60 with two decimals; leaving all eligible zones cancels countdown.
- [x] Nearest eligible entity is recalculated during countdown.
- [x] Vehicle speed gate is always active, defaults 10000 km/h; zero requires complete stop.
- [x] Spatial activation occurs only in current interior/dimension; changing either cancels pending opening.
- [x] Already open Review Mode survives world-context/map/runtime/link changes and recalculates afterward.
- [x] Pending/missing/unavailable/excluded links never auto-open.

## Tests

- [x] Repository-local spatial simulation plus a manual MTA moving vehicle/ped/object/destruction checklist left `not run`.
- [x] Radius/delay/speed boundary and nearest-target race tests.
- [x] Interior/dimension change and review-in-progress tests.

## Components

- Server spatial eligibility/index.
- MTA client Activation Zone visualization/detection.
- Automatic-open coordinator.
- Review Mode integration.

## Implementation status

- `client/activation.lua` separates the decision from the world-polling that
  feeds it, so the rules that matter are testable without a game running: the
  update takes a player observation and a candidate list and returns either
  nothing or the card to open.
- A zone exists only where its Runtime Instance does. An unstreamed or
  destroyed instance produces no zone and cancels a pending opening, while its
  Spatial Link is left completely alone.
- Radius is validated, never clamped: a silently corrected 200 m would leave the
  user with a zone they never chose. Range 0.5–50 m on a 0.5 m step; zero and
  non-numeric are rejected with distinct reasons.
- Re-targeting restarts the countdown rather than inheriting the previous
  entity's elapsed time, so walking past one zone into another cannot open the
  second instantly.
- The speed gate is always applied; its default is simply far above anything
  reachable. Zero means a complete stop.
- An open card outranks the world: map, runtime and link changes may happen
  underneath it, and activation recalculates only once it closes.

Automated evidence: `pytest -q tests/test_activation_zone.py` → 35 passed;
full suite 389 passed; mypy strict clean.

## Manual runtime checklist

See `docs/checklists/ticket22-activation-zone.md` (`Status: not run`).
