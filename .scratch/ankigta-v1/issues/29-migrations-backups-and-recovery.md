# 29 — Migrations, backups and corruption recovery

**What to build:** Versioned SQLite migrations, automatic rotating backups and explicit recovery screen that never silently replaces a corrupt database.

**Blocked by:** 05 — Admin-only F7 with one persisted Map Entity; 11 — Persistent Change History.

**Status:** resolved

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Verify programmatically — launching disposable copies is allowed, driving a GUI with screenshots or synthetic input is not, and the installed MTA/GTA tree stays unmodified. Acceptance that only a human can observe stays a manual checklist marked `not run`.

## Acceptance criteria

- [x] Every migration runs in a transaction after a verified pre-migration backup. `Store.open` refuses to migrate at all unless `Backup.createPreMigration` returned a copy that opened as SQLite and passed verification; each step is a `transaction(...)`, and the one step that cannot be (the `map_entities` rebuild, which needs foreign keys off) re-enables them and runs `PRAGMA foreign_key_check` before reporting success.
- [x] After data changes, no more than one daily backup is created per day. `Backup.noteDataChange` marks the store dirty and a timer copies afterwards; `createDaily` returns the existing entry when one already carries today's `dayKey`. A day with no data change produces no copy at all.
- [x] Rotation retains seven daily and three pre-migration copies. Retention is per kind, so the two never evict each other. A copy whose file could not be deleted stays in the manifest rather than becoming an untracked file nothing will ever rotate.
- [x] Backup is atomic, contains server SQLite, and excludes connection config/UI placement. The copy is `fileCopy`'d to a staging name, opened as SQLite and verified, and only then renamed into its listed name — a name in the manifest never refers to a half-written file. `connection.json` and `@ankigta-settings.json` are separate files and are not in the backup directory; the test reads the copied bytes and checks neither appears.
- [x] Backup creation does not delay F7 availability beyond its accepted envelope. Copying is off the request path: a data change only sets a flag and arms a timer, and the test proves the copy exists only after the timer fires, not before.
- [x] Corrupt primary DB opens a dedicated recovery state; no silent automatic rollback. Damage is answered before anything is created, migrated or written. `Store.open` leaves the file exactly as found and enters a recovery state; the test compares SHA-256 of every file before and after, for garbage, truncated and page-level damage.
- [x] User selects a verified backup; damaged original is preserved for diagnostics. The state carries every copy with the answer to "can this be used" and the reason when it cannot. The recovery screen shows unusable copies rather than hiding them, refuses to send one, and the damaged original is renamed into `backups/quarantine-N.sqlite` — moved, never deleted — and listed by name.
- [x] Failed restore leaves both original and backup recoverable. The copy is staged and verified while the original is still in place; the original is then moved aside rather than removed; the source backup is never renamed or deleted at any point. A journal records the phase, so a restart after an interrupted restore finishes only the last rename and only when the primary path is empty — anything else is reported and left alone.
- [x] Change History consistency/constraints survive successful migration/restore. Verification refuses a copy whose history cursor dangles or points past the highest entry, or whose foreign keys are violated. After a restore the entry count, the cursor and a working Undo are asserted against the reopened database.

## Tests

- [x] Migration from every shipped schema version with real data. `tests/lua/shipped_schemas.py` writes out each shape ANKIGTA has shipped — v1, v2, v3-legacy, v3, v4 — as the SQL that version really had, filled with maps, Map Entities, Spatial Links, metadata, Change History and settings. Migrating an empty database proves nothing: the statements that break are the ones that move rows.
- [x] Fault injection during backup, migration, rotation and restore. Failures arrive as the answer an MTA call actually gives — a `fileCopy` that writes a prefix and reports failure, a `fileRename` that refuses, a `fileDelete` that fails, a `dbQuery` that returns `SQLITE_IOERR` on a named statement. Each test states which files were left and in what condition, not merely that nothing raised.
- [x] Corruption detection, backup verification and user-choice recovery tests. `tests/test_corruption_recovery.py` holds the negative property; `tests/test_recovery_ui.py` drives the screen the user actually sees.

## Components

- Server SQLite schema/migrator.
- Backup rotation/validation.
- Recovery UI.

## Implementation status

**Resolved.** The negative property is the point of the ticket and is where the
tests are concentrated: a damaged database is never replaced without a person
saying so, and every assertion about that reports the state the files were left
in rather than that nothing raised.

### The rule the module exists to enforce

Nothing in `server/backup.lua` deletes the primary database, nothing restores on
its own, and the only function that moves the primary out of the way is the one
a user action calls. When it does move it, it moves it into quarantine rather
than into the bin, because a database that failed is the only evidence of why.

`Store.open` answers "is this still a database" before it creates, migrates or
writes anything, because every one of those would be a change to a file that
must not be changed. A file that is merely absent is not damaged — a new
install still gets a fresh schema — and the guard tells them apart.

### Migrations are pinned by floor

Each step names the *earliest* version it applies from (`version >= from`),
never the version it expects to find. `== N` is how this repository already
broke once: a step that bumps the number first leaves the shape repair after it
looking at `N + 1`, deciding it has nothing to do, and shipping a database that
is at the current version while still carrying an older shape. A step with no
`to` is a shape repair; its `needed` probe both decides whether it runs and,
once it has run, terminates the loop, which is bounded so a probe that never
clears is a reported failure rather than a server that hangs on start.

The `map_entities` rebuild is the one migration that cannot rename the table out
of the way: SQLite rewrites the `REFERENCES` clauses of `spatial_links`,
`map_entity_metadata` and `identity_collisions` to follow the renamed table, and
dropping it afterwards then cascades their rows into nothing — inside a
migration that reported success. It follows the procedure SQLite documents
instead, and checks the constraints before trusting the result.

### The recovery screen

`client/recovery.lua` is the missing half this pass added. The server publishes
`Store.recovery()` to an authorized Study Player — as state, re-read on every
send, because a copy can go bad between two glances — and accepts one restore
request. The request is guarded on the recovery state itself, not merely on
being well formed: a database that opened cleanly is never replaced from there,
because doing it on request would be the silent replacement ADR 0016 forbids
with one extra click in front of it.

The screen lists every copy with what is wrong with it. A copy that failed
verification is shown and cannot be chosen — hiding it would leave the user
believing there was never a backup at all — and the check lives in the click
handler as well as in the disabled state, because the disabled button is the
hint and the guard is the rule.

### Harness work this needed

`tests/lua/sandbox.py` dispatched every `onClientGUIClick` handler in the
resource at once, which would have let "the user's choice reaches the restore"
pass by pressing every button on the screen. Handlers are now recorded with the
element they were attached to, and `sandbox.click(handle)` runs only that
control's own handlers, the way MTA dispatches a GUI event to the element.

The `Faults` class injects failures at the MTA API boundary rather than in Lua:
a crash halfway through a backup is not something a test can wish for, so the
stubs count their calls and start refusing at the point a test names.

Automated evidence: `pytest -q tests/test_migrations.py
tests/test_backup_rotation.py tests/test_backup_fault_injection.py
tests/test_corruption_recovery.py tests/test_recovery_ui.py` → 92 passed. Each
load-bearing test was mutation-checked: ignoring the damage report, pinning a
migration to `== N`, publishing a copy before verifying it, migrating without a
verified pre-migration copy, keeping one copy too many in rotation, moving the
original aside before the copy is made, deleting the damaged original instead of
quarantining it, dropping the recovery-state guard on restore, dropping the
authority guard on the state, and letting an unverified copy be sent — every one
of them makes a test fail.

## Manual runtime checklist

See `docs/checklists/ticket29-migrations-backups-recovery.md` (`Status: not run`).
