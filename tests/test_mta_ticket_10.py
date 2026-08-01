from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RESOURCE = REPO_ROOT / "mta" / "ankigta"
STORE = RESOURCE / "server" / "store.lua"
IDENTITY = RESOURCE / "server" / "map_identity.lua"
MAIN = RESOURCE / "server" / "main.lua"
F7 = RESOURCE / "client" / "f7.lua"


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


def test_store_persists_entity_metadata_and_missing_state() -> None:
    store = source(STORE)

    assert "map_entity_metadata" in store
    assert "name TEXT NOT NULL" in store
    assert "entity_tag TEXT NOT NULL" in store
    assert "radius REAL NOT NULL" in store
    assert "show_radius INTEGER NOT NULL" in store
    assert "presence_state TEXT NOT NULL" in store
    assert "Store.markEntityMissing" in store
    assert "Store.clearEntityMissing" in store


def test_missing_detection_uses_saved_map_identity_not_runtime_destruction() -> None:
    identity = source(IDENTITY)
    destroy_handler = function_body(identity, "MapIdentity.handleEditorElementDestroyed")

    assert "MapIdentity.refreshEntityPresence" in identity
    assert "xmlLoadFile" in function_body(identity, "mapFileContainsEntity")
    assert "ankigtaEntityId" in function_body(identity, "mapFileContainsEntity")
    assert "ankigtaMapId" in function_body(identity, "mapFileContainsEntity")
    assert "Store.markEntityMissing" in identity
    assert "Store.clearEntityMissing" in identity
    assert "Store.markEntityMissing" not in destroy_handler
    snapshot = function_body(identity, "MapIdentity.linkSnapshot")
    assert snapshot.index("isIdentityCollision") < snapshot.index(
        'row.entity_state == "entity_missing"'
    )


def test_relink_is_atomic_and_keeps_target_identity() -> None:
    store = source(STORE)
    relink = function_body(store, "Store.relinkEntity")

    assert 'source.entity_state ~= "entity_missing"' in relink
    assert "target.link_state" in relink
    assert "card_missing" in relink
    assert "INSERT INTO spatial_links" in relink
    assert "DELETE FROM spatial_links" in relink
    assert "persistent Map Entity remains available" in relink
    assert "historyTransaction(" in relink
    assert "reversible" in relink
    assert "targetMapId" in relink
    assert "targetEntityId" in relink


def test_f7_exposes_missing_metadata_and_relink_actions() -> None:
    main = source(MAIN)
    client = source(F7)

    assert "refreshEntityPresence" in main
    assert "relinkEntity" in main
    assert "Entity missing" in main
    assert "entityTag" in main
    assert "showRadius" in main
    assert "RELINK_ENTITY_REQUEST_EVENT" in main
    assert 'relink_entity' in main
    assert "RELINK_ENTITY_REQUEST_EVENT" in client
    assert "Relink entity" in client
    assert "relinkPreview" in client


def test_ticket_10_manual_runtime_checklist_is_not_run() -> None:
    checklist = REPO_ROOT / "docs" / "checklists" / "ticket10-entity-missing-relink.md"
    text = source(checklist)
    assert "Status: not run" in text
    for scenario in ("map edit", "reload", "cross-map", "interior", "dimension", "restart"):
        assert scenario in text
