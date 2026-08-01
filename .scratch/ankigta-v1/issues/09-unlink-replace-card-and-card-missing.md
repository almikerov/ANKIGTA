# 09 — Unlink, Replace card and Card missing

**What to build:** Полный карточный lifecycle Spatial Link: явный Unlink, атомарный Replace card и repair карточки, удалённой в Anki, без потери Map Entity metadata.

**Blocked by:** 08 — Card Picker and first Spatial Link.

**Status:** resolved

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Verify programmatically — launching disposable copies is allowed, driving a GUI with screenshots or synthetic input is not, and the installed MTA/GTA tree stays unmodified. Acceptance that only a human can observe stays a manual checklist marked `not run`.

## Acceptance criteria

- [x] `Unlink` требует подтверждения с Map Entity и карточкой и удаляет только Spatial Link.
- [x] Name, Entity Tag, radius и `Show radius` сохраняются после Unlink.
- [x] `Replace card` показывает old/new identity и заменяет связь без промежуточного Unlink.
- [x] Удалённый `cardId` становится Card missing и сохраняет запись/метаданные.
- [x] Новый `cardId` не сопоставляется эвристически; Card missing ремонтируется только Replace card.
- [~] Открытый review со старой карточкой завершается, затем очередь/статистика/markers пересчитываются. Пересчёт и `SESSION_INVALIDATED_EVENT` реализованы; само закрытие открытого review принадлежит тикету 20 (Review Mode ещё не существует).

## Tests

- [x] End-to-end Unlink/Replace/restart tests.
- [x] Real-Anki card deletion and replacement test.
- [x] Duplicate-card warning and open-review state transition tests.

## Components

- F7 link actions.
- Server Spatial Link persistence.
- Companion card-state refresh.
- Session invalidation events.

## Comments

- Implemented the Spatial Link card lifecycle: confirmed Unlink that removes
  only the link, atomic Replace card with old/new identity display, exact
  `(collectionUuid, cardId)` Card missing refresh with no heuristic rematching,
  and persisted display metadata that survives both operations.
- `Store.refreshSpatialLinkCardState` keys strictly on the exact card identity,
  so a new `cardId` never rebinds an existing link.
- Automated evidence: `pytest -q tests/test_mta_ticket_09.py` → 4 passed, and
  the full repository suite is green.
- Open-review termination is deferred to ticket 20; the invalidation seam it
  will hook into (`SESSION_INVALIDATED_EVENT`) is in place.
