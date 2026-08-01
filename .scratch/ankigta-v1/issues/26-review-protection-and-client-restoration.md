# 26 — Review Protection and client restoration

**What to build:** Отдельные Review Protection и Disable player controls с exact snapshot restoration после обычного закрытия, CEF failure, disconnect и restart.

**Blocked by:** 20 — Minimal Review Mode.

**Status:** resolved

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Verify programmatically — launching disposable copies is allowed, driving a GUI with screenshots or synthetic input is not, and the installed MTA/GTA tree stays unmodified. Acceptance that only a human can observe stays a manual checklist marked `not run`.

## Acceptance criteria

- [x] Review Protection and Disable player controls are independent and default enabled.
- [~] Protected Study Player and occupied vehicle receive no new damage; old health is not restored and world is not frozen. Реализовано через damage-proof игрока и занятого транспорта; какие именно источники урона покрыты — ручная проверка.
- [~] Other players receive no independent study protection; vehicle passengers may only benefit indirectly. Защита ставится только localPlayer и его транспорту; проверка на живых игроках ручная.
- [x] Review Mode captures prior cursor, controls, camera, audio and protection state.
- [x] Close/Esc/CEF failure/disconnect/resource stop restores captured values, not unconditional enabled defaults.
- [x] No failure leaves cursor, controls, audio muting or damage protection stuck.
- [x] Card audio and world muting remain separate controls.

## Tests

- [~] Source-contract/event simulation plus a manual MTA damage-coverage checklist left `not run`.
- [x] Pre-disabled controls/muted audio snapshot restoration tests.
- [x] CEF/resource/disconnect crash cleanup tests.

## Components

- MTA client Review Mode state restoration.
- Server/client Review Protection.
- Input/audio/camera adapters.

## Implementation status

- Review Protection and Disable player controls are two settings, both on by
  default and genuinely independent: wanting protection without losing the
  controls is a reasonable thing to want, so neither implies the other.
- Protection prevents **new** damage to the Study Player and the vehicle they
  occupy. It is not a heal and it does not freeze anything: a source test
  enforces that no health, armour, game-speed or freeze call appears in the
  module.
- Only `localPlayer` and their vehicle are touched, so another player nearby
  gets nothing, and a passenger benefits only because the vehicle does.
- Open captures cursor, the controls it disables, camera target, radio channel,
  world sound and the damage-proof state of both player and vehicle. Close
  restores those captured values — protection another resource had already set
  survives a review, because restoring ANKIGTA's default would silently strip it.
- Every exit restores: normal close, Esc, a browser that could not be created,
  authorization loss and resource stop are each covered by a test.

Automated evidence: `pytest -q tests/test_review_mode_behavior.py` → 48 passed;
full suite 407 passed; mypy strict clean.

## Manual runtime checklist

See `docs/checklists/ticket26-review-protection.md` (`Status: not run`).
