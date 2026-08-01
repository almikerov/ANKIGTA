# 25 — Teleport and Runtime Instance lifecycle

**What to build:** Прямой Teleport к Map Entity и устойчивое наблюдение Runtime Instance без safe-landing search или ANKIGTA-owned respawn.

**Blocked by:** 07 — Vehicle, ped and copied-ID collisions.

**Status:** ready-for-agent

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Verify programmatically — launching disposable copies is allowed, driving a GUI with screenshots or synthetic input is not, and the installed MTA/GTA tree stays unmodified. Acceptance that only a human can observe stays a manual checklist marked `not run`.

## Acceptance criteria

- [ ] Available Runtime Instance uses one consistent current position/interior/dimension snapshot.
- [ ] Unavailable/destroyed instance uses authored map position/interior/dimension.
- [ ] Teleport intentionally permits water, empty space, collision and vehicle interior.
- [ ] Occupied vehicle and all passengers teleport together.
- [ ] State race never mixes current coordinates with authored world context.
- [ ] Destruction removes runtime availability but preserves Map Entity/Spatial Link.
- [ ] ANKIGTA never respawns/recreates object, vehicle or ped; reappearance with same identity restores availability.

## Tests

- [ ] Repository-local runtime-state simulation plus a manual MTA object/vehicle/ped teleport checklist left `not run`.
- [ ] Driver/passenger and cross-interior/dimension tests.
- [ ] Destruction/reappearance/state-race tests.

## Components

- Server Map Entity/Runtime Instance registry.
- MTA teleport command.
- Vehicle/passenger handling.
