# Handoff: MTA server-side loopback transport prototype

## Purpose

Continue in a **new chat** and build disposable prototype 0004 answering:

> Can server-side Lua in a real MTA Server reliably and safely exchange local HTTP requests with the companion add-on over loopback while preserving request identity, recovering from connection loss, and remaining unreachable from other computers?

This prototype tests transport and lifecycle behavior only. It must use a real MTA Server and a disposable companion HTTP harness. It must not modify production ANKIGTA code or Anki scheduling data.

## Read first

- `AGENTS.md`
- `CONTEXT.md`
- `docs/design/confirmed-baseline.md`
- `docs/design/preliminary-spec-audit.md`
- `docs/prototypes/0001-exact-card-idempotent-review.md`
- `docs/prototypes/0002-filtered-deck-fsrs-admission.md`
- `docs/prototypes/0003-companion-lifecycle-recovery.md`

Relevant decisions:

- `docs/adr/0002-use-server-side-lua-as-the-anki-gateway.md`
- `docs/adr/0006-allow-an-optional-token-on-the-same-host.md`
- `docs/adr/0007-make-the-companion-add-on-the-review-coordinator.md`
- `docs/adr/0008-make-ratings-idempotent.md`
- `docs/adr/0012-limit-v1-to-tested-anki-on-windows-with-fsrs.md`
- `docs/adr/0014-split-settings-by-authority.md`
- `docs/adr/0017-keep-anki-authoritative-for-study-data.md`
- `docs/adr/0021-pause-when-the-bound-anki-collection-changes.md`

Treat the old `ANKIGTA_SPEC.md` only as preliminary material. Current context, ADRs, confirmed baseline and measured prototype evidence take precedence.

## Prior evidence that constrains this prototype

- Prototype 0001 proved that transport-level retry must not be confused with successful scheduler admission or rating.
- Prototype 0002 proved the Anki-side exact-card admission mechanism; do not repeat it here.
- Prototype 0003 proved collection-scoped durable transaction recovery at tested process boundaries. The transport must preserve the original `reviewTransactionId`; it must not invent a replacement during timeout/retry.
- `Outcome Unknown` is a valid quarantine result. Transport uncertainty must not trigger a blind rating retry.
- ANKIGTA does not launch Anki or switch profiles. The user starts Anki and opens the intended profile.
- Establishing or restoring Companion Connection never starts studying or creates `ANKIGTA Session`.

## Fixed product constraints

- Windows only for v1.
- Anki Desktop, companion add-on and MTA Server run on the same computer.
- Only server-side Lua communicates with the companion add-on.
- Client-side Lua and CEF have no direct companion/Anki network path.
- Listener binds only to `127.0.0.1` and, where supported, `::1`.
- Binding to `0.0.0.0`, `::`, a LAN address or an external interface is forbidden.
- LAN and internet clients remain unsupported even with a valid token.
- A free loopback port is selected automatically by default and synchronized between both sides.
- Manual port override exists only as an advanced setting.
- A cryptographically random token is enabled by default and configured on both sides.
- The token may be explicitly disabled with a warning.
- Token values and sensitive headers never appear in normal UI, logs, report or evidence.
- A manual `Подключиться` action remains available while disconnected; automatic detection/reconnect also remains enabled.
- Reconnection leaves studying paused.
- Prototype code is disposable and must not enter production.

## Scope

Build:

1. a minimal disposable MTA resource whose network calls originate only from server-side Lua;
2. a disposable HTTP companion harness that models:
   - health/identity read;
   - structured read response;
   - idempotent review request keyed by collection identity and `reviewTransactionId`;
   - stored-result query;
   - controlled delays, disconnects, malformed responses and lost replies;
3. an external test orchestrator for starting/stopping MTA and the harness, allocating ports and collecting redacted evidence;
4. a read-only evidence verifier.

The harness is not an Anki add-on and must not be presented as production companion behavior. It only supplies the minimum protocol semantics needed to test MTA transport.

Do not test:

- real Anki card mutation, FSRS or filtered decks;
- CEF card rendering or hostile templates;
- Map Editor IDs;
- profile switching;
- AnkiWeb;
- final production API schema beyond the minimal request envelope needed for transport;
- automatic add-on installation/update.

## Non-negotiable safety rules

- Use a disposable MTA Server instance/config and resource directory.
- Do not edit the user's normal MTA server resources.
- Listener must fail closed if safe loopback binding cannot be achieved.
- Do not temporarily bind externally for testing.
- Use only generated disposable secrets; never read or reuse a real user token.
- Evidence records a stable redaction marker instead of the secret.
- Source and evidence scans must fail if the raw disposable token appears.
- Do not use client-side Lua, CEF, browser JavaScript, shelling from MTA, or an external LAN proxy as the MTA→companion gateway.
- Do not claim success from a standalone Lua interpreter or mock callback; the request must run inside a real MTA Server resource.
- Do not treat an HTTP resend as a new logical review.
- No production code, direct SQL write, scheduler mutation or Anki profile access.
- Keep all disposable source/runtime/evidence under `.scratch/0004-mta-loopback-transport-prototype/`.

## Environment inventory

Record:

- Windows edition/build;
- exact MTA Server build and architecture;
- MTA Lua/runtime details exposed by the server;
- exact HTTP function(s) and options used by server-side Lua;
- companion harness Python/runtime and HTTP stack;
- IPv4 and IPv6 status;
- active network interfaces and the LAN address used only for a negative reachability probe;
- firewall or local security behavior that materially affects the result.

If MTA Server is not already available, obtain it only from an official source in the prototype chat, record the source/version/hash, and isolate it under `.scratch`. Do not install or modify a production server.

## Minimal request envelope

Use a JSON envelope sufficient to prove identity preservation:

```json
{
  "protocolVersion": 1,
  "requestId": "opaque request identifier",
  "operation": "health|read|review|reviewStatus",
  "collectionIdentity": "disposable collection identity",
  "reviewTransactionId": "present for review/reviewStatus",
  "cardId": 123,
  "payload": {}
}
```

The exact field spelling may change if MTA constraints require it, but the prototype must preserve distinct request identity and logical review identity. `requestId` identifies one HTTP attempt/request flow; `reviewTransactionId` identifies one logical rating transaction and remains unchanged across retries.

Every response must echo enough non-secret identity to correlate it safely and contain either structured success or structured error. Never echo the token.

## Port and token setup

Test two modes:

1. **Protected default**
   - generated disposable token;
   - token required;
   - wrong/missing token rejected before operation execution.
2. **Explicitly unprotected**
   - token disabled by a deliberate harness setting;
   - missing token accepted;
   - evidence records a warning state, not a secret.

Test:

- automatic free-port allocation;
- occupied candidate port;
- consistent handoff of the selected port to the MTA resource without exposing the token in command output;
- valid manual override;
- invalid range/non-numeric override;
- occupied manual override;
- manual override that would require non-loopback binding.

If atomic two-sided configuration cannot be truthfully modeled without production storage, report the exact boundary. Do not claim that a test orchestrator environment variable is itself the production synchronization design.

## Required scenarios

### S1 — Real MTA server-side IPv4 request

1. Start the harness on `127.0.0.1`.
2. Start the disposable real MTA Server and resource.
3. Issue health/read requests from server-side Lua.
4. Prove callback completion, status, headers, body and identity correlation.
5. Prove neither client-side Lua nor CEF participated.

IPv4 loopback success is mandatory.

### S2 — IPv6 loopback

Repeat S1 against `::1`.

Record whether the MTA HTTP stack, URL parser and Windows runtime support the path. IPv6 success is required only if the tested environment exposes compatible IPv6 support; an unavailable capability must be classified precisely and must not cause fallback to an external bind.

### S3 — Client/CEF isolation

Use the disposable resource manifest and source scan to prove:

- only server scripts contain companion URL/token/request code;
- no client script or CEF asset can address the companion;
- server responses sent to clients contain no token or privileged transport configuration.

### S4 — Envelope and Unicode fidelity

Round-trip:

- `requestId`;
- `reviewTransactionId`;
- collection identity;
- numeric `cardId`;
- Russian and mixed Unicode;
- structured success and structured error.

Test realistic UTF-8 JSON responses at increasing sizes, including at least small, medium and large card-render-shaped payloads. Suggested checkpoints are 64 KiB, 256 KiB and 1 MiB. Report measured success/failure and latency; do not invent a universal limit from one machine.

### S5 — Token enforcement and redaction

Prove:

- correct token succeeds;
- wrong token is rejected without executing the operation;
- missing token is rejected in protected mode;
- missing token succeeds only in explicitly unprotected mode;
- token is absent from MTA logs, harness logs, report, structured evidence and verifier output;
- authorization errors do not reveal the expected token.

### S6 — Loopback-only reachability

1. Record listener endpoints without secrets.
2. Prove IPv4 listener is on `127.0.0.1`, not `0.0.0.0`.
3. If IPv6 is enabled, prove listener is on `::1`, not `::`.
4. Attempt the same request through the machine's LAN address.
5. Prove the LAN path cannot reach the listener.

A firewall-only rejection is not sufficient evidence for a listener that is actually bound externally.

### S7 — Companion absent at MTA startup

1. Start MTA/resource while the harness is absent.
2. Prove MTA main/game processing does not block.
3. Capture disconnected state and bounded failed callback.
4. Start the harness later.
5. Prove automatic connection detection succeeds.
6. Repeat with the manual `Подключиться` action.
7. Prove neither path starts studying or creates a session.

### S8 — Companion disappears during a request

1. Send a delayed request.
2. Stop the harness before its response.
3. Prove the MTA callback reaches a bounded failure/timeout.
4. Prove `requestId` and `reviewTransactionId` remain available for reconciliation.
5. Prove game/server event processing remains responsive.

### S9 — Lost response after accepted review

1. Send a review request with one `reviewTransactionId`.
2. Let the harness durably store the result, then intentionally drop the HTTP response.
3. Retry/reconcile with the same `reviewTransactionId`.
4. Prove the harness returns the stored result and executes the logical review once.
5. Prove the transport does not create a new review ID.

This tests transport preservation, not Anki scheduler idempotency.

### S10 — Identical and conflicting retry

Prove:

- identical request with the same collection/card/rating returns the prior result;
- the same `reviewTransactionId` with changed collection/card/rating returns structured conflict;
- no conflicting request reaches the mutation counter.

### S11 — Resource restart

1. Leave one request unresolved.
2. Restart the disposable MTA resource.
3. Prove unresolved transport state is not silently marked successful.
4. Reconcile using the original `reviewTransactionId`.
5. Prove no new logical review is created.

### S12 — MTA Server restart

Repeat the restart boundary for the whole disposable MTA Server. If persistence requires a disposable journal, document its boundary and ensure it is not presented as final production storage.

### S13 — Port conflict and automatic selection

1. Occupy the preferred candidate port with an unrelated process.
2. Start automatic allocation.
3. Prove a free loopback port is chosen.
4. Prove both prototype sides use the same selected port.
5. Prove the unrelated listener is not mistaken for companion by requiring protocol identity and token validation.

### S14 — Manual port override

Test:

- valid free loopback port;
- occupied port;
- out-of-range and malformed values;
- configuration implying external binding.

Failures must be structured and non-blocking.

### S15 — Malformed and adverse responses

Test separately:

- slow response;
- configured timeout;
- malformed JSON;
- wrong `Content-Type`;
- valid JSON with wrong request identity;
- oversized response at and beyond observed safe checkpoints;
- premature connection close;
- HTTP error status;
- response missing required fields.

No case may hang MTA or reuse another request's callback/result.

### S16 — Parallel read requests

Issue multiple safe read requests with unique `requestId` values and varied delays. Prove callback/result correlation remains exact and ordering is not assumed.

### S17 — Rating serialization

Issue overlapping review requests. Prove the transport/coordinator boundary serializes mutation-like operations or otherwise rejects unsafe concurrency while allowing independent reads where safe.

Do not implement a scheduler. The harness mutation counter only proves transport ordering and transaction identity.

### S18 — Reconnect lifecycle

Exercise:

- disconnect;
- automatic reconnect;
- manual `Подключиться`;
- resource restart;
- harness restart;
- port change.

Prove reconnect does not automatically start studying, create `ANKIGTA Session`, reopen Review Mode or discard an unresolved transaction.

### S19 — Clean shutdown

Stop the resource, MTA server and harness. Prove:

- no external listener remains;
- no production file changed;
- disposable processes terminated;
- raw token is absent from retained evidence.

## Timing and capacity evidence

Measure:

- local request latency distribution for successful small reads;
- delayed-start detection/reconnect time;
- actual connection and response timeout behavior;
- number of physical HTTP attempts per `requestId`;
- logical executions per `reviewTransactionId`;
- parallel-read completion and callback correlation;
- tested payload-size checkpoints and first observed failure;
- MTA event-loop responsiveness during delay/timeout.

Do not convert one-machine observations into unsupported production promises. Recommend product thresholds only after reporting raw evidence.

## Success criteria

Overall verdict is `passed` only if:

1. A real MTA Server resource performs successful server-side Lua HTTP exchange over IPv4 loopback.
2. No client-side Lua or CEF network gateway is involved.
3. Listener endpoints are loopback-only and unreachable through the LAN address.
4. Protected mode validates the token before operation execution and retained artifacts contain no raw secret.
5. Explicitly unprotected mode works only after deliberate disablement and produces a warning state.
6. `requestId` and `reviewTransactionId` remain distinct and stable through timeout, loss and retry.
7. Lost-response replay returns one stored logical result without a second logical review.
8. Identical and conflicting retries are unambiguous and non-mutating where required.
9. Delayed startup, companion disappearance, resource restart, MTA restart and reconnect do not block MTA.
10. Malformed, mismatched, oversized and prematurely closed responses fail predictably without callback mixing.
11. Parallel read callbacks remain correctly correlated.
12. Mutation-like review requests remain serialized or are safely rejected.
13. Automatic port conflict handling and manual override produce unambiguous results.
14. Reconnection does not start studying or create an Anki session.
15. No production ANKIGTA or Anki data is modified.
16. Structured evidence and hashes pass the read-only verifier.

IPv6 is reported separately. Lack of compatible IPv6 support may yield an IPv4-only passed result if IPv4 is loopback-only and the product documents that restriction. Any workaround requiring external bind, client gateway or LAN proxy fails the gate.

Use `partially passed` when the core IPv4 server-side path works but a required reliability/security scenario is unproved. Use `failed` if real MTA cannot reach a safe loopback listener, if external binding is required, if only client-side access works, if request identity is lost, or if secrets leak into retained artifacts.

## Required evidence

Capture:

- exact environment and executable hashes;
- disposable MTA server/resource configuration;
- companion harness listener configuration with secret values redacted;
- MTA and harness event timelines;
- request/response metadata without sensitive headers;
- request ID / review transaction ID / physical attempt / logical execution table;
- disconnect, timeout, restart and reconnect observations;
- payload-size and latency results;
- listener socket evidence and LAN negative probe;
- source scan proving no client/CEF gateway, forbidden bind or production path;
- secret-leak scan across all retained text evidence;
- process/port cleanup evidence;
- SHA-256 manifest for prototype source and primary evidence.

Provide a read-only verifier that checks structured evidence and prints:

- evidence verification result;
- per-scenario verdicts;
- IPv4 and IPv6 verdicts;
- overall verdict;
- measured limits and unproved boundaries.

## Assumptions forbidden without proof

- MTA `fetchRemote` or another HTTP function permits loopback on Windows.
- A URL that says `localhost` is necessarily loopback-only.
- Binding to IPv6 `::` is equivalent to `::1`.
- A firewall makes an external bind acceptable.
- MTA callbacks cannot be mixed when responses arrive out of order.
- HTTP library retry preserves the original logical request identity.
- Transport timeout means the companion did not execute the request.
- Resource restart preserves Lua memory.
- MTA Server restart preserves unresolved request state.
- A new `requestId` may replace the original `reviewTransactionId`.
- Correct token behavior means the token is absent from logs.
- Automatic port selection implies both sides are atomically configured.
- A mock Lua interpreter proves real MTA Server behavior.
- IPv4 results automatically apply to IPv6.
- One successful large response establishes an unlimited payload size.
- Reconnect may safely start studying.

## Expected repository artifact

Write the canonical report to:

```text
docs/prototypes/0004-mta-loopback-transport.md
```

It must include:

- verdict: `passed`, `failed` or `partially passed`;
- exact tested environment;
- real MTA Server setup and HTTP API inventory;
- scenario-by-scenario results;
- measured timing/payload/retry behavior;
- IPv4/IPv6 and loopback-only conclusions;
- redacted token/security conclusions;
- request identity and idempotency-transport findings;
- verifier instructions/output;
- hashes and reproducible commands;
- proven/disproven assumptions;
- unproved boundaries;
- required project-document changes;
- whether a narrower follow-up is justified.

Keep disposable source, runtime and evidence under:

```text
.scratch/0004-mta-loopback-transport-prototype/
```

Do not present it as production ANKIGTA.

## Suggested skills

- **Required:** `/prototype`
- **Optional for official MTA API investigation:** `/research`
- **After completion:** `/handoff` back to the main design chat, then `/grill-with-docs`

Do not invoke `/implement`, `/to-spec` or `/to-tickets`.

## Exact prompt for the new prototype chat

Open a new chat in the same ANKIGTA workspace and send:

```text
/prototype

Используй handoff:
docs/handoffs/0004-mta-loopback-transport-prototype.md

Создай одноразовый prototype 0004 и проверь на настоящем MTA Server, может ли
server-side Lua надёжно и безопасно обмениваться HTTP-запросами с disposable
companion harness через loopback, сохраняя requestId/reviewTransactionId,
переживая disconnect/restart и оставаясь недоступным через LAN.

Перед началом прочитай все источники истины из handoff и учти результаты
prototypes 0001–0003. Полностью выполни safety setup, required scenarios,
success criteria и evidence requirements.

Обязателен реальный MTA Server. Результат только на mock Lua не принимается.
IPv4 loopback обязателен; IPv6 проверь по фактической поддержке среды. Не
используй external bind, LAN proxy, client-side Lua или CEF как gateway.

Используй только disposable generated token и не сохраняй его в логах,
отчёте или evidence. Не создавай production-код и не изменяй Anki.

Не исследуй FSRS/filtered deck, CEF rendering, Map Editor, AnkiWeb или profile
switching.

Сохрани канонический отчёт в:
docs/prototypes/0004-mta-loopback-transport.md

Добавь read-only verifier, структурированные evidence, secret/source scans и
SHA-256 manifest. Прототипный код и runtime оставь только под:
.scratch/0004-mta-loopback-transport-prototype/

Если безопасный server-side loopback невозможен либо требует ослабления
границы, зафиксируй failed/partially passed и точную границу без обхода.
```
