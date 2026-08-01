# 24 — Pick Entity

**What to build:** Модальный world-selection путь от F7 до первой видимой управляемой Runtime Instance под crosshair с корректным occlusion и восстановлением ввода.

**Blocked by:** 05 — Admin-only F7 with one persisted Map Entity; 08 — Card Picker and first Spatial Link.

**Status:** resolved

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Verify programmatically — launching disposable copies is allowed, driving a GUI with screenshots or synthetic input is not, and the installed MTA/GTA tree stays unmodified. Acceptance that only a human can observe stays a manual checklist marked `not run`.

## Acceptance criteria

- [x] Entering Pick Entity hides F7, enables movement/look and blocks shooting, vehicle entry and ordinary interactions.
- [x] Left click selects first visible managed Runtime Instance under crosshair; walls occlude and streaming is the only distance bound.
- [x] Unmanaged/unloaded/outside-loaded-map element is rejected with reason.
- [x] Destroyed/unstreamed entity can be selected only through F7 list.
- [x] Esc cancels; success opens F7 focused on selected Map Entity.
- [x] Success/cancel/error/resource stop restore exact prior cursor/control state.
- [x] Mode can supply a valid target to Relink entity without bypassing target eligibility.

## Tests

- [x] Source-contract/raycast simulation.
- [x] Streaming boundary and invalid target diagnostics.
- [x] Modal input cleanup on every exit path.
- [ ] Manual MTA occlusion/selection checklist — left `not run` per the environment boundary.

## Components

- MTA client Pick Entity state machine.
- Raycast/streaming integration.
- F7 focus/relink handoff.
- Server target validation.

## Implementation status

Repository-local acceptance evidence:

- [x] Modal Pick Entity state machine captures/restores the prior cursor and
  every control it changes; F7 is gated while the modal is active.
- [x] Client raycast stops at the first collision, rejects unmanaged or
  unstreamed hits, and sends only eligible element candidates to the server.
- [x] Server validation applies the Study Player ACL, supported element type,
  stock Map Editor identity, persisted Map Entity lookup and loaded-resource
  ownership checks.
- [x] Success returns persistent map/entity IDs and reopens F7 with that row
  focused; Relink preview can enter the same mode with `relink` purpose.

The repository-local test suite for this ticket passes. The real MTA
occlusion/streaming/input smoke test remains `not run`.

## Manual runtime checklist

See `docs/checklists/ticket24-pick-entity.md` (`Status: not run`).

## Answer

Implemented only the Pick Entity client/server seam: modal input lifecycle,
crosshair raycast with stock occlusion, client streaming checks, server-side
Map Entity eligibility validation, F7 focus handoff and Relink target handoff.
No installed MTA/GTA runtime was launched or inspected. The manual runtime
checklist remains explicitly `not run`.
