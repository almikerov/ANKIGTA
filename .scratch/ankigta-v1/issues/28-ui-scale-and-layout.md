# 28 — UI Scale and layout

**What to build:** Масштабируемое и восстанавливаемое размещение F7, Review Mode и HUD на поддерживаемых разрешениях.

**Blocked by:** 20 — Minimal Review Mode; 23 — Next Card Indicator and statistics.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] UI Scale defaults 1, accepts 0.5–2, button step 0.05 and manual two-decimal input.
- [ ] Scale applies immediately; required primary actions remain reachable without horizontal page scrolling.
- [ ] F7/Review Mode drag by title; HUD moves only in Edit HUD layout.
- [ ] Modal warnings move with parent.
- [ ] Positions persist as normalized client coordinates outside Change History.
- [ ] Resolution/aspect/scale changes clamp windows so a title remains reachable.
- [ ] `Reset UI layout` is always visible/reachable.
- [ ] 1280×720, 1920×1080 and 3840×2160 pass layout tests.
- [ ] Connected gamepad triggers no ANKIGTA action and has no dedicated UI/support.

## Tests

- [ ] Automated layout screenshots/geometry assertions at three resolutions and scale boundaries.
- [ ] Drag, persistence, clamp and reset tests.
- [ ] Keyboard/mouse modal accessibility and gamepad-noise test.

## Components

- MTA client window/HUD layout manager.
- F7, Review Mode and HUD presentation.
- Client UI settings.

