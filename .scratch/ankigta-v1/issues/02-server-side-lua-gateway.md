# 02 — Server-side Lua gateway

**What to build:** Сквозной health-путь от MTA Server через server-side Lua к companion add-on по numeric IPv4 loopback. Study Player видит состояние соединения в MTA, а client-side Lua и CEF не получают privileged control API.

**Blocked by:** 01 — Companion health and Anki version.

**Status:** resolved

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Verify programmatically — launching disposable copies is allowed, driving a GUI with screenshots or synthetic input is not, and the installed MTA/GTA tree stays unmodified. Acceptance that only a human can observe stays a manual checklist marked `not run`.

## Acceptance criteria

- [x] MTA Server вызывает health operation только через server-side Lua и только на `127.0.0.1`.
- [x] Ответ принимается лишь после проверки Content-Type, protocol version, JSON envelope и совпадающего `requestId`.
- [x] Client-side Lua и CEF не содержат control gateway, connection token или операции rating/scheduler/collection.
- [x] HTTP `200` с повреждённым envelope отображается как protocol error.
- [x] Обычный запрос завершается не позднее 5 секунд и не блокирует MTA main loop.
- [x] Успешное соединение не начинает обучение, не создаёт filtered deck и не открывает Review Mode.

## Tests

- [x] Real-MTA integration test server-side `fetchRemote` → companion health.
- [x] Негативные тесты LAN/`::1`/client-side access.
- [x] Contract-тесты timeout, malformed JSON, wrong identity и late callback.

## Components

- MTA server resource.
- Companion control endpoint.
- Connection status presentation.
