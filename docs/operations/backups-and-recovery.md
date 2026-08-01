# Backups and recovery

ANKIGTA backs up **its own database and nothing else**: the Map Entity records,
Spatial Links, Entity Tags, radii, `Include in study` and the Change History.

It does not back up your Anki collection. Anki owns your study data and its own
backups (ADR 0017), and nothing here reads or writes them. It also does not
back up the connection file or your UI placement; those are configuration, not
data you would mourn.

There is no manual backup button and no manual restore command inside F7. What
exists is automatic rotation, and a recovery screen that appears when the
database cannot be opened.

## Where the copies are

Inside the resource folder, beside the database:

```
<MTA Server>/mods/deathmatch/resources/ankigta/
    ankigta.sqlite            the live database
    backups/                  the rotating copies
        manifest.json         what each copy is, and whether it verified
```

This is why the removal steps in
[installation](installation.md#remove) say to take both out of the resource
folder before deleting it.

## When a copy is made

- **Before every schema migration.** An upgrade that changes the schema writes
  a verified copy first, and only then migrates. If the migration fails, the
  copy is the state you were in.
- **At most once a day after data changes.** Linking, unlinking, editing
  metadata or undoing marks the database dirty; a timer copies it a few seconds
  later, off the path F7 waits on. A day with no changes adds no copy.

Rotation keeps **seven daily** copies and **three pre-migration** ones
(ADR 0016). A copy is written to a staging file, opened as SQLite, verified,
and only then entered in the manifest — so a name in the manifest never refers
to a half-written file.

## When the database will not open

ANKIGTA never silently rolls back to a copy. If the database is corrupt, or a
previous restore was interrupted, the F7 surface is replaced by a recovery
screen listing the copies that verified *just now* — not the ones that verified
when they were written.

You choose one. ANKIGTA then:

1. moves the damaged database into `backups/` as a quarantined file, rather
   than deleting it, so it can still be examined;
2. copies your chosen backup into place;
3. verifies the result before it is used.

If no copy verifies, ANKIGTA stays in recovery and says so. It does not invent
an empty database over the top of your data.

Restoring is a user choice with a consequence: the changes made after that copy
was taken are not in it, and the Change History cannot undo across a restore
(the SQLite rotation and the product's undo log are different things, spec
Implementation Decision 16).

## Recovering by hand

You should not need to, and the supported paths above never ask you to open
SQLite. If you want a copy of your world for your own reasons, the files in
`backups/` are ordinary SQLite databases: copy one somewhere and open it with
whatever you like. Copying one *back* over `ankigta.sqlite` while the resource
is stopped also works, and ANKIGTA will migrate it forward on the next start —
but the recovery screen does the same thing with verification in front of it.

## What is not covered

- **Anki.** A lost review, a deleted card or a broken collection is Anki's
  backup to restore, not ours. A card deleted in Anki becomes `Card missing` in
  F7 with its Map Entity and the old link record kept, so restoring the card in
  Anki does not automatically re-link it: use `Replace card`.
- **`.map` files.** ANKIGTA never writes one, and never backs one up. Map
  Editor's own save lifecycle is not atomic and has no external-change
  protection; use the editor's own backups (see
  [supported versions](../release/supported-versions.md#accepted-limitations)).
- **Cloud or AnkiWeb.** ANKIGTA never starts, waits for, or configures a sync.
