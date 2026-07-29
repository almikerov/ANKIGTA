# 15 — One rating through MTA

**What to build:** Первый complete study tracer: scheduler-admitted Card X проходит через MTA question/answer choice к companion, штатно получает одну оценку Anki и возвращает подтверждённый результат.

**Blocked by:** 02 — Server-side Lua gateway; 14 — Exact Card Admission.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] MTA создаёт отдельные stable `requestId` и `reviewTransactionId`.
- [ ] Again/Hard/Good/Easy принимаются только для scheduler-admitted identity.
- [ ] Companion является единственным coordinator и вызывает Anki scheduler ровно один раз.
- [ ] Успех подтверждается matching protocol/result identity, card state и одним `revlog`.
- [ ] Повторное нажатие/duplicate callback не создаёт вторую logical request.
- [ ] Transport error или HTTP status сами по себе не объявляют rating applied/unapplied.
- [ ] Full session rebuild происходит только после подтверждённого terminal result.

## Tests

- [ ] End-to-end MTA Server → real Anki all-four-ratings test.
- [ ] Duplicate click, malformed response and out-of-order callback tests.
- [ ] Control comparison of card/FSRS/revlog semantic result.

## Components

- MTA rating command path.
- Companion Review Transaction coordinator.
- Anki scheduler integration.
- Result/status UI.

