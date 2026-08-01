# 21 — Best-effort CEF, media and External Card Page

**What to build:** Расширить Review Mode до принятого stock-MTA best-effort contract: реальные HTML/CSS/JavaScript/media, non-blocking warnings, external resources/navigation и optional `Вернуться к карточке`.

**Blocked by:** 20 — Minimal Review Mode.

**Status:** resolved

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Verify programmatically — launching disposable copies is allowed, driving a GUI with screenshots or synthetic input is not, and the installed MTA/GTA tree stays unmodified. Acceptance that only a human can observe stays a manual checklist marked `not run`.

## Acceptance criteria

- [~] Card HTML/CSS/JavaScript/media references передаются без намеренного удаления/обрезки; pixel/behavioral equivalence с Anki не обещается. Ничего не вырезается по пути; сама точность рендера проверяется только глазами.
- [x] Rendering/script/template/media errors показывают warning и оставляют Again/Hard/Good/Easy enabled.
- [x] Missing media показывает placeholder/warning и не блокирует rating.
- [~] External HTTP(S) resources используют stock MTA domain permissions. Клиент вносит в whitelist только loopback; внешние ресурсы остаются под stock-разрешениями MTA — проверяется вручную.
- [x] Main-frame navigation создаёт External Card Page, но outer Review Mode и rating controls остаются доступны.
- [x] `Вернуться к карточке` выдаёт fresh capability для current side и остаётся optional.
- [~] Card-visible `window.mta` stub допускается, но remote content не выполняет privileged dispatch. Prototype 0006: browser-process отбрасывает TriggerLuaEvent для remote browser; проверка в ручном чеклисте.
- [~] Popup остаётся stock-blocked; system-browser handoff/download behavior не заявляются как supported. OnBeforePopup всегда блокирует; handoff и загрузки не заявлены.
- [x] Card audio и game-world muting регулируются раздельно.

## Tests

- [~] Repository-local corpus harness plus a manual MTA CEF HTML/CSS/JS/media/audio checklist left `not run`. Корпус готов с прототипа 0006; сверка требует клиента.
- [x] External resource/navigation/return and popup tests.
- [x] Focus, resource restart and cleanup lifecycle tests.
- [x] Negative privileged-dispatch test.

## Components

- MTA CEF card surface.
- Companion rendering/media.
- Review Mode warnings and return action.
- Client audio settings.

## Implementation status

- Card content reaches CEF exactly as the companion rendered it; nothing is
  stripped or truncated on the way. Equivalence with Anki Desktop is explicitly
  not promised — this is the best-effort contract ADR 0027 accepted.
- Every failure is a warning, never a blocker. A broken template, a failed load
  and a missing medium all leave Again/Hard/Good/Easy enabled: a card that
  fails to render is still a card the player can answer.
- Main-frame navigation becomes an External Card Page. MTA reports navigation
  after the fact and it cannot be cancelled from Lua (prototype 0006), so
  instead of pretending to prevent it, the outer Review Mode and rating bar stay
  usable and a `Вернуться к карточке` control appears.
- That control is optional and never automatic — the card may have navigated
  somewhere the player actually wanted to read — and it requests a *fresh*
  capability for the side that was open, since the previous one has expired or
  been spent.
- Card audio and game-world audio are separate: muting a noisy card does not
  silence GTA, and playing in silence does not force card audio off.

Automated evidence: `pytest -q tests/test_review_mode_behavior.py` → 38 passed;
full suite 397 passed; mypy strict clean.

## Manual runtime checklist

See `docs/checklists/ticket21-cef-best-effort.md` (`Status: not run`). This is
the ticket that most depends on it: fidelity is exactly the thing no automated
check here can judge.
