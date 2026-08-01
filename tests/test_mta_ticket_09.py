from __future__ import annotations

import re
import sqlite3
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RESOURCE = REPO_ROOT / "mta" / "ankigta"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def function_body(lua: str, name: str) -> str:
    match = re.search(
        rf"(?:local )?function {re.escape(name)}\([^)]*\)(.*?)"
        rf"(?=\n(?:local function |function |[A-Za-z][A-Za-z.]* = |addEvent\())",
        lua,
        flags=re.DOTALL,
    )
    assert match, f"Lua function not found: {name}"
    return match.group(1)


def test_current_schema_persists_display_metadata_and_card_missing_state() -> None:
    store = source(RESOURCE / "server" / "store.lua")
    schema = function_body(store, "createCurrentSchema")
    # Ticket 09 needs schema 4 or later; later tickets may migrate past it.
    schema_version = re.search(r"CURRENT_SCHEMA_VERSION = (\d+)", store)
    assert schema_version and int(schema_version.group(1)) >= 4
    history_schema = function_body(store, "ensureChangeHistorySchema")
    assert "CREATE TABLE IF NOT EXISTS map_entity_metadata" in history_schema
    assert "name TEXT NOT NULL DEFAULT ''" in history_schema
    assert "entity_tag TEXT NOT NULL DEFAULT ''" in history_schema
    assert "radius REAL NOT NULL DEFAULT 3" in history_schema
    assert "show_radius INTEGER NOT NULL DEFAULT 0" in history_schema
    assert "state IN ('active', 'card_missing')" in schema


def test_link_mutations_are_atomic_and_identity_checked() -> None:
    store = source(RESOURCE / "server" / "store.lua")
    unlink = function_body(store, "Store.unlinkSpatialLink")
    replace = function_body(store, "Store.replaceSpatialLink")
    refresh = function_body(store, "Store.refreshSpatialLinkCardState")

    assert "transaction(Store.connection" in unlink
    assert "DELETE FROM spatial_links" in unlink
    assert "expectedCardIdentity" in unlink
    assert "transaction(Store.connection" in replace
    assert "UPDATE spatial_links" in replace
    assert "oldCardIdentity" in replace
    assert "refresh" in refresh.lower()
    assert "card_missing" in refresh


def test_missing_card_is_visible_but_not_eligible_and_ui_requires_confirmation() -> None:
    identity = source(RESOURCE / "server" / "map_identity.lua")
    server = source(RESOURCE / "server" / "main.lua")
    client = source(RESOURCE / "client" / "f7.lua")

    snapshot = function_body(identity, "MapIdentity.linkSnapshot")
    assert "Card missing" in snapshot
    assert "study = false" in snapshot
    assert "activation = false" in snapshot
    assert "statistics = false" in snapshot
    assert "markers = false" in snapshot
    assert "Unlink" in client
    assert "Replace card" in client
    assert "oldCardIdentity" in client
    assert "newCardIdentity" in client
    assert "confirmation" in client.lower()
    assert "SESSION_INVALIDATED_EVENT" in server


def test_server_refreshes_dependents_after_unlink_or_replace() -> None:
    server = source(RESOURCE / "server" / "main.lua")
    companion = source(RESOURCE / "server" / "companion.lua")
    assert "triggerEvent(SESSION_INVALIDATED_EVENT" in server
    assert "sendF7Snapshot(player)" in server
    assert "oldIdentity" in server
    assert "newIdentity" in server
    assert 'CARD_READ_PATH = "/v1/cards/read"' in companion
    assert "refreshSpatialLinkCardState" in companion
