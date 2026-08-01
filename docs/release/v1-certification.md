# ANKIGTA v1 — certification record

**Version:** 1.0.0 (MTA resource and companion add-on, one number, held to it
by a test)

**Matrix:** the one in [supported-versions.md](supported-versions.md) — Windows,
Anki Desktop 26.05 with the V3 scheduler and FSRS, MTA Server and Client 1.6
release build 24124. Anything else is unsupported until its suites pass; that
is a rule, not a preference (spec Implementation Decision 17).

This file records what was proven, by what, and what is still `not run`. It
does not restate numbers: the evidence is
[`v1-performance-report.json`](v1-performance-report.json), written by
`python -m tests.perf --report docs/release/v1-performance-report.json` on the
machine below, and `tests/test_release_record.py` holds this file to it.

## Automated gates

Every one of these is repository-local, unattended and re-runnable. All pass on
the recorded commit.

| Gate | Command | State |
| --- | --- | --- |
| Whole suite | `python -m pytest tests/ -q` | passed |
| Types | `python -m mypy` | passed, strict |
| Performance | `python -m tests.perf` | report clear, exit 0 |
| Packaging and artifact inventory | `pytest tests/test_packaging.py` | passed |
| Secret scan | `pytest tests/test_packaging.py -k secret` | passed |
| Install / upgrade / uninstall / reinstall | `pytest tests/test_certification.py` | passed |
| Post-removal data integrity | `pytest tests/test_certification.py -k after_the_resource_is_gone` | passed |
| Filtered deck and Exact Card Admission | `pytest tests/test_exact_card_admission.py tests/test_session.py` | passed |
| Rating idempotence and durable recovery | `pytest tests/test_review_transaction.py tests/test_review_journal.py tests/test_corruption_recovery.py` | passed |
| Reviewer arbitration and lifecycle | `pytest tests/test_arbitration.py tests/test_study_lifecycle.py` | passed |
| IPv4 loopback transport | `pytest tests/test_mta_ticket_02.py tests/test_companion_connection.py tests/test_health_contract.py` | passed |
| Content endpoint and Review Mode | `pytest tests/test_content_endpoint.py tests/test_review_mode_behavior.py` | passed |
| Migrations, backups and corruption recovery | `pytest tests/test_migrations.py tests/test_backup_rotation.py tests/test_backup_fault_injection.py` | passed |
| Over-reference-volume integrity | `pytest tests/test_over_limit_integrity.py` | passed |

The spec's technical release gates (Implementation Decision 18) each have a
suite in that list. Where a gate's *runtime* half needs a person — real Map
Editor, real CEF, real frames — it is in the checklist section below and is
`not run`.

## Performance

`blocksRelease` is `false` in
[`v1-performance-report.json`](v1-performance-report.json): every threshold in
story 58 was measured and every one is inside its limit. A threshold that could
not be measured would block too — not measured is not passed.

**The measuring machine is not the documented reference machine, and the report
says so.** Its `machine.matchesReferenceEnvelope` is `false`, and
`machine.unconfirmed` names what the run could not establish:

- `storage_is_ssd` — no harness can ask the platform about the specific device
  without risking a wrong answer, and a wrong answer is worse than an absent
  one;
- `anki_desktop_installed` — an automated check never launches Anki, because
  the companion writes to a real collection;
- `mta_server_available` — no MTA Server package was configured for the run
  (`--mta-server-root` was not given).

It also reports 15.24 GiB against a documented 16 GiB, which is the ordinary
difference between installed and addressable memory but is not something a
report is entitled to round away.

So: **the thresholds are met and the numbers are real, on a machine that
differs from the documented one in ways the report names.** Taking them again
on the certifying machine is the first item of
[`ticket30-performance-acceptance.md`](../checklists/ticket30-performance-acceptance.md),
which is still `not run`.

## What a release ships

Built by `python -m tools.package --out dist --manifest dist/artifacts.json`:

- `ankigta-mta-resource-1.0.0.zip` — unpacks as `ankigta/`, into
  `<MTA Server>/mods/deathmatch/resources/`.
- `ankigta-companion-1.0.0.ankiaddon` — unpacks as Anki's own add-on folder,
  into `<Anki data folder>/addons21/ankigta_companion/`.

`artifacts.json` lists every file with its SHA-256. The same source builds the
same bytes: entries are sorted, timestamps and permissions are fixed, and a
test compares two builds.

No archive contains `user_files/`, `__pycache__`, a `.pyc`, a database or a
log. The secret scan looks for the shape of a credential — an assigned token,
a bearer literal, a private key block, an AWS key — rather than for today's
value, and a test plants one to prove the scan can fail.

## Open criteria

These are named rather than closed. Naming them is the point: a certification
that quietly omits a criterion is worse than one that reports it.

### A clean install seeds three shipped tracer fixtures

`meta.xml` loads `maps/ticket05.map` and `maps/ticket07-matrix.map`, and
`Store.open` seeds `ticket05-map/ticket05-entity` into every new database;
`ticket07-map`'s vehicle and ped rows are seeded the first time one is
resolved. A user's first F7 therefore lists Map Entities they did not place.

Not closed here because it is not a packaging problem. `Store.singleMapEntity`
is the seam `prepareObjectPendingMapSave` and its vehicle and ped siblings
resolve through, so removing the fixtures is a redesign of the identity path
that tickets 05 to 07 own, not a change to what goes in the zip. The exact set
is pinned by `test_a_clean_install_seeds_exactly_the_fixtures_it_ships`, so it
cannot grow without a test saying so.

### The reference-machine performance run

See above. The numbers are real and the thresholds are met; the machine is not
the documented one, by its own report.

### Everything a person has to look at

Listed below, all `not run`.

## Manual checklists, all `not run`

An unexecuted runtime checklist is neither a pass nor a failure (spec Release
rule). None of these has been run, and none of them may be marked otherwise by
an implementation pass.

| Checklist | Covers |
| --- | --- |
| [ticket31-install-update-remove.md](../checklists/ticket31-install-update-remove.md) | following the install document on a real machine; update, removal, reinstall; no stranded cards in a real collection |
| [ticket31-canonical-end-to-end.md](../checklists/ticket31-canonical-end-to-end.md) | the canonical scenario; every card state; the world moving; the marker; how the timing feels |
| [ticket30-performance-acceptance.md](../checklists/ticket30-performance-acceptance.md) | the same thresholds by stopwatch and frame counter on the reference machine |
| [ticket07-map-editor.md](../checklists/ticket07-map-editor.md) | stock Map Editor save, read-back, clone, copy, collision |
| [ticket21-cef-best-effort.md](../checklists/ticket21-cef-best-effort.md) | real CEF rendering, media, focus, external navigation |
| [ticket22-activation-zone.md](../checklists/ticket22-activation-zone.md) | moving entities, streaming, and how the delay feels |
| [ticket23-indicator-statistics.md](../checklists/ticket23-indicator-statistics.md) | the marker and the counters on screen |
| the rest of `docs/checklists/` | the runtime half of tickets 10 and 13 to 29 |

## Accepted limitations, stated as they are

The stock Map Editor and the stock MTA browser have limits ANKIGTA does not
work around and does not describe as anything better. They are written out in
[supported-versions.md](supported-versions.md#accepted-limitations): a save
that is not atomic as a whole, no protection against an external `.map` edit,
best-effort card rendering with no pixel or behavioural promise, a card-visible
but non-functional `window.mta` stub, and one domain permission covering both
subresources and main-frame navigation.

Diagnostics say the same thing. `ANKIGTA.Activation.diagnostics` reports why
nothing opened rather than claiming something did; a render or media failure is
a warning that leaves rating available rather than a block; and a Review
Transaction whose outcome cannot be proven stays `Outcome Unknown` instead of
being retried into a second review.

## Release decision

The automated half of v1 is complete and passing, on artifacts that are built
reproducibly and inventoried. The half that needs a person is written down,
scoped and `not run`.

**v1 is not certified for publication until the checklists above have been
executed on the certified matrix and their results recorded.** That is the
spec's own rule, and this record exists so that the distance between "the tests
pass" and "the product works" is visible rather than assumed.
