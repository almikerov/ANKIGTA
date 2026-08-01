# 14 — Exact Card Admission

**What to build:** Поддерживаемый путь, который временно делает выбранную Card X scheduler-top через X-only rebuild owned deck, проверяет допуск и затем возвращает полный session set.

**Blocked by:** 12 — Full ANKIGTA Session.

**Status:** ready-for-agent

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Verify programmatically — launching disposable copies is allowed, driving a GUI with screenshots or synthetic input is not, and the installed MTA/GTA tree stays unmodified. Acceptance that only a human can observe stays a manual checklist marked `not run`.

## Acceptance criteria

- [ ] Admission отклоняется при wrong collection, inactive/stale card, session collision или открытой Review Transaction.
- [ ] Owned deck перестраивается в exact X-only membership.
- [ ] Companion наблюдает scheduler-top и сравнивает полную Anki Card Identity до rating.
- [ ] Mismatch/absence делает открытие Preview only и не вызывает scheduler answer.
- [ ] После завершения/сверки полного review full membership восстанавливается.
- [ ] Suspended/Buried не допускаются даже при явном X-only запросе.
- [ ] Direct non-top answer, private queue mutation и scheduling SQL отсутствуют.

## Tests

- [ ] Повтор матрицы Prototype 0002 на production contract.
- [ ] Non-top rejection control from Prototype 0001.
- [ ] X-only/full rebuild failure and restart boundaries.

## Components

- Companion exact-admission coordinator.
- Versioned session control operations.
- Anki scheduler/filtered-deck integration.

