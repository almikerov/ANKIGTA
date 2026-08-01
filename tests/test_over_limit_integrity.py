"""Ticket 30 — past the reference volume, data is still whole.

The promise is narrow and worth stating exactly: over the reference volume,
ANKIGTA may warn and may be slower, and may not truncate or corrupt anything it
persisted. "Nothing raised" is not evidence for that. So every assertion here
reports the state the files were left in — how many rows survived, whether
SQLite still calls the database intact, and what is on disk — the way ticket
29's tests do, because the failure this is guarding against is the quiet one.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any, Iterator
from xml.etree import ElementTree

import pytest

from tests.lua import MtaSandbox
from tests.perf.dataset import (
    MAP_ID,
    REFERENCE_MAP_ENTITIES,
    REFERENCE_SPATIAL_LINKS,
    card_id,
    entity_id,
    fill_store,
)


REPO_ROOT = Path(__file__).resolve().parents[1]

#: Comfortably past the reference volume in both dimensions, and small enough
#: that the test stays a test. The property is about being over the line, not
#: about how far over it.
OVER_MAP_ENTITIES = REFERENCE_MAP_ENTITIES + 2_000
OVER_SPATIAL_LINKS = REFERENCE_SPATIAL_LINKS + 1_000


def manifest_scripts(*kinds: str) -> list[str]:
    manifest = ElementTree.parse(REPO_ROOT / "mta" / "ankigta" / "meta.xml")
    return [
        str(element.get("src"))
        for element in manifest.iter("script")
        if element.get("type") in kinds
    ]


def start(directory: Path) -> MtaSandbox:
    sandbox = MtaSandbox(database_path=str(directory / "ankigta.sqlite"))
    for script in manifest_scripts("shared", "server"):
        sandbox.load(script)
    sandbox.trigger("onResourceStart")
    return sandbox


def file_state(directory: Path) -> str:
    """Every file, its size and — for a database — what SQLite makes of it.

    This is the string every assertion below carries, so a failure says what
    was left behind rather than only which comparison went wrong.
    """
    lines: list[str] = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        data = path.read_bytes()
        entry = (
            f"{path.relative_to(directory).as_posix()}"
            f" bytes={len(data)}"
            f" sha256={hashlib.sha256(data).hexdigest()[:16]}"
        )
        if path.suffix == ".sqlite":
            entry += f" integrity={integrity_of(path)}"
            entry += f" rows={row_counts(path)}"
        lines.append(entry)
    return "\n".join(lines) or "(no files)"


def integrity_of(path: Path) -> str:
    try:
        connection = sqlite3.connect(path)
    except sqlite3.Error as error:  # pragma: no cover - a file SQLite refuses
        return f"unopenable:{error}"
    try:
        return str(connection.execute("PRAGMA integrity_check").fetchone()[0])
    except sqlite3.Error as error:
        return f"check_failed:{error}"
    finally:
        connection.close()


def row_counts(path: Path) -> dict[str, int]:
    connection = sqlite3.connect(path)
    try:
        counts: dict[str, int] = {}
        for table in (
            "maps",
            "map_entities",
            "spatial_links",
            "map_entity_metadata",
            "change_history",
        ):
            try:
                counts[table] = int(
                    connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                )
            except sqlite3.Error:
                counts[table] = -1
        return counts
    finally:
        connection.close()


@pytest.fixture
def over_limit(tmp_path: Path) -> Iterator[tuple[MtaSandbox, Path]]:
    directory = tmp_path / "resource"
    directory.mkdir()
    sandbox = start(directory)
    fill_store(
        sandbox,
        map_entities=OVER_MAP_ENTITIES,
        spatial_links=OVER_SPATIAL_LINKS,
    )
    try:
        yield sandbox, directory
    finally:
        sandbox.close()


def call(sandbox: MtaSandbox, expression: str, *args: Any) -> Any:
    return sandbox.eval(expression)(*args)


def volume(sandbox: MtaSandbox) -> dict[str, Any]:
    return dict(
        sandbox.to_python(
            call(sandbox, "function() return ANKIGTA.Store.volumeReport() end")
        )
    )


def test_over_the_reference_volume_warns_and_keeps_every_row(
    over_limit: tuple[MtaSandbox, Path],
) -> None:
    sandbox, directory = over_limit

    report = volume(sandbox)
    state = file_state(directory)

    assert report["overReference"] is True, state
    assert any(
        "volume_over_reference" in message
        for message in sandbox.recorder.debug_messages()
    ), state
    counts = row_counts(directory / "ankigta.sqlite")
    # Nothing pruned to fit: the tracer entities the store seeds are extra, so
    # the floor is what was written rather than an exact total.
    assert counts["map_entities"] >= OVER_MAP_ENTITIES, state
    assert counts["spatial_links"] == OVER_SPATIAL_LINKS, state
    assert integrity_of(directory / "ankigta.sqlite") == "ok", state


def test_the_snapshot_over_the_limit_serves_every_entity(
    over_limit: tuple[MtaSandbox, Path],
) -> None:
    """Slower is allowed; a shorter list is not.

    A cap that quietly dropped the tail would look exactly like this test
    passing on counts alone, so the first and last entity are named.
    """
    sandbox, directory = over_limit
    player = sandbox.add_study_player()

    sandbox.trigger(
        "ankigta:requestF7",
        sandbox.eval("resourceRoot"),
        client=player,
    )
    sent = sandbox.recorder.client_events[-1]
    state = file_state(directory)

    assert sent.name == "ankigta:f7Snapshot", state
    snapshot = sandbox.to_python(sent.args[0])
    listed = {
        entry["mapEntity"]["entityId"]
        for entry in snapshot["entities"]
        if entry["mapEntity"]["mapId"] == MAP_ID
    }
    assert len(listed) == OVER_MAP_ENTITIES, state
    assert entity_id(0) in listed, state
    assert entity_id(OVER_MAP_ENTITIES - 1) in listed, state
    assert snapshot["diagnostics"]["overReferenceVolume"] is True, state


def test_writing_over_the_limit_persists_and_survives_a_restart(
    tmp_path: Path,
) -> None:
    """A change made past the reference volume is a change that is still there.

    The store is closed and reopened rather than only read back, because the
    failure this guards against — a write that never reached the file — is
    invisible to a reader holding the same connection.
    """
    directory = tmp_path / "resource"
    directory.mkdir()
    sandbox = start(directory)
    try:
        fill_store(
            sandbox,
            map_entities=OVER_MAP_ENTITIES,
            spatial_links=OVER_SPATIAL_LINKS,
        )
        # An ordinary user action, through the store's own API and its Change
        # History, on an entity past the reference volume.
        target = entity_id(OVER_SPATIAL_LINKS + 5)
        linked = call(
            sandbox,
            """
            function(mapId, entityId, uuid, cardId)
                return ANKIGTA.Store.activateSpatialLink({
                    mapId = mapId,
                    entityId = entityId,
                    cardIdentity = {collectionUuid = uuid, cardId = cardId},
                    mapLocator = {
                        resourceName = "ankigta",
                        mapFile = "Ticket 30 reference map",
                    },
                    verifiedMapSha256 = string.rep("b", 64),
                })
            end
            """,
            MAP_ID,
            target,
            "30000000-3000-4000-8000-300000000030",
            card_id(999_999),
        )
        before = file_state(directory)
        assert linked is not False, f"{linked}\n{before}"
    finally:
        sandbox.close()

    reopened = start(directory)
    try:
        state = file_state(directory)
        row = sandbox_row(reopened, MAP_ID, target)
        assert row is not False, state
        assert int(row["card_id"]) == card_id(999_999), state
        assert row["link_state"] == "active", state
        history = dict(
            reopened.to_python(
                call(
                    reopened,
                    "function() return ANKIGTA.Store.historyStatus() end",
                )
            )
        )
        # The history is bounded, not truncated: the change is still undoable.
        assert history["canUndo"] is True, state
        assert integrity_of(directory / "ankigta.sqlite") == "ok", state
    finally:
        reopened.close()


def sandbox_row(sandbox: MtaSandbox, map_id: str, entity_id_value: str) -> Any:
    row = call(
        sandbox,
        """
        function(mapId, entityId)
            local rows = ANKIGTA.Store.listMapEntities()
            if not rows then return false end
            for _, candidate in ipairs(rows) do
                if candidate.map_id == mapId
                    and candidate.entity_id == entityId
                then
                    return candidate
                end
            end
            return false
        end
        """,
        map_id,
        entity_id_value,
    )
    if row is False:
        return False
    return dict(sandbox.to_python(row))


def test_a_backup_taken_over_the_limit_is_a_whole_database(
    over_limit: tuple[MtaSandbox, Path],
) -> None:
    """The copy is the thing a recovery would restore from, so a copy that
    stopped short past the reference volume would be the corruption this
    criterion is about, only discovered later."""
    sandbox, directory = over_limit

    created = call(sandbox, "function() return ANKIGTA.Backup.createDaily() end")
    state = file_state(directory)
    assert created is not False, state

    copies = sandbox.to_python(
        call(sandbox, "function() return ANKIGTA.Backup.list() end")
    )
    assert copies, state
    # `Backup.list` reports newest first.
    latest = copies[0]
    copy_path = directory / str(latest["path"])
    assert copy_path.is_file(), state
    assert integrity_of(copy_path) == "ok", state
    copied = row_counts(copy_path)
    original = row_counts(directory / "ankigta.sqlite")
    assert copied == original, state
