# Ticket 29 — Migrations, backups and recovery manual checklist

Status: not run

Migration from every shipped schema shape against real rows, the daily and
pre-migration retentions, atomic publication, verification, quarantine, the
restore ordering and fault injection through the middle of a backup, a
migration, a rotation and a restore are all covered automatically, against real
SQLite files whose bytes are compared before and after. The recovery screen is
covered as far as a screen can be without a person: the state reaches an
authorized player, the copies are listed with what is wrong with each, an
unverified copy cannot be chosen, and the choice made on the screen is followed
until the Spatial Link only the backup held is readable again.

What is left for a human is everything that is about a running MTA server, a
real clock, a real disk and what the screen actually looks like.

## Scenarios

- Start a real MTA server on a database from a previous ANKIGTA build. Confirm
  a pre-migration copy appears in `backups/` before the schema changes, that
  the server reaches F7 normally, and that `schema_meta.version` is current.
- Work in F7 for eight consecutive days, changing data on each. Confirm exactly
  one daily copy per day, that the eighth day evicts the oldest, and that the
  pre-migration copies are untouched by that eviction.
- Time the first F7 open after a data change on a cold profile. Confirm the
  window appears within its accepted envelope and that the copy is written
  afterwards, not before it.
- Fill the disk, then change data. Confirm the failed daily copy is logged, no
  half-written file is left in `backups/`, and the server keeps running.
- Kill the server process during a backup, during a migration and during a
  restore. For each, list `backups/` and confirm which files exist, then start
  the server again and confirm it either finishes the restore it had already
  been told to make or asks rather than guesses.
- Corrupt the database with a hex editor (wreck a page, keeping the header).
  Start the server, join as the Study Player and confirm the recovery screen
  appears on its own, that the damaged file is still byte-for-byte as you left
  it, and that no new database was created.
- On that screen, confirm the copy list is legible: the day, the kind, the
  schema version and — for a copy that failed verification — the reason.
  Confirm the wording reads as an offer to choose rather than a report of
  something already done.
- Choose the verified copy. Confirm the data comes back, the damaged original
  appears under `backups/` with a `quarantine-` name, and the screen closes.
- Corrupt every copy as well as the database. Confirm the screen says no copy
  passed verification, that the restore button cannot be pressed, and that
  nothing on disk is replaced or deleted.
- Take the quarantined file to a SQLite tool and confirm it is the damaged
  original rather than an empty or rewritten file.
- Confirm the backup directory holds only `.sqlite` copies and the manifest —
  no connection config, no client settings file, no UI placement.

## Expected evidence

Directory listings of `backups/` at each step, SHA-256 of the damaged database
before and after the recovery screen was open, the server log lines for
`database_recovery` and `daily_backup_failed`, and screenshots of the recovery
screen — including the "no copy passed verification" state.
