# 21 — Best-effort CEF, media and External Card Page

**What to build:** Расширить Review Mode до принятого stock-MTA best-effort contract: реальные HTML/CSS/JavaScript/media, non-blocking warnings, external resources/navigation и optional `Вернуться к карточке`.

**Blocked by:** 20 — Minimal Review Mode.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Card HTML/CSS/JavaScript/media references передаются без намеренного удаления/обрезки; pixel/behavioral equivalence с Anki не обещается.
- [ ] Rendering/script/template/media errors показывают warning и оставляют Again/Hard/Good/Easy enabled.
- [ ] Missing media показывает placeholder/warning и не блокирует rating.
- [ ] External HTTP(S) resources используют stock MTA domain permissions.
- [ ] Main-frame navigation создаёт External Card Page, но outer Review Mode и rating controls остаются доступны.
- [ ] `Вернуться к карточке` выдаёт fresh capability для current side и остаётся optional.
- [ ] Card-visible `window.mta` stub допускается, но remote content не выполняет privileged dispatch.
- [ ] Popup остаётся stock-blocked; system-browser handoff/download behavior не заявляются как supported.
- [ ] Card audio и game-world muting регулируются раздельно.

## Tests

- [ ] Real-MTA corpus smoke: HTML/CSS/JS, local media, audio, missing/broken media/template.
- [ ] External resource/navigation/return and popup tests.
- [ ] Focus, resource restart and cleanup lifecycle tests.
- [ ] Negative privileged-dispatch test.

## Components

- MTA CEF card surface.
- Companion rendering/media.
- Review Mode warnings and return action.
- Client audio settings.

