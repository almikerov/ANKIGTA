# 03 — Connection config and reconnect

**What to build:** Пользовательский путь первоначальной настройки и последующего восстановления Companion Connection: автоматический port/token, versioned connection config, advanced Manual Connection Mode, last-known-good rollback и ручная кнопка `Подключиться`.

**Blocked by:** 02 — Server-side Lua gateway.

**Status:** ready-for-agent

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Do not launch or access installed MTA/GTA; use the read-only MTA source reference, official manuals and repository-local tests. Prepare any real-runtime verification as a manual checklist and leave it `not run` unless the user separately authorizes runtime validation.

## Acceptance criteria

- [x] После однократного выбора MTA resource folder companion выбирает свободный loopback-порт, генерирует токен и публикует configuration без ручного копирования.
- [x] Candidate полностью проверяется до atomic replace; хранится ровно одна подтверждённая предыдущая версия.
- [x] MTA проверяет format/version/protocol identity и использует last-known-good с явной ошибкой, если новая версия непригодна.
- [x] Manual port/token включает Manual Connection Mode только на изменённой стороне и не перезаписывается автоматикой.
- [x] Effective-config mismatch блокирует соединение до ручного согласования либо возврата обеих сторон в Automatic Connection Mode.
- [x] Токен маскируется и исключается из обычных логов; явный пустой токен работает с закрываемым предупреждением.
- [x] Auto-reconnect и `Подключиться` восстанавливают соединение, но оставляют studying/session/Review Mode выключенными.

## Tests

- [x] Fault-injection тесты temporary write, validation failure, replace failure и rollback.
- [x] Repository-local transport simulation for occupied port, port change, wrong/empty token, disconnect and reconnect.
- [ ] Manual MTA runtime checklist — not run (requires separately authorized runtime validation).
- [x] Secret scan UI/log/config diagnostics.

### Manual MTA runtime checklist (not run)

1. In a disposable local MTA resource, start ANKIGTA and verify the first
   automatic connection publishes `connection.json` with loopback host, a
   free port and a generated token.
2. Occupy the published port, restart the companion, and verify the revision
   changes while the token remains stable.
3. Exercise correct, wrong and explicitly empty-token requests; verify that
   mismatch blocks connection and that the empty-token warning can be closed.
4. Corrupt `connection.json` and verify last-known-good rollback is reported
   without exposing the token.
5. Stop and restart the companion; verify automatic reconnect and the manual
   `Подключиться` action restore only the connection state, with study/session/
   Review Mode still disabled.

## Components

- Companion connection-config publisher.
- MTA config reader and gateway.
- Add-on/MTA advanced settings.
- Connection status UI.
