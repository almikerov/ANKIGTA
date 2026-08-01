"""Ticket 30 — the presence refresh that runs inside every F7 open.

`MapIdentity.refreshEntityPresence` establishes Entity missing from the saved
map data, and F7 waits for it. It used to answer each Map Entity by parsing the
whole map file again, and to write a row per entity to record that nothing had
changed — work that is invisible on a tracer-sized world and is the whole of
F7's two-second budget, several times over, on a reference-sized one.

These are behavioural: the real scripts run against a real map file and a real
database, and the assertions are on what was parsed, what was written, and what
the store ended up saying.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterator
from xml.etree import ElementTree

import pytest

from tests.lua import MtaSandbox


REPO_ROOT = Path(__file__).resolve().parents[1]

RESOURCE_NAME = "ticket30-map-resource"
MAP_FILE = "reference.map"
VIRTUAL_PATH = f":{RESOURCE_NAME}/{MAP_FILE}"
MAP_ID = "ticket30-map"


def manifest_scripts(*kinds: str) -> list[str]:
    manifest = ElementTree.parse(REPO_ROOT / "mta" / "ankigta" / "meta.xml")
    return [
        str(element.get("src"))
        for element in manifest.iter("script")
        if element.get("type") in kinds
    ]


@pytest.fixture
def server(tmp_path: Path) -> Iterator[MtaSandbox]:
    sandbox = MtaSandbox(database_path=str(tmp_path / "ankigta.sqlite"))
    try:
        for script in manifest_scripts("shared", "server"):
            sandbox.load(script)
        sandbox.trigger("onResourceStart")
        yield sandbox
    finally:
        sandbox.close()


def seed_world(sandbox: MtaSandbox, entity_ids: list[str]) -> None:
    """A map and its Map Entity, written straight into the open database.

    Through SQL rather than through the Map Editor path: what is under test is
    the refresh, and a hundred entities arrive from one save rather than from a
    hundred user actions.
    """
    connection: sqlite3.Connection = sandbox.connection.raw
    connection.execute(
        "INSERT OR IGNORE INTO maps (map_id, resource_name, map_name)"
        " VALUES (?, ?, ?)",
        (MAP_ID, RESOURCE_NAME, MAP_FILE),
    )
    connection.executemany(
        "INSERT OR IGNORE INTO map_entities (map_id, entity_id, entity_type,"
        " model, authored_x, authored_y, authored_z, rotation_x, rotation_y,"
        " rotation_z, interior, dimension)"
        " VALUES (?, ?, 'object', 1337, 0, 0, 0, 0, 0, 0, 0, 0)",
        [(MAP_ID, entity_id) for entity_id in entity_ids],
    )


def refresh(sandbox: MtaSandbox) -> Any:
    return sandbox.eval(
        "function() return ANKIGTA.MapIdentity.refreshEntityPresence() end"
    )()


def presence(sandbox: MtaSandbox) -> dict[str, str]:
    cursor = sandbox.connection.raw.execute(
        "SELECT entity_id, presence_state FROM map_entity_metadata"
    )
    return {row[0]: row[1] for row in cursor.fetchall()}


def test_the_map_file_is_parsed_once_however_many_entities_it_holds(
    server: MtaSandbox,
) -> None:
    """The parse is per document, not per entity.

    A hundred entities in one map is one map file. Answering each of them by
    reparsing it is a hundred parses for one document, and the shape of that
    cost is quadratic in a world where both numbers grow together.
    """
    entity_ids = [f"ref-{index:04d}" for index in range(100)]
    seed_world(server, entity_ids)
    server.write_map_file(
        VIRTUAL_PATH,
        {MAP_ID: "ankigta_map_identity", **{entity: "object" for entity in entity_ids}},
    )
    server.xml_loads.clear()

    assert refresh(server) is True

    # One parse per document. The store's own tracer entity lives in a second
    # map, so two documents are read, and neither is read twice.
    assert server.xml_loads.count(VIRTUAL_PATH) == 1
    assert len(server.xml_loads) == len(set(server.xml_loads))


def test_an_entity_the_saved_map_no_longer_holds_becomes_entity_missing(
    server: MtaSandbox,
) -> None:
    seed_world(server, ["kept", "removed"])
    server.write_map_file(
        VIRTUAL_PATH, {MAP_ID: "ankigta_map_identity", "kept": "object"}
    )

    assert refresh(server) is True

    assert presence(server)["removed"] == "entity_missing"
    assert presence(server).get("kept") in (None, "identified")


def test_an_entity_the_saved_map_holds_again_stops_being_missing(
    server: MtaSandbox,
) -> None:
    seed_world(server, ["restored"])
    server.write_map_file(VIRTUAL_PATH, {MAP_ID: "ankigta_map_identity"})
    refresh(server)
    assert presence(server)["restored"] == "entity_missing"

    server.write_map_file(
        VIRTUAL_PATH, {MAP_ID: "ankigta_map_identity", "restored": "object"}
    )

    assert refresh(server) is True
    assert presence(server)["restored"] == "identified"


def test_a_refresh_that_changes_nothing_writes_nothing(
    server: MtaSandbox,
) -> None:
    """The refresh runs on every F7 open.

    Recording "still there" for every Map Entity is two statements per entity
    to store what was already stored, which on the reference world is twenty
    thousand writes inside a window the player is waiting on.
    """
    entity_ids = [f"ref-{index:04d}" for index in range(50)]
    seed_world(server, entity_ids)
    server.write_map_file(
        VIRTUAL_PATH,
        {MAP_ID: "ankigta_map_identity", **{entity: "object" for entity in entity_ids}},
    )
    refresh(server)
    before = server.connection.raw.total_changes

    assert refresh(server) is True

    assert server.connection.raw.total_changes == before


def test_a_map_file_that_cannot_be_read_leaves_presence_alone(
    server: MtaSandbox,
) -> None:
    """"Not there" is not "its entities are gone".

    A map whose resource is not loaded reads as no file at all, and treating
    that as an empty map would mark every Map Entity in it missing.
    """
    seed_world(server, ["unreadable"])

    assert refresh(server) is True

    assert presence(server).get("unreadable") in (None, "identified")
