# 13 — Early, unavailable and daily-limit behavior

**What to build:** Полную eligibility policy вокруг `ANKIGTA Session`: Preview only для Unavailable/Not-due по умолчанию, включаемое early review и предупреждение для новых карточек сверх исходного дневного лимита.

**Blocked by:** 12 — Full ANKIGTA Session.

**Status:** resolved

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Verify programmatically — launching disposable copies is allowed, driving a GUI with screenshots or synthetic input is not, and the installed MTA/GTA tree stays unmodified. Acceptance that only a human can observe stays a manual checklist marked `not run`.

## Acceptance criteria

- [x] Suspended/Buried отображаются как Unavailable Card, сохраняют links и никогда не входят в rating/session/activation.
- [x] Not-due Card по умолчанию Preview only и исключена из automatic study.
- [x] `Разрешить досрочное повторение` включает supported early review через Anki и показывает предупреждение.
- [x] Настройка никогда не overriding suspended/buried и деградирует в Preview на несовместимой версии.
- [x] Все linked new cards входят независимо от исходного daily limit.
- [x] Карточка сверх сегодняшнего лимита остаётся rateable и показывает точный warning.
- [x] Классификация warning использует проверенный Anki query и не реализует собственный scheduler.

## Tests

- [~] Real-Anki matrix suspended, buried, future review and all four ratings. Матрица очередей покрыта модульно; сверка с живой коллекцией остаётся ручной.
- [x] Daily-limit boundary/control comparison.
- [x] Scheduler-state refresh after status changes.

## Components

- Companion eligibility/statistics query.
- Session coordinator.
- F7/Review Mode status warnings.
- Early-review setting.

## Implementation status

- `eligibility.py` separates three permissions that were previously tangled:
  may a card be shown, may it be rated, and may it drive automatic study.
  Suspended and buried cards remain viewable and keep their links, but are
  never rateable and never enter the queue, activation or markers.
- Not-due is Preview only by default. Enabling early review makes it rateable
  with a warning; on a build whose early-review behaviour is unverified the
  setting degrades to Preview rather than guessing. No setting reaches the
  suspended/buried branch — that governs *when* a card may be rated, never the
  user's own hold.
- Every linked new card enters regardless of the source deck's daily limit
  (ADR 0020); the limit becomes a warning. Whether a card is beyond the limit
  arrives through an injected query, so no scheduler logic is reimplemented
  here (ADR 0017), and a source test enforces that.
- The session now uses this one rule for both membership and admission, so the
  two can no longer disagree.

**Defect found and fixed.** The queue mapping recognised only
`QUEUE_TYPE_SIBLING_BURIED (-2)`. A **manually buried** card (`-3`) fell through
to `REVIEW` and would therefore have been admitted to a session and rated —
precisely what burying prevents. `QUEUE_TYPE_DAY_LEARN_RELEARN (3)` and
`QUEUE_TYPE_PREVIEW (4)` were also misread as due reviews. Values verified
against Anki 26.05 `anki/consts.py`. An unrecognised queue is now treated as
not-due rather than assumed rateable.

**Second defect, unrelated to this ticket.** `AnkiFilteredDeckBackend.cleanup`
had stopped clearing its ownership marker: a ticket-14 edit inserted
`scheduler_top` between the delete and the `_set_config(None)`, leaving that
call unreachable after a `return`. A stale marker would let ANKIGTA claim a
future deck that reused the id. Fixed, mutation-checked, and the fake that hid
it — its `delete` never removed the deck — now behaves like the real one.

Automated evidence: `pytest -q tests/test_eligibility.py` → 23 passed; full
suite 308 passed; mypy strict clean.

## Manual runtime checklist

See `docs/checklists/ticket13-eligibility.md` (`Status: not run`).
