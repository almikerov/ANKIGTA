from __future__ import annotations

import re
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

from tests.lua import MtaSandbox
from tests.lua.constants import string_constants

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
RESOURCE = REPO_ROOT / "mta" / "ankigta"
PROTOTYPE = REPO_ROOT / "docs" / "prototypes" / "0005-map-editor-identity-persistence.md"
ADR = REPO_ROOT / "docs" / "adr" / "0025-use-the-stock-map-editor.md"
EDF = RESOURCE / "ankigta.edf"
META = RESOURCE / "meta.xml"
SERVER_IDENTITY = RESOURCE / "server" / "map_identity.lua"
SERVER_MAIN = RESOURCE / "server" / "main.lua"
CLIENT_F7 = RESOURCE / "client" / "panel.lua"
SERVER_STORE = RESOURCE / "server" / "store.lua"


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


def test_identity_uses_edf_child_and_object_property_without_map_writes() -> None:
    definition = ET.parse(EDF).getroot()
    meta = _source(META)
    identity_source = _source(SERVER_IDENTITY)

    map_identity = definition.find("./element[@name='ankigta_map_identity']")
    assert map_identity is not None
    assert map_identity.find("./data[@name='ankigtaMapId'][@type='string']") is not None

    assert 'edf:definition="ankigta.edf"' in meta

    assert 'edfSetElementProperty(mapIdentity, "ankigtaMapId", mapId)' in identity_source
    assert (
        'edfSetElementProperty(objectElement, "ankigtaEntityId", entityId)'
        in identity_source
    )
    assert "fileCreate(" not in identity_source
    assert "fileWrite(" not in identity_source
    assert "xmlSaveFile(" not in identity_source


def test_pending_map_save_is_visible_but_ineligible_until_read_back() -> None:
    identity = _source(SERVER_IDENTITY)
    server = _source(SERVER_MAIN)
    client = _source(CLIENT_F7)

    prepare = _function_body(identity, "MapIdentity.preparePendingMapSave")
    snapshot = _function_body(identity, "MapIdentity.linkSnapshot")
    entity_contract = _function_body(server, "entityContract")

    assert 'state = "Pending Map Save"' in prepare
    assert "study = false" in prepare
    assert "activation = false" in prepare
    assert "statistics = false" in prepare
    assert "markers = false" in prepare
    assert "ANKIGTA.Store" not in prepare
    assert "pendingByEntity[entityKey(row.map_id, row.entity_id)]" in snapshot
    assert "link = ANKIGTA.MapIdentity.linkSnapshot(row)" in entity_contract
    f7_keys = string_constants(CLIENT_F7)
    assert "guidanceKey = entry.link.guidanceKey" in _source(CLIENT_F7)
    assert "ankigta:recheckPendingMapSave" in f7_keys


def test_auto_observer_and_manual_recheck_share_independent_read_back() -> None:
    identity = _source(SERVER_IDENTITY)

    read_back = _function_body(identity, "readBackSavedMap")
    attempt = _function_body(identity, "attemptReadBack")
    manual = _function_body(identity, "MapIdentity.recheckPendingMapSave")
    observe = _function_body(identity, "observeSavedMap")

    assert "xmlLoadFile(pending.mapLocator.virtualPath, true)" in read_back
    assert 'xmlNodeGetName(child) == "ankigta_map_identity"' in read_back
    assert 'xmlNodeGetAttribute(child, "ankigtaMapId")' in read_back
    assert 'xmlNodeGetName(child) == "object"' in read_back
    assert 'xmlNodeGetAttribute(child, "ankigtaEntityId")' in read_back
    assert 'return false, "partial_read_back"' in read_back
    assert 'return false, "ambiguous_read_back"' in read_back
    assert 'return true, "verified"' in read_back

    assert "readBackSavedMap(pending)" in attempt
    assert "ANKIGTA.Store.activateSpatialLink(pending)" in attempt
    assert "assignIdentity(" not in attempt
    assert "attemptReadBack(pending, \"manual\")" in manual
    assert "attemptReadBack(pending, \"automatic\")" in observe
    assert "assignIdentity(" not in manual
    assert "assignIdentity(" not in observe
    assert "xmlSaveFile(" not in identity
    assert "fileWrite(" not in identity


def test_only_verified_active_spatial_link_is_persisted() -> None:
    store = _source(SERVER_STORE)
    identity = _source(SERVER_IDENTITY)

    schema = _function_body(store, "createCurrentSchema")
    activation = _function_body(store, "Store.activateSpatialLink")
    snapshot = _function_body(identity, "MapIdentity.linkSnapshot")

    spatial_link_sql = re.search(
        r"\[\[(\s*CREATE TABLE spatial_links \(.*?)\]\]",
        schema,
        flags=re.DOTALL,
    )
    assert spatial_link_sql is not None
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE maps (
                map_id TEXT PRIMARY KEY,
                resource_name TEXT NOT NULL,
                map_name TEXT NOT NULL
            );
            CREATE TABLE map_entities (
                map_id TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                model INTEGER NOT NULL,
                authored_x REAL NOT NULL,
                authored_y REAL NOT NULL,
                authored_z REAL NOT NULL,
                rotation_x REAL NOT NULL,
                rotation_y REAL NOT NULL,
                rotation_z REAL NOT NULL,
                interior INTEGER NOT NULL,
                dimension INTEGER NOT NULL,
                PRIMARY KEY (map_id, entity_id),
                FOREIGN KEY (map_id) REFERENCES maps(map_id) ON DELETE CASCADE
            );
            """
        )
        connection.execute(spatial_link_sql.group(1))
        columns = {
            row[1]: row[2]
            for row in connection.execute("PRAGMA table_info(spatial_links)")
        }
        assert columns == {
            "map_id": "TEXT",
            "entity_id": "TEXT",
            "collection_uuid": "TEXT",
            "card_id": "INTEGER",
            "state": "TEXT",
            "verified_map_sha256": "TEXT",
        }
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO spatial_links VALUES (?, ?, ?, ?, ?, ?)",
                ("m", "e", "collection", 6, "Pending Map Save", "0" * 64),
            )
    finally:
        connection.close()

    assert "transaction(Store.connection" in activation
    assert "INSERT INTO spatial_links" in activation
    assert '"active"' in activation
    assert "pending" not in schema.lower()
    assert "pending" not in activation.lower()
    assert "row.link_state == \"active\"" in snapshot
    assert "activeByEntity" not in identity


def test_unsaved_close_discards_pending_while_failed_save_stays_pending() -> None:
    identity = _source(SERVER_IDENTITY)
    server = _source(SERVER_MAIN)
    client = _source(CLIENT_F7)

    destroyed = _function_body(identity, "MapIdentity.handleEditorElementDestroyed")
    discard = _function_body(identity, "discardPending")

    assert "readSavedMapHash(pending)" in destroyed
    assert "currentHash == pending.baselineHash" in destroyed
    assert 'discardPending(pending, "unsaved_close_or_reload")' in destroyed
    assert 'attemptReadBack(pending, "close_or_reload")' in destroyed
    assert "pendingByEntity[key] = nil" in discard
    assert "PENDING_NOTICE_EVENT" in discard
    assert "notice.pendingDiscarded" in string_constants(SERVER_IDENTITY)
    assert 'addEventHandler("onElementDestroy", root' in server
    assert "ANKIGTA.MapIdentity.handleEditorElementDestroyed(source)" in server
    assert 'local PENDING_NOTICE_EVENT = "ankigta:pendingMapSaveNotice"' in client
    assert "outputChatBox" in client


def test_public_object_prepare_path_uses_stock_editor_and_acl_boundary() -> None:
    identity = _source(SERVER_IDENTITY)
    server = _source(SERVER_MAIN)
    meta = _source(META)

    prepare_object = _function_body(identity, "MapIdentity.prepareObjectPendingMapSave")
    public_prepare = _function_body(server, "prepareObjectPendingMapSave")

    assert "exports.editor_main:getCurrentMapName()" in identity
    assert 'xmlLoadFile(":" .. mapName .. "/meta.xml", true)' in identity
    assert "createMapIdentity(player)" in prepare_object
    assert "exports.edf:edfCreateElement(" in identity
    assert "exports.editor_main:import(container)" in identity
    assert "readSavedMapHash(pending)" not in prepare_object
    assert "readMapFileHash(mapLocator.virtualPath)" in prepare_object
    assert "MapIdentity.preparePendingMapSave(" in prepare_object
    assert "playerAuthorization(player)" in public_prepare
    assert "ANKIGTA.Store.singleMapEntity()" in public_prepare
    assert "ANKIGTA.MapIdentity.prepareObjectPendingMapSave(" in public_prepare
    assert '<export function="prepareObjectPendingMapSave" type="server" />' in meta
    assert "fileCreate(" not in identity
    assert "fileWrite(" not in identity
    assert "xmlSaveFile(" not in identity


def test_f7_manual_recheck_is_acl_guarded_and_repeats_only_read_back() -> None:
    identity = _source(SERVER_IDENTITY)
    server = _source(SERVER_MAIN)
    client = _source(CLIENT_F7)

    recheck = _function_body(server, "recheckPendingMapSave")
    manual_read_back = _function_body(identity, "MapIdentity.recheckPendingMapSave")

    assert (
        'local RECHECK_REQUEST_EVENT = "ankigta:recheckPendingMapSave"' in server
    )
    assert (
        'local RECHECK_REQUEST_EVENT = "ankigta:recheckPendingMapSave"' in client
    )
    assert "playerAuthorization(player)" in recheck
    assert "ANKIGTA.MapIdentity.recheckPendingMapSave(mapId, entityId)" in recheck
    assert "sendF7Snapshot(player)" in recheck
    assert "assignIdentity(" not in manual_read_back
    assert "createMapIdentity(" not in manual_read_back
    assert "triggerServerEvent(" in client
    assert "RECHECK_REQUEST_EVENT" in client
    assert "actions.recheck" in client
    assert "selectedEntityId" in client


def test_automatic_activation_refreshes_open_f7_through_a_server_only_event() -> None:
    identity = _source(SERVER_IDENTITY)
    server = _source(SERVER_MAIN)

    attempt = _function_body(identity, "attemptReadBack")
    assert (
        'local IDENTITY_CHANGED_EVENT = "ankigta:mapIdentityChanged"' in identity
    )
    assert "triggerEvent(" in attempt
    assert "IDENTITY_CHANGED_EVENT" in attempt
    assert 'addEvent(IDENTITY_CHANGED_EVENT, false)' in server
    assert "sendF7Snapshot(player)" in server


def test_source_and_manual_contract_preserve_stock_editor_limits() -> None:
    identity = _source(SERVER_IDENTITY)
    prototype = _source(PROTOTYPE)
    adr = _source(ADR)

    assert "EDF custom child element" in prototype
    assert "публичного durable `before-save`/`after-save` callback" in prototype.lower()
    assert "не делает атомарной всю Editor-транзакцию" in prototype
    assert "не поставляет собственный fork" in adr
    assert "отсутствие атомарности" in adr
    assert "защиты от внешнего изменения файла" in adr

    assert "setTimer(observeSavedMap, 500, 0)" in identity
    assert "xmlLoadFile(pending.mapLocator.virtualPath, true)" in identity
    assert "fileCreate(" not in identity
    assert "fileWrite(" not in identity
    assert "xmlSaveFile(" not in identity
    assert "atomic" not in identity.lower()
    assert "external conflict" not in identity.lower()


def test_read_back_binds_entity_id_to_the_selected_editor_element() -> None:
    identity = _source(SERVER_IDENTITY)
    read_back = _function_body(identity, "readBackSavedMap")
    prepare = _function_body(identity, "MapIdentity.preparePendingMapSave")

    assert 'editorElementId = getElementData(objectElement, "me:ID")' in prepare
    assert 'xmlNodeGetAttribute(child, "id") == pending.editorElementId' in read_back
    assert "selectedEntityIdentityCount ~= 1" in read_back
    assert "expectedEntityIdentityCount > 1" in read_back


def test_activation_updates_the_verified_map_locator_in_the_same_transaction() -> None:
    store = _source(SERVER_STORE)
    activation = _function_body(store, "Store.activateSpatialLink")

    assert "transaction(Store.connection" in activation
    assert "UPDATE maps SET resource_name = ?, map_name = ?" in activation
    assert "value.mapLocator.resourceName" in activation
    assert "value.mapLocator.mapFile" in activation
    assert activation.index("UPDATE maps SET") < activation.index(
        "INSERT INTO spatial_links"
    )


def test_pending_guidance_is_honest_after_failed_read_back() -> None:
    identity = _source(SERVER_IDENTITY)
    client = _source(CLIENT_F7)
    snapshot = _function_body(identity, "MapIdentity.linkSnapshot")

    assert "pending.lastReadBackOutcome" in snapshot
    assert 'guidanceKey = "guidance.retrySave"' in snapshot
    assert "guidanceKey = entry.link.guidanceKey" in client

    # The guidance is a key now, so honesty is a property of what it resolves
    # to. Both languages have to name the stock Save and the recheck action,
    # not a vague "try again".
    sandbox = MtaSandbox()
    try:
        sandbox.load("shared/locale.lua")
        for language, expected in (
            ("en", ("stock Save", "Check again")),
            ("ru", ("stock Save", "Проверить ещё раз")),
        ):
            sandbox.eval("function(l) ANKIGTA.Locale.setLanguage(l) end")(language)
            guidance = sandbox.eval(
                'ANKIGTA.Locale.text("guidance.retrySave")'
            )
            for phrase in expected:
                assert phrase in guidance, (language, guidance)
    finally:
        sandbox.close()


def test_prepare_never_overwrites_existing_persistent_ids() -> None:
    identity = _source(SERVER_IDENTITY)
    prepare = _function_body(identity, "MapIdentity.preparePendingMapSave")

    assert 'getElementData(mapIdentity, "ankigtaMapId")' in prepare
    assert 'getElementData(objectElement, "ankigtaEntityId")' in prepare
    assert 'return false, "persistent_map_identity_conflict"' in prepare
    assert 'return false, "persistent_entity_identity_conflict"' in prepare
    assert prepare.index("persistent_map_identity_conflict") < prepare.index(
        "assignIdentity("
    )
    assert prepare.index("persistent_entity_identity_conflict") < prepare.index(
        "assignIdentity("
    )
