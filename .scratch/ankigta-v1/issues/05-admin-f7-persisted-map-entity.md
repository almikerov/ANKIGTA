# 05 — Admin-only F7 with one persisted Map Entity

**What to build:** Минимальный вертикальный world-management путь: Study Player с MTA Admin ACL открывает F7 и видит одну сохраняемую Map Entity; обычный игрок не получает UI или данные.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Server SQLite создаётся с versioned schema и хранит одну Map Entity поддерживаемого типа с authored transform/world context.
- [ ] Только вошедший аккаунт с требуемым MTA ACL right получает F7 и данные Map Entity.
- [ ] События обычного игрока отклоняются server-side и не раскрывают Map Entity или настройки.
- [ ] F7 различает Map Entity и текущую Runtime Instance и остаётся доступным, когда экземпляр не streamed/destroyed.
- [ ] Перезапуск MTA resource сохраняет запись и восстанавливает F7.
- [ ] Минимальная миграция схемы выполняется транзакционно и не повреждает существующую запись.

## Tests

- [ ] Real-MTA ACL integration test Admin vs ordinary player.
- [ ] SQLite create/restart/minimal-migration test.
- [ ] Client/server contract test отсутствующей Runtime Instance.

## Components

- MTA server SQLite store.
- MTA ACL authorization.
- Minimal F7 server/client UI.
- Runtime Instance observation.

