# 14 — Exact Card Admission

**What to build:** Поддерживаемый путь, который временно делает выбранную Card X scheduler-top через X-only rebuild owned deck, проверяет допуск и затем возвращает полный session set.

**Blocked by:** 12 — Full ANKIGTA Session.

**Status:** resolved

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Verify programmatically — launching disposable copies is allowed, driving a GUI with screenshots or synthetic input is not, and the installed MTA/GTA tree stays unmodified. Acceptance that only a human can observe stays a manual checklist marked `not run`.

## Acceptance criteria

- [x] Admission отклоняется при wrong collection, inactive/stale card, session collision или открытой Review Transaction.
- [x] Owned deck перестраивается в exact X-only membership.
- [x] Companion наблюдает scheduler-top и сравнивает полную Anki Card Identity до rating.
- [x] Mismatch/absence делает открытие Preview only и не вызывает scheduler answer.
- [x] После завершения/сверки полного review full membership восстанавливается.
- [x] Suspended/Buried не допускаются даже при явном X-only запросе.
- [x] Direct non-top answer, private queue mutation и scheduling SQL отсутствуют.

## Tests

- [x] Повтор матрицы Prototype 0002 на production contract.
- [x] Non-top rejection control from Prototype 0001.
- [x] X-only/full rebuild failure and restart boundaries.

## Components

- Companion exact-admission coordinator.
- Versioned session control operations.
- Anki scheduler/filtered-deck integration.

## Implementation status

- `SessionCoordinator.admit()` rebuilds the owned deck to an exact X-only
  membership, then asks Anki for scheduler-top through `get_queued_cards`, which
  observes without advancing.
- The comparison is on the full `AnkiCardIdentity`, not the numeric `cardId`, so
  the same number in another collection is correctly a different card (ADR 0009).
- A mismatch or absent top returns `previewOnly` with a reason and restores the
  full membership, so a refused admission cannot strand the session on an
  X-only deck. Rating is authorized by `admitted` alone.
- Suspended and buried cards are refused before the deck is touched, matching
  prototype 0002 S7; a not-due card needs explicit early review.
- `SessionCoordinator.restore()` rebuilds the full membership after a completed
  review, and is a no-op when no admission is open.
- Exposed as versioned control operations `/v1/session/admit` and
  `/v1/session/restore`; the MTA gateway that calls them belongs to ticket 15.
- A source-contract test asserts the module never calls `answerCard`, never
  touches a private scheduler queue and never writes scheduling SQL.

Automated evidence: `pytest -q tests/test_exact_card_admission.py` → 18 passed;
full suite 177 passed; mypy strict clean.

## Manual runtime checklist

See `docs/checklists/ticket14-exact-card-admission.md` (`Status: not run`).
