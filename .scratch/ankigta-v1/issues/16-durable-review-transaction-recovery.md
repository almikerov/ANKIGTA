# 16 — Durable Review Transaction recovery

**What to build:** Production durable journal и автоматическое exactly-once recovery для потери ответа, companion/MTA restart и неопределённого исхода.

**Blocked by:** 04 — Bound Anki Collection identity; 15 — One rating through MTA.

**Status:** resolved

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Verify programmatically — launching disposable copies is allowed, driving a GUI with screenshots or synthetic input is not, and the installed MTA/GTA tree stays unmodified. Acceptance that only a human can observe stays a manual checklist marked `not run`.

## Acceptance criteria

- [x] Journal key — collection UUID + `reviewTransactionId`; cardId/rating immutable.
- [x] Intent и before-state evidence durable до scheduler invocation.
- [x] Identical replay возвращает прежний result; conflicting replay rejected без mutation.
- [x] Proven applied не вызывает scheduler повторно и показывает `Rating applied`.
- [x] Proven unapplied resends тот же transaction максимум один раз и показывает `Rating resent`.
- [x] Indeterminate result durable как Outcome Unknown, не blind-retry и исключает только affected card.
- [x] Collection switch/session rebuild ждут reconciliation.
- [x] Garbage collection удаляет только terminal records, больше не нужные ни одной стороне.
- [~] Crash внутри atomic Anki answer/rebuild либо reconciles authoritative evidence, либо честно остаётся Outcome Unknown. Логика реконсиляции реализована и покрыта тестами; сам crash внутри атомарной операции Anki остаётся ручной проверкой (prototype 0003 его тоже не смог инжектировать).

## Tests

- [x] Fault injection before call, after commit, after durable result and before response.
- [x] Companion process, MTA resource and full MTA restart tests.
- [x] Journal GC/retention/conflict tests.
- [~] Atomic-backend termination gate with zero-or-one `revlog` assertion (manual: not run).

## Components

- Companion durable Review Transaction journal.
- Reconciliation engine.
- MTA durable pending-request state.
- Recovery status UI.

## Implementation status

- `ReviewJournal` is a companion-owned SQLite journal keyed by
  `(collection_uuid, reviewTransactionId)`; `cardId` and rating are immutable
  once recorded, so a conflicting reuse raises `transaction_conflict` without
  touching the stored record.
- Intent and the before-snapshot are durable before Anki is invoked, and the
  scheduler call is counted *before* it is made — a crash in between must look
  like a call that may have happened.
- Reconciliation decides only from evidence supplied by an injected verifier:
  proven applied completes without a second call; proven unapplied resends the
  same id at most once; anything else becomes a durable `outcome_unknown`.
- A `received` record was never handed to the scheduler, so it is safe to
  resend without needing proof.
- `outcome_unknown` is a quarantine: it survives restart, blocks the affected
  card and any collection switch or session rebuild, is never blind-retried,
  and is never garbage collected — it is the only remaining record that the
  rating happened at all.
- `ReviewCoordinator` writes through the journal, so ticket 15's in-memory
  exactly-once promise now survives a process restart.

The no-guessing rule was mutation-checked: making an indeterminate outcome
resolve to `completed` fails four tests.

Automated evidence: `pytest -q tests/test_review_journal.py
tests/test_review_transaction.py` → 39 passed; full suite 229 passed; mypy
strict clean.

## Manual runtime checklist

See `docs/checklists/ticket16-durable-recovery.md` (`Status: not run`).
