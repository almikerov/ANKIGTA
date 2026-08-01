"""Ticket 29 — when copies are taken, what they hold, and which are kept.

ADR 0016 fixes three numbers and one prohibition: a copy before every migration,
at most one a day after data changes, seven daily and three pre-migration copies
retained, and nothing in a copy that is not the server database. All four are
checked here against real files on disk, because "a backup was created" is a
claim about a file and not about a return value.

The envelope belongs here too. `Backup creation does not delay F7` is only
meaningful if the copy is genuinely off the request path, so the test for it
counts the `fileCopy` calls a data change and an F7 snapshot actually make.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterator

import pytest

from tests.lua import MtaSandbox
from tests.lua import shipped_schemas


def server(directory: Path) -> MtaSandbox:
    sandbox = MtaSandbox(database_path=str(directory / "ankigta.sqlite"))
    sandbox.load("shared/settings.lua")
    sandbox.load("server/backup.lua")
    sandbox.load("server/store.lua")
    return sandbox


def call(sandbox: MtaSandbox, expression: str, *args: Any) -> Any:
    return sandbox.eval(expression)(*args)


def as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def backups(sandbox: MtaSandbox) -> list[dict[str, Any]]:
    return as_list(
        sandbox.to_python(call(sandbox, "function() return ANKIGTA.Backup.list() end"))
    )


def make_daily(sandbox: MtaSandbox) -> Any:
    return sandbox.to_python(
        call(sandbox, "function() return ANKIGTA.Backup.createDaily() end")
    )


def change_data(sandbox: MtaSandbox, radius: float) -> Any:
    return call(
        sandbox,
        'function(r) return ANKIGTA.Store.setUserSetting("activationRadius", r) end',
        radius,
    )


@pytest.fixture
def store(tmp_path: Path) -> Iterator[MtaSandbox]:
    sandbox = server(tmp_path)
    call(sandbox, "function() return ANKIGTA.Store.open() end")
    try:
        yield sandbox
    finally:
        sandbox.close()


# --- how often a daily copy is taken ------------------------------------------


def test_a_data_change_produces_exactly_one_daily_backup_that_day(
    store: MtaSandbox,
) -> None:
    change_data(store, 5)
    change_data(store, 6)
    change_data(store, 7)

    store.fire_timers()

    daily = [entry for entry in backups(store) if entry["kind"] == "daily"]
    assert len(daily) == 1
    assert daily[0]["verified"] is True


def test_a_change_the_next_day_produces_a_second_daily_backup(
    store: MtaSandbox,
) -> None:
    change_data(store, 5)
    store.fire_timers()
    first = [entry for entry in backups(store) if entry["kind"] == "daily"]

    store.advance_days(1)
    change_data(store, 6)
    store.fire_timers()

    daily = [entry for entry in backups(store) if entry["kind"] == "daily"]
    assert len(daily) == 2
    assert {entry["day"] for entry in daily} == {
        first[0]["day"],
        str(
            call(store, "function(t) return ANKIGTA.Backup.dayKey(t) end", store.real_time)
        ),
    }


def test_no_data_change_means_no_daily_backup_at_all(store: MtaSandbox) -> None:
    """Opening and reading is not a data change; a copy a day is not a copy a run."""
    call(store, "function() return ANKIGTA.Store.listMapEntities() end")
    call(store, "function() return ANKIGTA.Store.historyStatus() end")

    store.fire_timers()

    assert [entry for entry in backups(store) if entry["kind"] == "daily"] == []


# --- the envelope -------------------------------------------------------------


def test_copying_happens_off_the_request_path(store: MtaSandbox) -> None:
    """The F7 envelope is two seconds; a database copy is not spent inside it.

    Not a stopwatch — a count. A data change and a full entity read must make no
    `fileCopy` call at all; the copy happens on the timer afterwards. A timing
    assertion would pass on a fast machine with the copy in the wrong place.
    """
    store.faults.calls.clear()

    change_data(store, 8)
    call(store, "function() return ANKIGTA.Store.listMapEntities() end")

    assert store.faults.calls["fileCopy"] == 0

    store.fire_timers()

    assert store.faults.calls["fileCopy"] == 1


def test_a_failed_daily_backup_does_not_take_the_store_down(
    store: MtaSandbox,
) -> None:
    """A copy that cannot be made is a diagnostic, not an outage."""
    change_data(store, 9)
    store.faults.fail_after("fileCopy")

    store.fire_timers()

    assert backups(store) == []
    assert any(
        "daily_backup_failed" in line for line in store.recorder.debug_messages()
    )
    # The database is still open and still writable.
    assert change_data(store, 10) is True


# --- retention ----------------------------------------------------------------


def test_seven_daily_copies_are_kept_and_the_eighth_day_evicts_the_oldest(
    store: MtaSandbox, tmp_path: Path
) -> None:
    days = []
    for index in range(10):
        change_data(store, 1 + index * 0.5)
        store.fire_timers()
        days.append(
            str(call(store, "function() return ANKIGTA.Backup.dayKey() end"))
        )
        store.advance_days(1)

    daily = [entry for entry in backups(store) if entry["kind"] == "daily"]
    assert len(daily) == 7
    # The seven kept are the seven most recent days, and the evicted files are
    # gone from disk rather than merely unlisted.
    assert [entry["day"] for entry in daily] == list(reversed(days[3:]))
    on_disk = {path.name for path in (tmp_path / "backups").glob("ankigta-daily-*.sqlite")}
    assert on_disk == {Path(entry["path"]).name for entry in daily}


def test_three_pre_migration_copies_are_kept(store: MtaSandbox, tmp_path: Path) -> None:
    for _ in range(5):
        call(store, "function() return ANKIGTA.Backup.createPreMigration() end")

    premigration = [
        entry for entry in backups(store) if entry["kind"] == "premigration"
    ]
    assert len(premigration) == 3
    on_disk = {
        path.name for path in (tmp_path / "backups").glob("ankigta-premigration-*.sqlite")
    }
    assert on_disk == {Path(entry["path"]).name for entry in premigration}


def test_the_two_retentions_do_not_evict_each_other(
    store: MtaSandbox,
) -> None:
    """Seven daily and three pre-migration, not ten of whichever came last."""
    for index in range(9):
        change_data(store, 1 + index * 0.5)
        store.fire_timers()
        store.advance_days(1)
    for _ in range(4):
        call(store, "function() return ANKIGTA.Backup.createPreMigration() end")

    kinds = [entry["kind"] for entry in backups(store)]

    assert kinds.count("daily") == 7
    assert kinds.count("premigration") == 3


# --- what a copy holds --------------------------------------------------------


def test_a_copy_is_the_whole_database_and_is_published_in_one_step(
    store: MtaSandbox, tmp_path: Path
) -> None:
    change_data(store, 11)
    store.fire_timers()

    entry = backups(store)[0]
    copied = tmp_path / entry["path"]
    # Byte for byte the database as it stood, not a re-serialisation of it.
    assert copied.read_bytes() == (tmp_path / "ankigta.sqlite").read_bytes()
    # Nothing is left under a staging name for someone to mistake for a backup.
    assert not (tmp_path / "backups" / "staging.sqlite").exists()
    assert sorted(path.name for path in (tmp_path / "backups").iterdir()) == [
        "ankigta-daily-1.sqlite",
        "manifest.json",
    ]


def test_a_copy_carries_the_change_history_and_its_cursor(
    store: MtaSandbox, tmp_path: Path
) -> None:
    change_data(store, 12)
    call(store, "function() return ANKIGTA.Store.undo() end")
    store.fire_timers()

    copied = tmp_path / backups(store)[0]["path"]
    connection = sqlite3.connect(copied)
    try:
        assert connection.execute("SELECT COUNT(*) FROM change_history").fetchone() == (
            1,
        )
        # The cursor sits before the entry, exactly as the undo left it, so the
        # restored database can still redo.
        assert connection.execute(
            "SELECT cursor_id FROM change_history_state"
        ).fetchone() == (0,)
    finally:
        connection.close()


def test_the_ui_placement_file_is_not_in_the_backup_directory(
    store: MtaSandbox, tmp_path: Path
) -> None:
    """Backups hold server SQLite. Client-side placement is not server data."""
    store.write_file("@ankigta-settings.json", '{"uiScale": 1.25}')
    store.write_file("connection.json", '{"port": 40010}')
    change_data(store, 13)

    store.fire_timers()

    copied = [path.name for path in (tmp_path / "backups").iterdir()]
    assert "@ankigta-settings.json" not in copied
    assert "connection.json" not in copied


# --- verification is what makes a copy a recovery option ----------------------


def test_verification_rejects_a_database_from_a_newer_build(
    tmp_path: Path,
) -> None:
    """A copy this build cannot read is not a copy it may offer to restore."""
    future = tmp_path / "future.sqlite"
    shipped_schemas.build(future, "v4")
    connection = sqlite3.connect(future)
    try:
        connection.execute("UPDATE schema_meta SET version = 99 WHERE singleton = 1")
        connection.commit()
    finally:
        connection.close()

    sandbox = server(tmp_path)
    try:
        call(sandbox, "function() return ANKIGTA.Store.open() end")

        outcome = sandbox.to_python(
            call(
                sandbox,
                "function(p) local ok, why = ANKIGTA.Backup.verify(p) "
                "return {ok = ok and true or false, reason = why or false} end",
                "future.sqlite",
            )
        )

        assert outcome["ok"] is False
        assert outcome["reason"] == "backup_schema_unsupported"
    finally:
        sandbox.close()


def test_verification_rejects_a_copy_whose_change_history_cursor_dangles(
    store: MtaSandbox, tmp_path: Path
) -> None:
    """Restoring a copy has to leave Change History usable, so it is checked."""
    change_data(store, 14)
    store.fire_timers()
    copied = tmp_path / backups(store)[0]["path"]
    connection = sqlite3.connect(copied)
    try:
        connection.execute("UPDATE change_history_state SET cursor_id = 99")
        connection.commit()
    finally:
        connection.close()

    listed = backups(store)

    assert listed[0]["verified"] is False
    assert listed[0]["reason"] == "backup_history_cursor_out_of_range"


def test_verification_rejects_a_copy_with_a_broken_foreign_key(
    store: MtaSandbox, tmp_path: Path
) -> None:
    change_data(store, 15)
    store.fire_timers()
    copied = tmp_path / backups(store)[0]["path"]
    connection = sqlite3.connect(copied)
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            "INSERT INTO spatial_links VALUES "
            "('ghost-map', 'ghost', ?, 1, 'active', ?)",
            (shipped_schemas.UUID, "0" * 64),
        )
        connection.commit()
    finally:
        connection.close()

    listed = backups(store)

    assert listed[0]["verified"] is False
    assert listed[0]["reason"] == "backup_constraints_violated"
