# 09 — Unlink, Replace card and Card missing

**What to build:** Полный карточный lifecycle Spatial Link: явный Unlink, атомарный Replace card и repair карточки, удалённой в Anki, без потери Map Entity metadata.

**Blocked by:** 08 — Card Picker and first Spatial Link.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] `Unlink` требует подтверждения с Map Entity и карточкой и удаляет только Spatial Link.
- [ ] Name, Entity Tag, radius и `Show radius` сохраняются после Unlink.
- [ ] `Replace card` показывает old/new identity и заменяет связь без промежуточного Unlink.
- [ ] Удалённый `cardId` становится Card missing и сохраняет запись/метаданные.
- [ ] Новый `cardId` не сопоставляется эвристически; Card missing ремонтируется только Replace card.
- [ ] Открытый review со старой карточкой завершается, затем очередь/статистика/markers пересчитываются.

## Tests

- [ ] End-to-end Unlink/Replace/restart tests.
- [ ] Real-Anki card deletion and replacement test.
- [ ] Duplicate-card warning and open-review state transition tests.

## Components

- F7 link actions.
- Server Spatial Link persistence.
- Companion card-state refresh.
- Session invalidation events.

