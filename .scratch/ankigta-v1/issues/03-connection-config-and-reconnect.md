# 03 — Connection config and reconnect

**What to build:** Пользовательский путь первоначальной настройки и последующего восстановления Companion Connection: автоматический port/token, versioned connection config, advanced Manual Connection Mode, last-known-good rollback и ручная кнопка `Подключиться`.

**Blocked by:** 02 — Server-side Lua gateway.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] После однократного выбора MTA resource folder companion выбирает свободный loopback-порт, генерирует токен и публикует configuration без ручного копирования.
- [ ] Candidate полностью проверяется до atomic replace; хранится ровно одна подтверждённая предыдущая версия.
- [ ] MTA проверяет format/version/protocol identity и использует last-known-good с явной ошибкой, если новая версия непригодна.
- [ ] Manual port/token включает Manual Connection Mode только на изменённой стороне и не перезаписывается автоматикой.
- [ ] Effective-config mismatch блокирует соединение до ручного согласования либо возврата обеих сторон в Automatic Connection Mode.
- [ ] Токен маскируется и исключается из обычных логов; явный пустой токен работает с закрываемым предупреждением.
- [ ] Auto-reconnect и `Подключиться` восстанавливают соединение, но оставляют studying/session/Review Mode выключенными.

## Tests

- [ ] Fault-injection тесты temporary write, validation failure, replace failure и rollback.
- [ ] Real-MTA тест occupied port, port change, wrong/empty token, disconnect и reconnect.
- [ ] Secret scan UI/log/config diagnostics.

## Components

- Companion connection-config publisher.
- MTA config reader and gateway.
- Add-on/MTA advanced settings.
- Connection status UI.

