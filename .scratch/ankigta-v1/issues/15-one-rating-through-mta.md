# 15 — One rating through MTA

**What to build:** Первый complete study tracer: scheduler-admitted Card X проходит через MTA question/answer choice к companion, штатно получает одну оценку Anki и возвращает подтверждённый результат.

**Blocked by:** 02 — Server-side Lua gateway; 14 — Exact Card Admission.

**Status:** resolved

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Verify programmatically — launching disposable copies is allowed, driving a GUI with screenshots or synthetic input is not, and the installed MTA/GTA tree stays unmodified. Acceptance that only a human can observe stays a manual checklist marked `not run`.

## Acceptance criteria

- [x] MTA создаёт отдельные stable `requestId` и `reviewTransactionId`.
- [x] Again/Hard/Good/Easy принимаются только для scheduler-admitted identity.
- [x] Companion является единственным coordinator и вызывает Anki scheduler ровно один раз.
- [x] Успех подтверждается matching protocol/result identity, card state и одним `revlog`.
- [x] Повторное нажатие/duplicate callback не создаёт вторую logical request.
- [x] Transport error или HTTP status сами по себе не объявляют rating applied/unapplied.
- [x] Full session rebuild происходит только после подтверждённого terminal result.

## Tests

- [x] End-to-end MTA Server → real Anki all-four-ratings test.
- [x] Duplicate click, malformed response and out-of-order callback tests.
- [x] Control comparison of card/FSRS/revlog semantic result.

## Components

- MTA rating command path.
- Companion Review Transaction coordinator.
- Anki scheduler integration.
- Result/status UI.

## Implementation status

- `Gateway.requestRating` mints a `reviewTransactionId` that is independent of
  the transport `requestId`, so a retried request is the same review while a
  new click is a new one.
- `ReviewCoordinator.rate()` calls Anki once per transaction. A repeat replays
  the recorded outcome; a repeat asking for a *different* rating is refused as
  `transaction_conflict`.
- Only the admitted card can be rated, compared on full Anki Card Identity, and
  it must still be scheduler-top when the rating arrives.
- Neither a transport error, a timeout, an HTTP status, a malformed body nor a
  mismatched identity is treated as evidence about what Anki did: all settle as
  `outcome_unknown`, which is never retried blindly and blocks further ratings.
- The full session is rebuilt only after a confirmed terminal result.
- Exposed as `/v1/review/rate`; durable cross-restart reconciliation of an
  `outcome_unknown` transaction is ticket 16.

While writing the gateway path, MTA's `CScriptArgReader::ReadLuaArgumentsTable`
was found to forward `fetchRemote` callback arguments by iterating the table
with `lua_next`, whose order Lua does not guarantee. The review path therefore
passes a pure array table. The pre-existing mixed tables on the health, card and
session paths still work but rely on traversal order; that is filed separately.

Automated evidence: `pytest -q tests/test_review_transaction.py
tests/test_gateway_rating_behavior.py` → 31 passed; full suite 208 passed;
mypy strict clean.

## Manual runtime checklist

See `docs/checklists/ticket15-one-rating-through-mta.md` (`Status: not run`).
