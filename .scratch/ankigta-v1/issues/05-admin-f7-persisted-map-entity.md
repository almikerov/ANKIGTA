# 05 — Admin-only F7 with one persisted Map Entity

**What to build:** Минимальный вертикальный world-management путь: Study Player с MTA Admin ACL открывает F7 и видит одну сохраняемую Map Entity; обычный игрок не получает UI или данные.

**Blocked by:** None — can start immediately.

**Status:** resolved

## Acceptance criteria

- [x] Server SQLite создаётся с versioned schema и хранит одну Map Entity поддерживаемого типа с authored transform/world context.
- [x] Только вошедший аккаунт с требуемым MTA ACL right получает F7 и данные Map Entity.
- [x] События обычного игрока отклоняются server-side и не раскрывают Map Entity или настройки.
- [x] F7 различает Map Entity и текущую Runtime Instance и остаётся доступным, когда экземпляр не streamed/destroyed.
- [x] Перезапуск MTA resource сохраняет запись и восстанавливает F7.
- [x] Минимальная миграция схемы выполняется транзакционно и не повреждает существующую запись.

## Tests

- [ ] Real-MTA ACL integration test Admin vs ordinary player — оставлен для ручной проверки по указанию пользователя; MTA автоматически не запускался.
- [x] SQLite create/restart/minimal-migration test.
- [x] Client/server source-contract test отсутствующей Runtime Instance.

## Components

- MTA server SQLite store.
- MTA ACL authorization.
- Minimal F7 server/client UI.
- Runtime Instance observation.

## Answer

Реализован минимальный admin-only F7 vertical slice: versioned SQLite store с одной object Map Entity, server-side ACL gate, разделение authored Map Entity и наблюдаемой Runtime Instance, повторная авторизация клиента после перезапуска ресурса и транзакционная миграция v1 → v2. Blocking edges тикетов 06, 07 и 29 не пересечены.

Финальный автоматический набор ограничен source-contract и автономными SQLite-тестами и не запускает MTA. Real-MTA ACL сценарий остаётся явно отмеченным для ручной проверки.
