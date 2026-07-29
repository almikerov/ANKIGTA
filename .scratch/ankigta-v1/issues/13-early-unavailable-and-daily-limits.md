# 13 — Early, unavailable and daily-limit behavior

**What to build:** Полную eligibility policy вокруг `ANKIGTA Session`: Preview only для Unavailable/Not-due по умолчанию, включаемое early review и предупреждение для новых карточек сверх исходного дневного лимита.

**Blocked by:** 12 — Full ANKIGTA Session.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Suspended/Buried отображаются как Unavailable Card, сохраняют links и никогда не входят в rating/session/activation.
- [ ] Not-due Card по умолчанию Preview only и исключена из automatic study.
- [ ] `Разрешить досрочное повторение` включает supported early review через Anki и показывает предупреждение.
- [ ] Настройка никогда не overriding suspended/buried и деградирует в Preview на несовместимой версии.
- [ ] Все linked new cards входят независимо от исходного daily limit.
- [ ] Карточка сверх сегодняшнего лимита остаётся rateable и показывает точный warning.
- [ ] Классификация warning использует проверенный Anki query и не реализует собственный scheduler.

## Tests

- [ ] Real-Anki matrix suspended, buried, future review and all four ratings.
- [ ] Daily-limit boundary/control comparison.
- [ ] Scheduler-state refresh after status changes.

## Components

- Companion eligibility/statistics query.
- Session coordinator.
- F7/Review Mode status warnings.
- Early-review setting.

