# 11 — Persistent Change History

**What to build:** Сохраняемую Change History последних 100 пользовательских изменений с multi-step Undo/Redo, работающую после закрытия F7 и перезапуска resource.

**Blocked by:** 08 — Card Picker and first Spatial Link.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Eligible server-owned edits записывают reversible before/after entry в той же логической транзакции.
- [ ] Хранятся последние 100 entries; старые удаляются предсказуемо.
- [ ] Undo/Redo переживают F7 close и resource restart.
- [ ] Новая операция после Undo удаляет оставшуюся Redo branch.
- [ ] Spatial Link, metadata, `Include in study` и ordinary user settings включены.
- [ ] Connection settings, UI placement, Anki ratings, runtime events, automatic IDs, migrations и backups исключены.
- [ ] Relink entity отменяется и восстанавливается целиком без duplicate active records.

## Tests

- [ ] Persistence and 100-entry boundary tests.
- [ ] Multi-step Undo/Redo and branch truncation tests.
- [ ] Transaction-failure tests ensuring data/history cannot diverge.

## Components

- Server SQLite change journal.
- F7 Undo/Redo controls.
- Server command transaction boundary.

