"""Behavioral tests for `server/store.lua`, executed in a real Lua 5.1 VM.

These complement the source-contract tests: instead of asserting that the file
contains certain text, they open the store against real SQLite, mutate it, and
assert on the resulting rows and return values.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import pytest

from tests.lua import MtaSandbox


@pytest.fixture
def store(tmp_path: Path) -> Iterator[tuple[MtaSandbox, Any]]:
    sandbox = MtaSandbox(database_path=str(tmp_path / "ankigta.sqlite"))
    # meta.xml loads the shared schema before the store, and the store now
    # validates against it, so the harness loads them in the same order.
    sandbox.load("shared/settings.lua")
    # The store asks the backup module for a verified copy before it
    # migrates, so it is loaded here in the order meta.xml declares.
    sandbox.load("server/backup.lua")
    sandbox.load("server/store.lua")
    handle = sandbox.eval("ANKIGTA.Store")
    try:
        yield sandbox, handle
    finally:
        sandbox.close()


def call(sandbox: MtaSandbox, expression: str, *args: Any) -> Any:
    return sandbox.eval(expression)(*args)


def rows(sandbox: MtaSandbox, sql: str) -> list[dict[str, Any]]:
    """Read straight from SQLite, bypassing the Lua layer under test."""
    cursor = sandbox.connection.raw.execute(sql)
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, record)) for record in cursor.fetchall()]


def test_open_creates_the_current_schema_and_seeds_tracer_entities(
    store: tuple[MtaSandbox, Any],
) -> None:
    sandbox, handle = store

    assert call(sandbox, "function() return ANKIGTA.Store.open() end") is True
    assert handle.ready is True
    assert handle.schemaVersion == 4

    # Opening seeds only the object tracer; the vehicle and ped tracers are
    # seeded lazily by the first runtime lookup for those types.
    seeded = rows(sandbox, "SELECT map_id, entity_id, entity_type FROM map_entities")
    assert [row["entity_id"] for row in seeded] == ["ticket05-entity"]
    assert seeded[0]["entity_type"] == "object"

    expected = {"map_id", "entity_id", "entity_type", "model", "interior", "dimension"}
    columns = {
        row["name"] for row in rows(sandbox, "PRAGMA table_info(map_entities)")
    }
    assert expected <= columns


def test_reopening_an_existing_database_preserves_rows(
    store: tuple[MtaSandbox, Any],
) -> None:
    sandbox, handle = store
    call(sandbox, "function() return ANKIGTA.Store.open() end")
    before = rows(sandbox, "SELECT map_id, entity_id FROM map_entities")

    call(sandbox, "function() return ANKIGTA.Store.close() end")
    assert call(sandbox, "function() return ANKIGTA.Store.open() end") is True

    assert rows(sandbox, "SELECT map_id, entity_id FROM map_entities") == before
    assert handle.ready is True


def test_user_setting_round_trips_and_records_one_history_entry(
    store: tuple[MtaSandbox, Any],
) -> None:
    sandbox, _ = store
    call(sandbox, "function() return ANKIGTA.Store.open() end")

    ok = call(
        sandbox,
        'function() return ANKIGTA.Store.setUserSetting("activationRadius", 7) end',
    )
    assert ok is not False

    stored = rows(sandbox, "SELECT setting_key, setting_value FROM user_settings")
    assert [row["setting_key"] for row in stored] == ["activationRadius"]

    history = rows(sandbox, "SELECT operation FROM change_history")
    assert len(history) == 1


def test_change_history_keeps_only_the_most_recent_hundred_entries(
    store: tuple[MtaSandbox, Any],
) -> None:
    sandbox, _ = store
    call(sandbox, "function() return ANKIGTA.Store.open() end")

    sandbox.execute(
        """
        for index = 1, 130 do
            ANKIGTA.Store.setUserSetting("maxActivationSpeedKmh", index)
        end
        """
    )

    history = rows(
        sandbox,
        "SELECT history_id FROM change_history ORDER BY history_id",
    )
    assert len(history) == 100

    # The bound must evict the oldest, not refuse the newest.
    assert history[-1]["history_id"] > history[0]["history_id"]
    setting = rows(
        sandbox,
        "SELECT setting_value FROM user_settings "
        "WHERE setting_key = 'maxActivationSpeedKmh'",
    )
    assert "130" in str(setting[0]["setting_value"])


def test_undo_restores_the_previous_value_and_redo_reapplies_it(
    store: tuple[MtaSandbox, Any],
) -> None:
    sandbox, _ = store
    call(sandbox, "function() return ANKIGTA.Store.open() end")

    sandbox.execute('ANKIGTA.Store.setUserSetting("activationRadius", 3)')
    sandbox.execute('ANKIGTA.Store.setUserSetting("activationRadius", 9)')

    def current() -> str:
        found = rows(
            sandbox,
            "SELECT setting_value FROM user_settings "
            "WHERE setting_key = 'activationRadius'",
        )
        return str(found[0]["setting_value"])

    assert "9" in current()

    call(sandbox, "function() return ANKIGTA.Store.undo() end")
    assert "3" in current()

    call(sandbox, "function() return ANKIGTA.Store.redo() end")
    assert "9" in current()


def test_a_new_change_after_undo_truncates_the_redo_branch(
    store: tuple[MtaSandbox, Any],
) -> None:
    sandbox, _ = store
    call(sandbox, "function() return ANKIGTA.Store.open() end")

    sandbox.execute('ANKIGTA.Store.setUserSetting("activationRadius", 1)')
    sandbox.execute('ANKIGTA.Store.setUserSetting("activationRadius", 2)')
    call(sandbox, "function() return ANKIGTA.Store.undo() end")

    sandbox.execute('ANKIGTA.Store.setUserSetting("activationRadius", 3)')

    redone, reason = call(sandbox, "function() return ANKIGTA.Store.redo() end")
    assert redone is False
    assert reason == "nothing_to_redo"

    # Being unreachable is not enough: an orphaned future entry left in the
    # table would still consume the 100-entry budget and could resurface.
    assert len(rows(sandbox, "SELECT history_id FROM change_history")) == 2

    found = rows(
        sandbox,
        "SELECT setting_value FROM user_settings "
        "WHERE setting_key = 'activationRadius'",
    )
    assert "3" in str(found[0]["setting_value"])


def test_card_state_refresh_never_rebinds_a_different_card(
    store: tuple[MtaSandbox, Any],
) -> None:
    sandbox, _ = store
    call(sandbox, "function() return ANKIGTA.Store.open() end")

    sandbox.execute(
        """
        ANKIGTA.Store.linkCardToEntity({
            mapId = "ticket05-map",
            entityId = "ticket05-entity",
            cardIdentity = {collectionUuid = "collection-a", cardId = 111},
            mapLocator = {
                resourceName = "ankigta",
                mapFile = "Ticket 05 tracer map",
            },
            verifiedMapSha256 = string.rep("A", 64),
        })
        """
    )
    linked = rows(sandbox, "SELECT collection_uuid, card_id, state FROM spatial_links")
    assert len(linked) == 1, "the link must exist before the refresh is meaningful"

    # A different card id in the same collection must not touch this link.
    sandbox.execute(
        """
        ANKIGTA.Store.refreshSpatialLinkCardState(
            {collectionUuid = "collection-a", cardId = 222},
            false
        )
        """
    )
    assert rows(sandbox, "SELECT state FROM spatial_links")[0]["state"] == "active"

    # The exact identity does mark it missing.
    sandbox.execute(
        """
        ANKIGTA.Store.refreshSpatialLinkCardState(
            {collectionUuid = "collection-a", cardId = 111},
            false
        )
        """
    )
    assert rows(sandbox, "SELECT state FROM spatial_links")[0]["state"] == "card_missing"


def test_the_same_card_id_in_another_collection_is_a_different_card(
    store: tuple[MtaSandbox, Any],
) -> None:
    sandbox, _ = store
    call(sandbox, "function() return ANKIGTA.Store.open() end")

    sandbox.execute(
        """
        ANKIGTA.Store.linkCardToEntity({
            mapId = "ticket05-map",
            entityId = "ticket05-entity",
            cardIdentity = {collectionUuid = "collection-a", cardId = 111},
            mapLocator = {
                resourceName = "ankigta",
                mapFile = "Ticket 05 tracer map",
            },
            verifiedMapSha256 = string.rep("A", 64),
        })
        """
    )

    sandbox.execute(
        """
        ANKIGTA.Store.refreshSpatialLinkCardState(
            {collectionUuid = "collection-b", cardId = 111},
            false
        )
        """
    )

    assert rows(sandbox, "SELECT state FROM spatial_links")[0]["state"] == "active"


def test_operations_are_rejected_before_the_store_is_open(
    store: tuple[MtaSandbox, Any],
) -> None:
    sandbox, handle = store

    assert handle.ready is False
    ok, category = call(
        sandbox,
        'function() return ANKIGTA.Store.setUserSetting("activationRadius", 1) end',
    )
    assert ok is False
    assert category == "storage_unavailable"
