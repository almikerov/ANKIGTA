"""Ticket 27 — the settings stores.

Every setting is read, written, persisted and recovered through the shared
schema. The schema was already correct before this ticket; what it lacked was
anyone calling it. These tests exist to pin the call sites, so a later change
that quietly reintroduces a hand-rolled range check fails here.

The schema is mutated in several tests rather than merely read: asserting that
a module agrees with a schema it reads from is tautological, so the schema is
changed and the module has to follow.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator
from xml.etree import ElementTree

import pytest

from ankigta_companion.connection import CompanionConnectionManager
from ankigta_companion.contract import (
    CollectionObservation,
    CollectionState,
    RuntimeObservation,
)
from tests.lua import MtaSandbox


AUTOMATIC_TOKEN = "ticket27-automatic-token"


@pytest.fixture
def connection() -> Iterator[MtaSandbox]:
    sandbox = MtaSandbox()
    sandbox.load("shared/settings.lua")
    sandbox.load("server/connection_config.lua")
    try:
        yield sandbox
    finally:
        sandbox.close()


def publish(
    sandbox: MtaSandbox,
    *,
    port: int = 32145,
    token: str = AUTOMATIC_TOKEN,
    revision: int = 1,
    companion: dict[str, Any] | None = None,
) -> None:
    """Write the connection file exactly as the companion add-on publishes it.

    The shape is taken from `ConnectionConfigPublisher.publish`, not from
    memory: a double that drifts from its producer has already shipped two bugs
    in this repository.
    """
    sandbox.write_file(
        "connection.json",
        json.dumps(
            {
                "format": "ankigta-connection",
                "formatVersion": 1,
                "protocol": "ankigta-control",
                "protocolVersion": 1,
                "revision": revision,
                "host": "127.0.0.1",
                "automatic": {"port": port, "token": token},
                "companion": companion or {"mode": "automatic"},
            }
        ),
    )


def set_manual(sandbox: MtaSandbox, port: Any, token: str) -> Any:
    return sandbox.eval(
        "function(p, t) return ANKIGTA.ConnectionConfig.setManual(p, t) end"
    )(port, token)


def load_effective(sandbox: MtaSandbox) -> tuple[Any, ...]:
    """`loadEffective` returns config, category, details -- keep all of them."""
    result = sandbox.eval(
        "function() return ANKIGTA.ConnectionConfig.loadEffective() end"
    )()
    return result if isinstance(result, tuple) else (result,)


def effective(sandbox: MtaSandbox) -> Any:
    config = load_effective(sandbox)[0]
    assert config is not False, "expected a usable effective connection config"
    return config


def refused(sandbox: MtaSandbox) -> tuple[Any, ...]:
    result = load_effective(sandbox)
    assert result[0] is False, f"expected a refusal, got {result[0]}"
    return result[1:]


def manual_file(sandbox: MtaSandbox) -> dict[str, Any]:
    decoded: dict[str, Any] = json.loads(sandbox.read_file("connection-manual.json"))
    return decoded


# --- the connection override, through the schema -----------------------------


def test_the_manual_port_range_is_the_schema_s_range(connection: MtaSandbox) -> None:
    """Narrow the schema and the writer has to narrow with it."""
    publish(connection)
    connection.eval(
        "function() ANKIGTA.Settings.schema.connectionPort.rule.maximum = 40000 end"
    )()

    rejected, reason, field = set_manual(connection, 50000, "manual-token")

    assert rejected is False
    assert reason == "settings.error.out_of_range"
    assert field == "connectionPort"
    assert set_manual(connection, 39000, "manual-token") is True


@pytest.mark.parametrize(
    ("port", "reason"),
    [
        (0, "settings.error.out_of_range"),
        (65536, "settings.error.out_of_range"),
        (8080.5, "settings.error.not_on_step"),
        ("http", "settings.error.not_a_number"),
    ],
)
def test_an_invalid_manual_port_is_rejected_with_a_localizable_reason(
    connection: MtaSandbox,
    port: Any,
    reason: str,
) -> None:
    publish(connection)

    rejected, why, field = set_manual(connection, port, "manual-token")

    assert rejected is False
    assert why == reason
    assert field == "connectionPort"
    assert "connection-manual.json" not in connection.files


def test_a_manual_override_records_the_side_that_made_it(
    connection: MtaSandbox,
) -> None:
    publish(connection)

    assert set_manual(connection, 40001, "manual-token") is True

    assert manual_file(connection)["overrideSide"] == "server"


def test_an_override_made_on_another_side_does_not_govern_this_one(
    connection: MtaSandbox,
) -> None:
    """ADR 0014: an override is local to the side that made it.

    A client-side override reaching the server's file is not a value the server
    adopts, and not a conflict it resolves by picking a winner.
    """
    publish(connection)
    connection.write_file(
        "connection-manual.json",
        json.dumps(
            {
                "format": "ankigta-mta-connection-settings",
                "formatVersion": 1,
                "mode": "manual",
                "port": 40002,
                "token": "someone-elses-token",
                "overrideSide": "client",
            }
        ),
    )

    assert refused(connection)[0] == "foreign_manual_connection_override"


def test_an_unstamped_manual_override_is_not_silently_adopted(
    connection: MtaSandbox,
) -> None:
    publish(connection)
    connection.write_file(
        "connection-manual.json",
        json.dumps(
            {
                "format": "ankigta-mta-connection-settings",
                "formatVersion": 1,
                "mode": "manual",
                "port": 40003,
                "token": "unstamped-token",
            }
        ),
    )

    assert refused(connection)[0] == "foreign_manual_connection_override"


def test_a_matching_manual_override_governs_the_local_side(
    connection: MtaSandbox,
) -> None:
    digest = connection.eval('function(t) return hash("sha256", t) end')(
        "agreed-token"
    )
    publish(
        connection,
        companion={
            "mode": "manual",
            "port": 40004,
            "tokenDigest": digest,
        },
    )

    assert set_manual(connection, 40004, "agreed-token") is True
    config = effective(connection)

    assert config["port"] == 40004
    assert config["localMode"] == "manual"
    assert config["companionMode"] == "manual"


def test_a_disagreeing_override_is_an_error_not_a_winner(
    connection: MtaSandbox,
) -> None:
    publish(connection, port=32145)

    assert set_manual(connection, 40005, AUTOMATIC_TOKEN) is True
    reason, details = refused(connection)

    assert reason == "effective_config_mismatch"
    assert details["localPort"] == 40005
    assert details["companionPort"] == 32145


def test_going_back_to_automatic_drops_the_local_override(
    connection: MtaSandbox,
) -> None:
    publish(connection, port=32145)
    set_manual(connection, 40006, "manual-token")

    assert connection.eval(
        "function() return ANKIGTA.ConnectionConfig.useAutomatic() end"
    )() is True
    config = effective(connection)

    assert config["port"] == 32145
    assert config["localMode"] == "automatic"


def test_a_manual_override_survives_a_restart(connection: MtaSandbox) -> None:
    """The remaining two settings persist in the connection file, so a restart
    recovers them by reading it back."""
    digest = connection.eval('function(t) return hash("sha256", t) end')(
        "agreed-token"
    )
    publish(
        connection,
        companion={"mode": "manual", "port": 40010, "tokenDigest": digest},
    )
    assert set_manual(connection, 40010, "agreed-token") is True

    restarted = MtaSandbox()
    restarted.files.update(connection.files)
    restarted.load("shared/settings.lua")
    restarted.load("server/connection_config.lua")
    try:
        config = effective(restarted)
        assert config["port"] == 40010
        assert config["localMode"] == "manual"
        assert config["tokenConfigured"] is True
    finally:
        restarted.close()


def test_a_published_port_outside_the_schema_range_is_not_loaded(
    connection: MtaSandbox,
) -> None:
    publish(connection, port=70000)

    assert refused(connection)[0] == "connection_config_invalid"


def test_the_published_port_is_checked_against_the_schema_s_range(
    connection: MtaSandbox,
) -> None:
    """The reader has no range of its own either."""
    publish(connection, port=32145)
    assert effective(connection)["port"] == 32145

    connection.eval(
        "function() ANKIGTA.Settings.schema.connectionPort.rule.maximum = 10000 end"
    )()

    assert refused(connection)[0] == "connection_config_invalid"


# --- persistence: the server's own settings ----------------------------------


@pytest.fixture
def store(tmp_path: Any) -> Iterator[MtaSandbox]:
    sandbox = MtaSandbox(database_path=str(tmp_path / "ankigta.sqlite"))
    # The resource loads the schema before the store; so does the harness.
    sandbox.load("shared/settings.lua")
    sandbox.load("server/backup.lua")
    sandbox.load("server/store.lua")
    sandbox.eval("function() return ANKIGTA.Store.open() end")()
    try:
        yield sandbox
    finally:
        sandbox.close()


def set_setting(sandbox: MtaSandbox, key: str, value: Any) -> Any:
    return sandbox.eval(
        "function(k, v) return ANKIGTA.Store.setUserSetting(k, v) end"
    )(key, value)


def sqlite_rows(sandbox: MtaSandbox, sql: str) -> list[dict[str, Any]]:
    cursor = sandbox.connection.raw.execute(sql)
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, record)) for record in cursor.fetchall()]


def stored_settings(sandbox: MtaSandbox) -> dict[str, str]:
    return {
        str(row["setting_key"]): str(row["setting_value"])
        for row in sqlite_rows(
            sandbox, "SELECT setting_key, setting_value FROM user_settings"
        )
    }


def history_count(sandbox: MtaSandbox) -> int:
    return len(sqlite_rows(sandbox, "SELECT history_id FROM change_history"))


@pytest.mark.parametrize(
    ("key", "value", "reason"),
    [
        ("somethingInvented", 1, "settings.error.unknown"),
        ("indicatorMode", "minimap_only", "wrong_authority"),
        ("activationRadius", 200, "settings.error.out_of_range"),
        ("activationRadius", 1.3, "settings.error.not_on_step"),
        ("reviewMode", "allow_early", "settings.error.not_a_choice"),
    ],
)
def test_the_database_refuses_what_the_schema_refuses(
    store: MtaSandbox,
    key: str,
    value: Any,
    reason: str,
) -> None:
    """Checking that the key is a string was never a check on the setting."""
    rejected, why = set_setting(store, key, value)

    assert rejected is False
    assert why == reason
    assert stored_settings(store) == {}
    assert history_count(store) == 0


def test_connection_overrides_are_not_kept_in_the_database(
    store: MtaSandbox,
) -> None:
    """They live in the connection file, and they are not shared state."""
    rejected, why = set_setting(store, "connectionPort", 40007)

    assert rejected is False
    assert why == "not_a_stored_setting"
    assert stored_settings(store) == {}


def test_a_valid_setting_is_stored_and_recorded_once(store: MtaSandbox) -> None:
    assert set_setting(store, "activationRadius", 7) is True

    assert stored_settings(store).keys() == {"activationRadius"}
    assert history_count(store) == 1


def test_a_setting_excluded_from_history_is_stored_without_an_entry(
    store: MtaSandbox,
) -> None:
    """Mutate the schema, and persistence has to follow it."""
    store.eval(
        "function() ANKIGTA.Settings.schema.activationRadius.excludedFromHistory"
        " = true end"
    )()

    assert set_setting(store, "activationRadius", 7) is True

    assert stored_settings(store).keys() == {"activationRadius"}
    assert history_count(store) == 0


def test_a_number_typed_as_text_is_stored_as_a_number(store: MtaSandbox) -> None:
    assert set_setting(store, "activationRadius", "7") is True

    assert store.eval(
        'function() return ANKIGTA.Store.listUserSettings().activationRadius end'
    )() == 7


def test_a_value_persisted_as_text_is_read_back_as_a_number(
    store: MtaSandbox,
) -> None:
    """An older version stored what it was handed; the reader still has to give
    back the type the schema describes."""
    store.connection.raw.execute(
        "INSERT INTO user_settings (setting_key, setting_value) VALUES (?, ?)",
        ("activationRadius", '"7"'),
    )

    assert store.eval(
        "function() return ANKIGTA.Store.listUserSettings().activationRadius end"
    )() == 7


def test_stored_settings_are_read_back_as_the_schema_s_types(
    store: MtaSandbox,
) -> None:
    set_setting(store, "activationRadius", 7.5)
    set_setting(store, "reviewMode", "allow_all")

    persisted = store.eval("function() return ANKIGTA.Store.listUserSettings() end")()

    assert persisted["activationRadius"] == 7.5
    assert persisted["reviewMode"] == "allow_all"


# --- the server settings store -----------------------------------------------


def open_server(database_path: str) -> MtaSandbox:
    """Start the server side the way meta.xml does, and open the database."""
    sandbox = MtaSandbox(database_path=database_path)
    sandbox.load("shared/settings.lua")
    sandbox.load("server/connection_config.lua")
    sandbox.load("server/backup.lua")
    sandbox.load("server/store.lua")
    sandbox.load("server/settings_store.lua")
    sandbox.eval("function() return ANKIGTA.Store.open() end")()
    sandbox.eval("function() return ANKIGTA.SettingsStore.load() end")()
    return sandbox


@pytest.fixture
def server(tmp_path: Any) -> Iterator[MtaSandbox]:
    sandbox = open_server(str(tmp_path / "ankigta.sqlite"))
    try:
        yield sandbox
    finally:
        sandbox.close()


def get(sandbox: MtaSandbox, key: str) -> Any:
    return sandbox.eval(
        "function(k) return ANKIGTA.SettingsStore.get(k) end"
    )(key)


def put(sandbox: MtaSandbox, key: str, value: Any) -> Any:
    return sandbox.eval(
        "function(k, v) return ANKIGTA.SettingsStore.set(k, v) end"
    )(key, value)


def test_an_unset_setting_reads_as_its_schema_default(server: MtaSandbox) -> None:
    server.eval(
        "function() ANKIGTA.Settings.schema.activationRadius.default = 4.5 end"
    )()
    server.eval("function() return ANKIGTA.SettingsStore.load() end")()

    assert get(server, "activationRadius") == 4.5


def test_a_written_setting_reads_back_and_is_persisted(server: MtaSandbox) -> None:
    assert put(server, "activationRadius", 7) is True

    assert get(server, "activationRadius") == 7
    assert stored_settings(server).keys() == {"activationRadius"}


def test_the_store_refuses_what_the_schema_refuses(server: MtaSandbox) -> None:
    rejected, reason = put(server, "activationRadius", 200)

    assert rejected is False
    assert reason == "settings.error.out_of_range"
    # Not clamped to 50 either: the value the user never chose stays unchosen.
    assert get(server, "activationRadius") == 3


def test_the_server_may_not_write_a_setting_the_client_owns(
    server: MtaSandbox,
) -> None:
    rejected, reason = put(server, "indicatorMode", "minimap_only")

    assert rejected is False
    assert reason == "wrong_authority"
    assert stored_settings(server) == {}


def test_the_server_does_not_answer_for_a_setting_it_does_not_own(
    server: MtaSandbox,
) -> None:
    """Handing back a default for a value that lives on another machine would
    read like an answer."""
    unavailable, reason = get(server, "indicatorMode")

    assert unavailable is False
    assert reason == "wrong_authority"


def keys_owned_by(sandbox: MtaSandbox, side: str) -> set[str]:
    """Every setting the schema says this side owns outright."""
    schema = sandbox.eval("ANKIGTA.Settings.schema")
    owned = set()
    for key in schema.keys():
        kind = sandbox.eval(
            "function(s, k) return ANKIGTA.Settings.writeKind(s, k) end"
        )(side, key)
        if kind == "authority":
            owned.add(str(key))
    return owned


SERVER_VALUES = {
    "activationRadius": 7.5,
    "activationDelaySeconds": 2.5,
    "maxActivationSpeedKmh": 45,
    "reviewMode": "allow_all",
}


def test_every_setting_the_server_owns_survives_a_restart(tmp_path: Any) -> None:
    database = str(tmp_path / "ankigta.sqlite")
    first = open_server(database)
    # Derived from the schema, so a new server-owned setting cannot be added
    # without either covering it here or failing this test.
    assert keys_owned_by(first, "server") == set(SERVER_VALUES)
    for key, value in SERVER_VALUES.items():
        assert put(first, key, value) is True, key
    first.close()
    written = SERVER_VALUES

    second = open_server(database)
    try:
        for key, value in written.items():
            assert get(second, key) == value, key
    finally:
        second.close()


def test_a_stored_value_the_schema_no_longer_accepts_falls_back_to_default(
    tmp_path: Any,
) -> None:
    database = str(tmp_path / "ankigta.sqlite")
    first = open_server(database)
    put(first, "activationRadius", 40)
    first.close()

    second = MtaSandbox(database_path=database)
    second.load("shared/settings.lua")
    second.load("server/connection_config.lua")
    second.load("server/backup.lua")
    second.load("server/store.lua")
    second.load("server/settings_store.lua")
    try:
        # A later version narrows the range; the stored 40 is no longer a value
        # the user could choose, so it must not come back to life.
        second.eval(
            "function() ANKIGTA.Settings.schema.activationRadius.rule.maximum = 10 end"
        )()
        second.eval("function() return ANKIGTA.Store.open() end")()
        second.eval("function() return ANKIGTA.SettingsStore.load() end")()

        assert get(second, "activationRadius") == 3
        assert any(
            "discarded_stored_setting" in line
            for line in second.recorder.debug_messages()
        )
    finally:
        second.close()


def test_the_connection_port_is_read_and_written_through_the_connection_file(
    server: MtaSandbox,
) -> None:
    """It is an override, so it never lands in the shared database."""
    publish(server, port=32145)

    assert get(server, "connectionPort") == 32145
    assert put(server, "connectionPort", 40008) is True

    assert manual_file(server)["overrideSide"] == "server"
    assert manual_file(server)["port"] == 40008
    assert stored_settings(server) == {}


def test_an_invalid_connection_port_is_refused_by_the_same_rule(
    server: MtaSandbox,
) -> None:
    publish(server, port=32145)

    rejected, reason = put(server, "connectionPort", 70000)

    assert rejected is False
    assert reason == "settings.error.out_of_range"
    assert "connection-manual.json" not in server.files


def test_the_token_is_writable_but_never_readable(server: MtaSandbox) -> None:
    publish(server, port=32145)

    assert put(server, "connectionToken", "replacement-token") is True
    unavailable, reason = get(server, "connectionToken")

    assert unavailable is False
    assert reason == "settings.error.secret_not_readable"
    # It was still written where the transport reads it from.
    assert manual_file(server)["token"] == "replacement-token"


def test_a_snapshot_carries_every_answerable_setting_and_no_secret(
    server: MtaSandbox,
) -> None:
    publish(server, port=32145)

    snapshot = server.eval("function() return ANKIGTA.SettingsStore.all() end")()
    keys = set(snapshot.keys())

    assert {
        "activationRadius",
        "activationDelaySeconds",
        "maxActivationSpeedKmh",
        "reviewMode",
        "connectionPort",
    } == keys
    assert "connectionToken" not in keys


def manifest_scripts(*kinds: str) -> list[str]:
    """The scripts meta.xml declares, in declared order.

    Reading the manifest rather than repeating it means a script that never got
    registered fails here instead of quietly working in tests only.
    """
    manifest = ElementTree.parse(
        Path(__file__).resolve().parents[1] / "mta" / "ankigta" / "meta.xml"
    )
    return [
        str(element.get("src"))
        for element in manifest.iter("script")
        if element.get("type") in kinds
    ]


def start_resource(database_path: str) -> MtaSandbox:
    """Load the whole server side and fire `onResourceStart`, as MTA does."""
    sandbox = MtaSandbox(database_path=database_path)
    for script in manifest_scripts("shared", "server"):
        sandbox.load(script)
    sandbox.trigger("onResourceStart")
    return sandbox


# --- the client settings store -----------------------------------------------


def load_client(files: dict[str, bytes] | None = None) -> MtaSandbox:
    """Load the client side as meta.xml declares it, without starting it."""
    sandbox = MtaSandbox()
    if files is not None:
        sandbox.files.update(files)
    for script in manifest_scripts("shared", "client"):
        sandbox.load(script)
    return sandbox


def open_client(files: dict[str, bytes] | None = None) -> MtaSandbox:
    """Start the client side on top of an existing client-side disk.

    Started through `onClientResourceStart`, so restart recovery is exercised
    on the path MTA actually takes rather than by a test calling `load`.
    """
    sandbox = load_client(files)
    sandbox.trigger("onClientResourceStart")
    return sandbox


@pytest.fixture
def player() -> Iterator[MtaSandbox]:
    sandbox = open_client()
    try:
        yield sandbox
    finally:
        sandbox.close()


def client_get(sandbox: MtaSandbox, key: str) -> Any:
    return sandbox.eval("function(k) return ANKIGTA.ClientSettings.get(k) end")(key)


def client_put(sandbox: MtaSandbox, key: str, value: Any) -> Any:
    return sandbox.eval(
        "function(k, v) return ANKIGTA.ClientSettings.set(k, v) end"
    )(key, value)


def test_a_client_setting_starts_at_its_schema_default(player: MtaSandbox) -> None:
    assert client_get(player, "indicatorMode") == "none"
    assert client_get(player, "closeAfterRating") is True
    assert client_get(player, "muteGameWorld") is False


def test_a_client_setting_is_written_applied_and_persisted(
    player: MtaSandbox,
) -> None:
    assert client_put(player, "indicatorMode", "minimap_only") is True

    assert client_get(player, "indicatorMode") == "minimap_only"
    # Stored, and actually in force -- a setting nothing applies is a setting
    # the user did not change.
    assert player.eval("ANKIGTA.Indicator.mode") == "minimap_only"
    assert "@ankigta-settings.json" in player.files


@pytest.mark.parametrize(
    ("key", "value", "reason"),
    [
        ("indicatorMode", "sphere_only", "settings.error.not_a_choice"),
        ("uiScale", 10, "settings.error.out_of_range"),
        ("closeAfterRating", "yes", "settings.error.not_a_boolean"),
        ("nothingLikeThis", 1, "settings.error.unknown"),
    ],
)
def test_the_client_refuses_what_the_schema_refuses(
    player: MtaSandbox,
    key: str,
    value: Any,
    reason: str,
) -> None:
    rejected, why = client_put(player, key, value)

    assert rejected is False
    assert why == reason
    assert "@ankigta-settings.json" not in player.files


def test_the_client_may_not_write_a_setting_the_server_owns(
    player: MtaSandbox,
) -> None:
    rejected, reason = client_put(player, "activationRadius", 7)

    assert rejected is False
    assert reason == "wrong_authority"
    assert "@ankigta-settings.json" not in player.files


CLIENT_VALUES = {
    "indicatorMode": "sphere_and_minimap",
    "focusOnSelect": False,
    "reviewProtection": False,
    "disablePlayerControls": False,
    "closeAfterRating": False,
    "cardAudioEnabled": False,
    "muteGameWorld": True,
    "uiScale": 1.25,
    # Normalized coordinates, which is what the schema accepts: a fraction of
    # the screen describes the same corner at every resolution.
    "uiPlacement": {"f7": {"x": 0.25, "y": 0.4}},
}


def lua_value(sandbox: MtaSandbox, value: Any) -> Any:
    """A nested mapping as a Lua table, since Lua is where it is going."""
    if isinstance(value, dict):
        return sandbox.table(
            {key: lua_value(sandbox, item) for key, item in value.items()}
        )
    return value


def plain(value: Any) -> Any:
    """A value read back out of Lua, as plain Python."""
    if hasattr(value, "keys"):
        return {str(key): plain(value[key]) for key in value.keys()}
    return value


def test_every_setting_the_client_owns_survives_a_restart_and_is_reapplied(
    player: MtaSandbox,
) -> None:
    written = CLIENT_VALUES
    assert keys_owned_by(player, "client") == set(written)
    for key, value in written.items():
        assert client_put(player, key, lua_value(player, value)) is True, key

    restarted = open_client(player.files)
    try:
        for key, value in written.items():
            assert plain(client_get(restarted, key)) == value, key
        assert restarted.eval("ANKIGTA.Indicator.mode") == "sphere_and_minimap"
        assert restarted.eval("function() return reviewModeState() end")()[
            "cardAudioEnabled"
        ] is False
    finally:
        restarted.close()


def test_a_stored_client_value_the_schema_rejects_falls_back_to_default(
    player: MtaSandbox,
) -> None:
    client_put(player, "uiScale", 1.8)

    restarted = load_client(player.files)
    try:
        restarted.eval(
            "function() ANKIGTA.Settings.schema.uiScale.rule.maximum = 1.5 end"
        )()
        restarted.trigger("onClientResourceStart")

        assert client_get(restarted, "uiScale") == 1
        assert any(
            "discarded_stored_setting" in line
            for line in restarted.recorder.debug_messages()
        )
    finally:
        restarted.close()


def test_a_stored_setting_this_side_does_not_own_is_not_adopted(
    player: MtaSandbox,
) -> None:
    """An edited file is not a licence to write another side's setting."""
    player.write_file(
        "@ankigta-settings.json",
        json.dumps({"indicatorMode": "minimap_only", "activationRadius": 42}),
    )

    restarted = open_client(player.files)
    try:
        assert client_get(restarted, "indicatorMode") == "minimap_only"
        # Not adopted, and not answered from the file either: a server-owned
        # setting is only ever what the server last said it was.
        unavailable, reason = client_get(restarted, "activationRadius")
        assert unavailable is False
        assert reason == "not_received"
        assert any(
            "discarded_stored_setting" in line
            for line in restarted.recorder.debug_messages()
        )
    finally:
        restarted.close()


def test_a_corrupt_settings_file_leaves_every_default_in_place(
    player: MtaSandbox,
) -> None:
    player.write_file("@ankigta-settings.json", "{not json at all")

    restarted = open_client(player.files)
    try:
        assert client_get(restarted, "indicatorMode") == "none"
        assert client_get(restarted, "uiScale") == 1
    finally:
        restarted.close()


# --- the add-on's half of the same setting -----------------------------------


def test_the_add_on_accepts_exactly_the_ports_the_schema_allows(
    connection: MtaSandbox,
    tmp_path: Any,
) -> None:
    """The add-on cannot call the Lua schema, so the bound is read from it here.

    Without this, "the port range" is two numbers in two languages that agree
    only until one of them is edited.
    """
    rule = connection.eval("ANKIGTA.Settings.schema.connectionPort.rule")
    minimum, maximum = int(rule["minimum"]), int(rule["maximum"])
    manager = CompanionConnectionManager(
        observe=lambda: RuntimeObservation(
            anki_version="26.05",
            v3_scheduler=True,
            fsrs_enabled=True,
            collection=CollectionObservation(state=CollectionState.OPEN),
        ),
        settings_path=tmp_path / "connection-settings.json",
        generate_token=lambda: "ticket27-token",
    )

    for outside in (minimum - 1, maximum + 1):
        with pytest.raises(ValueError):
            manager.set_manual_connection(outside, "token")

    for inside in (minimum, maximum):
        # Past the range check, and stopped later for an unrelated reason.
        with pytest.raises(RuntimeError) as stopped:
            manager.set_manual_connection(inside, "token")
        assert "not started" in str(stopped.value)


# --- across the boundary: the server's settings reaching the client ----------


def settings_payload(server: MtaSandbox) -> Any:
    """The settings the server actually sent, taken from the recorded event."""
    sent = [
        event
        for event in server.recorder.client_events
        if event.name == "ankigta:settings"
    ]
    assert sent, "the server never sent its settings"
    return server.to_python(sent[-1].args[0])


def test_the_client_is_told_the_settings_the_server_owns(tmp_path: Any) -> None:
    """A radius nobody can read is a radius nobody applies."""
    database = str(tmp_path / "ankigta.sqlite")
    first = start_resource(database)
    assert put(first, "activationRadius", 12.5) is True
    assert put(first, "activationDelaySeconds", 2.5) is True
    first.close()

    server = MtaSandbox(database_path=database)
    for script in manifest_scripts("shared", "server"):
        server.load(script)
    publish(server, port=32145)
    player = server.add_study_player()
    server.trigger("onResourceStart")
    # The client asks, rather than the server pushing at its own start. On a
    # restart this side comes up first, and a client whose scripts have not
    # started has registered no events, so a push then is simply lost.
    server.trigger(
        "ankigta:requestAuthorization",
        server.eval("resourceRoot"),
        client=player,
    )
    payload = settings_payload(server)
    server.close()

    assert payload["activationRadius"] == 12.5
    # The client's own settings are not in it: the server has no business
    # telling a machine what its own presentation settings are. Neither is the
    # connection override, which is local to the side that made it.
    assert "indicatorMode" not in payload
    assert "connectionPort" not in payload
    assert "connectionToken" not in payload

    player = open_client()
    try:
        player.trigger(
            "ankigta:settings",
            player.eval("resourceRoot"),
            player.table(payload),
        )

        assert player.eval("ANKIGTA.Activation.settings.defaultRadius") == 12.5
        assert player.eval("ANKIGTA.Activation.settings.delaySeconds") == 2.5
        assert client_get(player, "activationRadius") == 12.5
    finally:
        player.close()


def test_the_client_ignores_a_pushed_value_the_schema_rejects(
    player: MtaSandbox,
) -> None:
    before = player.eval("ANKIGTA.Activation.settings.defaultRadius")

    player.trigger(
        "ankigta:settings",
        player.eval("resourceRoot"),
        player.table({"activationRadius": 200}),
    )

    assert player.eval("ANKIGTA.Activation.settings.defaultRadius") == before
    # Not kept either: a value that failed the schema is not a value to report
    # back later as the server's.
    unavailable, reason = client_get(player, "activationRadius")
    assert unavailable is False
    assert reason == "not_received"
    assert any(
        "discarded_stored_setting" in line and "activationRadius" in line
        for line in player.recorder.debug_messages()
    )


def test_the_server_does_not_get_to_set_a_setting_the_client_owns(
    player: MtaSandbox,
) -> None:
    player.trigger(
        "ankigta:settings",
        player.eval("resourceRoot"),
        player.table({"indicatorMode": "minimap_only"}),
    )

    assert player.eval("ANKIGTA.Indicator.mode") == "none"
    assert client_get(player, "indicatorMode") == "none"
    assert any(
        "discarded_stored_setting" in line and "indicatorMode" in line
        for line in player.recorder.debug_messages()
    )


def test_the_client_does_not_keep_the_connection_override_of_its_own(
    player: MtaSandbox,
) -> None:
    """It is written through the connection settings, which the server owns."""
    rejected, reason = client_put(player, "connectionPort", 40011)

    assert rejected is False
    assert reason == "not_a_stored_setting"
    assert "@ankigta-settings.json" not in player.files


def test_a_setting_that_cannot_be_written_does_not_change_in_memory_either(
    player: MtaSandbox,
) -> None:
    """Reporting a value the next restart will not have is worse than failing."""
    assert client_put(player, "uiScale", 1.5) is True
    player.file_writes_fail = True

    rejected, reason = client_put(player, "uiScale", 1.75)

    assert rejected is False
    assert reason == "settings_write_failed"
    assert client_get(player, "uiScale") == 1.5


def test_the_review_mode_a_request_asks_for_outlives_the_request(
    tmp_path: Any,
) -> None:
    """The server owns the mode, so the study request changes the setting and
    the setting is what governs -- including after a restart."""
    database = str(tmp_path / "ankigta.sqlite")
    server = MtaSandbox(database_path=database)
    for script in manifest_scripts("shared", "server"):
        server.load(script)
    study_player = server.add_study_player()
    server.trigger("onResourceStart")
    server.trigger(
        "ankigta:startStudy",
        server.eval("resourceRoot"),
        "allow_all",
        client=study_player,
    )
    server.close()

    restarted = MtaSandbox(database_path=database)
    for script in manifest_scripts("shared", "server"):
        restarted.load(script)
    publish(restarted, port=32145)
    restarted_player = restarted.add_study_player()
    restarted.trigger("onResourceStart")
    try:
        assert get(restarted, "reviewMode") == "allow_all"

        # A later request names no mode at all; the stored one is what the
        # companion is told, not `false`.
        restarted.trigger(
            "ankigta:startStudy",
            restarted.eval("resourceRoot"),
            client=restarted_player,
        )
        sent = restarted.recorder.remote_fetches[-1]
        assert json.loads(sent["options"]["postData"])["allowEarlyReview"] is True
    finally:
        restarted.close()


@pytest.mark.parametrize(
    ("mode", "takes_not_due"),
    [("allow_due", False), ("allow_all", True)],
)
def test_each_review_mode_admits_the_cards_its_name_says(
    tmp_path: Any,
    mode: str,
    takes_not_due: bool,
) -> None:
    """The point of the rename: each value now says which cards it takes.

    `Allow due` builds the session out of what the scheduler calls due;
    `Allow all` takes cards whether they are due or not. Asserted at the
    request the companion actually receives, because that is where the mode
    stops being a word and starts being a session.
    """
    server = MtaSandbox(database_path=str(tmp_path / "ankigta.sqlite"))
    for script in manifest_scripts("shared", "server"):
        server.load(script)
    publish(server, port=32145)
    study_player = server.add_study_player()
    server.trigger("onResourceStart")
    try:
        server.trigger(
            "ankigta:startStudy",
            server.eval("resourceRoot"),
            mode,
            client=study_player,
        )

        assert get(server, "reviewMode") == mode
        sent = server.recorder.remote_fetches[-1]
        body = json.loads(sent["options"]["postData"])
        assert body["allowEarlyReview"] is takes_not_due
    finally:
        server.close()


def test_starting_the_resource_restores_what_the_user_chose(tmp_path: Any) -> None:
    """Restart recovery has to happen on the real start path, not only when a
    test remembers to call `load`."""
    database = str(tmp_path / "ankigta.sqlite")
    first = start_resource(database)
    assert put(first, "activationRadius", 12.5) is True
    first.close()

    second = start_resource(database)
    try:
        assert get(second, "activationRadius") == 12.5
    finally:
        second.close()
