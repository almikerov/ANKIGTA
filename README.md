# ANKIGTA

Study Anki cards where they live in a game world. A `Map Entity` in MTA:SA —
an object, a vehicle or a ped placed with the stock Map Editor — is linked to
one Anki Card. Walk up to it and the card opens; answer it and the rating goes
to Anki's own scheduler. Where the target stands becomes part of remembering
the card.

Anki stays the owner of your study data. ANKIGTA sends it Again/Hard/Good/Easy
and nothing else: no scheduler of its own, no SQL against your collection, no
private queue.

## What it is made of

- `mta/ankigta/` — the MTA resource. Server-side Lua owns Map Entity records,
  Spatial Links, settings and Change History, and is the only gateway to the
  companion. Client-side Lua owns F7, the HUD, Review Mode and the world
  polling.
- `companion/ankigta_companion/` — the Anki add-on. It owns the connection, the
  collection identity, the `ANKIGTA Session` filtered deck, Exact Card
  Admission and the durable Review Transaction journal.
- `docs/` — ADRs, design records, operator documentation and the manual
  checklists.
- `tests/` — the whole automated suite, including a real Lua 5.1 harness that
  runs the resource scripts (`tests/lua/`) and the release benchmark
  (`tests/perf/`).

## Start here

| If you want to | Read |
| --- | --- |
| Install, update or remove it | [docs/operations/installation.md](docs/operations/installation.md) |
| Know which versions work | [docs/release/supported-versions.md](docs/release/supported-versions.md) |
| Know what is backed up, and how to recover | [docs/operations/backups-and-recovery.md](docs/operations/backups-and-recovery.md) |
| See what v1 was certified against | [docs/release/v1-certification.md](docs/release/v1-certification.md) |
| Understand the vocabulary | [CONTEXT.md](CONTEXT.md) |
| Work on it | [AGENTS.md](AGENTS.md) and `docs/agents/` |

## Building a release

```bash
python -m tools.package --out dist --manifest dist/artifacts.json
```

Two archives and an inventory listing every file with its SHA-256. The same
source builds the same bytes.

## Running the checks

```bash
python -m pytest tests/ -q
```

```bash
python -m mypy
```

```bash
python -m tests.perf --report build/ankigta-performance.json
```

The last one is the release gate: it prints one line per threshold and exits
non-zero when a threshold is over its limit **or** when a measurement could not
be taken. A number that was never measured is not a number that passed.

## What v1 does not do

Single player only, Windows only, keyboard and mouse only. No multiplayer
study, no gamepad, no bulk linking or CSV import, no AnkiWeb integration, and
no fork of MTA's Map Editor or browser — the limitations of the stock ones are
listed as they are in
[supported-versions.md](docs/release/supported-versions.md#accepted-limitations)
rather than papered over.
