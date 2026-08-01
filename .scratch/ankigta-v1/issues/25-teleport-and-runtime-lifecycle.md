# 25 — Teleport and Runtime Instance lifecycle

**What to build:** Прямой Teleport к Map Entity и устойчивое наблюдение Runtime Instance без safe-landing search или ANKIGTA-owned respawn.

**Blocked by:** 07 — Vehicle, ped and copied-ID collisions.

**Status:** resolved

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Verify programmatically — launching disposable copies is allowed, driving a GUI with screenshots or synthetic input is not, and the installed MTA/GTA tree stays unmodified. Acceptance that only a human can observe stays a manual checklist marked `not run`.

## Acceptance criteria

- [x] Available Runtime Instance uses one consistent current position/interior/dimension snapshot.
- [x] Unavailable/destroyed instance uses authored map position/interior/dimension.
- [~] Teleport intentionally permits water, empty space, collision and vehicle interior. Никакого поиска безопасной точки в коде нет (проверяется тестом); фактическое приземление — ручная проверка.
- [x] Occupied vehicle and all passengers teleport together.
- [x] State race never mixes current coordinates with authored world context.
- [x] Destruction removes runtime availability but preserves Map Entity/Spatial Link.
- [x] ANKIGTA never respawns/recreates object, vehicle or ped; reappearance with same identity restores availability.

## Tests

- [~] Repository-local runtime-state simulation plus a manual MTA object/vehicle/ped teleport checklist left `not run`.
- [x] Driver/passenger and cross-interior/dimension tests.
- [x] Destruction/reappearance/state-race tests.

## Components

- Server Map Entity/Runtime Instance registry.
- MTA teleport command.
- Vehicle/passenger handling.

## Implementation status

- `server/teleport.lua` resolves one consistent snapshot: position, interior and
  dimension all come from the same source. If the Runtime Instance is missing,
  destroyed, or disappears *between* the reads, the entire live reading is
  discarded and the authored values are used — a half-live snapshot would drop
  the player somewhere that exists in neither place. Mutation-checked: removing
  the post-read availability re-check fails the state-race test.
- `Teleport.findRuntimeInstance` resolves by persistent identity rather than by
  a remembered element. That is what makes ADR 0004 work: ANKIGTA recreates
  nothing, so when the map or the owning resource brings an entity back, it is
  recognised as the same Map Entity and its Spatial Link becomes usable again.
- `teleportPlayerToMapEntity` is the entry point, ACL-gated and exported. The
  client names a Map Entity and the server resolves the coordinates, so a client
  cannot ask to be moved to arbitrary ones.
- No safe-landing search (ADR 0005): a source test keeps `processLineOfSight`,
  `getGroundPosition`, `isLineOfSightClear` and `getWaterLevel` out entirely.

**Defect found by code review, in this ticket's own code.** Occupants were
iterated with `ipairs`. MTA's `CLuaVehicleDefs::GetVehicleOccupants` keys the
table by **seat starting at 0** and omits empty seats, so `ipairs` began at 1 —
skipping the driver, who is the teleporting player — and stopped at the first
empty seat. Combined with the interior asymmetry below, the driver would have
been left in interior 0 while their car went to interior 3.

The test suite did not catch it because the harness stub built a dense, 1-based
table: the one shape MTA never returns. The stub now reproduces the real seat
keying, which made both passenger tests fail immediately. Fixed with `pairs`,
mutation-checked, and covered by a test that puts the driver in seat 0 with a
gap at seat 1.

**Engine asymmetry, also verified in source.**
`CStaticFunctionDefinitions::SetElementDimension` loops a vehicle's seats and
sets each occupant's dimension; `SetElementInterior` does not. Occupants
therefore get their interior set explicitly, with the citation in a comment so
it is not later "simplified" away.

Automated evidence: `pytest -q tests/test_teleport.py` → 16 passed; full suite
423 passed; mypy strict clean.

## Manual runtime checklist

See `docs/checklists/ticket25-teleport.md` (`Status: not run`).
