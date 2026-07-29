# 24 — Pick Entity

**What to build:** Модальный world-selection путь от F7 до первой видимой управляемой Runtime Instance под crosshair с корректным occlusion и восстановлением ввода.

**Blocked by:** 05 — Admin-only F7 with one persisted Map Entity; 08 — Card Picker and first Spatial Link.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Entering Pick Entity hides F7, enables movement/look and blocks shooting, vehicle entry and ordinary interactions.
- [ ] Left click selects first visible managed Runtime Instance under crosshair; walls occlude and streaming is the only distance bound.
- [ ] Unmanaged/unloaded/outside-loaded-map element is rejected with reason.
- [ ] Destroyed/unstreamed entity can be selected only through F7 list.
- [ ] Esc cancels; success opens F7 focused on selected Map Entity.
- [ ] Success/cancel/error/resource stop restore exact prior cursor/control state.
- [ ] Mode can supply a valid target to Relink entity without bypassing target eligibility.

## Tests

- [ ] Real-MTA raycast/occlusion and managed/unmanaged selection tests.
- [ ] Streaming boundary and invalid target diagnostics.
- [ ] Modal input cleanup on every exit path.

## Components

- MTA client Pick Entity state machine.
- Raycast/streaming integration.
- F7 focus/relink handoff.
- Server target validation.

