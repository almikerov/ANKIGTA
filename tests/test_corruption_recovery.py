"""Ticket 29 — a damaged database is never silently replaced.

This is the negative half of the ticket and the half worth most: the happy path
is one restore that worked, while the property under test here is everything
ANKIGTA must *not* do when it opens a database it cannot read. It must not
create a fresh one over the top, must not roll back to a backup on its own,
must not touch a byte of the damaged file, and must not spend a backup nobody
chose. The user picks a copy, and the damaged original is kept for diagnosis.

Every assertion below therefore reports the state the files were left in, byte
for byte, rather than only that nothing raised.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterator

import pytest

from tests.lua import MtaSandbox
from tests.lua import shipped_schemas


UUID = shipped_schemas.UUID


# --- harness ------------------------------------------------------------------


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def server(directory: Path) -> MtaSandbox:
    """The server side, loaded but not started."""
    sandbox = MtaSandbox(database_path=str(directory / "ankigta.sqlite"))
    sandbox.load("shared/settings.lua")
    sandbox.load("server/backup.lua")
    sandbox.load("server/store.lua")
    # The tracer fixture, asked for rather than seeded into every database:
    # a player listing entities they never placed was it leaking out of
    # the tests it was written for.
    sandbox.eval("function() ANKIGTA.Store.seedTracerFixtures = true end")()
    return sandbox


def call(sandbox: MtaSandbox, expression: str, *args: Any) -> Any:
    return sandbox.eval(expression)(*args)


def opened(sandbox: MtaSandbox) -> Any:
    return call(sandbox, "function() return ANKIGTA.Store.open() end")


def status(sandbox: MtaSandbox) -> dict[str, Any]:
    return dict(
        sandbox.to_python(call(sandbox, "function() return ANKIGTA.Store.status() end"))
    )


def recovery(sandbox: MtaSandbox) -> Any:
    return sandbox.to_python(
        call(sandbox, "function() return ANKIGTA.Store.recovery() end")
    )


def as_list(value: Any) -> list[Any]:
    """An empty Lua table arrives as `{}`; a filled array arrives as a list."""
    return list(value) if isinstance(value, list) else []


def backups(sandbox: MtaSandbox) -> list[dict[str, Any]]:
    return as_list(
        sandbox.to_python(call(sandbox, "function() return ANKIGTA.Backup.list() end"))
    )


def make_daily(sandbox: MtaSandbox) -> Any:
    return sandbox.to_python(
        call(sandbox, "function() return ANKIGTA.Backup.createDaily() end")
    )


def restore(sandbox: MtaSandbox, backup_id: Any) -> dict[str, Any]:
    return dict(
        sandbox.to_python(
            call(
                sandbox,
                "function(id) local ok, why = ANKIGTA.Backup.restore(id) "
                "return {ok = ok and true or false, reason = why or false} end",
                backup_id,
            )
        )
    )


@pytest.fixture
def workspace(tmp_path: Path) -> Iterator[Path]:
    yield tmp_path


def seeded(directory: Path) -> MtaSandbox:
    """A started server with a real database, one Spatial Link and one backup."""
    sandbox = server(directory)
    opened(sandbox)
    linked = sandbox.to_python(
        call(
            sandbox,
            """
            function(uuid)
                return ANKIGTA.Store.activateSpatialLink({
                    mapId = "ticket05-map",
                    entityId = "ticket05-entity",
                    cardIdentity = {collectionUuid = uuid, cardId = 4242},
                    mapLocator = {
                        resourceName = "ankigta",
                        mapFile = "Ticket 05 tracer map",
                    },
                    verifiedMapSha256 = string.rep("b", 64),
                })
            end
            """,
            UUID,
        )
    )
    assert linked is not False, "the fixture must have data worth restoring"
    make_daily(sandbox)
    call(sandbox, "function() return ANKIGTA.Store.close() end")
    return sandbox


def corrupt(path: Path, *, mode: str = "garbage") -> None:
    """Damage a database the way a disk or a killed process does."""
    original = path.read_bytes()
    if mode == "garbage":
        path.write_bytes(b"this is not a database, it is a note to self." * 40)
    elif mode == "truncated":
        path.write_bytes(original[: len(original) // 3])
    elif mode == "page":
        # Keep a valid header and wreck a page, so SQLite opens the file and
        # only then finds it malformed.
        damaged = bytearray(original)
        damaged[len(damaged) // 2 :] = b"\xde\xad\xbe\xef" * (
            (len(damaged) - len(damaged) // 2) // 4
        )
        path.write_bytes(bytes(damaged))
    else:
        raise ValueError(mode)


# --- the property ------------------------------------------------------------


@pytest.mark.parametrize("mode", ["garbage", "truncated", "page"])
def test_a_corrupt_database_is_never_silently_replaced(
    workspace: Path, mode: str
) -> None:
    """The whole ticket in one test: opening damage changes nothing on disk."""
    primary = workspace / "ankigta.sqlite"
    seeded(workspace).close()
    backup_files = sorted(p for p in workspace.rglob("*.sqlite") if p != primary)
    assert backup_files, "the fixture must leave a backup to be tempted by"
    before = {path: digest(path) for path in [primary, *backup_files]}
    corrupt(primary, mode=mode)
    before[primary] = digest(primary)

    sandbox = server(workspace)
    try:
        assert opened(sandbox) is False

        # Nothing on disk moved: not the damaged database, not the backup.
        after = {path: digest(path) for path in before}
        assert after == before, "opening a damaged database rewrote a file"

        state = status(sandbox)
        assert state["ready"] is False
        assert state["errorCategory"] == "database_corrupt"

        # And the user is asked, rather than told what was done for them.
        chosen = recovery(sandbox)
        assert isinstance(chosen, dict)
        assert chosen["state"] == "recovery"
        assert chosen["reason"] == "database_corrupt"
        assert chosen["awaitingChoice"] is True
        assert [entry["verified"] for entry in as_list(chosen["backups"])] == [True]
    finally:
        sandbox.close()


def test_a_corrupt_database_with_no_backup_still_refuses_to_start_fresh(
    workspace: Path,
) -> None:
    """With nothing to restore from, the answer is still not "make a new one"."""
    primary = workspace / "ankigta.sqlite"
    sandbox = server(workspace)
    opened(sandbox)
    call(sandbox, "function() return ANKIGTA.Store.close() end")
    sandbox.close()
    corrupt(primary)
    damaged = digest(primary)

    sandbox = server(workspace)
    try:
        assert opened(sandbox) is False

        assert digest(primary) == damaged
        chosen = recovery(sandbox)
        assert as_list(chosen["backups"]) == []
        assert chosen["awaitingChoice"] is True
        # No usable copy is still a state the user is shown, not a silent wipe.
        assert status(sandbox)["errorCategory"] == "database_corrupt"
    finally:
        sandbox.close()


def test_recovery_does_not_arm_itself_for_a_database_that_is_merely_new(
    workspace: Path,
) -> None:
    """An absent database is not a damaged one; the guard must tell them apart."""
    sandbox = server(workspace)
    try:
        assert opened(sandbox) is True

        assert status(sandbox)["ready"] is True
        assert recovery(sandbox) is False
    finally:
        sandbox.close()


# --- the user's choice reaches the restore ------------------------------------


def test_the_user_choosing_a_verified_backup_restores_it(workspace: Path) -> None:
    primary = workspace / "ankigta.sqlite"
    seeded(workspace).close()
    corrupt(primary)

    sandbox = server(workspace)
    try:
        opened(sandbox)
        offered = as_list(recovery(sandbox)["backups"])
        assert len(offered) == 1

        outcome = restore(sandbox, offered[0]["id"])

        assert outcome["ok"] is True
        # The Spatial Link the backup held is back, and readable through Lua.
        assert opened(sandbox) is True
        links = sandbox.to_python(
            call(
                sandbox,
                'function() return ANKIGTA.Store.getMapEntity('
                '"ticket05-map", "ticket05-entity") end',
            )
        )
        assert links["card_id"] == 4242
        assert links["link_state"] == "active"
    finally:
        sandbox.close()


def test_the_damaged_original_is_kept_for_diagnosis(workspace: Path) -> None:
    primary = workspace / "ankigta.sqlite"
    seeded(workspace).close()
    corrupt(primary)
    damaged = digest(primary)

    sandbox = server(workspace)
    try:
        opened(sandbox)
        chosen = as_list(recovery(sandbox)["backups"])[0]

        outcome = restore(sandbox, chosen["id"])
        assert outcome["ok"] is True

        quarantined = [
            path
            for path in workspace.rglob("*")
            if path.is_file() and digest(path) == damaged
        ]
        assert quarantined, "the damaged database was thrown away"
        # And it is named, not merely left lying about, so support can ask for it.
        listed = sandbox.to_python(
            call(sandbox, "function() return ANKIGTA.Backup.quarantined() end")
        )
        assert [entry["path"] for entry in as_list(listed)] == [
            quarantined[0].relative_to(workspace).as_posix()
        ]
    finally:
        sandbox.close()


def test_an_unverifiable_backup_is_offered_to_nobody_and_refused_on_request(
    workspace: Path,
) -> None:
    """A copy that does not survive verification is not a recovery option."""
    primary = workspace / "ankigta.sqlite"
    seeded(workspace).close()
    copies = sorted(p for p in workspace.rglob("*.sqlite") if p != primary)
    assert len(copies) == 1
    corrupt(copies[0], mode="page")
    corrupt(primary)
    poisoned = digest(copies[0])

    sandbox = server(workspace)
    try:
        opened(sandbox)
        chosen = recovery(sandbox)

        offered = as_list(chosen["backups"])
        assert [entry["verified"] for entry in offered] == [False]
        # Asking for it anyway is refused, and refused before anything moves.
        outcome = restore(sandbox, offered[0]["id"])
        assert outcome["ok"] is False
        assert outcome["reason"] == "backup_integrity_failed"
        assert digest(primary) != poisoned
        assert digest(copies[0]) == poisoned
    finally:
        sandbox.close()


def test_restoring_leaves_change_history_and_its_constraints_intact(
    workspace: Path,
) -> None:
    """A restored database is a working one, not merely a present one."""
    primary = workspace / "ankigta.sqlite"
    sandbox = server(workspace)
    opened(sandbox)
    call(
        sandbox,
        """
        function()
            ANKIGTA.Store.setUserSetting("activationRadius", 9)
            ANKIGTA.Store.setMapIncludeInStudy("ticket05-map", false)
        end
        """,
    )
    make_daily(sandbox)
    call(sandbox, "function() return ANKIGTA.Store.close() end")
    sandbox.close()
    corrupt(primary)

    sandbox = server(workspace)
    try:
        opened(sandbox)
        restore(sandbox, as_list(recovery(sandbox)["backups"])[0]["id"])
        assert opened(sandbox) is True

        history = sandbox.to_python(
            call(sandbox, "function() return ANKIGTA.Store.historyStatus() end")
        )
        assert history["entryCount"] == 2
        assert history["canUndo"] is True
        # Undo still works against the restored rows, so the cursor and the
        # journal agree with each other and with the data.
        assert call(sandbox, "function() return ANKIGTA.Store.undo() end") is not False
        assert (
            shipped_schemas.rows(primary, "PRAGMA foreign_key_check") == []
        )
        assert shipped_schemas.rows(primary, "PRAGMA integrity_check") == [
            {"integrity_check": "ok"}
        ]
    finally:
        sandbox.close()


def test_the_backup_holds_the_database_and_not_the_connection_config(
    workspace: Path,
) -> None:
    """Backups carry server SQLite whole, and nothing that is not it."""
    sandbox = server(workspace)
    try:
        opened(sandbox)
        sandbox.write_file("connection.json", json.dumps({"port": 40010}))
        sandbox.write_file("@ankigta-settings.json", json.dumps({"uiScale": 1.5}))

        make_daily(sandbox)

        entry = backups(sandbox)[0]
        copied = workspace / entry["path"]
        assert copied.is_file()
        # It is a database, whole enough to read the same rows back out of.
        connection = sqlite3.connect(copied)
        try:
            names = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        finally:
            connection.close()
        assert {"maps", "map_entities", "spatial_links", "change_history"} <= names

        # Neither the connection config nor the client's UI file is in there.
        assert entry["path"].endswith(".sqlite")
        payload = copied.read_bytes()
        assert b"40010" not in payload
        assert b"uiScale" not in payload
    finally:
        sandbox.close()
