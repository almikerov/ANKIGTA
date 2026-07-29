# 26 — Review Protection and client restoration

**What to build:** Отдельные Review Protection и Disable player controls с exact snapshot restoration после обычного закрытия, CEF failure, disconnect и restart.

**Blocked by:** 20 — Minimal Review Mode.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Review Protection and Disable player controls are independent and default enabled.
- [ ] Protected Study Player and occupied vehicle receive no new damage; old health is not restored and world is not frozen.
- [ ] Other players receive no independent study protection; vehicle passengers may only benefit indirectly.
- [ ] Review Mode captures prior cursor, controls, camera, audio and protection state.
- [ ] Close/Esc/CEF failure/disconnect/resource stop restores captured values, not unconditional enabled defaults.
- [ ] No failure leaves cursor, controls, audio muting or damage protection stuck.
- [ ] Card audio and world muting remain separate controls.

## Tests

- [ ] Real-MTA damage/event coverage for player and occupied vehicle.
- [ ] Pre-disabled controls/muted audio snapshot restoration tests.
- [ ] CEF/resource/disconnect crash cleanup tests.

## Components

- MTA client Review Mode state restoration.
- Server/client Review Protection.
- Input/audio/camera adapters.

