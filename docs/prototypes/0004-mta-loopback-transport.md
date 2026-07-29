# Prototype 0004 — MTA server-side loopback transport

**Verdict:** `partially passed`.

The **IPv4 transport gate itself passed**. The complete prototype is classified
as `partially passed` because a post-canonical environment inventory invoked the
official stable NSIS installer with a disposable `/D` target, but the installer
reused a pre-existing `C:\Games\MTA San Andreas 1.6` path. The canonical MTA
run had already completed entirely from `.scratch` and is unaffected; however,
byte-for-byte non-modification of that external installation was not captured
before the late action.

**Question tested:** Can a real MTA Server resource use server-side Lua to
exchange authenticated HTTP requests with a disposable companion on loopback,
keep `requestId` and `reviewTransactionId` distinct through loss/restart, and
remain unreachable through the machine's LAN address?

**Answer:** Yes on numeric IPv4 loopback (`127.0.0.1`) in the tested
environment. A real MTA Server resource completed the required server-side
`fetchRemote` exchanges, protected operations were authenticated before
execution, the LAN probe could not reach the listener, and retry/reconciliation
kept one stable `reviewTransactionId` with one logical execution. The tested MTA
HTTP path did not work with an otherwise functioning `::1` listener and returned
MTA/cURL status `6`; no external bind or gateway fallback was used.

This is a throwaway feasibility result, not production code or a production
storage/configuration design.

## Scope and safety boundary

The prototype read the handoff's sources of truth and treated these results from
Prototypes 0001–0003 as binding:

- transport retry is not scheduler success;
- a review keeps the original `reviewTransactionId` through uncertainty;
- timeout/disconnect means `Outcome Unknown`, not scheduler failure or success;
- reconnect never starts studying, creates an `ANKIGTA Session`, or opens Review
  Mode;
- only server-side Lua may act as the MTA gateway.

All generated code, the extracted server, logs, temporary journals and runtime
files used by the canonical transport run are under
`.scratch/0004-mta-loopback-transport-prototype/`. The only repository artifact
outside that disposable directory is this report. The prototype did not launch,
read or modify Anki, and it did not add production ANKIGTA code. It did not
investigate FSRS/filtered decks, CEF rendering, Map Editor, AnkiWeb or profile
switching.

Post-run safety deviation: a later environment inventory attempted to install
the official stable package into a disposable target, but NSIS reused the
pre-existing `C:\Games\MTA San Andreas 1.6` location. The external installation
and server directories predated the action (creation timestamps
`2026-07-22T17:43:36Z`), and the normal MTA resource directory retained its
older last-write timestamp (`2026-07-23T10:51:59Z`). The observed
`Uninstall.exe` last-write timestamp became `2026-07-29T01:13:08Z`. No normal
resource was intentionally edited or used by the canonical run, and no Anki or
production ANKIGTA data was touched, but there is no pre-action hash manifest
for the external installation. Structured details are retained in
`evidence/safety-deviation.json`.

The companion accepted only the exact numeric hosts `127.0.0.1` and `::1`.
External bind values were rejected before socket creation. No firewall rule,
LAN proxy, client-side Lua or CEF gateway was added. The disposable token was
generated per run, transferred through temporary files, loaded into memory,
removed, redacted from structured records and scanned before cleanup. No raw
token is retained in this report, logs or evidence.

## Tested environment

| Item | Observed value |
| --- | --- |
| Host OS | Windows 11 Pro, version `10.0.26200`, x64 |
| Python harness | CPython `3.14.6`, stdlib `ThreadingHTTPServer` |
| MTA package | Official Windows x64 server package `mtasa_x64-1.6-rc-24124-20260702.exe` |
| MTA runtime | `MTA:SA Server 1.6-release-24124`, sortable `1.6.0-9.24124.0`, netcode `474`, Windows x64 |
| Lua | Lua `5.1`, as reported inside the real resource |
| MTA package SHA-256 | `7971e3424a06beb2b6382099afa92292c8ef4d7f708b4ee81f7d3219fd89e39a` |
| Extracted `MTA Server64.exe` SHA-256 | `bef3ed99f86c452f4bcaccdcd91df3ad9de584d991e3f333866213a01b9c77af` |
| Stable full installer also checked | `mtasa-1.6.exe`, SHA-256 `b58328e72922321de59531acd139ff829cfc29270108e000956b5a1bd7c928b1` |
| Package signature | Valid Authenticode signature; signer `Open Source Developer, Kevin Natanael Gross`, Certum certificate thumbprint `249F84E70825961A975E1B2EC78F83391289B314` |
| Physical LAN address used for negative probe | `192.168.1.100/24` |

The packages came from the [official MTA nightly server page](https://nightly.mtasa.com/)
and the [official stable installer endpoint](https://mirror-cdn.multitheftauto.com/mtasa/main/mtasa-1.6.exe).
The real server did not enter its run loop directly from the repository's
Cyrillic path in this environment. The orchestrator temporarily mapped `P:` to
the same disposable runtime directory with `subst`; all files remained under
`.scratch`, and cleanup proved that the mapping was removed.

## Real MTA setup and HTTP API inventory

The extracted real server was configured only inside the disposable runtime:

- MTA game/server bind: `127.0.0.1`, UDP port `22143`;
- built-in MTA HTTP server disabled (`httpserver=0`);
- LAN broadcast and ASE disabled;
- only resource `p0004_transport` autostarted;
- `meta.xml` declares one script with `type="server"` and no client script or
  browser asset;
- ACL grants the disposable resource only the needed `fetchRemote` and
  `restartResource` capabilities.

The resource used the documented asynchronous server-side
[`fetchRemote`](https://wiki.multitheftauto.com/wiki/FetchRemote) options-table
form. It also observed `getRemoteRequestInfo` and exercised
`abortRemoteRequest`. The tested callback supplied body, status/error code and
response headers. `abortRemoteRequest` returned true but did not itself invoke a
callback in this build, so the prototype coordinator emitted a bounded
synthetic terminal status `1002` and quarantined any later callback. That
behavior is an observed prototype boundary, not a claimed MTA guarantee.

Every request carried a structured JSON envelope containing protocol version,
`requestId`, operation, collection identity and numeric `cardId`; review-like
operations also carried a separate `reviewTransactionId`. The companion journal
was keyed by `reviewTransactionId` plus a collection/card/rating predicate.
Identical replay returned the stored result and changed predicates returned
conflict.

## Scenario results

| Scenario | Verdict | Real observation |
| --- | --- | --- |
| S1 — IPv4 request | passed | 21/21 health/read callbacks completed through real server-side Lua with status `200`, headers/body and exact request correlation. |
| S2 — IPv6 | incompatible | Python/Windows bound `::1`, but MTA returned status `6` before the harness received an operation. No fallback was attempted. |
| S3 — client/CEF isolation | passed | Manifest/source scan found one server script, no client script, no CEF/browser assets, no client-event secret transfer and `fetchRemote` only in server Lua. |
| S4 — envelope/Unicode | passed | Stable request/review IDs, collection, 13-digit numeric card ID, Russian/English/Japanese/emoji and structured `400` error round-tripped. |
| S5 — token | passed | Correct token `200`; wrong and missing token `401` before operation execution; missing token `200` only in explicitly unprotected warning mode; raw-secret scan clean. |
| S6 — reachability | passed | `netstat` showed only `127.0.0.1:<ephemeral> LISTENING`; request through `192.168.1.100` timed out and did not reach the harness. |
| S7 — absent at startup | passed | Initial callback bounded at status `28` in 1,056 ms; later automatic and manual connect probes returned `200` in 41/46 ms; event-loop timer advanced and lifecycle stayed idle. |
| S8 — disappears | passed | Harness was killed after accepting a delayed review; MTA returned bounded status `56` in 41 ms, retained both IDs and continued timer ticks. |
| S9 — lost accepted reply | passed | Harness stored review then dropped reply; MTA saw status `52`; status reconciliation with the same review ID returned stored `logicalExecution=1`. |
| S10 — retry conflict | passed | Identical replay returned `200` with `replayed=true`; changed card/rating predicate returned structured `409`; mutation count remained one. |
| S11 — resource restart | passed | Resource stopped before callback, recorded unresolved state without success, restarted, then queried the original review ID and recovered execution one. |
| S12 — MTA restart | passed | After a stored result with dropped reply left `Outcome Unknown`, the whole MTA process was stopped/restarted; the original review ID reconciled to execution one. |
| S13 — automatic port | passed | Preferred port `53936` was occupied; harness and Lua used selected port `53937`; authenticated companion identity matched. |
| S14 — manual port | passed | Free loopback accepted; occupied, non-numeric, low/high range and external-bind values produced distinct structured errors. |
| S15 — adverse responses | passed | Nine malformed/slow/abort/close/status/identity/size cases all completed without pending or mixed callbacks. |
| S16 — parallel reads | passed | Six requests returned out of issue order at 40–566 ms with exact per-request callback identity. |
| S17 — serialization | passed | Two reviews shared one MTA queue and executed start/complete A then start/complete B; an independent read used a separate queue and overlapped safely. |
| S18 — reconnect lifecycle | passed | Disconnect, auto/manual reconnect, resource restart, harness/server restart and port change were exercised; studying/session/Review Mode flags stayed false. |
| S19 — shutdown | passed | Final MTA shutdown was resource-requested and exited `0`; harness stopped gracefully; no listener, MTA process, secret file or `subst` mapping remained. |

### S12 precision

S12 proves recovery of an unresolved **logical outcome** after a full MTA
restart. The first MTA instance had already received transport status `52`
after the companion durably stored the review and deliberately dropped the
reply; it was then stopped. This does not prove that MTA preserves an in-flight
Lua object, callback or socket across process death. Recovery came from the
stable `reviewTransactionId` and the disposable companion journal, as intended.

## Timing, size and retry evidence

Twenty successful small reads in S1 measured from Lua issue tick to callback:

- minimum `42 ms`;
- median `206 ms`;
- maximum `369 ms`.

These reads were issued at 40 ms spacing, so later callback latency includes
MTA queueing. This is not a production service-level claim.

Payload checkpoints:

| Requested blob | Retained HTTP body size | Lua callback latency | Result |
| ---: | ---: | ---: | --- |
| 64 KiB | 65,820 bytes | 44 ms | success |
| 256 KiB | 262,429 bytes | 46 ms | success |
| 1 MiB | 1,048,862 bytes | 96 ms | success |
| 2 MiB adverse observation | 2,097,433 bytes | 580 ms | success |

No payload failure was observed through a 2 MiB payload. This establishes no
universal MTA limit; a production design still needs an explicit application
cap and timeout policy.

Other measured boundaries:

- companion absent: configured connection timeout `1,200 ms`, callback status
  `28` after `1,056 ms`;
- harness killed during request: status `56` after `41 ms`;
- reply dropped after store: status `52` after `40 ms`;
- explicit abort: `abortRemoteRequest=true`, synthetic coordinator status
  `1002` after `703 ms`;
- 700 ms delayed response: success after `745 ms`;
- six varied-delay parallel reads: `40, 120, 161, 241, 404, 566 ms`;
- every retained request used one configured MTA connection attempt;
- lost-response, identical replay, conflict, resource restart and MTA restart
  all retained the original review ID and reported logical execution `1`.

MTA's HTTP layer treated malformed JSON, wrong content type and wrong response
identity as successful HTTP `200` transports. The application boundary must
therefore validate JSON, `Content-Type`, required fields and response identity
before accepting a result. Premature close produced `52`; explicit HTTP error
preserved `503`. The prototype verifier performs those protocol checks without
claiming that MTA itself does.

## Security conclusions

Proved in this environment:

- the IPv4 companion socket was bound to `127.0.0.1`, never `0.0.0.0`;
- an IPv6 test socket was bound to `::1`, never `::`;
- the LAN-address path could not reach the IPv4 listener;
- protected authorization was checked before operation dispatch;
- authorization errors disclosed no expected credential;
- no raw disposable credential remained in the scanned source, logs, report or
  structured evidence;
- client-side Lua and CEF did not participate;
- reconnect paths did not begin a study lifecycle.

Loopback is a network-exposure boundary, not an authorization boundary.
Protected mode remains required because other local processes can reach
loopback. Explicit unprotected mode was included only to prove that disabling
authentication is a deliberate, visibly weaker state.

## Proven and disproven assumptions

Proven:

- real MTA Server 1.6 server-side Lua can call an IPv4 loopback HTTP companion;
- asynchronous callbacks remain responsive while the companion is absent,
  delayed or disappears;
- numeric `requestId`/review transaction correlation survives out-of-order
  callbacks and retry/reconciliation;
- stable review identity plus a journal can distinguish identical replay from a
  conflicting mutation;
- loopback-only listener configuration can survive automatic port conflict
  handling without relaxing to LAN exposure.

Disproven or narrowed:

- IPv4 success does not imply IPv6 success; the tested MTA path failed against a
  live `::1` listener with status `6`;
- HTTP `200` does not imply a valid application response;
- a transport failure does not prove that a review was not executed;
- `abortRemoteRequest=true` does not guarantee a later MTA callback in the
  tested build;
- one successful 2 MiB response does not imply an unlimited safe payload.

## Unproved boundaries

- The disposable orchestrator writes the chosen port to both prototype sides.
  It does **not** prove an atomic production two-sided configuration/storage
  design.
- The JSON companion journal proves transport reconciliation only. It is not a
  production durable store, an Anki transaction, or proof of scheduler
  idempotency.
- The prototype did not exercise Anki, `anki.scheduler.answerCard`, add-on
  permissions, or collection locking.
- No production latency, response-size, retry, queue-depth or timeout thresholds
  are established by this single Windows machine.
- IPv6 remains unsupported for this product boundary until a narrower real-MTA
  investigation explains status `6` and passes without external binding.
- General clean shutdown is demonstrated by S19. Earlier scenario processes
  were intentionally terminated by the orchestrator after evidence capture and
  commonly exited `1`; those exits are not presented as graceful.

## Evidence and verifier

Primary structured evidence is in
`.scratch/0004-mta-loopback-transport-prototype/evidence/`:

- `environment.json`;
- `scenarios.json`;
- `secret-scan.json`;
- `source-scan.json`;
- `safety-deviation.json`;
- `cleanup.json`;
- `manifest.json`.

Raw per-process event timelines, redacted listener records, MTA stdout/stderr
and disposable review journals are under `runtime/suite-harness/` and
`runtime/suite-mta/`. The initial exploratory run is retained separately under
`failed-attempts/orchestrator-run-01/`; it exposed the no-callback abort behavior
and was not used as canonical evidence.

Run the complete disposable experiment, manifest build and verifier from the
repository root:

```powershell
& .\.scratch\0004-mta-loopback-transport-prototype\run.ps1
```

Run only the read-only verifier:

```powershell
python .\.scratch\0004-mta-loopback-transport-prototype\verify_evidence.py
```

The manifest covers prototype source, disposable MTA resource/configuration,
primary evidence and this report. The verifier rehashes every entry, evaluates
S1–S19, reports IPv4/IPv6 separately and prints measured/unproved boundaries.
The canonical read-only verification completed with:

```text
evidence verification result: passed
S1, S3–S19: passed
S2: incompatible — MTA fetchRemote status 6 against a live ::1 listener
IPv4 verdict: passed
IPv6 verdict: incompatible
overall verdict: partially passed (IPv4 transport passed; post-run safety deviation)
manifest errors: none
```

## Required project-document changes

No production document was changed by this prototype. A subsequent decision
change should:

1. update the confirmed baseline from “real MTA loopback unproved” to “real MTA
   server-side IPv4 loopback passed on Windows/MTA 1.6 build 24124”;
2. document numeric IPv4 loopback as the supported transport boundary and IPv6
   as currently incompatible;
3. require protected mode, response-envelope validation, explicit payload caps
   and `Outcome Unknown` reconciliation;
4. create a production ADR for atomic companion port/config publication and
   durable review-result reconciliation before implementation.

## Follow-up

A broad transport prototype is not needed again. Two narrower follow-ups are
justified before production work:

- diagnose MTA status `6` for a numeric `[::1]` URL on this Windows build,
  without external bind or proxy;
- design and test the production atomic port/config handoff plus durable
  reconciliation store. That work must remain separate from Anki scheduler
  behavior.
