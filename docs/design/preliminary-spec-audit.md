# Preliminary specification audit

> Sources: `SHARED - Интеграция Anki с MTA.md` and `ANKIGTA_SPEC.md`. Both are treated as preliminary. The user subsequently confirmed that decisions marked accepted in the source interview are valid even where the export omitted an intervening reply.

## Verdict

The product direction and high-level architecture are clear enough to continue design, but the current `ANKIGTA_SPEC.md` is not implementation-ready. It predates later accepted decisions and still contains several contradicted statements.

Review ownership is resolved at the design level: the companion add-on coordinates a transaction and Anki owns scheduling. Prototype 0001 failed direct rating of an arbitrary non-top card, Prototype 0002 passed exact admission through an owned filtered deck, and Prototype 0003 partially passed: durable exactly-once recovery worked at tested restart boundaries, while supported profile switching and safe immediate cleanup of an in-flight standard Reviewer rating did not. Prototype 0004 also partially passed: the real MTA server-side IPv4 loopback path, isolation, token checks and reconnect/replay behavior worked, while IPv6 was incompatible and production configuration persistence and limits remain unproved. Prototype 0005 failed after a limited runtime smoke-check and source/manual proof: supported EDF/element-data storage exists, but stock Editor lacks identity-aware collision handling, a public durable read-back completion contract, external-conflict protection and an atomic whole-save transaction; S1–S18 remain unexecuted end-to-end. Prototype 0006 failed the original strict CEF contract; v1 now deliberately accepts stock-MTA bridge/navigation limits and best-effort rendering without rating blocks for rendering errors or External Card Page.

## Already answered explicitly

- Product purpose: spatially situated Anki study inside MTA.
- Supported Map Editor entity types: object, vehicle and ped.
- Per-entity radius receives a copied default; default is 3 m.
- Stable entity ID is automatically assigned and persisted through a verified map save.
- Runtime markers/zones follow live dynamic entities; destruction does not delete the saved link.
- ANKIGTA does not respawn destroyed entities.
- A real rescheduling filtered deck passed its compatibility prototype on Anki 26.05.
- Server-side Lua is the sole gateway to the privileged companion control API; real MTA `fetchRemote` proved this path over `127.0.0.1` without a client-side Lua or CEF control gateway.
- Anki, companion add-on and MTA Server are on the same computer in v1.
- The user launches Anki Desktop and opens the intended profile; ANKIGTA never launches Anki or switches profiles.
- Companion add-on installation and updates are manual; ANKIGTA treats a missing/nonresponsive add-on as a normal connection failure and has no separate add-on version-compatibility flow.
- ANKIGTA never closes Anki Desktop on MTA/resource shutdown; it only cleans up its filtered deck and connection.
- If Anki is absent or later closes, ANKIGTA pauses study and asks the user to open it.
- Reopening Anki triggers automatic reconnection, while a manual `Connect` button remains available whenever disconnected.
- Reconnection reconciles pending ratings but leaves study paused; it does not rebuild the filtered deck, reactivate spatial triggers or reopen a review automatically.
- Initial connection also leaves study inactive until the user explicitly chooses `Start studying`.
- ANKIGTA never triggers or waits for AnkiWeb sync and has no cloud-sync settings; it uses the current local bound collection.
- A user-initiated AnkiWeb sync takes priority: ANKIGTA resolves any submitted rating, closes an unrated review, cleans its filtered deck and remains paused afterward.
- Standard Anki Reviewer and ANKIGTA study are mutually exclusive; starting the Reviewer pauses and cleans up ANKIGTA, which must later be restarted explicitly.
- Token is optional with a dismissible warning; connection failures are diagnosed automatically.
- Token protection is enabled by default, generated and configured on both local components automatically; explicitly disabling it produces the warning.
- Companion add-on owns automatic port/token configuration and, after one-time selection of the MTA resource folder, atomically publishes a local connection file for MTA to read.
- Both the companion add-on and MTA advanced settings retain manual port/token replacement fields; the current token is never revealed in plaintext.
- Entering a manual port or token enables a local Manual Connection Mode; automatic configuration does not overwrite it, and an effective-config mismatch blocks connection with an explicit error until both sides are manually aligned or returned to Automatic Connection Mode.
- v1 trusts the local Windows machine and its processes; the token prevents accidental requests and separates card content from the control API, but is not a defense against local malware or an administrator. No special encrypted vault is required, while UI and log redaction remain mandatory.
- Automatic connection config keeps one last-known-good version; a new file is validated before atomic replacement, and MTA falls back with an explicit error when the new format/version/protocol identity is invalid.
- A transport request keeps a distinct `requestId`; a rating additionally keeps its original `reviewTransactionId` across timeout, lost response and restart.
- Ordinary control requests time out after 5 seconds; read-only operations retry once with the same `requestId`, ratings reconcile the same `reviewTransactionId`, and session rebuild has a separate 30-second timeout with progress.
- Reconnect never starts studying, creates a filtered deck or opens Review Mode automatically.
- Review Protection is separate from control disabling.
- The driving speed gate is always active, configurable, and defaults to 10000 km/h.
- Loaded maps are included by default and may be excluded with `Include in study`.
- The study queue is global across interior/dimension.
- Teleport is deliberately direct and transports the occupied vehicle and passengers.
- Unavailable entities remain visible at authored coordinates.
- `Activation Zone` is a world-space sphere; `Minimap Blip` is a separate concept.
- `Close after rating` is boolean and applies to every accepted rating.
- A missing individual media asset does not by itself block rating.
- Supported cards render best effort inside stock MTA CEF; v1 does not promise pixel-perfect or fully behaviorally equivalent output relative to Anki Desktop. CEF may contact only a separate read-only add-on content endpoint through a short-lived per-render capability; it never receives companion control operations or the permanent connection token. The 2 MiB cap applies to control JSON, not the whole card.
- Card CEF may load external HTTP(S) images, fonts, styles and scripts through stock MTA domain permissions. A card-visible `window.mta` stub is accepted because native remote dispatch is denied.
- The top-level Review Mode remains outside the card surface and stock MTA blocks popups. Main-frame navigation inside the card surface may occur for an allowed external domain; system-browser handoff, download behavior and third-party pages are not supported v1 promises.
- An External Card Page leaves rating available; `Вернуться к карточке` is an optional convenience action.
- Statistics use `Total`, `New`, `Learning`, `Due`, and `Early`, counting unique cards.
- Companion add-on is the sole Review Transaction coordinator; Anki owns scheduling.
- Ratings are idempotent by `reviewTransactionId`.
- Recovery is automatic: an already-applied rating is acknowledged, a provably unapplied rating is resent, and an unknown result keeps only that card blocked while reconciliation continues.
- Card links are scoped by Anki collection identity.
- v1 pauses study when Anki leaves the bound collection; it never migrates links or matches another collection by `cardId`.
- The user selects one Bound Anki Collection; the selected deck is only an initial Card Picker filter and never scopes existing links or the study session.
- Profile switching closes an unrated card without mutation, but waits for an already-submitted Review Transaction to reconcile before changing collections.
- Open reviews may finish across map/link/runtime changes.
- v1 supports tested Anki Desktop versions on Windows with FSRS.
- Unsupported, unsafe or broken templates show a warning but remain rateable at the user's discretion.
- Review Protection is enabled by default.
- Early reviews change scheduling only through supported Anki behavior, otherwise they degrade to Preview only.
- Not-due cards default to Preview only; the explicit `Allow early review` setting enables supported Anki rating with a warning and never overrides suspended/buried state.
- With early review enabled, not-due cards participate fully in the filtered deck, spatial activation and next-card indication; otherwise they remain outside automatic study.
- Statistics include a separate `Early` count; `Total` is the unique union of `New`, `Learning`, `Due` and `Early`.
- `Early` remains visible and shows zero when early review is disabled or empty.
- Session start, pause, cleanup and crash ordering are defined at the product level.
- Maps have persistent identities with an explicit copied-map decision.
- Spatial activation is restricted to the current interior/dimension even though the study queue is global.
- Card audio and world muting are separate.

## Partially answered

| Topic | What is known | What is still missing |
| --- | --- | --- |
| Activation radius | Copied default, default 3 m, range 0.5–50 m, step 0.5 m, explicit validation | Persistence and migration of values from future schema versions |
| Automatic opening delay | Global numeric seconds field; default 1; range 0–60; two decimal places; explicit validation | Persistence and migration of values from future schema versions |
| Stable identity | v1 uses the stock MTA Map Editor without a fork: EDF custom child for map identity, element data/EDF for entity ID, duplicate blocking, automatic post-save read-back and manual `Проверить ещё раз`. Stock save atomicity and external-change protection are explicitly not promised. | End-to-end validation of assignment/save/reload/copy scenarios |
| Filtered deck | Real rescheduling deck, full-set rebuild, X-only Exact Card Admission, rating and cleanup passed on Anki 26.05; all linked new cards are admitted with a warning beyond Anki's daily limit | Production API contract, version matrix and atomic-rebuild crash handling |
| Durable review recovery | Collection-scoped journal, restart recovery, identical/conflicting retry and `Outcome Unknown` quarantine passed at the injected Prototype 0003 boundaries | Production storage/GC, native commit receipt and termination inside Anki's atomic answer/rebuild operation |
| Collection identity | Add-on-owned UUID distinguished equal card IDs and survived restart/profile rename; a present original forces a duplicate to become new, while an absent original permits a restore/move decision | Technical collision detection, local registration and atomic UUID assignment |
| Profile switching | No documented supported add-on API; ANKIGTA deliberately does not launch Anki or switch profiles | User opens the intended profile; technical work is limited to detecting and validating the Bound Anki Collection |
| Standard Reviewer arbitration | Unrated question/answer can leave without mutation; an in-flight rating keeps Reviewer state until its callback finishes, then closes and starts ANKIGTA | AQT close surface remains version-sensitive; timeout/error handling must never force cleanup |
| Same-host security and transport | Real MTA IPv4 loopback, LAN isolation, token validation/redaction, automatic free-port selection, manual override, bounded failure, reconnect and replay identity passed; v1 is explicitly limited to `127.0.0.1`, with incompatible `::1` excluded; add-on owns automatic config and publishes it to the selected MTA resource folder, while both UIs retain advanced manual replacement fields; mismatch blocks connection without silent overwrite; 5-second control timeout, one identical read retry and 30-second rebuild timeout are accepted; the local machine/processes are trusted and no encrypted vault is required; one last-known-good config is retained for validated atomic rollback | Technical proof of the accepted atomic commit/recovery contract, content streaming limits and production backpressure thresholds |
| World contexts | Queue is global; spatial interaction is local to current interior/dimension | Race handling while the player changes world context |
| Review protection | Damage prevention is separate from controls and enabled by default | Exact damage/event coverage and restoration after crashes |
| Settings | Server/client/add-on/connection ownership and collection scope are defined | Storage schema, migrations and technical synchronization |
| Statistics | `Total`, `New`, `Learning`, `Due` and `Early` meanings and uniqueness are agreed | Exact scheduler query and update timing |
| Card rendering | Stock MTA CEF rendering is best effort without a pixel/behavioral-equivalence promise; rendering, template, JavaScript and media errors warn but do not block rating; External Card Page also leaves rating available and has an optional return action; content uses a short-lived read-only capability with no companion control access; external HTTP(S) resources and child-surface navigation use stock MTA behavior; a non-privileged `window.mta` stub is accepted; popups remain stock-blocked; system-browser handoff/download behavior are unsupported | Real-MTA smoke and lifecycle tests of the reduced supported behavior |
| Unavailable cards | Suspended/buried links remain visible and support Preview only, but never rating or automatic activation | Scheduler-state refresh timing |
| Anki synchronization | Anki owns study data; ANKIGTA owns spatial/game data; automatic refresh, no heuristic card replacement, and pause on collection change | Companion change-notification, cache validation and stable production collection identity |
| Player scope | Single MTA Admin is the only Study Player; multiplayer study is permanently excluded | Technical validation of MTA ACL authorization |
| Change history and relinking | Last 100 eligible user edits plus reversible Entity missing relink with metadata transfer and identity preservation | Technical validation |
| Pick Entity | World selection of visible managed Runtime Instances with modal input and list fallback | Raycast/streaming validation in MTA |

## Contradictions

| Current preliminary spec | Explicitly supported direction |
| --- | --- |
| Client-side Lua is the Anki gateway | Server-side Lua is the only MTA-side gateway |
| API token is required before linking | Token is optional; absence produces a dismissible warning |
| Only `object` elements are managed | object, vehicle and ped are managed |
| `Allow automatic activation while driving` checkbox | No checkbox; an always-active configurable speed threshold |
| Counter is named `Remaining` | Counter is named `Total` |
| `Close after successful rating` | `Close after rating`, boolean, closes after any accepted rating |
| Destroyed object implies `Object missing` | A destroyed Runtime Instance is not the same as a missing persisted Map Entity |
| Q28 is the current unresolved question | Q28 and later decisions are confirmed by the user's subsequent blanket confirmation |
| Compound key `resource + map file + object ID` is final | Persistent `ankigtaMapId` plus entity ID survives rename; copied-ID conflicts require a user choice |
| Card identity is only `cardId` | Card identity is scoped by Anki collection identity |
| Profile name/path can identify a collection | Equal card IDs exist across profiles; name/path are not stable identity |
| A non-private Anki method is automatically a supported add-on API | Prototype 0003 found working non-private profile/Reviewer surfaces without a documented add-on contract |
| Closing Reviewer UI cancels or safely detaches an in-flight rating | The backend may commit while the stock callback still depends on Reviewer state; immediate cleanup is unsafe |
| A successful IPv4 loopback test implies that MTA can also use `::1` | On the tested build, MTA returned status `6` before reaching a working IPv6 listener |
| HTTP `200` proves that a companion operation succeeded | Success requires valid Content-Type, JSON envelope, required fields and matching request/transaction identity |
| `abortRemoteRequest=true` guarantees the normal callback | On the tested build it did not; the prototype required a synthetic terminal outcome and quarantine of a late callback |
| A remote MTA browser does not expose `window.mta` | Reference source injects it into every V8 context; native `isLocal` blocks privileged dispatch, but the stub remains card-visible |
| External subresources can be allowed without allowing navigation to the same domain | Stock MTA uses one domain allow-state for both resource loading and main-frame navigation |
| The Lua popup event can prove a genuine user click | Native CEF receives `user_gesture`, but stock MTA does not pass it to Lua |

## Decisions still requiring implementation detail or proof

- Exact SQLite schema, migration rules and transaction boundaries.
- Exact companion API and the internal Anki interfaces it may safely use.
- Real-MTA smoke and lifecycle tests for best-effort rendering, media playback and non-blocking error warnings.
- Versioned production API and recovery contract for full-set and X-only filtered-deck rebuilds.
- A supported query for classifying a new card as beyond today's original-deck limit without reimplementing Anki scheduling.
- Production durable-journal storage, garbage collection and atomic-backend crash handling; process-restart recovery itself passed the tested Prototype 0003 boundaries.
- Technical proof for detecting copied collection UUIDs and atomically assigning a new UUID after the confirmed Collection Copy Decision.
- Reliable detection and validation of the user-opened Bound Anki Collection.
- Versioned integration contract for Reviewer close and callback completion; a timeout must block session start instead of forcing cleanup.
- Technical proof of the accepted temporary-write/validate/atomic-replace/one-version rollback protocol for the add-on-owned connection file.
- Production transport policies for content streaming/range/cache/per-media limits, backpressure, callback quarantine and validation of every response envelope; limits must preserve supported-card rendering fidelity.
- End-to-end proof of automatic post-save read-back and the manual `Проверить ещё раз` fallback.
- Repeatable benchmark harness for the confirmed F7, spatial-index, session-rebuild and large-collection limits.

## Critical gaps

1. **Remaining recovery boundaries.** Specify production journal storage/GC and prove or safely bound atomic-backend interruption; keep `Outcome Unknown` quarantined.
2. **Collection identity proof.** Prove duplicate detection and atomic UUID assignment for the accepted original-vs-new copy decision.
3. **Map/entity persistence.** The architecture now deliberately accepts stock Editor save limitations. The EDF/element-data identity workflow, duplicate blocking and post-save read-back still require end-to-end proof.
4. **Trust boundary.** Keep the accepted numeric IPv4-only loopback path and trusted-local-machine model. Prototype 0006 proved the disposable content capability model; v1 deliberately accepts stock-MTA bridge/navigation/link limitations and still needs real-MTA validation of the reduced contract. Atomic connection-config publication also remains open.
5. **Versioned session contract.** Turn the passed create/rebuild/admit/pause/cleanup behavior into a supported production API with repeatable compatibility tests.
6. **Optional product polish.** Exact colors may be resolved later; gamepad and all bulk operations are excluded.
7. **Acceptance proof.** Implement repeatable end-to-end, benchmark, migration and recovery tests for the confirmed Definition of Done.
8. **Automatic backups.** Implement and test the confirmed seven-daily/three-pre-migration rotation and explicit corruption recovery flow.

## Implementation readiness

The confirmed design is ready to be converted into a buildable specification. It is not ready for direct implementation from this audit alone: the specification must turn the accepted Anki lifecycle fallbacks, stock Map Editor limitations, transport work and best-effort CEF behavior into explicit tickets and acceptance tests.
