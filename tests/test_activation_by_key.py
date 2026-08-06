"""Panel rebuild 05 — opening a card by pressing a key, and applying a global
to everything.

Two halves, and the second exists to cover the first. `Activation type` gives a
card a second way in: standing in the zone *offers* it and a press takes it, so
the delay and the speed threshold — which exist to be sure the player meant to
be there — do not stand between the offer and the card. And every global a link
can override gains a control that clears that override everywhere, driven by
which settings have overrides rather than by a list that will be missing the
next one.

What the harness cannot do is look at a frame. It can say which text ANKIGTA
asked MTA to draw and where, which key it bound, what it asked the server to
open, and what the store holds afterwards — which is what every claim below is
made of. That the prompt is *legible* stays a manual item.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator
from xml.etree import ElementTree

import pytest

from tests.lua import MtaSandbox


REPO_ROOT = Path(__file__).resolve().parents[1]

MAP_ID = "current-map-id"
UUID = "11111111-1111-4111-8111-111111111111"


def manifest_scripts(*kinds: str) -> list[str]:
    """The scripts meta.xml declares, in declared order."""
    manifest = ElementTree.parse(REPO_ROOT / "mta" / "ankigta" / "meta.xml")
    return [
        str(element.get("src"))
        for element in manifest.iter("script")
        if element.get("type") in kinds
    ]


def to_lua(sandbox: MtaSandbox, value: Any) -> Any:
    if isinstance(value, dict):
        return sandbox.lua.table_from(
            {key: to_lua(sandbox, item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return sandbox.lua.table_from([to_lua(sandbox, item) for item in value])
    return value


# --- the client, where a key is pressed and a prompt is drawn ----------------


@pytest.fixture
def client() -> Iterator[MtaSandbox]:
    sandbox = MtaSandbox()
    try:
        for script in manifest_scripts("shared", "client"):
            sandbox.load(script)
        sandbox.trigger("onClientResourceStart")
        yield sandbox
    finally:
        sandbox.close()


def authorize(sandbox: MtaSandbox) -> None:
    sandbox.eval(
        'function() triggerEvent("ankigta:setAuthorized", resourceRoot, true) end'
    )()


def announce_server(sandbox: MtaSandbox, **values: Any) -> None:
    """Server-owned settings, arriving over the wire the way they really do."""
    sandbox.eval(
        """
        function(values)
            triggerEvent("ankigta:settings", resourceRoot, values)
        end
        """
    )(to_lua(sandbox, values))


def standing(
    sandbox: MtaSandbox,
    *,
    entity_id: str = "gate-17",
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
) -> Any:
    """The Runtime Instance of a Map Entity, stamped the way ANKIGTA stamps it."""
    return sandbox.add_world_element(
        x=x,
        y=y,
        z=z,
        ankigtaEntityId=entity_id,
        ankigtaMapId=MAP_ID,
    )


def candidates(sandbox: MtaSandbox, links: list[dict[str, Any]]) -> None:
    """A watched link set, as the server sends one after Anki answers."""
    sandbox.eval(
        """
        function(links)
            triggerEvent("ankigta:spatialCandidates", resourceRoot, links)
        end
        """
    )(to_lua(sandbox, links))


def link(
    *,
    entity_id: str = "gate-17",
    radius: float = 3.0,
    activation_type: Any = None,
    activation_key: Any = None,
) -> dict[str, Any]:
    """One watched Spatial Link, as `server/main.lua` builds one.

    An absent `activationType` is the entity saying nothing of its own, which
    is what a NULL override column means and what makes it follow the global.
    """
    entry: dict[str, Any] = {
        "mapId": MAP_ID,
        "entityId": entity_id,
        "cardIdentity": {"collectionUuid": UUID, "cardId": 42},
        "radius": radius,
        "eligible": True,
    }
    if activation_type is not None:
        entry["activationType"] = activation_type
    if activation_key is not None:
        entry["activationKey"] = activation_key
    return entry


def observe(sandbox: MtaSandbox) -> Any:
    """One poll of the world, as the timer runs it."""
    return sandbox.eval("function() return ANKIGTA.Spatial.tick() end")()


def opened(sandbox: MtaSandbox) -> list[Any]:
    return [
        event.args
        for event in sandbox.recorder.server_events
        if event.name == "ankigta:requestSpatialOpen"
    ]


def press(sandbox: MtaSandbox, key: str) -> None:
    """The key, pressed. Whatever MTA would call, called."""
    handlers = sandbox.bound_keys.get((key, "down"), [])
    assert handlers, f"nothing is bound to {key}"
    for handler in handlers:
        handler()


def bound_key(sandbox: MtaSandbox) -> Any:
    return sandbox.eval("function() return ANKIGTA.Activation.boundKey() end")()


def offer(sandbox: MtaSandbox) -> Any:
    answer = sandbox.eval("function() return ANKIGTA.Activation.offer() end")()
    if answer is False:
        return None
    return sandbox.to_python(answer)


def entry(*, entity_id: str = "gate-17") -> dict[str, Any]:
    """One entry of the F7 snapshot, as `server/main.lua` builds it."""
    return {
        "mapEntity": {
            "mapId": MAP_ID,
            "entityId": entity_id,
            "type": "object",
            "model": 1337,
            "map": {"resourceName": "current-map", "mapName": "Current Map"},
            "authored": {
                "position": {"x": 0, "y": 0, "z": 0},
                "rotation": {"x": 0, "y": 0, "z": 0},
                "world": {"interior": 0, "dimension": 0},
            },
        },
        "runtimeInstance": {"available": True, "referenceId": entity_id},
        "metadata": {"name": "", "entityTag": ""},
        "link": {"state": "Active Spatial Link"},
    }


def push_snapshot(sandbox: MtaSandbox, entities: list[dict[str, Any]]) -> None:
    snapshot = {
        "visible": True,
        "cardPicker": {"enabled": False},
        "history": {"canUndo": False, "canRedo": False},
        "entities": entities,
        "currentMap": {"resourceName": "current-map", "mapIds": [MAP_ID]},
        "cardLinks": [],
    }
    sandbox.eval(
        """
        function(snapshot)
            triggerEvent("ankigta:f7Snapshot", resourceRoot, snapshot)
        end
        """
    )(to_lua(sandbox, snapshot))


def open_panel(sandbox: MtaSandbox) -> None:
    """F7, as the key press does it, and the page announcing it is ready: a
    state is only pushed into a page that has said so, and the settings rows
    travel in it."""
    authorize(sandbox)
    sandbox.eval(
        """
        function()
            if not ANKIGTA.Panel.isOpen() then togglePanel() end
            triggerEvent("ankigta:panelAction", resourceRoot, "ready", "{}")
        end
        """
    )()


def repush(sandbox: MtaSandbox) -> None:
    """Ask for the settings section, which pushes a fresh whole state."""
    sandbox.eval(
        """
        function()
            triggerEvent("ankigta:panelAction", resourceRoot,
                "openSettings", "{}")
        end
        """
    )()


def draw_marks(sandbox: MtaSandbox) -> None:
    """Decide what the marks are, then render one frame of them."""
    sandbox.eval("function() return ANKIGTA.WorldMarks.refresh() end")()
    sandbox.trigger("onClientRender")


def offering_world(
    sandbox: MtaSandbox, *, activation_key: Any = None
) -> None:
    """One entity in key mode, streamed in, with the player standing in it."""
    authorize(sandbox)
    standing(sandbox)
    push_snapshot(sandbox, [entry()])
    candidates(
        sandbox,
        [link(activation_type="key", activation_key=activation_key)],
    )
    observe(sandbox)


# --- two ways in, and the entity says which -----------------------------------


def test_activation_type_offers_automatic_and_key(client: MtaSandbox) -> None:
    """Globally, and on a link: the same shape the Activation Zone radius has."""
    definition = client.to_python(
        client.eval(
            """
            function()
                local rule = ANKIGTA.Settings.definition("activationType").rule
                return {
                    kind = rule.kind,
                    values = rule.values,
                    default = ANKIGTA.Settings.default("activationType"),
                    overridable =
                        ANKIGTA.Settings.entityOverrideColumn("activationType"),
                }
            end
            """
        )()
    )

    assert definition["kind"] == "choice"
    assert sorted(definition["values"]) == ["automatic", "key"]
    assert definition["default"] == "automatic"
    assert definition["overridable"] == "activation_type_override"


def test_automatic_is_what_it_was_delay_and_speed_included(
    client: MtaSandbox,
) -> None:
    """The shipped default, and nothing about it moves: the zone still decides
    on the player's behalf, and both gates still stand in the way."""
    authorize(client)
    standing(client)
    announce_server(client, activationDelaySeconds=1)
    candidates(client, [link()])

    # Standing still inside the zone, before the delay is up: nothing.
    observe(client)
    assert opened(client) == []

    # Moving faster than the threshold cancels it rather than letting the
    # countdown run out under a speeding player.
    client.player_velocity = (1.0, 0.0, 0.0)
    client.advance(2000)
    observe(client)
    assert opened(client) == []

    # Standing still again restarts the countdown rather than inheriting the
    # time that passed while the player was moving.
    client.player_velocity = (0.0, 0.0, 0.0)
    observe(client)
    assert opened(client) == []

    client.advance(2000)
    observe(client)
    assert len(opened(client)) == 1


def test_in_key_mode_standing_in_the_zone_alone_never_opens_the_card(
    client: MtaSandbox,
) -> None:
    """The whole difference: the zone offers, and only a press takes."""
    offering_world(client)

    for _ in range(5):
        client.advance(10_000)
        observe(client)

    assert opened(client) == []
    assert offer(client) is not None


def test_in_key_mode_pressing_the_key_opens_the_card(client: MtaSandbox) -> None:
    offering_world(client)

    press(client, "e")

    asked = opened(client)
    assert len(asked) == 1
    assert asked[0][0] == MAP_ID
    assert asked[0][1] == "gate-17"
    assert client.to_python(asked[0][2]) == {
        "collectionUuid": UUID,
        "cardId": 42,
    }


def test_in_key_mode_the_activation_delay_does_not_gate_the_press(
    client: MtaSandbox,
) -> None:
    """A press carries the certainty the delay waits for. The offer stands from
    the first observation that finds the player inside."""
    authorize(client)
    standing(client)
    announce_server(client, activationDelaySeconds=60)
    candidates(client, [link(activation_type="key")])

    observe(client)
    press(client, "e")

    assert len(opened(client)) == 1


def test_leaving_the_zone_takes_the_offer_away(client: MtaSandbox) -> None:
    offering_world(client)
    assert offer(client) is not None

    client.player_position = (500.0, 0.0, 0.0)
    observe(client)

    assert offer(client) is None
    press(client, "e")
    assert opened(client) == []


def test_a_press_with_nothing_offered_opens_nothing(client: MtaSandbox) -> None:
    """The key is bound from the start, so it has to be harmless when there is
    no offer -- otherwise the first press anywhere in the world is a card."""
    authorize(client)

    press(client, "e")

    assert opened(client) == []


def test_the_nearest_entity_says_how_it_opens(client: MtaSandbox) -> None:
    """One winner, chosen by distance, and then that entity's own answer about
    the way in. Two winners would mean two prompts and no way to say which the
    press meant."""
    authorize(client)
    standing(client, entity_id="near", x=1.0)
    standing(client, entity_id="far", x=2.0)
    candidates(
        client,
        [
            link(entity_id="near", activation_type="key"),
            link(entity_id="far", activation_type="automatic"),
        ],
    )

    client.advance(5_000)
    observe(client)

    # The nearer one is in key mode, so nothing opened by itself.
    assert opened(client) == []
    assert offer(client)["entityId"] == "near"


# --- which key, and what the entity says about it -----------------------------


def test_the_activation_key_is_settable_globally(client: MtaSandbox) -> None:
    announce_server(client, activationKey="q")

    assert bound_key(client) == "q"

    authorize(client)
    standing(client)
    candidates(client, [link(activation_type="key")])
    observe(client)
    press(client, "q")

    assert len(opened(client)) == 1


def test_a_link_can_name_a_key_of_its_own(client: MtaSandbox) -> None:
    """One object is the odd one out without moving everything else."""
    announce_server(client, activationKey="q")
    offering_world(client, activation_key="r")

    assert bound_key(client) == "r"
    assert offer(client)["key"] == "r"

    press(client, "r")
    assert len(opened(client)) == 1


def test_walking_away_from_an_odd_one_out_puts_the_global_key_back(
    client: MtaSandbox,
) -> None:
    offering_world(client, activation_key="r")
    assert bound_key(client) == "r"

    client.player_position = (500.0, 0.0, 0.0)
    observe(client)

    assert bound_key(client) == "e"
    # Through the binding rather than only through what the module says about
    # it: a key it has let go of has to stop arriving here, or the odd one out
    # would go on opening cards from across the map.
    bound = {key for key, _state in client.bound_keys}
    assert "r" not in bound
    assert "e" in bound


@pytest.mark.parametrize("key", ["F7", "escape"])
def test_a_key_ankigta_already_uses_is_refused_with_a_reason(
    client: MtaSandbox, key: str
) -> None:
    """Refused rather than allowed to shadow: the panel's own key opening a card
    instead is a different feature breaking for a reason nobody could see."""
    answer = client.eval(
        """
        function(key)
            local ok, reason = ANKIGTA.Settings.validate("activationKey", key)
            return {ok = ok, reason = reason or false}
        end
        """
    )(key)

    assert answer["ok"] is False
    assert answer["reason"] == "settings.error.key_in_use"


def test_a_key_mta_does_not_know_is_refused_too(client: MtaSandbox) -> None:
    """`bindKey` refuses a name it does not know, and a refusal there is a
    setting that reads as saved and binds nothing."""
    answer = client.eval(
        """
        function()
            local ok, reason =
                ANKIGTA.Settings.validate("activationKey", "not-a-key")
            return {ok = ok, reason = reason or false}
        end
        """
    )()

    assert answer["ok"] is False
    assert answer["reason"] == "settings.error.not_a_key"


def test_the_reserved_keys_are_the_ones_the_client_really_binds(
    client: MtaSandbox,
) -> None:
    """The refusal above is only honest while `reservedKeys` names the keys the
    client actually listens on. Both halves read the same table."""
    reserved = client.eval(
        """
        function()
            local keys = {}
            for _, key in pairs(ANKIGTA.Settings.reservedKeys) do
                keys[#keys + 1] = key
            end
            return keys
        end
        """
    )()
    reserved = {str(reserved[index]) for index in reserved.keys()}
    # The panel's key is bound from the start; the dismiss key is bound while
    # something is on screen to dismiss, so Pick Entity is started to see it.
    client.eval(
        """
        function()
            triggerEvent("ankigta:pickEntityStart", resourceRoot, "pick")
        end
        """
    )()
    bound = {key for key, _state in client.bound_keys}

    assert reserved <= bound
    # And nothing is bound that the schema neither reserves nor offers.
    offered = client.eval(
        "function() return ANKIGTA.Settings.offeredKeys() end"
    )()
    offered = {str(offered[index]) for index in offered.keys()}
    assert bound <= reserved | offered


def test_a_reserved_key_is_not_offered_in_the_panel(client: MtaSandbox) -> None:
    """A control that offers a value its own validator will refuse is a control
    arguing with itself."""
    offered = client.eval(
        "function() return ANKIGTA.Settings.offeredKeys() end"
    )()
    offered = {str(offered[index]) for index in offered.keys()}

    assert "F7" not in offered
    assert "escape" not in offered
    assert "e" in offered


# --- the prompt that says which key -------------------------------------------


def test_an_entity_offering_a_card_says_so_over_itself(
    client: MtaSandbox,
) -> None:
    """A key nobody can discover is a key nobody presses, and this is the whole
    of how it is discovered."""
    offering_world(client)

    draw_marks(client)

    assert "E to view" in client.drawn_text


def test_the_prompt_names_the_key_that_is_actually_bound(
    client: MtaSandbox,
) -> None:
    """Never the one the setting asked for: a name MTA refused would otherwise
    be drawn over the entity as an instruction that does nothing."""
    offering_world(client, activation_key="r")

    draw_marks(client)

    assert bound_key(client) == "r"
    assert "R to view" in client.drawn_text
    assert "E to view" not in client.drawn_text


def test_the_prompt_stops_when_the_player_leaves_the_zone(
    client: MtaSandbox,
) -> None:
    offering_world(client)
    draw_marks(client)
    assert "E to view" in client.drawn_text

    client.player_position = (500.0, 0.0, 0.0)
    observe(client)
    client.drawn_text.clear()
    draw_marks(client)

    assert client.drawn_text == []


def test_an_entity_in_automatic_says_nothing_over_itself(
    client: MtaSandbox,
) -> None:
    authorize(client)
    standing(client)
    push_snapshot(client, [entry()])
    candidates(client, [link()])
    observe(client)

    draw_marks(client)

    assert client.drawn_text == []


def test_the_prompt_obeys_the_draw_distance_ticket_04_set(
    client: MtaSandbox,
) -> None:
    """One door and one rule about distance, not a second one invented here: a
    mark with no far edge hangs in the air long after its object has gone."""
    offering_world(client)
    distance = client.eval(
        "function() return ANKIGTA.WorldMarks.drawDistance() end"
    )()

    client.camera_matrix = (0.0, distance + 10, 0.0, 0.0, 0.0, 0.0)
    draw_marks(client)
    assert client.drawn_text == []

    client.camera_matrix = (0.0, distance - 10, 0.0, 0.0, 0.0, 0.0)
    draw_marks(client)
    assert "E to view" in client.drawn_text


def test_the_prompt_is_not_drawn_behind_the_camera(client: MtaSandbox) -> None:
    """`getScreenFromWorldPosition` refuses rather than answering for a point
    the viewer is not looking at -- behind them, or off the edge of the screen
    -- and the refusal has to be taken as the answer. Drawing anyway would put
    the prompt of an entity the player has walked past on screen, mirrored
    across the middle of it. The distance rule does not catch this: the spot is
    near, it is just not being looked at."""
    offering_world(client)

    # The camera looks away from the entity, which is still well inside the
    # draw distance.
    client.camera_matrix = (0.0, -5.0, 0.0, 0.0, -50.0, 0.0)
    draw_marks(client)

    assert client.drawn_text == []


def test_the_prompt_costs_no_marker(client: MtaSandbox) -> None:
    """MTA stops streaming markers in at 32 (`CClientMarker::IsLimitReached`),
    and the coronas already share that budget. A prompt that took one from them
    would put a corona out somewhere else in the world to say a word over this
    one."""
    offering_world(client)

    draw_marks(client)

    assert "E to view" in client.drawn_text
    assert client.markers == []


def test_whether_the_prompt_is_drawn_is_decidable_from_outside(
    client: MtaSandbox,
) -> None:
    """Ticket 06 owns "one entity shows one thing", and it has to be able to
    take the entity for itself without reaching into the draw call."""
    offering_world(client)

    client.eval(
        """
        function()
            return ANKIGTA.WorldMarks.holdPromptBackWhen(function(mapId, entityId)
                return entityId == "gate-17"
            end)
        end
        """
    )()
    draw_marks(client)
    assert client.drawn_text == []

    # And the decision is in the plan rather than in the frame: the same
    # question, asked without drawing anything.
    planned = client.eval(
        "function() return ANKIGTA.WorldMarks.refresh().prompt end"
    )()
    assert planned is False

    client.eval("function() ANKIGTA.WorldMarks.holdPromptBackWhen(false) end")()
    draw_marks(client)
    assert "E to view" in client.drawn_text


def test_the_card_opens_the_one_way_in(client: MtaSandbox) -> None:
    """Nothing about admission or rating changes. A press asks the server to
    open the card through the same event walking into a zone uses, so there is
    one path into Review Mode rather than a second one beside it."""
    offering_world(client)

    press(client, "e")

    names = [
        event.name
        for event in client.recorder.server_events
        if event.name.startswith("ankigta:")
    ]
    assert "ankigta:requestSpatialOpen" in names
    # And no second way of asking was invented for the press.
    assert [name for name in names if "open" in name.lower()] == [
        "ankigta:requestSpatialOpen"
    ]


# --- the store's half: overrides, and clearing them everywhere ----------------


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


def seed_entity(sandbox: MtaSandbox, entity_id: str = "gate-17") -> None:
    connection = sandbox.connection.raw
    connection.execute(
        "INSERT OR IGNORE INTO maps (map_id, resource_name, map_name)"
        " VALUES (?, 'current-map', 'Current Map')",
        (MAP_ID,),
    )
    connection.execute(
        "INSERT OR REPLACE INTO map_entities (map_id, entity_id, entity_type,"
        " model, authored_x, authored_y, authored_z, rotation_x, rotation_y,"
        " rotation_z, interior, dimension)"
        " VALUES (?, ?, 'object', 1337, 10, 20, 30, 0, 0, 0, 0, 0)",
        (MAP_ID, entity_id),
    )
    connection.commit()


def write_metadata(
    sandbox: MtaSandbox,
    player: Any,
    metadata: dict[str, Any],
    *,
    entity_id: str = "gate-17",
) -> None:
    sandbox.trigger(
        "ankigta:updateEntityMetadata",
        sandbox.lua.globals().resourceRoot,
        MAP_ID,
        entity_id,
        to_lua(sandbox, metadata),
        client=player,
    )


def snapshot_rows(sandbox: MtaSandbox, player: Any) -> dict[str, Any]:
    sandbox.trigger(
        "ankigta:requestF7", sandbox.lua.globals().resourceRoot, client=player
    )
    event = [
        event
        for event in sandbox.recorder.client_events
        if event.name == "ankigta:f7Snapshot"
    ][-1]
    snapshot = sandbox.to_python(event.args[0])
    return {row["mapEntity"]["entityId"]: row for row in snapshot["entities"]}


def overridable(sandbox: MtaSandbox) -> list[str]:
    keys = sandbox.eval(
        "function() return ANKIGTA.Settings.entityOverridableKeys() end"
    )()
    return [str(keys[index]) for index in keys.keys()]


#: One value per overridable setting that no default happens to be, so a row
#: that lost its override is told apart from one that kept it.
OVERRIDE_VALUES = {
    "activationRadius": 7.5,
    "activationType": "key",
    "activationKey": "q",
    "showCorona": True,
    "coronaColor": "#ff8000",
    "coronaOpacity": 0.25,
    "textLabelField": "Back",
    "textLabelColor": "#00ff80",
    "textLabelSize": 1.5,
}


def metadata_for(sandbox: MtaSandbox) -> dict[str, Any]:
    """An override for every setting the schema says a link can carry.

    Built from the schema rather than written out, so a setting that gains an
    override without a value here fails this module rather than going untested.
    """
    fields = {}
    for key in overridable(sandbox):
        field = sandbox.eval(
            "function(key) return ANKIGTA.Settings.entityOverrideField(key) end"
        )(key)
        assert key in OVERRIDE_VALUES, f"{key} has no test value"
        fields[str(field)] = OVERRIDE_VALUES[key]
    return fields


def stored(sandbox: MtaSandbox, entity_id: str = "gate-17") -> dict[str, Any]:
    columns = [
        sandbox.eval(
            "function(key) return ANKIGTA.Settings.entityOverrideColumn(key) end"
        )(key)
        for key in overridable(sandbox)
    ]
    row = sandbox.connection.raw.execute(
        "SELECT " + ", ".join(columns) + " FROM map_entity_metadata"
        " WHERE entity_id = ?",
        (entity_id,),
    ).fetchone()
    if row is None:
        # No row at all is every override absent, which is what a metadata
        # table with no row for this entity means everywhere else.
        return {column: None for column in columns}
    return dict(zip(columns, row))


def test_every_declared_override_has_a_column_to_live_in(
    server: MtaSandbox,
) -> None:
    """The list is the schema's, and the table is built from it. A setting that
    declares an override the database has nowhere to keep would be a setting
    that reads as saved and is not."""
    columns = {
        row[1]
        for row in server.connection.raw.execute(
            "PRAGMA table_info(map_entity_metadata)"
        ).fetchall()
    }

    for key in overridable(server):
        column = server.eval(
            "function(key) return ANKIGTA.Settings.entityOverrideColumn(key) end"
        )(key)
        assert column in columns, f"{key} has no column"


def test_one_write_carries_every_override_the_schema_declares(
    server: MtaSandbox,
) -> None:
    """Six places write a metadata row, and each of them used to spell the
    column list out again -- so adding a column meant finding all six, and the
    one that was missed wrote a default over whatever the entity said. They go
    through one writer now, and what it writes is this list."""
    seed_entity(server)
    player = server.add_study_player()

    write_metadata(server, player, metadata_for(server))

    held = stored(server)
    assert held["radius_override"] == 7.5
    assert held["activation_type_override"] == "key"
    assert held["activation_key_override"] == "q"
    assert held["show_corona_override"] == 1
    assert held["corona_color_override"] == "#ff8000"
    assert held["corona_opacity_override"] == 0.25


def test_saving_a_name_leaves_every_override_where_it_was(
    server: MtaSandbox,
) -> None:
    """The one that keeps biting: a write that does not mention a field is not
    an answer about it."""
    seed_entity(server)
    player = server.add_study_player()
    write_metadata(server, player, metadata_for(server))
    before = stored(server)

    write_metadata(server, player, {"name": "North gate"})

    assert stored(server) == before


def test_show_corona_can_be_switched_off_on_one_entity(
    server: MtaSandbox,
) -> None:
    """`false` is a value now, not a way of saying nothing: with the global on,
    "not this one" has to be sayable."""
    seed_entity(server)
    player = server.add_study_player()

    write_metadata(server, player, {"showCorona": False})

    assert stored(server)["show_corona_override"] == 0
    assert snapshot_rows(server, player)["gate-17"]["metadata"]["showCorona"] is False


def test_clearing_show_corona_is_a_different_answer_from_switching_it_off(
    server: MtaSandbox,
) -> None:
    seed_entity(server)
    player = server.add_study_player()
    write_metadata(server, player, {"showCorona": False})

    write_metadata(server, player, {"showCorona": "inherit"})

    assert stored(server)["show_corona_override"] is None
    assert "showCorona" not in snapshot_rows(server, player)["gate-17"]["metadata"]


def test_an_activation_type_the_schema_would_refuse_is_refused_here_too(
    server: MtaSandbox,
) -> None:
    seed_entity(server)
    player = server.add_study_player()

    write_metadata(server, player, {"activationType": "whenever"})

    refused = [
        event.args
        for event in server.recorder.client_events
        if event.name == "ankigta:pendingMapSaveNotice"
    ]
    assert refused != []
    assert stored(server)["activation_type_override"] is None


def test_a_link_can_be_told_which_key_opens_it(server: MtaSandbox) -> None:
    seed_entity(server)
    player = server.add_study_player()

    write_metadata(server, player, {"activationKey": "q"})

    assert stored(server)["activation_key_override"] == "q"
    row = snapshot_rows(server, player)["gate-17"]["metadata"]
    assert row["activationKey"] == "q"


def test_a_link_cannot_be_told_to_use_a_key_ankigta_owns(
    server: MtaSandbox,
) -> None:
    """The same rule the global answers to. A value cannot be legal in Settings
    and illegal on an entity, or the other way round."""
    seed_entity(server)
    player = server.add_study_player()

    write_metadata(server, player, {"activationKey": "F7"})

    refused = [
        event.args
        for event in server.recorder.client_events
        if event.name == "ankigta:pendingMapSaveNotice"
    ]
    assert refused != []
    assert stored(server)["activation_key_override"] is None


def test_what_a_link_says_reaches_the_client_that_has_to_act_on_it(
    server: MtaSandbox,
) -> None:
    """The candidate set is what the activation rules read, so an override that
    never reaches it is an override nothing acts on."""
    seed_entity(server)
    player = server.add_study_player()
    # The map has to be in the world for its entities to be watched at all:
    # `World.loadedMapIds` narrows the set to what is really loaded.
    owner = server.add_resource("current-map", resource_type="map")
    standing = server.add_world_element(ankigtaEntityId="gate-17", map_id=MAP_ID)
    standing["__parent"] = owner
    server.connection.raw.execute(
        "INSERT INTO spatial_links (map_id, entity_id, collection_uuid,"
        " card_id, state, verified_map_sha256)"
        " VALUES (?, 'gate-17', ?, 42, 'active', ?)",
        (MAP_ID, UUID, "a" * 64),
    )
    server.connection.raw.commit()
    write_metadata(server, player, {"activationType": "key", "activationKey": "q"})

    server.trigger(
        "ankigta:cardStatesRefreshed",
        server.lua.globals().resourceRoot,
        player,
        to_lua(server, {f"{UUID}/42": "review"}),
        False,
    )

    sent = [
        server.to_python(event.args[0])
        for event in server.recorder.client_events
        if event.name == "ankigta:spatialCandidates"
    ][-1]
    assert len(sent) == 1
    assert sent[0]["activationType"] == "key"
    assert sent[0]["activationKey"] == "q"


# --- and the ones I already made ---------------------------------------------


def clear_overrides(
    sandbox: MtaSandbox, player: Any, key: str, *, confirmed: bool
) -> None:
    sandbox.trigger(
        "ankigta:clearEntityOverrides",
        sandbox.lua.globals().resourceRoot,
        key,
        confirmed,
        client=player,
    )


def counted(sandbox: MtaSandbox) -> list[tuple[str, int]]:
    return [
        (str(event.args[0]), int(event.args[1]))
        for event in sandbox.recorder.client_events
        if event.name == "ankigta:entityOverrideCount"
    ]


def history_rows(sandbox: MtaSandbox) -> list[tuple[str, str]]:
    return sandbox.connection.raw.execute(
        "SELECT operation, target FROM change_history ORDER BY history_id"
    ).fetchall()


def test_every_global_a_link_can_override_offers_the_bulk_control(
    client: MtaSandbox,
) -> None:
    """Beside the global it is about, for every one of them -- and driven by
    which settings have overrides rather than by a list in the panel."""
    open_panel(client)
    rows = client.pushed_panel_state()["settings"]["rows"]
    offered = {
        row["key"] for row in rows if row.get("clearOverrides") is True
    }

    assert offered == set(overridable(client))
    # And it is the set tickets 04, 05 and 06 built between them, so a control
    # that quietly stopped being offered is a failure here.
    assert offered == {
        "activationRadius",
        "activationType",
        "activationKey",
        "showCorona",
        "coronaColor",
        "coronaOpacity",
        "textLabelField",
        "textLabelColor",
        "textLabelSize",
    }


def test_a_setting_that_gains_an_override_gains_the_control(
    client: MtaSandbox,
) -> None:
    """Without being added to a list anywhere. The set has grown four times in
    four tickets, and the fifth will not edit the panel to do it either.

    The setting invented here is deliberately not one the schema holds: proving
    "a setting gains the control by having an override" needs one that has just
    gained one, and every shipped setting gained its control before this ran.
    """
    open_panel(client)
    before = client.pushed_panel_state()["settings"]["rows"]
    assert "invented" not in {row["key"] for row in before}

    client.eval(
        """
        function()
            ANKIGTA.Settings.schema.invented = {
                authority = ANKIGTA.Settings.SERVER,
                default = 1,
                rule = {kind = "number", minimum = 0.5, maximum = 4},
                entityOverride = {
                    column = "invented_override",
                    field = "invented",
                },
            }
        end
        """
    )()

    repush(client)
    after = client.pushed_panel_state()["settings"]["rows"]
    added = [row for row in after if row["key"] == "invented"]

    assert len(added) == 1
    assert added[0]["clearOverrides"] is True


def test_it_names_how_many_links_it_will_change_and_asks_first(
    server: MtaSandbox,
) -> None:
    """Clearing overrides across a world is not undone by pressing the control
    again, so nothing happens until the player has seen the number."""
    for entity_id in ("gate-17", "gate-18", "gate-19"):
        seed_entity(server, entity_id)
    player = server.add_study_player()
    for entity_id in ("gate-17", "gate-18"):
        write_metadata(server, player, {"radius": 7.5}, entity_id=entity_id)

    clear_overrides(server, player, "activationRadius", confirmed=False)

    assert counted(server) == [("activationRadius", 2)]
    # And nothing was cleared by the asking.
    assert stored(server, "gate-17")["radius_override"] == 7.5
    assert history_rows(server)[-1][0] == "entity_metadata"


def test_using_it_makes_every_link_follow_the_global(server: MtaSandbox) -> None:
    for entity_id in ("gate-17", "gate-18"):
        seed_entity(server, entity_id)
    player = server.add_study_player()
    for entity_id in ("gate-17", "gate-18"):
        write_metadata(server, player, {"radius": 7.5}, entity_id=entity_id)

    clear_overrides(server, player, "activationRadius", confirmed=True)

    assert stored(server, "gate-17")["radius_override"] is None
    assert stored(server, "gate-18")["radius_override"] is None


def test_changing_the_global_afterwards_moves_those_links_again(
    server: MtaSandbox,
) -> None:
    """Clearing, not copying. Writing today's value into every link as its own
    override would look identical for about a minute and then quietly stop
    tracking."""
    seed_entity(server)
    player = server.add_study_player()
    write_metadata(server, player, {"radius": 7.5})
    clear_overrides(server, player, "activationRadius", confirmed=True)

    server.trigger(
        "ankigta:updateSetting",
        server.lua.globals().resourceRoot,
        "activationRadius",
        12,
        client=player,
    )

    row = snapshot_rows(server, player)["gate-17"]
    assert "radius" not in row["metadata"]
    values = server.eval(
        "function() return ANKIGTA.SettingsStore.get('activationRadius') end"
    )()
    assert values == 12


def test_other_settings_overrides_are_untouched(server: MtaSandbox) -> None:
    seed_entity(server)
    player = server.add_study_player()
    write_metadata(server, player, metadata_for(server))

    clear_overrides(server, player, "activationRadius", confirmed=True)

    held = stored(server)
    assert held["radius_override"] is None
    assert held["activation_type_override"] == "key"
    assert held["activation_key_override"] == "q"
    assert held["show_corona_override"] == 1
    assert held["corona_color_override"] == "#ff8000"
    assert held["corona_opacity_override"] == 0.25


def test_it_is_one_change_history_entry_and_one_undo_puts_every_one_back(
    server: MtaSandbox,
) -> None:
    """One decision, one undo. Three entries would mean three presses to get
    back to where the player was."""
    for entity_id in ("gate-17", "gate-18", "gate-19"):
        seed_entity(server, entity_id)
    player = server.add_study_player()
    written = {"gate-17": 7.5, "gate-18": 12.0, "gate-19": 0.5}
    for entity_id, radius in written.items():
        write_metadata(server, player, {"radius": radius}, entity_id=entity_id)
    before = len(history_rows(server))

    clear_overrides(server, player, "activationRadius", confirmed=True)

    entries = history_rows(server)
    assert len(entries) == before + 1
    assert entries[-1][0] == "clear_entity_overrides"

    assert server.eval("function() return ANKIGTA.Store.undo() end")() is not False

    for entity_id, radius in written.items():
        assert stored(server, entity_id)["radius_override"] == radius


def test_undo_does_not_invent_an_override_for_a_link_that_had_none(
    server: MtaSandbox,
) -> None:
    """The sweep is one decision over the whole world, so reversing it has to
    leave the world in the state it recorded -- including the links that were
    already following the global."""
    for entity_id in ("gate-17", "gate-18"):
        seed_entity(server, entity_id)
    player = server.add_study_player()
    write_metadata(server, player, {"radius": 7.5}, entity_id="gate-17")
    write_metadata(server, player, {"name": "Second"}, entity_id="gate-18")

    clear_overrides(server, player, "activationRadius", confirmed=True)
    server.eval("function() return ANKIGTA.Store.undo() end")()

    assert stored(server, "gate-17")["radius_override"] == 7.5
    assert stored(server, "gate-18")["radius_override"] is None


def test_redoing_the_sweep_clears_them_again(server: MtaSandbox) -> None:
    seed_entity(server)
    player = server.add_study_player()
    write_metadata(server, player, {"radius": 7.5})
    clear_overrides(server, player, "activationRadius", confirmed=True)
    server.eval("function() return ANKIGTA.Store.undo() end")()

    server.eval("function() return ANKIGTA.Store.redo() end")()

    assert stored(server)["radius_override"] is None


def test_every_overridable_setting_can_be_counted_and_cleared(
    server: MtaSandbox,
) -> None:
    """The whole point of deriving the set from the schema: a setting that
    declares an override the store cannot sweep is a control that is offered and
    then fails."""
    seed_entity(server)
    player = server.add_study_player()
    write_metadata(server, player, metadata_for(server))

    for key in overridable(server):
        count = server.eval(
            "function(key) return ANKIGTA.Store.countEntityOverrides(key) end"
        )(key)
        assert count == 1, key
        cleared = server.to_python(
            server.eval(
                "function(key) return ANKIGTA.Store.clearEntityOverrides(key) end"
            )(key)
        )
        assert cleared["cleared"] == 1, key

    assert set(stored(server).values()) == {None}


def invalidations(sandbox: MtaSandbox) -> list[Any]:
    """Every "what may activate has changed" the server raised.

    The seam the study refresh hangs off. Asserting on it rather than on the
    candidate set that follows keeps the claim about the server's own decision:
    rebuilding the set needs Anki, and Anki is not what is under test here.
    """
    return [
        event.args
        for event in sandbox.recorder.local_events
        if event.name == "ankigta:sessionInvalidated"
    ]


def test_telling_one_entity_how_it_opens_reaches_the_watched_set(
    server: MtaSandbox,
) -> None:
    """The watched set is what the client acts on. An entity told to open by a
    key would go on opening by itself until the next time Anki happened to be
    asked -- which is whenever, and possibly never."""
    seed_entity(server)
    player = server.add_study_player()

    write_metadata(server, player, {"activationType": "key"})

    assert invalidations(server) != []


def test_naming_an_entity_does_not_cost_a_round_trip(server: MtaSandbox) -> None:
    """Nothing the watched set carries changed, so nothing asks Anki again."""
    seed_entity(server)
    player = server.add_study_player()

    write_metadata(server, player, {"name": "North gate"})

    assert invalidations(server) == []


def test_clearing_an_override_reaches_the_watched_set_too(
    server: MtaSandbox,
) -> None:
    """A cleared field is absent from the message and present in the row, which
    is the direction a comparison over what arrived would miss."""
    seed_entity(server)
    player = server.add_study_player()
    write_metadata(server, player, {"activationType": "key"})
    before = len(invalidations(server))

    write_metadata(server, player, {"activationType": "inherit"})

    assert len(invalidations(server)) > before


def test_the_sweep_reaches_the_watched_set(server: MtaSandbox) -> None:
    """A sweep that put every entity back on `Automatic` would otherwise leave
    every client still waiting for a press."""
    seed_entity(server)
    player = server.add_study_player()
    write_metadata(server, player, {"activationType": "key"})
    before = len(invalidations(server))

    clear_overrides(server, player, "activationType", confirmed=True)

    assert len(invalidations(server)) > before


def test_undoing_it_reaches_the_watched_set_as_well(server: MtaSandbox) -> None:
    seed_entity(server)
    player = server.add_study_player()
    write_metadata(server, player, {"activationType": "key"})
    clear_overrides(server, player, "activationType", confirmed=True)
    before = len(invalidations(server))

    server.eval("function(p) return undoChange(p) end")(player)

    assert len(invalidations(server)) > before


def test_a_setting_no_link_can_override_is_refused(server: MtaSandbox) -> None:
    answer = server.eval(
        """
        function()
            local ok, reason =
                ANKIGTA.Store.countEntityOverrides("activationDelaySeconds")
            return {ok = ok, reason = reason or false}
        end
        """
    )()

    assert answer["ok"] is False
    assert answer["reason"] == "settings.error.not_overridable"


def test_clearing_nothing_records_nothing(server: MtaSandbox) -> None:
    """No change, no history: an entry here would be a step that does nothing
    and an Undo that appears to have failed."""
    seed_entity(server)
    player = server.add_study_player()
    before = len(history_rows(server))

    clear_overrides(server, player, "activationRadius", confirmed=True)

    assert len(history_rows(server)) == before


# --- the strings this ticket needs --------------------------------------------


def locale_table() -> dict[str, str]:
    """The shipped strings, read out of the loaded chunk rather than grepped."""
    sandbox = MtaSandbox()
    try:
        sandbox.load("shared/locale.lua")
        strings = sandbox.eval("ANKIGTA.Locale.strings")
        return {str(key): str(strings[key]) for key in strings.keys()}
    finally:
        sandbox.close()


def test_every_word_this_ticket_puts_on_screen_has_a_string() -> None:
    table = locale_table()

    for key in (
        "settings.activationType",
        "settings.activationKey",
        "settings.showCorona",
        "settings.value.automatic",
        "settings.value.key",
        "settings.applyToAll",
        "settings.applyToAll.question",
        "settings.error.key_in_use",
        "settings.error.not_a_key",
        "f7.activationType",
        "f7.activationKey",
        "f7.activationPrompt",
        # `f7.followSettings` was the last entry in each drawn list, and the way
        # back is one button beside the field now -- so the words this ticket
        # needs for it are the button's.
        "f7.restoreGlobal",
    ):
        assert key in table, key

    # The prompt names a key, and the key is substituted rather than looked up.
    assert "%s" in table["f7.activationPrompt"]
    # The question names how many and which, in that order.
    assert table["settings.applyToAll.question"].index("%d") < table[
        "settings.applyToAll.question"
    ].index("%s")
