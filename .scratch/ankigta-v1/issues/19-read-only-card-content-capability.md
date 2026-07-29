# 19 — Read-only card content capability

**What to build:** Отдельный read-only loopback content endpoint для одного render, изолированный от companion control operations и постоянного token.

**Blocked by:** 01 — Companion health and Anki version; 04 — Bound Anki Collection identity.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Endpoint поддерживает только GET/HEAD issued render resources и не dispatches rating/scheduler/collection operations.
- [ ] Capability имеет минимум 256 bits randomness и binds collection/card/side/generation.
- [ ] Issuance lifetime 15 seconds; close/new generation revoke access.
- [ ] Per-render guardrails: 64 requests, 32 MiB unique bytes, HTML 4 MiB, one media 16 MiB, four concurrent serviced requests.
- [ ] Range returns 206; identical normalized retry не удваивает unique-byte budget.
- [ ] Expired/closed/wrong card/side/generation получают uniform non-enumerating denial.
- [ ] Responses set no-store, no-referrer and nosniff; overload returns bounded 503.
- [ ] Limit/missing-media error becomes render warning and не блокирует будущую rating UI.

## Tests

- [ ] Ported verifier scenarios from Prototype 0006.
- [ ] Capability misuse, expiry, generation and concurrency tests.
- [ ] Negative scan proving no control gateway/permanent token in content path.

## Components

- Companion content endpoint.
- Render capability issuer/store.
- Card media resolver.

