# Ticket 31 — install, update and remove manual checklist

Status: not run

The automated certification suite (`pytest tests/test_certification.py`) does
clean install, upgrade from every shipped schema, uninstall and reinstall
against the real unpacked artifact. What it cannot do is be a person following
written instructions on a real MTA server with a real Anki: whether the
documentation matches what is on the screen, whether an Anki add-on installed
by hand actually loads, and whether the filtered deck is really gone from a
real collection afterwards.

Run every scenario on the certified matrix
(`docs/release/supported-versions.md`) and write the machine down: CPU, RAM,
disk, Windows build, the exact Anki version, the exact MTA build.

Build the artifacts on that machine first, and keep the inventory:

```bash
python -m tools.package --out dist --manifest dist/artifacts.json
```

## Scenarios

### Clean install, following the document

- Start from a machine with no ANKIGTA: no `resources/ankigta`, no
  `addons21/ankigta_companion`, no `resource.ankigta.study` in `acl.xml`.
- Follow `docs/operations/installation.md` from the top, doing exactly what it
  says and nothing else. Note every point where you had to guess, look
  elsewhere, or do something the document did not mention.
- Confirm the resource starts with no error in the server console, and that
  `resources/ankigta/ankigta.sqlite` appeared on its own.
- Confirm Anki loaded the add-on: *Tools* has *ANKIGTA: Bound Anki Collection…*
  and *ANKIGTA: Companion Connection…*.
- Confirm the add-on asked once for the MTA resource folder, and that
  `connection.json` appeared inside it afterwards.
- Confirm you never typed a port or a token.
- Confirm you never opened a SQLite file or a `.map` file.

### First run and the canonical scenario

- Log in with the admin account. Press F7 and confirm the Map Entity list
  opens. Type something into the filter box and confirm the list narrows and
  the count reads `Showing N of M`.
- Take the canonical scenario end to end, on this installed copy: pick a Map
  Entity → link a card → save the map in Map Editor → confirm the link stops
  saying `Pending Map Save` → `Начать обучение` → walk into the Activation Zone
  → the card opens → reveal the answer → rate it → the HUD counters and the
  Next Card Indicator change.
- Confirm in Anki that the card got exactly one new `revlog` entry, and that
  its interval and FSRS state moved the way the same rating moves a card in
  Anki's own reviewer.

### Log in as an ordinary player

- Log in with an account that does **not** hold `resource.ankigta.study`.
- Confirm F7 does nothing, the HUD is absent, no marker appears, and nothing in
  the chat or the console reveals a card, a deck or a collection.

### Update over an existing install

- With a session running and cards in `ANKIGTA Session`, press `Pause studying`
  and confirm in Anki that the cards went back to their original decks and the
  filtered deck is gone.
- Stop the resource, unpack a new build over the old folder without deleting
  anything, and start it again.
- Confirm: your Spatial Links are still listed in F7; `ankigta.sqlite` and
  `backups/` were not replaced; your own files in the folder survived.
- Repeat the update **without** pausing first — stop the resource straight from
  a running session. Confirm the filtered deck is gone from Anki afterwards, or
  record that it was not: the stop request is issued at teardown and MTA may
  tear it down with the resource. Say which happened.

### Update from an older schema

- Take a copy of an ANKIGTA database from an earlier build (or one of the
  shapes `tests/lua/shipped_schemas.py` builds), put it in the resource folder,
  and start the new build.
- Confirm the server console reports the migration, that `backups/` gained a
  pre-migration copy, and that every Spatial Link you had is in F7 afterwards.

### Remove

- Press `Stop` in the study window. In Anki, confirm no deck named
  `ANKIGTA Session` exists and no card is sitting in one.
- Stop the resource. Copy `ankigta.sqlite` and `backups/` somewhere else, as
  the document says to.
- Delete `resources/ankigta/` and remove the ACL right. Delete
  `addons21/ankigta_companion/`.
- Confirm Anki starts with no ANKIGTA menu entries and no errors.
- Confirm your Anki collection is unchanged: the decks you had, the cards you
  had, and the review history you had.
- Open the copied `ankigta.sqlite` with any SQLite viewer and confirm your
  Spatial Links are still in it.

### Reinstall

- Unpack the resource again and put the copied database back. Confirm F7 lists
  the same Map Entities and the same links.
- Repeat without putting the database back, and confirm you get an empty world
  without touching SQLite.

## Expected evidence

Per scenario: the machine and version details; the console output of each start
and stop; screenshots or notes of the Anki deck list before and after; the
`dist/artifacts.json` inventory of the build used; and, for the canonical
scenario, the card's `revlog` row and FSRS state read out of Anki itself.

Where the document and the screen disagree, the screen is right and the
document is the defect.
