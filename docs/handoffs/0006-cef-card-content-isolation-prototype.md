# Handoff: Prototype 0006 — MTA CEF card rendering and isolation

## Purpose

This handoff is for a fresh, separate ANKIGTA prototype chat. It must answer one
technical risk question with disposable evidence and must not create production
ANKIGTA code:

> Может ли настоящий MTA CEF семантически эквивалентно отображать поддерживаемые
> Anki HTML/CSS/JavaScript/media через отдельный read-only loopback content
> endpoint, не предоставляя карточке MTA bridge, постоянный connection token или
> привилегированный control API, и при этом надёжно ограничивать capability,
> навигацию, popup и downloads?

The prototype may return `passed`, `partially passed` or `failed`. Do not hide
unsupported CEF behavior by rewriting or simplifying the test cards until they
cease to represent the original feature.

## Repository and authority

Repository:

```text
C:\Проекты\Программы\ANKIGTA
```

Read in this order:

1. `AGENTS.md`
2. `CONTEXT.md`
3. `docs/design/confirmed-baseline.md`
4. `docs/design/preliminary-spec-audit.md`
5. `docs/design/development-flow.md`
6. relevant ADRs:
   - `docs/adr/0002-use-server-side-lua-as-the-anki-gateway.md`
   - `docs/adr/0006-allow-an-optional-token-on-the-same-host.md`
   - `docs/adr/0007-make-the-companion-add-on-the-review-coordinator.md`
   - `docs/adr/0008-make-ratings-idempotent.md`
   - `docs/adr/0010-isolate-card-content-from-the-mta-bridge.md`
   - `docs/adr/0012-limit-v1-to-tested-anki-on-windows-with-fsrs.md`
   - `docs/adr/0014-split-settings-by-authority.md`
   - `docs/adr/0017-keep-anki-authoritative-for-study-data.md`
7. previous prototype reports only as constraints:
   - `docs/prototypes/0001-exact-card-idempotent-review.md`
   - `docs/prototypes/0002-filtered-deck-fsrs-admission.md`
   - `docs/prototypes/0003-companion-lifecycle-recovery.md`
   - `docs/prototypes/0004-mta-loopback-transport.md`
   - `docs/prototypes/0005-map-editor-identity-persistence.md`

`ANKIGTA_SPEC.md` and the original interview export are preliminary raw
material. Current glossary, accepted ADRs, confirmed baseline and verified
prototype evidence take precedence.

## Fixed product rules

Do not reopen these rules inside the prototype:

- Only server-side Lua may call the privileged companion control API.
- Client-side Lua and CEF never receive rating, scheduler, collection or
  session-control operations.
- Card JavaScript never receives the MTA bridge.
- Supported cards preserve Anki HTML, CSS, allowed JavaScript and media
  semantically; transport must not arbitrarily strip, truncate or rewrite them.
- After server-side admission, CEF may load the current render from a separate
  read-only loopback content endpoint.
- Access uses a short-lived capability URL for one render, not the permanent
  connection token.
- The content endpoint cannot rate cards, change scheduling, browse the
  collection, reveal the permanent token or invoke MTA functions.
- v1 uses numeric IPv4 loopback `127.0.0.1` only. IPv6 `::1`, LAN and external
  binding are unsupported.
- The 2 MiB limit applies to control JSON, not to the complete card. HTML and
  media use the separate content path.
- External HTTP(S) images, fonts, styles and scripts may load.
- Card content cannot replace top-level Review Mode, open popups
  automatically, navigate externally or start downloads.
- A link explicitly activated by the user opens in the Windows system browser.
- A missing individual media file shows a placeholder and warning but does not
  by itself block rating.
- An unsafe or fundamentally broken template receives a static safe preview
  and cannot be rated.
- Card audio and game-world muting are separate.
- Review Mode remains modal; loss of focus does not close or rate the card.
- Reconnection or content-endpoint recovery never starts studying or reopens
  Review Mode automatically.

## Prior evidence that constrains this prototype

- Prototype 0001 proved that rendering an arbitrary card and scheduler
  admission are different capabilities.
- Prototype 0002 proved Exact Card Admission on Anki 26.05. Do not repeat its
  scheduler matrix.
- Prototype 0003 proved durable transaction boundaries but found unsafe
  standard-Reviewer cleanup. Do not manipulate the normal Reviewer.
- Prototype 0004 proved the privileged server-side IPv4 control path. This
  prototype must keep content traffic separate and must not turn CEF into a
  second control gateway.
- Prototype 0005 established a safety fact about the installed MTA client: it
  is not portable and may write registered config/log paths even when connected
  to a disposable server. Capture, archive and restore such changes exactly;
  do not claim they remain inside the sandbox.

## Scope

Build the smallest disposable system that contains:

- a real MTA Server and client using real MTA CEF;
- one disposable MTA resource with a top-level Review Mode shell;
- a disposable loopback content harness emulating only the companion
  read-only content endpoint;
- short-lived per-render capabilities;
- a representative card corpus;
- structured browser, server and endpoint evidence;
- a read-only verifier.

The harness may use generated card fixtures and disposable Anki-produced
render snapshots. It must not open or alter the user's Anki profiles. It must
not implement scheduling, filtered decks, production connection config,
Spatial Link, F7 or production ANKIGTA code.

## Safety boundary

All prototype source, runtime copies, fixtures and evidence must live under:

```text
.scratch/0006-cef-card-content-isolation-prototype/
```

Before launching:

- resolve every absolute path;
- require an explicit prototype-only allow marker;
- record exact Windows, MTA, CEF/Chromium and harness versions;
- record a SHA-256 pre-run manifest for installed MTA, watched client
  config/log files, Anki preferences/collections, GTA settings, repository
  production documents and known user resources;
- use a disposable MTA Server/resource set and fresh ports;
- do not run an installer over an existing MTA installation.

After every destructive/adverse scenario:

- preserve logs, screenshots and structured events;
- record before/after hashes;
- stop MTA/GTA/harness processes;
- remove temporary listeners and mappings;
- archive external MTA-client config/log deviations, restore original bytes and
  prove exact post-cleanup hashes.

Never use user/production maps or resources as fixtures.

### Concurrent read-only MTA source reference

Optional reference source:

```text
C:\Проекты\Программы\GTARESTORED\PED BEHAVIOUR REFERENCE\MTA source code\
```

Another active ticket owns this directory. Treat it as concurrently mutable
and strictly read-only:

- no writes, Git/worktree operations, build/test, cache generation or
  formatting;
- read only individually needed files;
- record per-file SHA-256 and read time;
- do not attribute whole-tree diffs to Prototype 0006;
- if a file changes concurrently, reread it and record the uncertainty.

Observed runtime and hashed installed resources take precedence over this
reference tree.

## Card corpus

Prepare a versioned disposable corpus containing at least:

1. plain text and Unicode;
2. Anki-style front/back HTML and shared CSS;
3. CSS layout, fonts, pseudo-elements and animations;
4. safe inline and external JavaScript interaction;
5. local image, SVG, audio and video where MTA CEF supports them;
6. relative media URLs, escaped filenames, spaces and Unicode filenames;
7. multiple audio files and autoplay semantics matching the current side;
8. MathJax/LaTeX-style output or another realistic script-heavy template;
9. external HTTP(S) image, font, stylesheet and script;
10. missing media;
11. large HTML and media files;
12. popup, navigation, download and bridge-probing adversarial fixtures;
13. malformed/unsafe template requiring static preview.

For each supported fixture, retain a reference render from a controlled ordinary
browser or disposable Anki rendering surface. Record where pixel equivalence is
impossible and compare DOM, computed styles, dimensions, visible text,
interaction and media events instead.

## Capability contract to exercise

Each render capability must be:

- unguessable;
- bound to one collection identity, card ID, side and render generation;
- accepted only by the read-only content endpoint;
- unable to authorize control endpoints;
- invalid for another card or side;
- invalid after Review Mode closes;
- invalid after a short declared timeout;
- safe under identical subresource retries;
- absent from normal logs, external navigation targets and card-visible global
  state except where needed in the current document/subresource URLs.

Declare the capability lifetime before testing. Measure whether one-time use is
compatible with the multiple HTML/media requests a real page requires; if not,
define “one render” as a bounded request set rather than a single HTTP request
and report the exact rule.

## Required scenarios

### S1 — Real MTA CEF baseline

Open the disposable Review Mode in real MTA CEF and render the plain/Unicode
fixture. Prove the card document is inside the intended child content surface
and the top-level Review Mode remains controlled by ANKIGTA.

### S2 — HTML/CSS fidelity

Render representative Anki HTML/CSS fixtures. Compare visible text, DOM,
computed styles, layout dimensions and screenshots against the declared
reference. Record every material divergence.

### S3 — Allowed JavaScript behavior

Exercise buttons, reveal logic, timers, DOM updates and safe script-loaded
behavior. Prove allowed behavior works without MTA bridge access.

### S4 — Local media

Load local image/SVG/audio/video fixtures through the content endpoint. Verify
MIME type, relative URL resolution, Unicode/escaped filenames, playback events
and current-side audio behavior.

### S5 — Missing media

Request one absent media file. Show a placeholder and warning, keep Review Mode
usable and prove this alone does not mark the template unsafe.

### S6 — External HTTP(S) subresources

Load external image, font, CSS and JavaScript resources. Prove they work as
subresources while receiving no control token, MTA bridge or capability for a
different render.

### S7 — MTA bridge isolation

From card JavaScript, probe all known MTA/CEF bridge surfaces, parent/top/opener,
message channels and injected globals. The card must not call MTA functions,
client events or privileged Lua. A mere naming convention is not isolation.

### S8 — Control API isolation

Attempt rating, scheduler, collection and session requests from card content
using the render capability, missing token, guessed token and any content
endpoint method. Every mutation/control attempt must fail before dispatch.

### S9 — Cross-card and cross-side capability use

Use Card A capability for Card B, question capability for answer, expired
generation for a new render and a capability from a closed Review Mode. All
must fail without revealing whether the target card exists.

### S10 — Capability expiry and replay

Measure normal HTML/media request fan-out, identical retries, timeout expiry and
close-time revocation. No request after expiry may fetch new protected content.
Already loaded pixels may remain visible, but no privileged state may persist.

### S11 — Top-level navigation

Exercise redirects, `window.location`, forms, meta refresh, `target=_top`,
iframe escape and history manipulation. Card content must not replace the
top-level Review Mode or navigate MTA externally.

### S12 — Popups, new windows and downloads

Exercise `window.open`, `target=_blank`, JavaScript-created anchors, blob/data
URLs, attachment responses and automatic downloads. Automatic popup/download
must be blocked and leave Review Mode intact.

### S13 — Explicit user link

Perform a genuine user click on an allowed HTTP(S) link. Prove exactly one URL
opens in the Windows system browser and no automatic/script-only equivalent
does. Record any unavoidable external browser state and close it afterward.

### S14 — Unsafe or broken template

Feed malformed HTML, prohibited behavior and a fixture that cannot be presented
completely. Show static safe preview, block rating and preserve the Review Mode
shell.

### S15 — Size, streaming and range

Test declared checkpoints for large HTML, image, audio and video. Measure:

- maximum accepted HTML document size;
- per-media limit;
- total render budget;
- Range request behavior;
- streaming versus full buffering;
- memory growth and first-paint latency;
- cancellation when Review Mode closes.

Do not infer an unlimited safe size from one successful payload.

### S16 — Cache and freshness

Render a card, change its disposable source generation, render again and prove
the new capability cannot receive stale HTML/media from another card or side.
Record cache headers, cache key and cleanup behavior.

### S17 — Concurrency and backpressure

Open a media-heavy render while issuing multiple subresource requests and an
independent read. Prove bounded queues, correct per-render identity, no mixed
responses and a responsive top-level Review Mode.

### S18 — Endpoint and MTA failure

Stop or delay the content harness, close connections, return malformed MIME,
wrong identity, partial data and server errors. Review Mode must remain
closable, rating must be blocked when presentation is incomplete and recovery
must not auto-open the card.

### S19 — Review Mode lifecycle

Close with `Esc`, lose/regain focus, restart the disposable resource and
disconnect/reconnect. Prove capability revocation, restoration of cursor/input/
audio state and absence of automatic reopen or rating.

### S20 — Source and manifest isolation

Scan executable prototype sources and manifests. Prove:

- no client-side/CEF privileged control gateway;
- no permanent token injection;
- no production paths or Anki-profile access;
- no production ANKIGTA code;
- no unrecorded external changes after cleanup.

## Success criteria

The prototype passes only if:

1. real MTA CEF renders the supported corpus with declared semantic fidelity;
2. allowed JavaScript and local/external media work within a documented
   envelope;
3. card JavaScript cannot access MTA bridge, client events, permanent token or
   control API;
4. the content endpoint is genuinely read-only;
5. capabilities are card/side/generation-bound, short-lived and revoked on
   close;
6. cross-card, expired and replay misuse fails safely;
7. top-level replacement, automatic external navigation, popup and downloads
   are blocked;
8. a genuine user link opens only in the system browser;
9. missing individual media degrades visibly without automatically blocking
   rating;
10. unsafe/incomplete templates become non-ratable static previews;
11. measured streaming/range/cache/size/backpressure behavior supports a
    concrete production envelope;
12. adverse content/network failures leave Review Mode closable and do not
    create ratings;
13. cleanup and read-only verification pass with no unaccounted external
    mutation.

Use `partially passed` or `failed` when a security boundary depends on an
unproved convention, fidelity materially diverges, or the required content
envelope cannot be supported.

## Required evidence

Capture:

- exact OS, MTA, CEF/Chromium and harness versions;
- installed-resource/source provenance and hashes;
- card corpus and reference-render method;
- per-fixture screenshots, DOM/computed-style summaries and media events;
- endpoint request logs with capabilities redacted;
- bridge/control/navigation/popup/download attack results;
- capability issuance/expiry/revocation timelines;
- size/range/cache/memory/latency measurements;
- structured S1–S20 results;
- source scan;
- SHA-256 manifest;
- pre/post-cleanup isolation comparison;
- a read-only verifier with per-scenario and overall verdict.

Separate observed facts, inferences and unproved boundaries.

## Expected artifacts

Disposable prototype and evidence:

```text
.scratch/0006-cef-card-content-isolation-prototype/
```

Canonical report:

```text
docs/prototypes/0006-cef-card-content-isolation.md
```

Do not modify `CONTEXT.md`, ADRs or design baselines inside the prototype chat.
The main design chat will incorporate the result afterward.

At completion, create a result `/handoff` back to the main design chat. Do not
create production ANKIGTA code.

## Suggested skills

- `/prototype` — required for the disposable proof.
- `computer-use:computer-use` — required to operate real MTA CEF and perform
  genuine user-click/navigation scenarios.
- `/research` — optional for official MTA browser/CEF APIs and source research.
- `/handoff` — return the verified result to the main design chat.

Do not invoke `/implement`, `/to-spec` or `/to-tickets`.

## Exact prompt for the new prototype chat

```text
/prototype

Выполни Prototype 0006 ANKIGTA по handoff:
C:\Проекты\Программы\ANKIGTA\docs\handoffs\0006-cef-card-content-isolation-prototype.md

Используй настоящий MTA CEF и только disposable server/resource/content
harness. Сначала зафиксируй наблюдаемые критерии fidelity и isolation, затем
выполни S1–S20. Не создавай production-код, не открывай пользовательские
профили Anki и не превращай CEF в privileged control gateway.

Сохрани source, fixtures и evidence под:
.scratch/0006-cef-card-content-isolation-prototype/

Сохрани итоговый отчёт в:
docs/prototypes/0006-cef-card-content-isolation.md

Выполни read-only verifier и в конце подготовь /handoff обратно в главный
проектировочный чат ANKIGTA.
```
