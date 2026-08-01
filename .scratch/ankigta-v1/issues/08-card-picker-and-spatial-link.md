# 08 — Card Picker and first Spatial Link

**What to build:** Study Player выбирает Anki Card через встроенный Card Picker и создаёт первую активную Spatial Link для идентифицированной Map Entity.

**Blocked by:** 04 — Bound Anki Collection identity; 06 — Object Pending Map Save.

**Status:** resolved

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Verify programmatically — launching disposable copies is allowed, driving a GUI with screenshots or synthetic input is not, and the installed MTA/GTA tree stays unmodified. Acceptance that only a human can observe stays a manual checklist marked `not run`.

## Acceptance criteria

- [x] Card Picker получает card state только из текущей Bound Anki Collection.
- [x] Deck selection является только начальным Card Picker Deck Filter и не становится link/session scope.
- [x] Spatial Link хранит полную Anki Card Identity и обеспечивает максимум одну карточку на Map Entity.
- [x] Повторное использование одной карточки несколькими Map Entity разрешается после предупреждения со списком существующих связей.
- [x] Pending/collision Map Entity нельзя превратить в активную Spatial Link.
- [x] Перемещение карточки между колодами или изменение её текста/tag/template сохраняет связь.
- [x] Из ANKIGTA в Anki не записывается ничего при создании связи.

## Tests

- [ ] End-to-end F7 → Card Picker → persisted Spatial Link → restart.
- [x] Wrong collection, duplicate card use и deck-move tests.
- [x] Contract tests search pagination/filtering and stale card state.

## Components

- F7/Card Picker UI.
- Companion card search/read API.
- Server Spatial Link persistence.

## Implementation status

Repository-local acceptance evidence:

- [x] AC-1 Bound Anki Collection is the sole Card Picker source.
- [x] AC-2 Deck selection remains only the initial Card Picker Deck Filter.
- [x] AC-3 Spatial Link stores collection UUID plus cardId and enforces one link per Map Entity.
- [x] AC-4 Reusing a card warns with existing Spatial Links and remains allowed.
- [x] AC-5 Pending Map Save and Identity Collision cannot activate.
- [x] AC-6 Card identity survives deck moves and card metadata changes.
- [x] AC-7 Link creation has no Anki write path.

Automated checks cover wrong collection, duplicate-card reuse, deck moves,
pagination/filtering, stale reads and the MTA source contract. The real
F7-to-restart runtime scenario remains `not run` under the MTA/GTA boundary.

## Manual runtime checklist

Status: `not run`.

1. In a separately authorized disposable environment, open the Bound Anki Collection and MTA resource; verify F7/Card Picker never shows a different collection.
2. Select a deck, then move the selected card to another deck; verify the Spatial Link remains keyed by the same collection UUID and cardId.
3. Link an unlinked Map Entity, repeat the same card on another entity, and verify the warning lists existing links while allowing confirmation.
4. Save through stock Map Editor, wait for independent read-back, restart the resource, and verify the active Spatial Link persists.
5. Verify Pending Map Save and Identity Collision remain ineligible for study and spatial activation.

## Answer

Implemented the ticket-local Card Picker and first-link seam. The companion
now exposes read-only, paginated search/read operations scoped to the current
Bound Anki Collection, including explicit stale-card errors and full Anki Card
Identity. F7 requests those cards through the server-side gateway, warns when
the selected card is already linked, and prepares a link only through the
existing stock Map Editor Pending Map Save/read-back path. SQLite keeps one
active link per Map Entity while allowing the same card identity on multiple
entities. No Anki scheduling or content writes are performed.

Repository-local checks pass; the real MTA/Map Editor F7-to-restart scenario is
still `not run` and requires separately authorized runtime validation.
