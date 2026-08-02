from __future__ import annotations

import re
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

from tests.lua.constants import string_constants

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
RESOURCE = REPO_ROOT / "mta" / "ankigta"
IDENTITY = RESOURCE / "server" / "map_identity.lua"
STORE = RESOURCE / "server" / "store.lua"
MAIN = RESOURCE / "server" / "main.lua"
F7 = RESOURCE / "client" / "panel.lua"
META = RESOURCE / "meta.xml"


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


def test_supported_editor_types_share_pending_readback_contract() -> None:
    identity = source(IDENTITY)
    store = source(STORE)
    main = source(MAIN)

    # Markers joined the three: a marker is placed to mean "here", which is
    # what a card wants to hang on.
    assert (
        "entity_type TEXT NOT NULL CHECK"
        " (entity_type IN ('object', 'vehicle', 'ped', 'marker'))"
    ) in store
    assert "SUPPORTED_ENTITY_TYPES" in identity
    assert "MapIdentity.prepareVehiclePendingMapSave" in identity
    assert "MapIdentity.preparePedPendingMapSave" in identity
    assert "prepareManagedPendingMapSave" in identity
    read_back = function_body(identity, "readBackSavedMap")
    assert "vehicle" in read_back
    assert "ped" in read_back
    assert "ambiguous_read_back" in read_back
    assert "entityType" in read_back
    assert "prepareVehiclePendingMapSave" in main
    assert "preparePedPendingMapSave" in main
    assert 'singleMapEntity("vehicle", vehicleElement)' in main
    assert 'singleMapEntity("ped", pedElement)' in main
    assert "entityElement" in store


def test_collision_coordinator_blocks_ambiguous_ids_before_activation() -> None:
    identity = source(IDENTITY)
    store = source(STORE)

    assert "MapIdentity.detectIdentityCollisions" in identity
    assert "identity_collision" in identity
    assert "MapIdentity.resolveCopyDecision" in identity
    assert "original_or_renamed" in identity
    assert "new_copy" in identity
    assert "allowRename" in identity
    assert "createMapEntityCopy" in identity
    assert "recoverPersistedCollisions" in identity
    activation = function_body(store, "Store.activateSpatialLink")
    assert "Store.mapIdentityOwner" in activation
    assert "identity_collision" in activation
    assert "markIdentityCollision" in identity
    # Off the row rather than one query per entity (ticket 30), which is the
    # same answer `Store.isIdentityCollision` gives.
    assert "rowIsIdentityCollision" in identity
    assert "state = \"Identity Collision\"" in identity
    assert "needsEntityTypeMigration" in store
    # What the rebuild is called, and whether it goes via a `_legacy` table, is
    # incidental: ticket 29 replaced the rename-and-drop with the procedure
    # SQLite documents, because renaming took the dependent rows with it.
    # `tests/test_migrations.py` covers the shape repair on real data.
    assert "identity_collisions" in store
    assert "markEntityIdentityCollision" in store
    assert "clearEntityIdentityCollision" in store
    assert "updateMapLocator" in store
    assert "pendingByEntity[key] = collision" in identity
    assert "INSERT INTO spatial_links" in activation


def test_copy_decision_is_visible_in_f7_and_new_copy_has_no_link_transfer() -> None:
    client = source(F7)
    main = source(MAIN)
    meta = source(META)

    f7_keys = string_constants(F7)
    assert "ankigta:resolveMapCopyDecision" in f7_keys
    assert "original_or_renamed" in f7_keys
    assert "new_copy" in f7_keys
    assert "COPY_DECISION_REQUEST_EVENT" in client
    assert "copyCollision" in main
    assert "resolveCopyDecision" in main
    assert "new_copy" in main
    assert "automaticLinkTransfer = false" in main
    assert '<export function="resolveMapCopyDecision" type="server" />' in meta
    assert "newCopy = true" in source(IDENTITY)
    assert 'return true, "unlinked_copy"' in source(IDENTITY)
    assert "copyEntries" in source(IDENTITY)
    assert "copies = newCopies" in source(IDENTITY)
    assert "value.allowRename" in source(STORE)


def test_sql_fixture_rejects_duplicate_persistent_entity_ids() -> None:
    store = source(STORE)
    schema = re.search(r"\[\[(\s*CREATE TABLE map_entities \(.*?)\]\]", store, re.DOTALL)
    assert schema is not None
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        CREATE TABLE maps (map_id TEXT PRIMARY KEY);
        """
    )
    connection.executescript(schema.group(1))
    connection.execute("INSERT INTO maps VALUES ('m')")
    connection.execute(
        "INSERT INTO map_entities VALUES "
        "('m', 'e', 'vehicle', 411, 0, 0, 0, 0, 0, 0, 0, 0)"
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO map_entities VALUES "
            "('m', 'e', 'ped', 7, 1, 1, 1, 0, 0, 0, 0, 0)"
        )


def test_manual_editor_matrix_is_explicitly_not_run() -> None:
    checklist = REPO_ROOT / "docs" / "checklists" / "ticket07-map-editor.md"
    text = source(checklist)
    assert "Status: not run" in text
    for scenario in (
        "object",
        "vehicle",
        "ped",
        "clone",
        "copyResource",
        "renameResource",
        "Save As",
        "restart",
    ):
        assert scenario in text


def test_matrix_fixture_covers_all_stock_editor_entity_types() -> None:
    fixture = ET.parse(RESOURCE / "maps" / "ticket07-matrix.map").getroot()
    assert [child.tag for child in fixture] == ["object", "vehicle", "ped"]
    assert all(child.attrib["id"].startswith("ticket07-") for child in fixture)


def test_copy_fixture_matrix_preserves_embedded_ids_until_explicit_decision() -> None:
    original = ET.Element("map")
    ET.SubElement(original, "ankigta_map_identity", ankigtaMapId="map-a")
    ET.SubElement(
        original,
        "vehicle",
        id="vehicle-a",
        ankigtaEntityId="entity-a",
    )
    copied = ET.fromstring(ET.tostring(original))
    assert copied.find("ankigta_map_identity").attrib["ankigtaMapId"] == "map-a"
    assert copied.find("vehicle").attrib["ankigtaEntityId"] == "entity-a"

    identities = [
        (
            node.tag,
            node.attrib.get("ankigtaEntityId"),
        )
        for node in list(original) + list(copied)
        if node.tag in {"object", "vehicle", "ped"}
    ]
    assert identities.count(("vehicle", "entity-a")) == 2
    assert "original_or_renamed" in source(IDENTITY)
    assert "new_copy" in source(IDENTITY)
    assert "automaticLinkTransfer = false" in source(IDENTITY)
