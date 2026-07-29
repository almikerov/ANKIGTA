# 12 — Full ANKIGTA Session

**What to build:** Создание, перестройка, пауза и очистка одной owned rescheduling filtered deck из уникальных eligible Anki Card Active Map Set.

**Blocked by:** 04 — Bound Anki Collection identity; 08 — Card Picker and first Spatial Link.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Только явное `Начать обучение` из connected-paused создаёт `ANKIGTA Session`.
- [ ] Membership строится из уникальных Anki Card Identity active links; duplicate links не дублируют card.
- [ ] Owned deck collision обнаруживается и не захватывает чужую filtered deck.
- [ ] New/learning/relearning/due review входят через Anki scheduler state; suspended/buried/missing/pending исключаются.
- [ ] Input `cardId` order не используется как scheduler order.
- [ ] Pause/stop возвращает карточки в исходные колоды и удаляет owned deck.
- [ ] Rebuild timeout ограничен 30 секундами, показывает progress/cancel и не замораживает UI.
- [ ] Connection/reconnection сами не создают session.

## Tests

- [ ] Real-Anki full-set build/rebuild/pause/cleanup tests.
- [ ] Unique membership, deck-name collision and active-map changes.
- [ ] Timeout/cancel/restart tests proving no stranded cards.

## Components

- Companion session coordinator.
- Anki filtered-deck integration.
- MTA study-state UI.

