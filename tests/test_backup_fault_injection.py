"""Ticket 29 — what is left on disk when a backup, a migration, a rotation or a
restore stops halfway.

"It did not crash" is not an answer. Every test here injects a failure at a
point inside one of the four operations and then says, file by file, what the
state afterwards is: which databases exist, which of them still verify, and
which of the two things that must never both be lost — the original and the
copy — is still readable.

The failures arrive where they really arrive, at the MTA calls: `fileCopy`
returning false with a partial file written, `fileRename` refusing, `fileDelete`
refusing, a statement inside a migration transaction failing with an I/O error.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterator

import pytest

from tests.lua import MtaSandbox
from tests.lua import shipped_schemas
from tests.lua.shipped_schemas import rows


def server(directory: Path) -> MtaSandbox:
    sandbox = MtaSandbox(database_path=str(directory / "ankigta.sqlite"))
    sandbox.load("shared/settings.lua")
    sandbox.load("server/backup.lua")
    sandbox.load("server/store.lua")
    return sandbox


def call(sandbox: MtaSandbox, expression: str, *args: Any) -> Any:
    return sandbox.eval(expression)(*args)


def opened(sandbox: MtaSandbox) -> Any:
    return call(sandbox, "function() return ANKIGTA.Store.open() end")


def status(sandbox: MtaSandbox) -> dict[str, Any]:
    return dict(
        sandbox.to_python(call(sandbox, "function() return ANKIGTA.Store.status() end"))
    )


def as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def backups(sandbox: MtaSandbox) -> list[dict[str, Any]]:
    return as_list(
        sandbox.to_python(call(sandbox, "function() return ANKIGTA.Backup.list() end"))
    )


def outcome(sandbox: MtaSandbox, expression: str, *args: Any) -> dict[str, Any]:
    """Call something returning `value, reason` and read both halves."""
    return dict(
        sandbox.to_python(
            sandbox.eval(
                "function(...) local ok, why = (" + expression + ")(...) "
                "return {ok = ok and true or false, reason = why or false} end"
            )(*args)
        )
    )


def change_data(sandbox: MtaSandbox, radius: float) -> Any:
    return call(
        sandbox,
        'function(r) return ANKIGTA.Store.setUserSetting("activationRadius", r) end',
        radius,
    )


def sqlite_files(directory: Path) -> list[str]:
    return sorted(
        path.relative_to(directory).as_posix() for path in directory.rglob("*.sqlite")
    )


def readable(path: Path) -> bool:
    """Can this file still be opened and read as the database it was?"""
    if not path.is_file():
        return False
    connection = sqlite3.connect(path)
    try:
        return connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    except sqlite3.DatabaseError:
        return False
    finally:
        connection.close()


@pytest.fixture
def workspace(tmp_path: Path) -> Iterator[Path]:
    yield tmp_path


def seeded(directory: Path) -> MtaSandbox:
    """A server with data, one verified daily backup, and the store closed."""
    sandbox = server(directory)
    opened(sandbox)
    change_data(sandbox, 6)
    sandbox.fire_timers()
    assert len(backups(sandbox)) == 1
    call(sandbox, "function() return ANKIGTA.Store.close() end")
    return sandbox


# --- a failure partway through a backup ---------------------------------------


def test_a_copy_that_stops_halfway_leaves_no_backup_behind(
    workspace: Path,
) -> None:
    """A truncated copy must not survive under a name anything will offer."""
    sandbox = server(workspace)
    try:
        opened(sandbox)
        primary = workspace / "ankigta.sqlite"
        change_data(sandbox, 7)
        before = primary.read_bytes()
        # The copy writes the first kilobyte and then the disk stops answering.
        sandbox.faults.partial_copy(1024)

        sandbox.fire_timers()

        assert backups(sandbox) == []
        # State of the files: the database, and nothing else.
        assert sqlite_files(workspace) == ["ankigta.sqlite"]
        assert primary.read_bytes() == before
    finally:
        sandbox.close()


def test_a_copy_that_lands_but_cannot_be_recorded_is_not_reported_as_a_backup(
    workspace: Path,
) -> None:
    """The manifest is the promise; a copy nothing promised is not a backup."""
    sandbox = server(workspace)
    try:
        opened(sandbox)
        change_data(sandbox, 7)
        # The copy and the rename go through; writing the manifest does not.
        sandbox.faults.fail_after("fileWrite")

        result = outcome(sandbox, "ANKIGTA.Backup.createDaily")

        assert result["ok"] is False
        assert "manifest" in result["reason"]
        assert backups(sandbox) == []
        # The copy itself is intact, and the next attempt reuses its name
        # rather than piling a second file alongside it.
        orphan = workspace / "backups" / "ankigta-daily-1.sqlite"
        assert readable(orphan)
        sandbox.faults = type(sandbox.faults)()
        assert outcome(sandbox, "ANKIGTA.Backup.createDaily")["ok"] is True
        assert sqlite_files(workspace) == [
            "ankigta.sqlite",
            "backups/ankigta-daily-1.sqlite",
        ]
    finally:
        sandbox.close()


def test_a_copy_of_a_database_that_is_already_damaged_is_not_published(
    workspace: Path,
) -> None:
    """Verification is on the copy, so damage cannot be laundered into a backup."""
    sandbox = server(workspace)
    try:
        opened(sandbox)
        change_data(sandbox, 7)
        call(sandbox, "function() return ANKIGTA.Store.close() end")
        primary = workspace / "ankigta.sqlite"
        primary.write_bytes(b"not a database" * 500)

        result = outcome(sandbox, "ANKIGTA.Backup.createDaily")

        assert result["ok"] is False
        assert result["reason"] == "backup_integrity_failed"
        assert sqlite_files(workspace) == ["ankigta.sqlite"]
    finally:
        sandbox.close()


# --- a failure partway through a migration ------------------------------------


@pytest.mark.parametrize(
    "version, statement, surviving_version",
    [
        ("v1", "SET rotation_z = authored_heading", 1),
        ("v2", "CREATE TABLE spatial_links", 2),
        ("v3legacy", "INSERT INTO map_entities_rebuilt", 3),
        ("v3", "INSERT INTO spatial_links", 3),
    ],
)
def test_a_migration_that_fails_leaves_the_database_as_it_was(
    workspace: Path, version: str, statement: str, surviving_version: int
) -> None:
    database = workspace / "ankigta.sqlite"
    shipped_schemas.build(database, version)
    before = {
        "entities": rows(database, "SELECT * FROM map_entities ORDER BY entity_id"),
        "schema": rows(
            database, "SELECT name, sql FROM sqlite_master ORDER BY name"
        ),
    }

    sandbox = server(workspace)
    try:
        sandbox.faults.fail_sql_after(statement)

        assert opened(sandbox) is False

        # The store says why, and says it without having half-migrated.
        assert status(sandbox)["errorCategory"] == "migration_failed"
        assert rows(database, "SELECT version FROM schema_meta") == [
            {"version": surviving_version}
        ]
        assert (
            rows(database, "SELECT * FROM map_entities ORDER BY entity_id")
            == before["entities"]
        )
        assert (
            rows(database, "SELECT name, sql FROM sqlite_master ORDER BY name")
            == before["schema"]
        )

        # And the copy taken before it started is there, and usable.
        sandbox.faults = type(sandbox.faults)()
        premigration = [
            entry for entry in backups(sandbox) if entry["kind"] == "premigration"
        ]
        assert len(premigration) == 1
        assert premigration[0]["verified"] is True
        assert premigration[0]["schemaVersion"] == surviving_version
    finally:
        sandbox.close()


def test_a_migration_whose_commit_fails_rolls_the_whole_step_back(
    workspace: Path,
) -> None:
    """The last statement is the dangerous one: everything is already applied."""
    database = workspace / "ankigta.sqlite"
    shipped_schemas.build(database, "v1")

    sandbox = server(workspace)
    try:
        sandbox.faults.fail_sql_after("COMMIT")

        assert opened(sandbox) is False

        assert rows(database, "SELECT version FROM schema_meta") == [{"version": 1}]
        columns = {
            str(row["name"]) for row in rows(database, "PRAGMA table_info(map_entities)")
        }
        assert "rotation_z" not in columns
        assert "authored_heading" in columns
    finally:
        sandbox.close()


def test_no_verified_pre_migration_copy_means_no_migration_at_all(
    workspace: Path,
) -> None:
    """The one case a failed migration has nothing to fall back on is refused."""
    database = workspace / "ankigta.sqlite"
    shipped_schemas.build(database, "v2")
    before = database.read_bytes()

    sandbox = server(workspace)
    try:
        sandbox.faults.fail_after("fileCopy")

        assert opened(sandbox) is False

        assert status(sandbox)["errorCategory"] == "migration_backup_failed"
        # Not one statement of the migration ran.
        assert database.read_bytes() == before
        assert sqlite_files(workspace) == ["ankigta.sqlite"]
    finally:
        sandbox.close()


# --- a failure partway through a rotation -------------------------------------


def test_a_copy_that_cannot_be_deleted_stays_listed_rather_than_forgotten(
    workspace: Path,
) -> None:
    """Rotation may fail to evict; it may not lose track of what it left behind."""
    sandbox = server(workspace)
    try:
        opened(sandbox)
        for index in range(8):
            change_data(sandbox, 1 + index * 0.5)
            sandbox.fire_timers()
            sandbox.advance_days(1)
        assert len(backups(sandbox)) == 7
        oldest = min(entry["id"] for entry in backups(sandbox))

        # The ninth day's copy is made; evicting the oldest is refused.
        sandbox.faults.fail_after("fileDelete")
        change_data(sandbox, 9)
        result = outcome(sandbox, "ANKIGTA.Backup.createDaily")

        assert result["ok"] is False
        assert result["reason"] == "backup_rotation_delete_failed"
        listed = backups(sandbox)
        # Eight on disk and eight listed: over the retention, but nothing has
        # become an untracked file that rotation can never see again.
        assert len(listed) == 8
        assert oldest in [entry["id"] for entry in listed]
        assert len(list((workspace / "backups").glob("ankigta-daily-*.sqlite"))) == 8

        # Once the disk answers again, the next rotation catches up.
        sandbox.faults = type(sandbox.faults)()
        assert outcome(sandbox, "ANKIGTA.Backup.rotate")["ok"] is True
        assert len(backups(sandbox)) == 7
        assert len(list((workspace / "backups").glob("ankigta-daily-*.sqlite"))) == 7
    finally:
        sandbox.close()


# --- a failure partway through a restore --------------------------------------


def restore_state(workspace: Path) -> dict[str, Any]:
    """What is left, and what of it can still be read."""
    return {
        "files": sqlite_files(workspace),
        "primary_readable": readable(workspace / "ankigta.sqlite"),
        "backup_readable": readable(
            workspace / "backups" / "ankigta-daily-1.sqlite"
        ),
    }


def test_a_restore_whose_copy_fails_has_touched_nothing(workspace: Path) -> None:
    sandbox = seeded(workspace)
    try:
        damaged = workspace / "ankigta.sqlite"
        damaged.write_bytes(b"wrecked" * 900)
        opened(sandbox)
        chosen = backups(sandbox)[0]["id"]
        sandbox.faults.fail_after("fileCopy")

        result = outcome(sandbox, "ANKIGTA.Backup.restore", chosen)

        assert result["ok"] is False
        assert result["reason"] == "restore_copy_failed"
        state = restore_state(workspace)
        # The damaged original is still where it was, and so is the copy.
        assert state["files"] == [
            "ankigta.sqlite",
            "backups/ankigta-daily-1.sqlite",
        ]
        assert state["primary_readable"] is False
        assert state["backup_readable"] is True
    finally:
        sandbox.close()


def test_a_restore_that_cannot_move_the_original_aside_keeps_both(
    workspace: Path,
) -> None:
    """Nothing is overwritten to make room; if the original will not move, stop."""
    sandbox = seeded(workspace)
    try:
        damaged = workspace / "ankigta.sqlite"
        damaged.write_bytes(b"wrecked" * 900)
        wreck = damaged.read_bytes()
        opened(sandbox)
        chosen = backups(sandbox)[0]["id"]
        # The copy is staged; moving the original into quarantine is refused.
        sandbox.faults.fail_after("fileRename")

        result = outcome(sandbox, "ANKIGTA.Backup.restore", chosen)

        assert result["ok"] is False
        assert result["reason"] == "restore_quarantine_failed"
        assert damaged.read_bytes() == wreck
        assert readable(workspace / "backups" / "ankigta-daily-1.sqlite")
        # The staged copy is left as a third file, named in the journal.
        assert readable(workspace / "backups" / "staging.sqlite")
        journal = workspace / "backups" / "restore-journal.json"
        assert journal.is_file()
        assert "staging.sqlite" in journal.read_text(encoding="utf-8")
    finally:
        sandbox.close()


def test_a_restore_that_fails_on_the_last_step_leaves_both_recoverable(
    workspace: Path,
) -> None:
    """The worst moment: the original is aside and the copy is not yet in place."""
    sandbox = seeded(workspace)
    try:
        damaged = workspace / "ankigta.sqlite"
        damaged.write_bytes(b"wrecked" * 900)
        wreck = damaged.read_bytes()
        opened(sandbox)
        chosen = backups(sandbox)[0]["id"]
        # The quarantine rename goes through; the publish rename does not.
        sandbox.faults.fail_after("fileRename", successes=1)

        result = outcome(sandbox, "ANKIGTA.Backup.restore", chosen)

        assert result["ok"] is False
        assert result["reason"] == "restore_publish_failed"
        # There is no database at the primary path, and that is survivable
        # because all three of the others are on disk and intact.
        assert not damaged.exists()
        quarantined = workspace / "backups" / "quarantine-2.sqlite"
        assert quarantined.read_bytes() == wreck
        assert readable(workspace / "backups" / "ankigta-daily-1.sqlite")
        assert readable(workspace / "backups" / "staging.sqlite")
    finally:
        sandbox.close()


def test_restarting_after_an_interrupted_restore_finishes_it(
    workspace: Path,
) -> None:
    """The last rename is the only thing finished without asking again.

    It is finished only because the primary path is empty: there is nothing
    left there to lose, and the copy to put there is the one the user already
    chose. The quarantined original stays quarantined either way.
    """
    sandbox = seeded(workspace)
    try:
        (workspace / "ankigta.sqlite").write_bytes(b"wrecked" * 900)
        opened(sandbox)
        chosen = backups(sandbox)[0]["id"]
        sandbox.faults.fail_after("fileRename", successes=1)
        assert outcome(sandbox, "ANKIGTA.Backup.restore", chosen)["ok"] is False
    finally:
        sandbox.close()

    restarted = server(workspace)
    try:
        assert opened(restarted) is True

        assert status(restarted)["schemaVersion"] == 5
        assert readable(workspace / "ankigta.sqlite")
        assert not (workspace / "backups" / "staging.sqlite").exists()
        # The damaged original was not tidied away by the restart.
        assert readable(workspace / "backups" / "ankigta-daily-1.sqlite")
        assert (workspace / "backups" / "quarantine-2.sqlite").is_file()
    finally:
        restarted.close()


def test_a_restart_with_the_original_still_in_place_asks_rather_than_finishes(
    workspace: Path,
) -> None:
    """A journal plus a database at the primary path is a question, not a task."""
    sandbox = seeded(workspace)
    try:
        (workspace / "ankigta.sqlite").write_bytes(b"wrecked" * 900)
        wreck = (workspace / "ankigta.sqlite").read_bytes()
        opened(sandbox)
        chosen = backups(sandbox)[0]["id"]
        sandbox.faults.fail_after("fileRename")
        assert outcome(sandbox, "ANKIGTA.Backup.restore", chosen)["ok"] is False
    finally:
        sandbox.close()

    restarted = server(workspace)
    try:
        assert opened(restarted) is False

        state = dict(
            restarted.to_python(
                call(restarted, "function() return ANKIGTA.Store.recovery() end")
            )
        )
        assert state["reason"] == "restore_interrupted"
        assert state["awaitingChoice"] is True
        # Untouched: the file at the primary path is still the damaged one.
        assert (workspace / "ankigta.sqlite").read_bytes() == wreck
        assert readable(workspace / "backups" / "ankigta-daily-1.sqlite")
    finally:
        restarted.close()
