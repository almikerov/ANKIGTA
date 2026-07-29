# 02 — Server-side Lua gateway

**What to build:** Сквозной health-путь от MTA Server через server-side Lua к companion add-on по numeric IPv4 loopback. Study Player видит состояние соединения в MTA, а client-side Lua и CEF не получают privileged control API.

**Blocked by:** 01 — Companion health and Anki version.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] MTA Server вызывает health operation только через server-side Lua и только на `127.0.0.1`.
- [ ] Ответ принимается лишь после проверки Content-Type, protocol version, JSON envelope и совпадающего `requestId`.
- [ ] Client-side Lua и CEF не содержат control gateway, connection token или операции rating/scheduler/collection.
- [ ] HTTP `200` с повреждённым envelope отображается как protocol error.
- [ ] Обычный запрос завершается не позднее 5 секунд и не блокирует MTA main loop.
- [ ] Успешное соединение не начинает обучение, не создаёт filtered deck и не открывает Review Mode.

## Tests

- [ ] Real-MTA integration test server-side `fetchRemote` → companion health.
- [ ] Негативные тесты LAN/`::1`/client-side access.
- [ ] Contract-тесты timeout, malformed JSON, wrong identity и late callback.

## Components

- MTA server resource.
- Companion control endpoint.
- Connection status presentation.

