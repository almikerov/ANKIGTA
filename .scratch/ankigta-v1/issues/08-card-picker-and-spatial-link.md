# 08 — Card Picker and first Spatial Link

**What to build:** Study Player выбирает Anki Card через встроенный Card Picker и создаёт первую активную Spatial Link для идентифицированной Map Entity.

**Blocked by:** 04 — Bound Anki Collection identity; 06 — Object Pending Map Save.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Card Picker получает card state только из текущей Bound Anki Collection.
- [ ] Deck selection является только начальным Card Picker Deck Filter и не становится link/session scope.
- [ ] Spatial Link хранит полную Anki Card Identity и обеспечивает максимум одну карточку на Map Entity.
- [ ] Повторное использование одной карточки несколькими Map Entity разрешается после предупреждения со списком существующих связей.
- [ ] Pending/collision Map Entity нельзя превратить в активную Spatial Link.
- [ ] Перемещение карточки между колодами или изменение её текста/tag/template сохраняет связь.
- [ ] Из ANKIGTA в Anki не записывается ничего при создании связи.

## Tests

- [ ] End-to-end F7 → Card Picker → persisted Spatial Link → restart.
- [ ] Wrong collection, duplicate card use и deck-move tests.
- [ ] Contract tests search pagination/filtering and stale card state.

## Components

- F7/Card Picker UI.
- Companion card search/read API.
- Server Spatial Link persistence.

