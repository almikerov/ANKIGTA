from __future__ import annotations

import re
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RESOURCE = REPO_ROOT / "mta" / "ankigta"
SERVER_MAIN = RESOURCE / "server" / "main.lua"
SERVER_STORE = RESOURCE / "server" / "store.lua"
CLIENT_F7 = RESOURCE / "client" / "f7.lua"
META = RESOURCE / "meta.xml"
MAP = RESOURCE / "maps" / "ticket05.map"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _function_body(lua: str, name: str) -> str:
    match = re.search(
        rf"(?:local )?function {re.escape(name)}\([^)]*\)(.*?)"
        rf"(?=\n(?:local function |function |bindKey\(|addEvent\())",
        lua,
        flags=re.DOTALL,
    )
    assert match, f"Lua function not found: {name}"
    return match.group(1)


def _event_handler_body(lua: str, event: str, attached_to: str) -> str:
    prefix = f"addEventHandler({event}, {attached_to}, function("
    start = lua.find(prefix)
    assert start >= 0, f"Lua event handler not found: {event}"
    body_start = lua.find("\n", start) + 1
    end = lua.find("\nend)", body_start)
    assert body_start > 0 and end >= 0, f"Lua event handler is incomplete: {event}"
    return lua[body_start:end]


def _migration_statements(lua: str) -> list[str]:
    body = _function_body(lua, "migrateVersionOne")
    return [
        statement
        for statement in re.findall(r'"([^"\r\n]+)"', body)
        if statement.startswith(("ALTER TABLE", "UPDATE "))
    ]


def _current_schema_statements(lua: str) -> list[str]:
    body = _function_body(lua, "createCurrentSchema")
    statements = [
        statement.strip()
        for statement in re.findall(
            r"\[\[(.*?)\]\]",
            body,
            flags=re.DOTALL,
        )
    ]
    statements.extend(
        statement
        for statement in re.findall(r'"([^"\r\n]+)"', body)
        if statement.startswith("INSERT INTO schema_meta")
    )
    return statements


def _tracer_seed_statements(lua: str) -> list[str]:
    return [
        statement.strip()
        for statement in re.findall(
            r"\[\[(.*?)\]\]",
            _function_body(lua, "ensureTracerEntity"),
            flags=re.DOTALL,
        )
    ]


def _legacy_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE schema_meta (
            singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
            version INTEGER NOT NULL
        );
        INSERT INTO schema_meta (singleton, version) VALUES (1, 1);
        CREATE TABLE maps (
            map_id TEXT PRIMARY KEY,
            resource_name TEXT NOT NULL,
            map_name TEXT NOT NULL
        );
        CREATE TABLE map_entities (
            map_id TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            entity_type TEXT NOT NULL CHECK (entity_type = 'object'),
            model INTEGER NOT NULL,
            authored_x REAL NOT NULL,
            authored_y REAL NOT NULL,
            authored_z REAL NOT NULL,
            authored_heading REAL NOT NULL,
            interior INTEGER NOT NULL,
            dimension INTEGER NOT NULL,
            PRIMARY KEY (map_id, entity_id),
            FOREIGN KEY (map_id) REFERENCES maps(map_id) ON DELETE CASCADE
        );
        INSERT INTO maps VALUES (
            'ticket05-map', 'ankigta', 'Ticket 05 tracer map'
        );
        INSERT INTO map_entities VALUES (
            'ticket05-map', 'ticket05-entity', 'object', 1337,
            10.5, -20.25, 4.75, 135.0, 3, 17
        );
        """
    )
    return connection


def test_acceptance_checks_never_launch_mta() -> None:
    integration = REPO_ROOT / "tests" / "integration"
    ticket_harness = integration / "mta_ticket_05"
    run_script = integration / "run_mta_ticket_05.ps1"

    assert not (ticket_harness / "runner.py").exists()
    assert not (ticket_harness / "driver" / "server.lua").exists()
    assert not (ticket_harness / "driver" / "client.lua").exists()
    assert not run_script.exists()


def test_server_source_guards_f7_with_a_logged_player_and_acl_right() -> None:
    server = _source(SERVER_MAIN)
    meta = _source(META)
    send_snapshot = _function_body(server, "sendF7Snapshot")
    remote_f7 = _event_handler_body(server, "F7_REQUEST_EVENT", "resourceRoot")
    remote_authorization = _event_handler_body(
        server,
        "AUTHORIZATION_REQUEST_EVENT",
        "resourceRoot",
    )

    assert 'local STUDY_RIGHT = "resource.ankigta.study"' in server
    assert "getPlayerAccount(player)" in server
    assert "isGuestAccount(account)" in server
    assert "hasObjectPermissionTo(player, STUDY_RIGHT, false)" in server
    assert send_snapshot.index("playerAuthorization(player)") < send_snapshot.index(
        "buildF7Snapshot()"
    )
    assert "F7_DENIED_EVENT" in send_snapshot[
        : send_snapshot.index("buildF7Snapshot()")
    ]
    assert "return false" in send_snapshot[: send_snapshot.index("buildF7Snapshot()")]
    assert remote_f7.strip() == (
        "if not client or source ~= resourceRoot then\n"
        "        return\n"
        "    end\n"
        "    sendF7Snapshot(client)"
    )
    assert remote_authorization.strip() == (
        "if not client or source ~= resourceRoot then\n"
        "        return\n"
        "    end\n"
        "    sendAuthorization(client)"
    )
    assert server.count("sendF7Snapshot(") == 2
    assert server.count("buildF7Snapshot(") == 2
    assert "getF7SnapshotForAccount" not in server
    assert "getF7SnapshotForAccount" not in meta


def test_migration_sql_is_transactional_and_preserves_the_entity() -> None:
    store = _source(SERVER_STORE)
    statements = _migration_statements(store)
    assert statements == [
        "ALTER TABLE map_entities ADD COLUMN rotation_x REAL NOT NULL DEFAULT 0",
        "ALTER TABLE map_entities ADD COLUMN rotation_y REAL NOT NULL DEFAULT 0",
        "ALTER TABLE map_entities ADD COLUMN rotation_z REAL NOT NULL DEFAULT 0",
        "UPDATE map_entities SET rotation_z = authored_heading",
        "UPDATE schema_meta SET version = ? WHERE singleton = 1",
    ]
    assert all(
        marker in _function_body(store, "transaction")
        for marker in ("BEGIN IMMEDIATE", "ROLLBACK", "COMMIT")
    )
    transaction = _function_body(store, "transaction")
    migration = _function_body(store, "migrateVersionOne")
    assert migration.lstrip().startswith("return transaction(Store.connection, {")
    assert transaction.index("BEGIN IMMEDIATE") < transaction.index(
        "for _, step in ipairs(steps)"
    )
    assert transaction.index("for _, step in ipairs(steps)") < transaction.index(
        "COMMIT"
    )
    assert transaction.count("ROLLBACK") == 2

    connection = _legacy_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        for statement in statements:
            connection.execute(statement, (2,) if "?" in statement else ())
        connection.commit()

        entity = connection.execute(
            """
            SELECT map_id, entity_id, entity_type, model,
                   authored_x, authored_y, authored_z,
                   rotation_x, rotation_y, rotation_z,
                   interior, dimension
            FROM map_entities
            """
        ).fetchone()
        assert entity == (
            "ticket05-map",
            "ticket05-entity",
            "object",
            1337,
            10.5,
            -20.25,
            4.75,
            0.0,
            0.0,
            135.0,
            3,
            17,
        )
        assert connection.execute(
            "SELECT version FROM schema_meta"
        ).fetchone() == (2,)
    finally:
        connection.close()


def test_current_schema_create_and_restart_preserve_the_record(
    tmp_path: Path,
) -> None:
    database = tmp_path / "ankigta.sqlite"
    store = _source(SERVER_STORE)
    statements = _current_schema_statements(store)
    seed_statements = _tracer_seed_statements(store)
    assert len(statements) == 4
    assert len(seed_statements) == 2

    connection = sqlite3.connect(database)
    try:
        for statement in statements:
            connection.execute(statement, (2,) if "?" in statement else ())
        connection.execute(
            seed_statements[0],
            ("ticket05-map", "ankigta", "Ticket 05 tracer map"),
        )
        connection.execute(
            seed_statements[1],
            (
                "ticket05-map",
                "ticket05-entity",
                "object",
                1337,
                10.5,
                -20.25,
                4.75,
                0.0,
                0.0,
                135.0,
                3,
                17,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    restarted = sqlite3.connect(database)
    try:
        assert restarted.execute(
            "SELECT version FROM schema_meta WHERE singleton = 1"
        ).fetchone() == (2,)
        assert restarted.execute(
            """
            SELECT map_id, entity_id, entity_type, model,
                   authored_x, authored_y, authored_z,
                   rotation_x, rotation_y, rotation_z,
                   interior, dimension
            FROM map_entities
            """
        ).fetchone() == (
            "ticket05-map",
            "ticket05-entity",
            "object",
            1337,
            10.5,
            -20.25,
            4.75,
            0.0,
            0.0,
            135.0,
            3,
            17,
        )
    finally:
        restarted.close()

    store_open = _function_body(store, "Store.open")
    assert store_open.index("connect(DATABASE_PATH)") < store_open.index(
        "hasSchema(Store.connection)"
    )
    assert "createCurrentSchema(Store.connection)" in store_open
    assert "migrateVersionOne()" in store_open
    assert store_open.index("migrateVersionOne()") < store_open.index(
        "ensureTracerEntity()"
    )
    assert store_open.index("ensureTracerEntity()") < store_open.index(
        "Store.ready = true"
    )
    server_start = _event_handler_body(
        _source(SERVER_MAIN),
        '"onResourceStart"',
        "resourceRoot",
    )
    assert "ANKIGTA.Store.open()" in server_start


def test_failed_migration_rolls_back_without_partial_schema_change() -> None:
    statements = _migration_statements(_source(SERVER_STORE))
    connection = _legacy_connection()
    try:
        connection.execute(
            "ALTER TABLE map_entities ADD COLUMN rotation_x REAL NOT NULL DEFAULT 0"
        )
        connection.commit()

        connection.execute("BEGIN IMMEDIATE")
        try:
            for statement in statements:
                connection.execute(statement, (2,) if "?" in statement else ())
        except sqlite3.OperationalError:
            connection.rollback()
        else:
            raise AssertionError("the inconsistent v1 schema must reject migration")

        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(map_entities)")
        }
        assert "rotation_x" in columns
        assert "rotation_y" not in columns
        assert "rotation_z" not in columns
        assert connection.execute(
            "SELECT version FROM schema_meta"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT map_id, entity_id FROM map_entities"
        ).fetchone() == ("ticket05-map", "ticket05-entity")
    finally:
        connection.close()


def test_versioned_store_seeds_only_the_supported_object_record() -> None:
    store = _source(SERVER_STORE)
    map_root = ET.parse(MAP).getroot()
    objects = map_root.findall("object")

    assert "local CURRENT_SCHEMA_VERSION = 2" in store
    assert "entity_type TEXT NOT NULL CHECK (entity_type = 'object')" in store
    assert 'entityId = "ticket05-entity"' in store
    assert 'entityType = "object"' in store
    assert "model = 1337" in store
    assert "authoredX = 10.5" in store
    assert "authoredY = -20.25" in store
    assert "authoredZ = 4.75" in store
    assert "rotationZ = 135" in store
    assert "interior = 3" in store
    assert "dimension = 17" in store
    assert "backup" not in store.lower()
    assert len(objects) == 1
    assert objects[0].attrib == {
        "id": "ankigta-ticket05-runtime",
        "model": "1337",
        "posX": "10.5",
        "posY": "-20.25",
        "posZ": "4.75",
        "rotX": "0",
        "rotY": "0",
        "rotZ": "135",
        "interior": "3",
        "dimension": "17",
    }


def test_client_source_keeps_map_entity_visible_without_runtime_instance() -> None:
    server = _source(SERVER_MAIN)
    client = _source(CLIENT_F7)
    map_source = _source(MAP)

    assert "mapEntity = {" in server
    assert "runtimeInstance = runtimeSnapshot()" in server
    assert "if not isElement(runtimeInstance) then" in server
    assert 'addEventHandler("onElementDestroy", root' in server
    assert "runtimeInstance = nil" in server
    assert "getElementByID(runtime.referenceId)" in client
    assert "isElementStreamedIn(element)" in client
    assert "Runtime Instance destroyed" in client
    assert "Runtime Instance not streamed" in client
    assert "mapEntity.mapId .." in client
    assert 'id="ankigta-ticket05-runtime"' in map_source


def test_client_reauthorizes_after_resource_restart_before_opening_f7() -> None:
    server = _source(SERVER_MAIN)
    client = _source(CLIENT_F7)

    assert 'local AUTHORIZATION_REQUEST_EVENT = "ankigta:requestAuthorization"' in (
        server
    )
    assert 'local AUTHORIZATION_REQUEST_EVENT = "ankigta:requestAuthorization"' in (
        client
    )
    assert 'addEventHandler("onClientResourceStart", resourceRoot' in client
    assert "triggerServerEvent(AUTHORIZATION_REQUEST_EVENT, resourceRoot)" in client
    assert "if not authorized then" in _function_body(client, "requestF7")


def test_f7_restores_only_the_cursor_state_it_acquired() -> None:
    client = _source(CLIENT_F7)
    close_f7 = _function_body(client, "closeF7")
    render_snapshot = _function_body(client, "renderSnapshot")

    assert "cursorOwned = false" in client
    assert "cursorWasShowing = false" in client
    assert "if cursorOwned then" in close_f7
    assert "showCursor(cursorWasShowing)" in close_f7
    assert "cursorWasShowing = isCursorShowing()" in render_snapshot
    assert "cursorOwned = true" in render_snapshot
