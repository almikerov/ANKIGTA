"""Ticket 29 — migrating every shipped schema version, on real data.

Two rules this repository learned the hard way are pinned here.

**Migrate from what shipped, not from nothing.** A migration run against an
empty database exercises the `CREATE TABLE` and none of the `INSERT ... SELECT`,
so it cannot see a dropped column, a cascade that emptied a table or a CHECK
that rejects a row already stored. Every case below starts from a database in a
shape ANKIGTA really shipped, with maps, Map Entities, Spatial Links, metadata,
Change History and settings in it, and asserts the rows are still there
afterwards.

**Pin a migration to a floor, never to the current value.** `version == 3` stops
being true the moment a later step bumps the number, and the shape repair it
guarded silently stops running. Every step here declares the earliest version it
applies from, and the test that proves it is the one that hands it a *version 4*
database still carrying the version 3 shape.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import sqlite3

import pytest

from tests.lua import MtaSandbox
from tests.lua import shipped_schemas
from tests.lua.shipped_schemas import (
    MIGRATED_SCHEMA_FLOOR,
    SHIPPED_VERSIONS,
    rows,
)


def server(directory: Path) -> MtaSandbox:
    sandbox = MtaSandbox(database_path=str(directory / "ankigta.sqlite"))
    sandbox.load("shared/settings.lua")
    sandbox.load("server/backup.lua")
    sandbox.load("server/store.lua")
    return sandbox


def call(sandbox: MtaSandbox, expression: str, *args: Any) -> Any:
    return sandbox.eval(expression)(*args)


def opened(sandbox: MtaSandbox) -> Any:
    return call(sandbox, "function() return ANKIGTA.Store.open() end")


def status(sandbox: MtaSandbox) -> dict[str, Any]:
    return dict(
        sandbox.to_python(call(sandbox, "function() return ANKIGTA.Store.status() end"))
    )


@pytest.fixture
def workspace(tmp_path: Path) -> Iterator[Path]:
    yield tmp_path


def migrated(directory: Path, version: str, **kwargs: Any) -> MtaSandbox:
    shipped_schemas.build(directory / "ankigta.sqlite", version, **kwargs)
    sandbox = server(directory)
    assert opened(sandbox) is True, f"{version} did not migrate: {status(sandbox)}"
    return sandbox


# --- every shipped version reaches the current one ----------------------------


@pytest.mark.parametrize("version", SHIPPED_VERSIONS)
def test_every_shipped_version_migrates_to_the_current_schema(
    workspace: Path, version: str
) -> None:
    sandbox = migrated(workspace, version)
    try:
        assert status(sandbox)["schemaVersion"] >= MIGRATED_SCHEMA_FLOOR
    finally:
        sandbox.close()


@pytest.mark.parametrize("version", SHIPPED_VERSIONS)
def test_migration_keeps_every_map_entity_it_was_given(
    workspace: Path, version: str
) -> None:
    database = workspace / "ankigta.sqlite"
    shipped_schemas.build(database, version)
    before = {
        (row["map_id"], row["entity_id"]): row["entity_type"]
        for row in rows(database, "SELECT map_id, entity_id, entity_type FROM map_entities")
    }

    sandbox = server(workspace)
    try:
        assert opened(sandbox) is True

        after = {
            (row["map_id"], row["entity_id"]): row["entity_type"]
            for row in rows(
                database, "SELECT map_id, entity_id, entity_type FROM map_entities"
            )
        }
        # The tracer entity the store seeds is allowed to appear; nothing the
        # database already held is allowed to vanish.
        assert before.items() <= after.items()
    finally:
        sandbox.close()


@pytest.mark.parametrize("version", ["v3legacy", "v3", "v4"])
def test_migration_keeps_every_spatial_link_and_its_card_identity(
    workspace: Path, version: str
) -> None:
    database = workspace / "ankigta.sqlite"
    sandbox = migrated(workspace, version)
    try:
        preserved = rows(
            database,
            "SELECT map_id, entity_id, collection_uuid, card_id, state "
            "FROM spatial_links ORDER BY map_id",
        )

        assert [(row["map_id"], row["card_id"]) for row in preserved] == [
            ("second-map", 202),
            ("study-map", 101),
        ]
        assert {row["collection_uuid"] for row in preserved} == {shipped_schemas.UUID}
    finally:
        sandbox.close()


@pytest.mark.parametrize("version", ["v3", "v4"])
def test_migration_keeps_metadata_change_history_and_settings(
    workspace: Path, version: str
) -> None:
    """The tables ticket 11 owns survive a migration of the tables under them."""
    database = workspace / "ankigta.sqlite"
    sandbox = migrated(workspace, version)
    try:
        metadata = rows(
            database,
            "SELECT map_id, entity_id, name, radius, presence_state "
            "FROM map_entity_metadata ORDER BY map_id, entity_id",
        )
        assert [row["name"] for row in metadata] == ["Kerb", "Ворота склада", "Shed"]
        assert [row["presence_state"] for row in metadata] == [
            "identified",
            "identified",
            "entity_missing",
        ]

        # The per-map switch is gone, and so are the entries that replayed into
        # it. The cursor moves back to the newest surviving entry rather than
        # pointing at a deleted one, which Undo would never get past.
        assert [row["operation"] for row in rows(
            database, "SELECT operation FROM change_history ORDER BY history_id"
        )] == ["user_setting"]
        assert rows(database, "SELECT cursor_id FROM change_history_state") == [
            {"cursor_id": 1}
        ]
        assert rows(
            database,
            "SELECT name FROM sqlite_master WHERE name = 'map_preferences'",
        ) == []
        # A Spatial Link is not the map's preference: the map that had been
        # switched off keeps every one of them.
        assert [row["map_id"] for row in rows(
            database, "SELECT map_id FROM spatial_links ORDER BY map_id"
        )] == ["second-map", "study-map"]
        assert {
            row["setting_key"]
            for row in rows(database, "SELECT setting_key FROM user_settings")
        } == {"activationRadius", "maxActivationSpeedKmh", "reviewMode"}
    finally:
        sandbox.close()


@pytest.mark.parametrize("version", ["v3", "v4", "v5"])
def test_the_early_review_boolean_becomes_the_review_mode_it_meant(
    workspace: Path, version: str
) -> None:
    """A renamed setting is carried across, not quietly reset.

    `listUserSettings` drops a stored value the schema no longer accepts, so a
    rename with no migration behind it puts the user silently back on the
    default: someone who had early review on would find their session smaller
    after an update and nothing anywhere saying why.
    """
    database = workspace / "ankigta.sqlite"
    sandbox = migrated(workspace, version)
    try:
        assert rows(
            database,
            "SELECT setting_key, setting_value FROM user_settings "
            "WHERE setting_key IN ('allowEarlyReview', 'reviewMode')",
        ) == [{"setting_key": "reviewMode", "setting_value": '["allow_all"]'}]

        # And the value survives being read back through the schema, which is
        # the path that decides whether a session takes not-due cards.
        sandbox.execute("ANKIGTA.SettingsStore = nil")
        sandbox.load("server/settings_store.lua")
        sandbox.eval("function() return ANKIGTA.SettingsStore.load() end")()
        assert sandbox.eval(
            "function() return ANKIGTA.SettingsStore.get('reviewMode') end"
        )() == "allow_all"
    finally:
        sandbox.close()


def test_the_version_one_heading_becomes_the_rotation_it_meant(
    workspace: Path,
) -> None:
    """A migration that moves data has to be checked on the data it moved."""
    database = workspace / "ankigta.sqlite"
    sandbox = migrated(workspace, "v1")
    try:
        rotated = rows(
            database,
            "SELECT entity_id, rotation_x, rotation_y, rotation_z "
            "FROM map_entities WHERE map_id = 'study-map' ORDER BY entity_id",
        )

        assert rotated == [
            {"entity_id": "gate", "rotation_x": 0.0, "rotation_y": 0.0,
             "rotation_z": 135.0},
            {"entity_id": "shed", "rotation_x": 0.0, "rotation_y": 0.0,
             "rotation_z": 45.0},
        ]
    finally:
        sandbox.close()


@pytest.mark.parametrize("version", SHIPPED_VERSIONS)
def test_a_migrated_database_admits_the_states_and_types_it_now_has_to(
    workspace: Path, version: str
) -> None:
    """The point of the schema change, checked by writing what it enabled."""
    sandbox = migrated(workspace, version)
    try:
        stored = sandbox.to_python(
            call(
                sandbox,
                """
                function(uuid)
                    ANKIGTA.Store.activateSpatialLink({
                        mapId = "study-map",
                        entityId = "shed",
                        cardIdentity = {collectionUuid = uuid, cardId = 77},
                        mapLocator = {
                            resourceName = "ankigta", mapFile = "maps/study.map"
                        },
                        verifiedMapSha256 = string.rep("c", 64),
                    })
                    return ANKIGTA.Store.markCardMissing({
                        collectionUuid = uuid, cardId = 77
                    })
                end
                """,
                shipped_schemas.UUID,
            )
        )

        assert stored is not False
        assert rows(
            workspace / "ankigta.sqlite",
            "SELECT state FROM spatial_links WHERE entity_id = 'shed'",
        ) == [{"state": "card_missing"}]
    finally:
        sandbox.close()


@pytest.mark.parametrize("version", SHIPPED_VERSIONS)
def test_a_migrated_database_takes_a_vehicle_and_a_ped(
    workspace: Path, version: str
) -> None:
    sandbox = migrated(workspace, version)
    try:
        found = sandbox.to_python(
            call(sandbox, 'function() return ANKIGTA.Store.singleMapEntity("vehicle") end')
        )

        assert isinstance(found, dict)
        assert found["entity_type"] == "vehicle"
    finally:
        sandbox.close()


@pytest.mark.parametrize("version", SHIPPED_VERSIONS)
def test_migrating_is_idempotent_across_a_restart(
    workspace: Path, version: str
) -> None:
    """The second open must find nothing to do, and change nothing."""
    database = workspace / "ankigta.sqlite"
    sandbox = migrated(workspace, version)
    try:
        call(sandbox, "function() return ANKIGTA.Store.close() end")
        before = database.read_bytes()

        assert opened(sandbox) is True
        assert status(sandbox)["schemaVersion"] >= MIGRATED_SCHEMA_FLOOR
        call(sandbox, "function() return ANKIGTA.Store.close() end")

        assert database.read_bytes() == before
    finally:
        sandbox.close()


# --- the floor, not the current value ----------------------------------------


def test_a_shape_repair_is_pinned_to_a_floor_and_still_runs_above_it(
    workspace: Path,
) -> None:
    """`version == 3` would have skipped this database; `version >= 3` does not.

    Here is a database that says version 4 while `map_entities` still carries
    the object-only CHECK from version 3 — the exact state an interrupted or
    hand-edited upgrade leaves behind. A repair guarded on the current value
    reads 4, decides it has nothing to do, and the store comes up unable to
    store a vehicle. A repair guarded on a floor fixes it.
    """
    database = workspace / "ankigta.sqlite"
    shipped_schemas.build(database, "v3legacy", history=True)
    # Only the number moves: the shape stays as version 3 left it.
    connection = __import__("sqlite3").connect(database)
    try:
        connection.execute("UPDATE schema_meta SET version = 4 WHERE singleton = 1")
        connection.commit()
    finally:
        connection.close()
    definition = rows(
        database,
        "SELECT sql FROM sqlite_master WHERE name = 'map_entities'",
    )[0]["sql"]
    assert "entity_type = 'object'" in str(definition)

    sandbox = server(workspace)
    try:
        assert opened(sandbox) is True

        repaired = rows(
            database, "SELECT sql FROM sqlite_master WHERE name = 'map_entities'"
        )[0]["sql"]
        assert "entity_type = 'object'" not in str(repaired)
        assert "'vehicle'" in str(repaired)
    finally:
        sandbox.close()


def test_the_shape_repair_does_not_cascade_away_the_rows_hanging_off_it(
    workspace: Path,
) -> None:
    """Rebuilding `map_entities` must not take its dependants with it.

    `map_entity_metadata` and `spatial_links` both cascade on delete from
    `map_entities`. Rebuilding it by renaming, copying and dropping — the
    obvious way — makes the dependants follow the renamed table and then
    silently empties them when it is dropped.
    """
    database = workspace / "ankigta.sqlite"
    shipped_schemas.build(database, "v3legacy", history=True)

    sandbox = server(workspace)
    try:
        assert opened(sandbox) is True

        assert len(rows(database, "SELECT map_id FROM map_entity_metadata")) == 3
        assert len(rows(database, "SELECT map_id FROM spatial_links")) == 2
        assert len(rows(database, "SELECT map_id FROM identity_collisions")) == 1
        assert rows(database, "PRAGMA foreign_key_check") == []
    finally:
        sandbox.close()


def test_a_version_below_the_lowest_shipped_one_is_refused_not_guessed(
    workspace: Path,
) -> None:
    """An unknown schema is a state to report, never one to improvise on."""
    database = workspace / "ankigta.sqlite"
    shipped_schemas.build(database, "v5")
    connection = __import__("sqlite3").connect(database)
    try:
        connection.execute("UPDATE schema_meta SET version = 99 WHERE singleton = 1")
        connection.commit()
    finally:
        connection.close()
    before = database.read_bytes()

    sandbox = server(workspace)
    try:
        assert opened(sandbox) is False

        assert status(sandbox)["errorCategory"] == "unsupported_schema_version"
        assert database.read_bytes() == before
    finally:
        sandbox.close()


# --- a migration is preceded by a verified backup -----------------------------


@pytest.mark.parametrize("version", ["v1", "v2", "v3legacy", "v3"])
def test_a_migration_is_preceded_by_a_verified_pre_migration_backup(
    workspace: Path, version: str
) -> None:
    sandbox = migrated(workspace, version)
    try:
        listed = sandbox.to_python(
            call(sandbox, "function() return ANKIGTA.Backup.list() end")
        )

        premigration = [entry for entry in listed if entry["kind"] == "premigration"]
        assert len(premigration) == 1
        assert premigration[0]["verified"] is True
        # The copy is of the database as it was *before* the migration ran.
        assert premigration[0]["schemaVersion"] == {
            "v1": 1, "v2": 2, "v3legacy": 3, "v3": 3
        }[version]
    finally:
        sandbox.close()


def test_a_database_with_nothing_left_to_do_takes_no_pre_migration_backup(
    workspace: Path,
) -> None:
    """A copy per start would rotate the useful ones out within a day.

    "Nothing left to do" is asked of the *shape*, not of the version number:
    some steps here are shape repairs that bump nothing, so a database can sit
    at the current version and still be owed one. That is why this opens twice
    and looks at the second open -- the first is entitled to whatever it finds.
    """
    first = migrated(workspace, SHIPPED_VERSIONS[-1])
    first.close()

    sandbox = server(workspace)
    try:
        assert opened(sandbox) is True
        before = sandbox.to_python(
            call(sandbox, "function() return ANKIGTA.Backup.list() end")
        )
        taken = [entry for entry in before if entry["kind"] == "premigration"]
    finally:
        sandbox.close()

    again = server(workspace)
    try:
        assert opened(again) is True
        after = sandbox.to_python(
            call(again, "function() return ANKIGTA.Backup.list() end")
        )
        assert [
            entry for entry in after if entry["kind"] == "premigration"
        ] == taken
    finally:
        again.close()


# --- a radius of an entity's own, and the absence of one ----------------------


def test_a_database_written_before_keeps_every_radius_it_held(
    workspace: Path,
) -> None:
    """`radius` was NOT NULL, so it could not say "this entity follows the
    global" -- and naming an entity wrote a copy of the shipped default onto it.

    The column beside it can say that, and every number already on disk becomes
    an override of itself on the way there. A stored 3 might be a number
    somebody chose or the copy the old write path made, and nothing on disk can
    tell them apart, so the reading that changes nothing is the one to take.
    """
    database = workspace / "ankigta.sqlite"
    shipped_schemas.build(database, "v6", history=True)
    before = {
        (row["map_id"], row["entity_id"]): row["radius"]
        for row in rows(database, "SELECT map_id, entity_id, radius FROM map_entity_metadata")
    }
    assert before, "the fixture holds no metadata to keep"

    sandbox = server(workspace)
    try:
        assert opened(sandbox) is True

        after = {
            (row["map_id"], row["entity_id"]): row["radius_override"]
            for row in rows(
                database,
                "SELECT map_id, entity_id, radius_override FROM map_entity_metadata",
            )
        }
        assert after == before
    finally:
        sandbox.close()


def test_opening_a_database_twice_does_not_backfill_a_cleared_radius(
    workspace: Path,
) -> None:
    """The backfill runs when the column is added and never again.

    Running it on every open would undo the one thing the column exists for:
    an entity put back on the global would be pinned to whatever the inert
    column still held, the next time the server started.
    """
    database = workspace / "ankigta.sqlite"
    shipped_schemas.build(database, "v6", history=True)
    first = server(workspace)
    try:
        assert opened(first) is True
    finally:
        first.close()

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE map_entity_metadata SET radius_override = NULL"
            " WHERE entity_id = 'gate'"
        )

    second = server(workspace)
    try:
        assert opened(second) is True

        cleared = rows(
            database,
            "SELECT radius, radius_override FROM map_entity_metadata"
            " WHERE entity_id = 'gate'",
        )
        assert cleared[0]["radius_override"] is None
        # And the inert column is left exactly as it was found.
        assert cleared[0]["radius"] == 7.5
    finally:
        second.close()


def test_adding_the_radius_column_takes_a_verified_copy_first(
    workspace: Path,
) -> None:
    """`docs/operations/backups-and-recovery.md`: a copy before every schema
    migration, because a failure part-way has nothing else to fall back on.

    This one rewrites rows as well as adding a column, so it is a migration
    rather than one of the shape fixups `ensureChangeHistorySchema` does on
    every open -- those run outside the gate that takes the copy.
    """
    database = workspace / "ankigta.sqlite"
    shipped_schemas.build(database, "v6", history=True)

    sandbox = server(workspace)
    try:
        assert opened(sandbox) is True

        listed = sandbox.to_python(
            call(sandbox, "function() return ANKIGTA.Backup.list() end")
        )
        premigration = [
            entry for entry in listed if entry["kind"] == "premigration"
        ]
        assert len(premigration) == 1
        assert premigration[0]["verified"] is True
    finally:
        sandbox.close()

    # And the copy is of the database as it was *before*: no column on it.
    copied = workspace / premigration[0]["path"]
    columns = {
        row[1]
        for row in sqlite3.connect(copied)
        .execute("PRAGMA table_info(map_entity_metadata)")
        .fetchall()
    }
    assert "radius_override" not in columns
    assert "radius" in columns
