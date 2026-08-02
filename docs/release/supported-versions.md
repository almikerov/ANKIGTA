# Supported versions

## The certified matrix

ANKIGTA v1 supports exactly this:

| Component | Certified |
| --- | --- |
| Operating system | Windows |
| Anki Desktop | 26.05, **V3 scheduler**. FSRS on or off |
| MTA Server | 1.6 release build 24124 |
| MTA Client | 1.6 release build 24124 |
| ANKIGTA | 1.0.0 (resource and companion add-on, same number) |

Anki, the companion add-on and MTA Server run on one computer, and the
companion listens only on numeric IPv4 loopback `127.0.0.1`.

## The rule

**A build that is not on this list is unsupported until the suites for it
pass.** Compatibility is not inferred from a version number (spec
Implementation Decision 17). A patch release of Anki is a different build until
it has been run through the suites, and so is a newer MTA build.

Concretely:

- **Another Anki build.** Session creation and ratings stay blocked until the
  filtered-deck, rating/recovery and standard-Reviewer-arbitration suites pass
  on it. Preview may still work — you can look at a card — but ANKIGTA will not
  build `ANKIGTA Session` and will not send a rating to a scheduler it has not
  been tested against.
- **Another MTA build.** It is not listed as supported until the IPv4 transport
  and stock CEF smoke/lifecycle suites pass on it.
- **A scheduler other than V3.** ANKIGTA's job is to hand ratings to Anki
  rather than to reproduce its arithmetic, and the admission sequence it uses
  is V3's.

FSRS is deliberately *not* in that list. Nothing ANKIGTA does reads the
scheduling algorithm: Exact Card Admission asks the V3 scheduler for its top
card and Anki computes the interval. Prototype 0002 measured the
filtered-deck rating against an ordinary review with FSRS on, so that is the
configuration the equivalence was measured in — but refusing to connect over a
setting ANKIGTA never reads would have been refusing over nothing.

Adding a build to this table is a release operation with evidence attached, not
an edit to this file.

## What each suite is

The suites named above are the ones ANKIGTA can run:

| Suite | Command | Covers |
| --- | --- | --- |
| Filtered deck and admission | `pytest tests/test_exact_card_admission.py tests/test_session.py` | X-only rebuild, scheduler-top observation, full rebuild |
| Rating and recovery | `pytest tests/test_review_transaction.py tests/test_review_journal.py tests/test_corruption_recovery.py` | one rating is one `revlog`, durable journal, injected faults |
| Reviewer arbitration | `pytest tests/test_arbitration.py tests/test_study_lifecycle.py` | standard Reviewer exclusivity, AnkiWeb sync, pause and cleanup |
| IPv4 transport | `pytest tests/test_mta_ticket_02.py tests/test_companion_connection.py tests/test_health_contract.py` | loopback transport, protocol envelope, timeouts, late callbacks |
| CEF and content | `pytest tests/test_content_endpoint.py tests/test_review_mode_behavior.py` | capability binding, limits, render errors, External Card Page |
| Migration and backup | `pytest tests/test_migrations.py tests/test_backup_rotation.py tests/test_backup_fault_injection.py` | every shipped schema, pre-migration backup, rotation |
| Packaging and certification | `pytest tests/test_packaging.py tests/test_certification.py` | artifact inventory, secret scan, install/upgrade/uninstall/reinstall |
| Performance | `python -m tests.perf --report <path>` | every threshold in story 58 |

Each of these is repository-local and unattended. What they cannot reach — real
Map Editor interaction, real CEF rendering, real frames, a real person walking
into a zone — stays in `docs/checklists/` and is `not run` until a human runs
it. An unexecuted checklist is neither a pass nor a failure (spec Release
rule).

## Accepted limitations

These are limitations of the stock tools ANKIGTA deliberately does not fork,
stated as they are rather than as something stronger.

### Map Editor (ADR 0025, Prototype 0005)

- The editor's save is **not atomic as a whole**. Its own save lifecycle
  deletes the previous `.map`, creates a new empty one and then serialises
  into it; the low-level XML writer has temp/backup recovery, but the whole
  transaction does not.
- There is **no protection against external changes** to a `.map`. If something
  else edits the file, the editor may overwrite it.
- There is **no editor API** that simultaneously confirms a save finished,
  guarantees the write is durable, and offers an independent read-back — and no
  dirty-state, hash or compare-and-swap check.
- ANKIGTA therefore **never writes a `.map` in the background**. A new link is
  `Pending Map Save` until ANKIGTA has independently re-read unambiguous IDs
  after your own normal Save. A failed, partial or ambiguous read-back leaves
  the link pending and offers `Проверить ещё раз` / `Check again`, which
  repeats the read-back only.
- ANKIGTA does not claim to repair a `.map`, and it does not promise the save
  will not be lost. Use Map Editor's own backups.
- A custom map identity attribute on the `<map>` root is **not** preserved by
  the stock editor; ANKIGTA stores map identity in an EDF custom child element
  instead, and entity identity as element data / an EDF property.

### Stock MTA CEF (ADR 0026, ADR 0027, Prototype 0006)

- Card rendering is **best effort**. HTML, CSS, JavaScript and media are
  delivered without intentional removal, but pixel or behavioural equivalence
  with Anki Desktop is **not promised**.
- A render, script, template or media error shows a warning and **never**
  disables Again/Hard/Good/Easy. Rating a broken presentation stays your call.
- Card JavaScript can see a `window.mta` object. It **does not work**: MTA's
  native `isLocal` guard rejects privileged dispatch from a remote browser.
  ANKIGTA accepts the visible non-functional stub rather than claiming there is
  no bridge. The real boundary is that card content cannot perform a privileged
  MTA or Anki operation.
- MTA uses **one domain permission** for external subresources and for
  main-frame navigation. Allowing a domain for an image or a font also allows
  the card surface to navigate there, and Lua is told after the fact — ANKIGTA
  cannot cancel it beforehand and does not promise to. When it happens the
  window shows *External Card Page*, ratings stay enabled, and
  `Вернуться к карточке` / `Back to the card` reloads the current side.
- Popups stay blocked by stock MTA. Handing a link to the system browser,
  downloads and third-party page behaviour are **not supported**: MTA cannot
  tell Lua whether a link was a genuine click or a script call.

### Timing

- The Activation Zone is polled every 250 ms rather than every rendered frame,
  so with the automatic delay set to zero a card opens up to a quarter of a
  second after you cross the edge of a zone. The reasoning and the measurement
  are in `mta/ankigta/client/spatial.lua` and in the `spatial_frame` entry of a
  performance report.
- The vehicle speed gate converts GTA's own velocity units, which are per
  physics step rather than per second. It is calibrated against the game's
  speedometer by the ticket 22 manual checklist, not by an automated check.
