# 16 — Durable Review Transaction recovery

**What to build:** Production durable journal и автоматическое exactly-once recovery для потери ответа, companion/MTA restart и неопределённого исхода.

**Blocked by:** 04 — Bound Anki Collection identity; 15 — One rating through MTA.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Journal key — collection UUID + `reviewTransactionId`; cardId/rating immutable.
- [ ] Intent и before-state evidence durable до scheduler invocation.
- [ ] Identical replay возвращает прежний result; conflicting replay rejected без mutation.
- [ ] Proven applied не вызывает scheduler повторно и показывает `Rating applied`.
- [ ] Proven unapplied resends тот же transaction максимум один раз и показывает `Rating resent`.
- [ ] Indeterminate result durable как Outcome Unknown, не blind-retry и исключает только affected card.
- [ ] Collection switch/session rebuild ждут reconciliation.
- [ ] Garbage collection удаляет только terminal records, больше не нужные ни одной стороне.
- [ ] Crash внутри atomic Anki answer/rebuild либо reconciles authoritative evidence, либо честно остаётся Outcome Unknown.

## Tests

- [ ] Fault injection before call, after commit, after durable result and before response.
- [ ] Companion process, MTA resource and full MTA restart tests.
- [ ] Journal GC/retention/conflict tests.
- [ ] Atomic-backend termination gate with zero-or-one `revlog` assertion.

## Components

- Companion durable Review Transaction journal.
- Reconciliation engine.
- MTA durable pending-request state.
- Recovery status UI.

