# 11 — Persistent Change History

**What to build:** Сохраняемую Change History последних 100 пользовательских изменений с multi-step Undo/Redo, работающую после закрытия F7 и перезапуска resource.

**Blocked by:** 08 — Card Picker and first Spatial Link.

**Status:** resolved

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Verify programmatically — launching disposable copies is allowed, driving a GUI with screenshots or synthetic input is not, and the installed MTA/GTA tree stays unmodified. Acceptance that only a human can observe stays a manual checklist marked `not run`.

## Acceptance criteria

- [x] Eligible server-owned edits записывают reversible before/after entry в той же логической транзакции.
- [x] Хранятся последние 100 entries; старые удаляются предсказуемо.
- [x] Undo/Redo переживают F7 close и resource restart.
- [x] Новая операция после Undo удаляет оставшуюся Redo branch.
- [x] Spatial Link, metadata, `Include in study` и ordinary user settings включены.
- [x] Connection settings, UI placement, Anki ratings, runtime events, automatic IDs, migrations и backups исключены.
- [x] Relink entity отменяется и восстанавливается целиком без duplicate active records.

## Tests

- [x] Persistence and 100-entry boundary tests.
- [x] Multi-step Undo/Redo and branch truncation tests.
- [x] Transaction-failure tests ensuring data/history cannot diverge.

## Components

- Server SQLite change journal.
- F7 Undo/Redo controls.
- Server command transaction boundary.

## Comments

- Implemented persistent SQLite Change History with a 100-entry bound, durable cursor, branch truncation, atomic before/after journaling, Undo/Redo F7 controls, and coverage for Spatial Link, metadata, `Include in study`, ordinary settings and relink.
- Automated repository checks for ticket 11 and its blocking ticket 08 pass. Installed MTA/GTA runtime validation remains `not run` under the repository runtime boundary.
