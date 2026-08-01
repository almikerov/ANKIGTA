from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from tests.lua.constants import string_constants

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
RESOURCE = REPO_ROOT / "mta" / "ankigta"
SERVER_MAIN = RESOURCE / "server" / "main.lua"
SERVER_STORE = RESOURCE / "server" / "store.lua"
CLIENT_F7 = RESOURCE / "client" / "f7.lua"
SERVER_COMPANION = RESOURCE / "server" / "companion.lua"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _function_body(lua: str, name: str) -> str:
    match = re.search(
        rf"(?:local )?function {re.escape(name)}\([^)]*\)(.*?)"
        rf"(?=\n(?:local function |function |[A-Za-z][A-Za-z.]* = |addEvent\())",
        lua,
        flags=re.DOTALL,
    )
    assert match, f"Lua function not found: {name}"
    return match.group(1)


def test_spatial_link_schema_allows_card_reuse_but_one_link_per_entity() -> None:
    store = _source(SERVER_STORE)
    schema = _function_body(store, "createCurrentSchema")
    spatial_sql = re.search(
        r"\[\[(\s*CREATE TABLE spatial_links \(.*?)\]\]",
        schema,
        flags=re.DOTALL,
    )
    assert spatial_sql is not None
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE maps (map_id TEXT PRIMARY KEY, resource_name TEXT NOT NULL, map_name TEXT NOT NULL);
            CREATE TABLE map_entities (
                map_id TEXT NOT NULL, entity_id TEXT NOT NULL,
                entity_type TEXT NOT NULL, model INTEGER NOT NULL,
                authored_x REAL NOT NULL, authored_y REAL NOT NULL, authored_z REAL NOT NULL,
                rotation_x REAL NOT NULL, rotation_y REAL NOT NULL, rotation_z REAL NOT NULL,
                interior INTEGER NOT NULL, dimension INTEGER NOT NULL,
                PRIMARY KEY (map_id, entity_id),
                FOREIGN KEY (map_id) REFERENCES maps(map_id)
            );
            """
        )
        connection.execute(spatial_sql.group(1))
        connection.execute("INSERT INTO maps VALUES ('m', 'r', 'map')")
        connection.executemany(
            "INSERT INTO map_entities VALUES ('m', ?, 'object', 1, 0, 0, 0, 0, 0, 0, 0, 0)",
            [("e1",), ("e2",)],
        )
        connection.executemany(
            "INSERT INTO spatial_links VALUES ('m', ?, 'u', 7, 'active', ?)",
            [("e1", "a" * 64), ("e2", "b" * 64)],
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO spatial_links VALUES ('m', 'e1', 'u', 8, 'active', ?)",
                ("c" * 64,),
            )
    finally:
        connection.close()


def test_pending_and_collision_links_are_ineligible_and_picker_is_presented() -> None:
    identity = _source(RESOURCE / "server" / "map_identity.lua")
    server = _source(SERVER_MAIN)
    client = _source(CLIENT_F7)
    assert 'state = "Pending Map Save"' in identity
    assert "activation = false" in identity
    assert "identity_collision" in server or "collision" in identity
    assert "f7.cardPicker" in string_constants(CLIENT_F7)
    assert "CARD_PICKER" in client
    assert "link.state == \"Unlinked\"" in client
    assert "triggerServerEvent" in client
    assert "deckFilterEdit" in client
    assert "guiGridListGetSelectedItem(cardGrid)" in client
    assert "existingLinks" in client


def test_card_picker_uses_read_only_companion_search_and_pending_preparation() -> None:
    companion = _source(SERVER_COMPANION)
    server = _source(SERVER_MAIN)
    identity = _source(RESOURCE / "server" / "map_identity.lua")

    assert 'CARD_SEARCH_PATH = "/v1/cards/search"' in companion
    assert "Gateway.requestCardPicker" in companion
    assert "deckFilter" in companion
    assert "requestId" in companion
    assert "validCardPickerPayload" in companion
    assert "validCardView" in companion
    assert "response.error ~= nil and response.error ~= false" in companion
    assert "MapIdentity.prepareCardLinkForEntity" in server
    assert "Store.linkCardToEntity" not in _function_body(server, "linkCardToEntity")
    assert "preparePendingMapSave" in identity
    assert "MapIdentity.preparePendingMapSave(" in _function_body(
        identity, "MapIdentity.prepareCardLinkForEntity"
    )
