# 29 — Migrations, backups and corruption recovery

**What to build:** Versioned SQLite migrations, automatic rotating backups and explicit recovery screen that never silently replaces a corrupt database.

**Blocked by:** 05 — Admin-only F7 with one persisted Map Entity; 11 — Persistent Change History.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Every migration runs in a transaction after a verified pre-migration backup.
- [ ] After data changes, no more than one daily backup is created per day.
- [ ] Rotation retains seven daily and three pre-migration copies.
- [ ] Backup is atomic, contains server SQLite, and excludes connection config/UI placement.
- [ ] Backup creation does not delay F7 availability beyond its accepted envelope.
- [ ] Corrupt primary DB opens a dedicated recovery state; no silent automatic rollback.
- [ ] User selects a verified backup; damaged original is preserved for diagnostics.
- [ ] Failed restore leaves both original and backup recoverable.
- [ ] Change History consistency/constraints survive successful migration/restore.

## Tests

- [ ] Migration from every shipped schema version with real data.
- [ ] Fault injection during backup, migration, rotation and restore.
- [ ] Corruption detection, backup verification and user-choice recovery tests.

## Components

- Server SQLite schema/migrator.
- Backup rotation/validation.
- Recovery UI.

