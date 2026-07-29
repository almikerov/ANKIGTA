# 20 — Minimal Review Mode

**What to build:** Модальный MTA Review Mode, который показывает question/answer через stock CEF, оставляет outer rating controls под Lua/dx и завершает одну Review Transaction.

**Blocked by:** 15 — One rating through MTA; 19 — Read-only card content capability.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Review Mode opens question, explicitly reveals answer and shows Again/Hard/Good/Easy for scheduler-admitted card.
- [ ] CEF получает только short-lived content capability; control API/token остаются server-side.
- [ ] `Esc` closes without rating if none submitted.
- [ ] После submit кнопки не создают второй logical transaction; confirmed result updates/close behavior.
- [ ] `Close after rating` closes after every accepted rating, including Again.
- [ ] F7/E/1–9/+/− не выполняют игровые ANKIGTA actions while modal.
- [ ] Alt+Tab не closes/rates и требует click-to-refocus.
- [ ] Close/failure restores captured cursor/control/camera/audio state, not unconditional defaults.

## Tests

- [ ] Real-MTA question → answer → rating end-to-end test.
- [ ] Esc, duplicate click, focus loss and Close after rating tests.
- [ ] CEF/resource failure cleanup test.

## Components

- MTA client Review Mode shell.
- Stock MTA CEF child surface.
- MTA server rating/session path.
