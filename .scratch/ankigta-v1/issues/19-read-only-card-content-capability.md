# 19 — Read-only card content capability

**What to build:** Отдельный read-only loopback content endpoint для одного render, изолированный от companion control operations и постоянного token.

**Blocked by:** 01 — Companion health and Anki version; 04 — Bound Anki Collection identity.

**Status:** resolved

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Verify programmatically — launching disposable copies is allowed, driving a GUI with screenshots or synthetic input is not, and the installed MTA/GTA tree stays unmodified. Acceptance that only a human can observe stays a manual checklist marked `not run`.

## Acceptance criteria

- [x] Endpoint поддерживает только GET/HEAD issued render resources и не dispatches rating/scheduler/collection operations.
- [x] Capability имеет минимум 256 bits randomness и binds collection/card/side/generation.
- [x] Issuance lifetime 15 seconds; close/new generation revoke access.
- [x] Per-render guardrails: 64 requests, 32 MiB unique bytes, HTML 4 MiB, one media 16 MiB, four concurrent serviced requests.
- [x] Range returns 206; identical normalized retry не удваивает unique-byte budget.
- [x] Expired/closed/wrong card/side/generation получают uniform non-enumerating denial.
- [x] Responses set no-store, no-referrer and nosniff; overload returns bounded 503.
- [ ] Limit/missing-media error becomes render warning and не блокирует будущую rating UI.

## Tests

- [~] Ported verifier scenarios from Prototype 0006. Endpoint-side сценарии портированы; corpus fidelity в реальном CEF остаётся ручной проверкой.
- [x] Capability misuse, expiry, generation and concurrency tests.
- [x] Negative scan proving no control gateway/permanent token in content path.

## Components

- Companion content endpoint.
- Render capability issuer/store.
- Card media resolver.

## Implementation status

- `ContentServer` serves one render over loopback and nothing else: GET/HEAD
  only, every other method 405 before dispatch, and no control path at all.
- Capabilities are 256-bit, bound to collection, card, side and generation,
  live 15 seconds, and are revoked by close or by issuing a newer render.
- Budgets are enforced per render: 64 requests, 32 MiB unique bytes, 4 MiB
  HTML, 16 MiB per medium, 4 concurrent in-flight requests with a bounded 503
  beyond that. An identical retry spends a request but not the bytes again.
- Range requests return 206; missing media returns a placeholder plus
  `X-ANKIGTA-Warning: missing-media` rather than failing the render.
- Every failure — expired, closed, wrong card, wrong side, stale generation,
  guessed token, unknown file — returns an identical empty 404, so probing
  distinguishes nothing.
- A negative source test asserts the module references no session or review
  coordinator, no connection token and no control path.

Two implementation notes: the server is threaded, because a serialised one
could never exercise the concurrency guard, and `serve_forever` polls at 20 ms,
which cut this file's runtime from 12 s to 1.4 s.

Automated evidence: `pytest -q tests/test_content_endpoint.py` → 26 passed;
full suite 255 passed; mypy strict clean.

## Manual runtime checklist

See `docs/checklists/ticket19-card-content.md` (`Status: not run`).
