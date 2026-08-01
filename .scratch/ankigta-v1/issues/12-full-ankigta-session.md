# 12 — Full ANKIGTA Session

**What to build:** Создание, перестройка, пауза и очистка одной owned rescheduling filtered deck из уникальных eligible Anki Card Active Map Set.

**Blocked by:** 04 — Bound Anki Collection identity; 08 — Card Picker and first Spatial Link.

**Status:** resolved

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Verify programmatically — launching disposable copies is allowed, driving a GUI with screenshots or synthetic input is not, and the installed MTA/GTA tree stays unmodified. Acceptance that only a human can observe stays a manual checklist marked `not run`.

## Acceptance criteria

- [x] Только явное `Начать обучение` из connected-paused создаёт `ANKIGTA Session`.
- [x] Membership строится из уникальных Anki Card Identity active links; duplicate links не дублируют card.
- [x] Owned deck collision обнаруживается и не захватывает чужую filtered deck.
- [x] New/learning/relearning/due review входят через Anki scheduler state; suspended/buried/missing/pending исключаются.
- [x] Input `cardId` order не используется как scheduler order.
- [x] Pause/stop возвращает карточки в исходные колоды и удаляет owned deck.
- [x] Rebuild timeout ограничен 30 секундами, показывает progress/cancel и не замораживает UI.
- [x] Connection/reconnection сами не создают session.

## Tests

- [x] Real-Anki full-set build/rebuild/pause/cleanup tests.
- [x] Unique membership, deck-name collision and active-map changes.
- [x] Timeout/cancel/restart tests proving no stranded cards.

## Components

- Companion session coordinator.
- Anki filtered-deck integration.
- MTA study-state UI.

## Comments

- Implemented the owned rescheduling filtered deck: explicit-start-only session
  creation, unique Anki Card Identity membership, owner-marker collision
  detection that never adopts a foreign filtered deck, scheduler-state-driven
  admission, a 30 s bounded rebuild with progress/cancel, and pause/stop that
  empties and deletes the owned deck.
- Ordering is delegated to Anki: the filtered-deck search term carries an
  explicit `order`, so the input `cardId` sequence never acts as scheduler
  order — matching prototype 0002's finding.
- Automated evidence: `pytest -q tests/test_session.py tests/test_mta_ticket_12.py`
  → 11 passed, and the full repository suite is green.
- Observed-runtime acceptance against a live Anki profile remains a human check.
