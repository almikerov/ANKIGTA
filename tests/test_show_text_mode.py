"""Panel rebuild 06 — Review mode `Show text`: the card's words on the object.

A third Review Mode in which a linked Map Entity carries a **Text Label** — a
line from its card's note, drawn in the world — instead of opening the review
surface. Nothing is presented and nothing is rated (ADR 0029), so there is no
session, no filtered deck, no Exact Card Admission and no Review Transaction,
and the one door into Review Mode refuses to open.

What the harness cannot do is look at a frame. It can say which text ANKIGTA
asked MTA to draw and at what scale and colour, what the server put on the
wire, what the store holds and what the panel row says — which is what every
claim below is made of. That a label is *legible* against a night sky stays a
manual item.

`shared/text_label.lua`'s own decisions — which field, what markup means, where
a line stops — are `tests/test_text_label.py`.
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
    """The scripts meta.xml declares, in declared order.

    Reading the manifest rather than listing the scripts means one that was
    never registered fails here instead of quietly working in tests only.
    """
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


# --- the client, which draws what the server decided -------------------------


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


def snapshot_entry(*, entity_id: str = "gate-17") -> dict[str, Any]:
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
    sandbox.eval(
        """
        function(snapshot)
            triggerEvent("ankigta:f7Snapshot", resourceRoot, snapshot)
        end
        """
    )(
        to_lua(
            sandbox,
            {
                "visible": True,
                "cardPicker": {"enabled": False},
                "history": {"canUndo": False, "canRedo": False},
                "entities": entities,
                "currentMap": {
                    "resourceName": "current-map",
                    "mapIds": [MAP_ID],
                },
                "cardLinks": [],
            },
        )
    )


def label(
    *,
    entity_id: str = "gate-17",
    lines: list[str] | None = None,
    color: str = "#ffffff",
    size: float = 1.0,
) -> dict[str, Any]:
    """One Text Label, as `server/text_labels.lua` builds one."""
    return {
        "mapId": MAP_ID,
        "entityId": entity_id,
        "lines": ["hola"] if lines is None else lines,
        "color": color,
        "size": size,
    }


def send_labels(
    sandbox: MtaSandbox,
    labels: list[dict[str, Any]],
    *,
    distance: float = 25,
) -> None:
    """The label set arriving from the server, as it really arrives."""
    sandbox.eval(
        """
        function(labels, distance)
            triggerEvent(
                "ankigta:textLabels", resourceRoot, labels, distance
            )
        end
        """
    )(to_lua(sandbox, labels), distance)


def draw(sandbox: MtaSandbox) -> None:
    """One poll of each side, then one rendered frame.

    Both modules split the same way: which entities carry a mark is decided at
    the polling cadence, and the drawing follows the element per frame.
    """
    sandbox.eval("function() return ANKIGTA.WorldMarks.refresh() end")()
    sandbox.eval("function() return ANKIGTA.TextLabelDisplay.refresh() end")()
    sandbox.drawn_text.clear()
    sandbox.drawn_text_boxes.clear()
    sandbox.trigger("onClientRender")


def labelled_world(
    sandbox: MtaSandbox,
    labels: list[dict[str, Any]] | None = None,
    *,
    entities: list[str] | None = None,
    distance: float = 25,
) -> None:
    """Everything standing, snapshotted and labelled, ready to draw."""
    authorize(sandbox)
    for entity_id in entities or ["gate-17"]:
        standing(sandbox, entity_id=entity_id)
    push_snapshot(
        sandbox,
        [snapshot_entry(entity_id=entity_id) for entity_id in entities or ["gate-17"]],
    )
    send_labels(
        sandbox, labels if labels is not None else [label()], distance=distance
    )


def diagnostics(sandbox: MtaSandbox) -> dict[str, Any]:
    return dict(
        sandbox.to_python(
            sandbox.eval(
                "function() return ANKIGTA.TextLabelDisplay.diagnostics() end"
            )()
        )
    )


# --- the third Review Mode ---------------------------------------------------


def test_review_mode_offers_show_text_beside_the_two_it_had(
    client: MtaSandbox,
) -> None:
    definition = client.to_python(
        client.eval(
            """
            function()
                local rule = ANKIGTA.Settings.definition("reviewMode").rule
                return {
                    kind = rule.kind,
                    values = rule.values,
                    default = ANKIGTA.Settings.default("reviewMode"),
                }
            end
            """
        )()
    )

    assert definition["kind"] == "choice"
    assert sorted(definition["values"]) == ["allow_all", "allow_due", "show_text"]
    # And the mode a player already had is still the one they get.
    assert definition["default"] == "allow_due"


def test_each_of_the_three_settings_has_a_global_and_an_override(
    client: MtaSandbox,
) -> None:
    """The same shape the Activation Zone radius has: a value in Settings, and
    a NULL column on the Map Entity for the ones that answer for themselves."""
    described = client.to_python(
        client.eval(
            """
            function()
                local out = {}
                for _, key in ipairs({
                    "textLabelField", "textLabelColor", "textLabelSize"
                }) do
                    out[key] = {
                        kind = ANKIGTA.Settings.definition(key).rule.kind,
                        authority = ANKIGTA.Settings.authorityOf(key),
                        column = ANKIGTA.Settings.entityOverrideColumn(key),
                        field = ANKIGTA.Settings.entityOverrideField(key),
                    }
                end
                return out
            end
            """
        )()
    )

    assert described["textLabelField"]["column"] == "text_label_field_override"
    assert described["textLabelColor"]["column"] == "text_label_color_override"
    assert described["textLabelSize"]["column"] == "text_label_size_override"
    for key, entry in described.items():
        assert entry["authority"] == "server", key
        assert entry["field"] == key, key
    # The colour rule is ticket 04's, not a second one for this ticket.
    assert described["textLabelColor"]["kind"] == "color"


def test_the_distance_is_its_own_setting_and_not_the_activation_radius(
    client: MtaSandbox,
) -> None:
    """The Activation Zone radius is about opening cards and is unused here."""
    described = client.to_python(
        client.eval(
            """
            function()
                local rule = ANKIGTA.Settings.definition("textLabelDistance").rule
                return {
                    minimum = rule.minimum,
                    maximum = rule.maximum,
                    default = ANKIGTA.Settings.default("textLabelDistance"),
                    overridable = ANKIGTA.Settings.entityOverrideColumn(
                        "textLabelDistance"
                    ),
                }
            end
            """
        )()
    )

    assert described["default"] == 25
    # Global only: the ticket asks for one distance, not one per link.
    assert described["overridable"] is False


def test_the_distance_cannot_be_set_past_the_ceiling_everything_stops_at(
    client: MtaSandbox,
) -> None:
    """`client/world_marks.lua` stops everything ANKIGTA draws at its own
    distance. A label setting above it would read as saved and change nothing,
    so the rule refuses one -- and this is what pins the two numbers together
    rather than a comment in each file."""
    ceiling = client.eval("function() return ANKIGTA.WorldMarks.drawDistance() end")()
    maximum = client.eval(
        'function() return ANKIGTA.Settings.definition("textLabelDistance").rule.maximum end'
    )()

    assert maximum == ceiling
    refused, reason = client.eval(
        'function(v) return ANKIGTA.Settings.validate("textLabelDistance", v) end'
    )(ceiling + 1)
    assert refused is False
    assert reason == "settings.error.out_of_range"


# --- what is drawn -----------------------------------------------------------


def test_every_labelled_entity_in_range_carries_its_line(
    client: MtaSandbox,
) -> None:
    labelled_world(
        client,
        [
            label(entity_id="gate-17", lines=["hola"]),
            label(entity_id="gate-18", lines=["adios"]),
        ],
        entities=["gate-17", "gate-18"],
    )

    draw(client)

    assert "hola" in client.drawn_text
    assert "adios" in client.drawn_text
    assert diagnostics(client)["drawn"] == 2


def test_the_decision_is_polled_and_the_drawing_follows_the_element(
    client: MtaSandbox,
) -> None:
    """Which labels are near enough is a pass over every Spatial Link there is,
    so it happens on a timer rather than sixty times a second. Where the object
    has got to is read on the frame it is drawn, so a label on a vehicle keeps
    up with it rather than trailing a quarter of a second behind."""
    labelled_world(client, [label(lines=["hola"])])
    draw(client)
    element = client.eval(
        """
        function(mapId, entityId)
            return ANKIGTA.WorldMarks.elementFor(mapId, entityId)
        end
        """
    )(MAP_ID, "gate-17")
    before = min(
        box["left"] for box in client.drawn_text_boxes if box["text"] == "hola"
    )

    # The object moves, and only the frame is redrawn -- no poll.
    element["x"] = 4.0
    client.drawn_text.clear()
    client.drawn_text_boxes.clear()
    client.trigger("onClientRender")

    after = min(
        box["left"] for box in client.drawn_text_boxes if box["text"] == "hola"
    )
    assert after != before
    # And the poll really is a timer the resource started, not something a test
    # is calling on the code's behalf.
    assert client.eval(
        "function() return isTimer(ANKIGTA.TextLabelDisplay.timer) end"
    )() is True


def test_a_label_is_drawn_over_a_dark_outline_in_the_chosen_colour(
    client: MtaSandbox,
) -> None:
    """The outline is why a colour can be chosen freely: white text picked in
    daylight is unreadable against a white wall without it. That it *is*
    legible stays a manual item; that it is drawn is this."""
    labelled_world(client, [label(lines=["hola"], color="#ff8000")])

    draw(client)

    drawn = [box for box in client.drawn_text_boxes if box["text"] == "hola"]
    # Four offset passes and the line itself, at five distinct places.
    assert len(drawn) == 5
    assert len({(box["left"], box["top"]) for box in drawn}) == 5


def test_a_label_is_lifted_off_the_object_rather_than_drawn_inside_it(
    client: MtaSandbox,
) -> None:
    """A Map Entity's origin is usually its base, so a label drawn at it would
    sit inside whatever the object is."""
    labelled_world(client, [label(lines=["hola"])])

    draw(client)

    drawn = [box["top"] for box in client.drawn_text_boxes if box["text"] == "hola"]
    projected = client.eval(
        "function() return getScreenFromWorldPosition(0, 0, 0) end"
    )()
    object_y = projected[1]
    # Five draws: the line, and the four one-pixel outline passes around it.
    # The middle of them is where the line itself sits, and up on the screen is
    # a smaller y.
    assert sorted(drawn)[len(drawn) // 2] < object_y


def test_more_lines_are_stacked_rather_than_drawn_on_top_of_each_other(
    client: MtaSandbox,
) -> None:
    labelled_world(client, [label(lines=["one", "two", "three"])])

    draw(client)
    tops = {
        line: min(
            box["top"] for box in client.drawn_text_boxes if box["text"] == line
        )
        for line in ("one", "two", "three")
    }

    assert tops["one"] < tops["two"] < tops["three"]


def test_a_label_faces_the_player_from_whichever_side_they_look(
    client: MtaSandbox,
) -> None:
    """Drawn in screen space at the point the world position projects to, so
    there is no surface and no orientation to get wrong. A label you have to
    walk around is not a glance."""
    labelled_world(client, [label(lines=["hola"])])

    for camera in (
        (0.0, -10.0, 1.0, 0.0, 0.0, 1.0),
        (0.0, 10.0, 1.0, 0.0, 0.0, 1.0),
        (10.0, 0.0, 1.0, 0.0, 0.0, 1.0),
        (-10.0, 0.0, 1.0, 0.0, 0.0, 1.0),
    ):
        client.camera_matrix = camera
        draw(client)
        assert "hola" in client.drawn_text, camera


def test_a_label_behind_the_camera_is_not_drawn_at_all(
    client: MtaSandbox,
) -> None:
    """`getScreenFromWorldPosition` refuses rather than extrapolating, and the
    refusal is taken rather than worked around."""
    labelled_world(client, [label(lines=["hola"])])

    # Looking away from the object, which is still two metres behind.
    client.camera_matrix = (0.0, -2.0, 1.0, 0.0, -20.0, 1.0)
    draw(client)

    assert "hola" not in client.drawn_text


# --- when it is visible ------------------------------------------------------


def test_a_label_stops_at_the_distance_the_setting_names(
    client: MtaSandbox,
) -> None:
    labelled_world(
        client, [label(lines=["hola"])], distance=10
    )

    client.camera_matrix = (0.0, -8.0, 1.0, 0.0, 0.0, 1.0)
    draw(client)
    assert "hola" in client.drawn_text

    client.camera_matrix = (0.0, -12.0, 1.0, 0.0, 0.0, 1.0)
    draw(client)
    assert "hola" not in client.drawn_text


def test_the_outer_draw_rule_is_a_ceiling_rather_than_a_second_answer(
    client: MtaSandbox,
) -> None:
    """A distance the schema would refuse, forced onto the client the way a
    hand-edited value or an older server would: past the ceiling, the door does
    not draw it. The setting lives under the rule rather than instead of it."""
    labelled_world(client, [label(lines=["hola"])], distance=5000)

    ceiling = client.eval("function() return ANKIGTA.WorldMarks.drawDistance() end")()
    client.camera_matrix = (0.0, -(ceiling + 50), 1.0, 0.0, 0.0, 1.0)
    draw(client)

    assert "hola" not in client.drawn_text


def test_a_label_is_drawn_at_speed_because_reading_one_costs_nothing(
    client: MtaSandbox,
) -> None:
    """The Activation Zone has a speed gate because opening a card while
    driving is a card you cannot read and did not ask for. A label covers
    nothing and demands nothing (ADR 0029)."""
    labelled_world(client, [label(lines=["hola"])])
    client.player_velocity = (2.0, 0.0, 0.0)

    draw(client)

    assert "hola" in client.drawn_text


def test_a_label_in_another_dimension_is_not_drawn_through_it(
    client: MtaSandbox,
) -> None:
    authorize(client)
    element = standing(client)
    element["dimension"] = 7
    push_snapshot(client, [snapshot_entry()])
    send_labels(client, [label(lines=["hola"])])

    draw(client)

    assert "hola" not in client.drawn_text


# --- the cap -----------------------------------------------------------------


def maximum_drawn(sandbox: MtaSandbox) -> int:
    return int(sandbox.eval("function() return ANKIGTA.TextLabel.MAX_DRAWN end")())


def crowd(sandbox: MtaSandbox, count: int) -> None:
    """`count` labelled entities, each one metre further from the camera."""
    authorize(sandbox)
    entries, labels = [], []
    for index in range(count):
        entity_id = "gate-%02d" % index
        standing(sandbox, entity_id=entity_id, x=float(index))
        entries.append(snapshot_entry(entity_id=entity_id))
        labels.append(label(entity_id=entity_id, lines=["line-%02d" % index]))
    push_snapshot(sandbox, entries)
    send_labels(sandbox, labels, distance=150)


def test_the_cap_keeps_the_nearest_and_reports_what_it_dropped(
    client: MtaSandbox,
) -> None:
    """A cap applied quietly reads as "that is all there is", and a player
    standing in a room they filled with cards would conclude the rest never got
    linked."""
    limit = maximum_drawn(client)
    crowd(client, limit + 3)
    # Looking along +x from just before the first object, so "nearest" is the
    # lowest index and the order is not the one the snapshot happened to have.
    client.camera_matrix = (-1.0, 0.0, 1.0, 20.0, 0.0, 1.0)

    draw(client)

    assert diagnostics(client)["drawn"] == limit
    assert diagnostics(client)["dropped"] == 3
    assert "line-00" in client.drawn_text
    assert "line-%02d" % (limit + 2) not in client.drawn_text
    # And the number dropped is on screen, not only in a report.
    assert any("3" in line for line in client.drawn_text if "more" in line)


def test_what_was_dropped_survives_the_frame_it_was_dropped_in(
    client: MtaSandbox,
) -> None:
    """The notice on screen goes with the frame. A bug report is written
    afterwards, so the number is in the diagnostics too."""
    limit = maximum_drawn(client)
    crowd(client, limit + 3)
    client.camera_matrix = (-1.0, 0.0, 1.0, 20.0, 0.0, 1.0)
    draw(client)

    report = client.to_python(
        client.eval("function() return ANKIGTA.Diagnostics.snapshot() end")()
    )

    assert dict(report["textLabels"])["dropped"] == 3
    assert dict(report["textLabels"])["labels"] == limit + 3


def test_two_labels_at_the_same_distance_drop_in_a_repeatable_order(
    client: MtaSandbox,
) -> None:
    """`shared/nearest.lua`'s order, the one the Activation Zone and the Next
    Card Indicator use: a tie resolves on Map Entity identity rather than on
    whichever the snapshot happened to put first, so the same world drops the
    same ones every run."""
    ordered = client.to_python(
        client.eval(
            """
            function()
                local observer = {x = 0, y = 0, z = 0, interior = 0, dimension = 0}
                local labels = {
                    {mapId = "m", entityId = "b", lines = {"b"}},
                    {mapId = "m", entityId = "a", lines = {"a"}},
                }
                local entries = ANKIGTA.TextLabelDisplay.plan(
                    observer, labels, 50,
                    function(item)
                        return {
                            x = 1, y = 0, z = 0, interior = 0, dimension = 0,
                        }
                    end
                )
                local out = {}
                for index, entry in ipairs(entries) do
                    out[index] = entry.entityId
                end
                return out
            end
            """
        )()
    )

    assert list(ordered) == ["a", "b"]


# --- one entity shows one thing ----------------------------------------------


def offer_on(sandbox: MtaSandbox, entity_id: str = "gate-17") -> None:
    """The `<KEY> to view` offer standing on an entity, as ticket 05 makes one."""
    sandbox.eval(
        """
        function(links)
            triggerEvent("ankigta:spatialCandidates", resourceRoot, links)
        end
        """
    )(
        to_lua(
            sandbox,
            [
                {
                    "mapId": MAP_ID,
                    "entityId": entity_id,
                    "cardIdentity": {"collectionUuid": UUID, "cardId": 42},
                    "radius": 3,
                    "eligible": True,
                    "activationType": "key",
                }
            ],
        )
    )
    sandbox.eval("function() return ANKIGTA.Spatial.tick() end")()


def test_the_key_prompt_is_drawn_where_no_label_has_taken_the_entity(
    client: MtaSandbox,
) -> None:
    """The other half of the rule, so the rule below is not passing because the
    prompt never appears at all."""
    authorize(client)
    standing(client)
    push_snapshot(client, [snapshot_entry()])
    offer_on(client)

    draw(client)

    assert "E to view" in client.drawn_text


def test_an_entity_never_shows_a_label_and_the_key_prompt_at_once(
    client: MtaSandbox,
) -> None:
    """Both are text drawn on a Map Entity, and one entity shows one thing.
    The entity that has a Text Label is the one that shows text."""
    authorize(client)
    standing(client)
    push_snapshot(client, [snapshot_entry()])
    offer_on(client)
    send_labels(client, [label(lines=["hola"])])

    draw(client)

    assert "hola" in client.drawn_text
    assert "E to view" not in client.drawn_text


def test_the_prompt_comes_back_when_the_label_set_empties(
    client: MtaSandbox,
) -> None:
    """Leaving the mode is an empty set arriving, and the offer is the
    entity's again."""
    authorize(client)
    standing(client)
    push_snapshot(client, [snapshot_entry()])
    offer_on(client)
    send_labels(client, [label(lines=["hola"])])
    draw(client)

    send_labels(client, [])
    draw(client)

    assert "hola" not in client.drawn_text
    assert "E to view" in client.drawn_text


def test_a_label_on_another_entity_does_not_hold_this_ones_prompt_back(
    client: MtaSandbox,
) -> None:
    authorize(client)
    standing(client, entity_id="gate-17")
    standing(client, entity_id="gate-18", x=40.0)
    push_snapshot(
        client,
        [snapshot_entry(entity_id="gate-17"), snapshot_entry(entity_id="gate-18")],
    )
    offer_on(client, "gate-17")
    send_labels(client, [label(entity_id="gate-18", lines=["hola"])])

    draw(client)

    assert "E to view" in client.drawn_text


# --- the server decides what each label says ---------------------------------


def publish_connection(sandbox: MtaSandbox) -> None:
    """The connection file exactly as the companion add-on publishes it.

    Written even though most of what follows never asks Anki anything: the two
    paths that *do* -- writing a new link's words down, and reading a note back
    after a save -- have to be able to reach a gateway, and a mode that works
    with Anki shut is only interesting if it could have asked.
    """
    sandbox.write_file(
        "connection.json",
        json.dumps(
            {
                "format": "ankigta-connection",
                "formatVersion": 1,
                "protocol": "ankigta-control",
                "protocolVersion": 1,
                "revision": 1,
                "host": "127.0.0.1",
                "automatic": {"port": 32145, "token": "show-text-token"},
                "companion": {"mode": "automatic"},
            }
        ),
    )


@pytest.fixture
def server(tmp_path: Path) -> Iterator[MtaSandbox]:
    sandbox = MtaSandbox(database_path=str(tmp_path / "ankigta.sqlite"))
    try:
        for script in manifest_scripts("shared", "server"):
            sandbox.load(script)
        sandbox.trigger("onResourceStart")
        publish_connection(sandbox)
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


def seed_link(
    sandbox: MtaSandbox, entity_id: str = "gate-17", card_id: int = 42
) -> None:
    sandbox.connection.raw.execute(
        "INSERT OR REPLACE INTO spatial_links (map_id, entity_id,"
        " collection_uuid, card_id, state, verified_map_sha256)"
        " VALUES (?, ?, ?, ?, 'active', ?)",
        (MAP_ID, entity_id, UUID, card_id, "a" * 64),
    )
    sandbox.connection.raw.commit()


def load_map(sandbox: MtaSandbox, entity_id: str = "gate-17") -> Any:
    """The map really in the world, which is what `World.loadedMapIds` narrows
    the label set to."""
    owner = sandbox.add_resource("current-map", resource_type="map")
    element = sandbox.add_world_element(
        ankigtaEntityId=entity_id, map_id=MAP_ID
    )
    element["__parent"] = owner
    return element


def cache_note(
    sandbox: MtaSandbox, fields: list[tuple[str, str]], card_id: int = 42
) -> None:
    sandbox.eval(
        """
        function(uuid, cardId, fields)
            return ANKIGTA.Store.cacheCardNote(
                {collectionUuid = uuid, cardId = cardId}, fields
            )
        end
        """
    )(
        UUID,
        card_id,
        to_lua(
            sandbox,
            [{"name": name, "value": value} for name, value in fields],
        ),
    )


def set_setting(sandbox: MtaSandbox, player: Any, key: str, value: Any) -> None:
    sandbox.trigger(
        "ankigta:updateSetting",
        sandbox.lua.globals().resourceRoot,
        key,
        value,
        client=player,
    )


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


def sent_labels(sandbox: MtaSandbox) -> list[dict[str, Any]]:
    events = [
        event
        for event in sandbox.recorder.client_events
        if event.name == "ankigta:textLabels"
    ]
    assert events, "no label set was ever sent"
    return [dict(entry) for entry in sandbox.to_python(events[-1].args[0])]


def sent_distance(sandbox: MtaSandbox) -> float:
    events = [
        event
        for event in sandbox.recorder.client_events
        if event.name == "ankigta:textLabels"
    ]
    return float(events[-1].args[1])


def showing_text(
    sandbox: MtaSandbox,
    *,
    fields: list[tuple[str, str]] | None = None,
) -> Any:
    """One linked, loaded, cached Map Entity with the mode turned on."""
    seed_entity(sandbox)
    seed_link(sandbox)
    load_map(sandbox)
    player = sandbox.add_study_player()
    cache_note(
        sandbox, fields if fields is not None else [("Front", "hola")]
    )
    set_setting(sandbox, player, "reviewMode", "show_text")
    return player


def test_a_linked_entity_gets_the_words_behind_its_card(
    server: MtaSandbox,
) -> None:
    showing_text(server, fields=[("Front", "hola"), ("Back", "hello")])

    labels = sent_labels(server)

    assert len(labels) == 1
    assert labels[0]["entityId"] == "gate-17"
    assert list(labels[0]["lines"]) == ["hola"]


def test_outside_the_mode_the_set_is_empty(server: MtaSandbox) -> None:
    """Which is how the labels go away. A client that simply stopped hearing
    about them would go on drawing the last set it was given."""
    player = showing_text(server)
    assert sent_labels(server) != []

    set_setting(server, player, "reviewMode", "allow_due")

    assert sent_labels(server) == []


def test_the_global_field_decides_what_every_label_shows(
    server: MtaSandbox,
) -> None:
    player = showing_text(server, fields=[("Front", "hola"), ("Back", "hello")])

    set_setting(server, player, "textLabelField", "Back")

    assert list(sent_labels(server)[0]["lines"]) == ["hello"]


def test_one_entity_can_say_otherwise_and_the_rest_do_not_move(
    server: MtaSandbox,
) -> None:
    seed_entity(server, "gate-17")
    seed_entity(server, "gate-18")
    seed_link(server, "gate-17", card_id=42)
    seed_link(server, "gate-18", card_id=43)
    load_map(server, "gate-17")
    load_map(server, "gate-18")
    player = server.add_study_player()
    cache_note(server, [("Front", "hola"), ("Back", "hello")], card_id=42)
    cache_note(server, [("Front", "adios"), ("Back", "goodbye")], card_id=43)
    set_setting(server, player, "reviewMode", "show_text")

    write_metadata(server, player, {"textLabelField": "Back"}, entity_id="gate-17")

    by_entity = {entry["entityId"]: entry for entry in sent_labels(server)}
    # The one told otherwise shows `Back`; the other still shows the first
    # field with words, which is its own `Front`.
    assert list(by_entity["gate-17"]["lines"]) == ["hello"]
    assert list(by_entity["gate-18"]["lines"]) == ["adios"]


def test_the_colour_and_size_travel_with_each_label(server: MtaSandbox) -> None:
    player = showing_text(server)

    set_setting(server, player, "textLabelColor", "#ff8000")
    write_metadata(server, player, {"textLabelSize": 2.5})

    label_sent = sent_labels(server)[0]
    assert label_sent["color"] == "#ff8000"
    assert label_sent["size"] == 2.5


def test_the_distance_travels_with_the_set(server: MtaSandbox) -> None:
    player = showing_text(server)

    set_setting(server, player, "textLabelDistance", 60)

    assert sent_distance(server) == 60


def test_an_override_reaches_the_client_without_anki_being_asked(
    server: MtaSandbox,
) -> None:
    """The defect ticket 05 found, in a mode that never asks Anki at all: the
    watched set used to be rebuilt only on the way back from the companion, so
    an override sat in the store until something else happened to ask."""
    player = showing_text(server, fields=[("Front", "hola"), ("Back", "hello")])
    before = len(server.recorder.remote_fetches)

    write_metadata(server, player, {"textLabelField": "Back"})

    assert list(sent_labels(server)[0]["lines"]) == ["hello"]
    assert len(server.recorder.remote_fetches) == before


def test_clearing_an_override_everywhere_covers_these_three_too(
    server: MtaSandbox,
) -> None:
    """Ticket 05's sweep walks the settings that have overrides rather than a
    list, so these were covered by being declared."""
    player = showing_text(server)
    write_metadata(server, player, {"textLabelField": "Back"})

    server.trigger(
        "ankigta:clearEntityOverrides",
        server.lua.globals().resourceRoot,
        "textLabelField",
        True,
        client=player,
    )

    row = server.connection.raw.execute(
        "SELECT text_label_field_override FROM map_entity_metadata"
        " WHERE entity_id = 'gate-17'"
    ).fetchone()
    assert row[0] is None


def test_an_override_is_cleared_by_the_same_word_every_other_one_uses(
    server: MtaSandbox,
) -> None:
    """`"inherit"`, not `false`: `false` is a value `Show corona` can hold, so
    it cannot also be how a field says it holds nothing."""
    player = showing_text(server)
    write_metadata(server, player, {"textLabelColor": "#ff8000"})

    write_metadata(server, player, {"textLabelColor": "inherit"})

    row = server.connection.raw.execute(
        "SELECT text_label_color_override FROM map_entity_metadata"
        " WHERE entity_id = 'gate-17'"
    ).fetchone()
    assert row[0] is None


def test_a_colour_the_picker_would_refuse_is_refused_on_a_link_too(
    server: MtaSandbox,
) -> None:
    """A value cannot be legal in Settings and illegal on a row, or the other
    way round: both are checked against the schema's own rule."""
    player = showing_text(server)
    write_metadata(server, player, {"textLabelColor": "#ff8000"})

    write_metadata(server, player, {"textLabelColor": "not-a-colour"})

    row = server.connection.raw.execute(
        "SELECT text_label_color_override FROM map_entity_metadata"
        " WHERE entity_id = 'gate-17'"
    ).fetchone()
    # Refused, so what the entity already said stands.
    assert row[0] == "#ff8000"
    refusals = [
        server.to_python(event.args)
        for event in server.recorder.client_events
        if event.name == "ankigta:pendingMapSaveNotice"
    ]
    assert refusals[-1][1] == "settings.error.not_a_color"


# --- when a field cannot be shown --------------------------------------------


def test_a_missing_field_falls_through_to_the_first_with_words(
    server: MtaSandbox,
) -> None:
    player = showing_text(server, fields=[("Front", "hola")])

    set_setting(server, player, "textLabelField", "Meaning")

    label_sent = sent_labels(server)[0]
    assert list(label_sent["lines"]) == ["hola"]
    assert label_sent["fallback"] is True
    assert label_sent["reason"] == "field_missing"


def test_a_wordless_field_falls_through_and_says_which_kind_it_was(
    server: MtaSandbox,
) -> None:
    player = showing_text(
        server, fields=[("Front", "[sound:hola.mp3]"), ("Back", "hello")]
    )

    set_setting(server, player, "textLabelField", "Front")

    label_sent = sent_labels(server)[0]
    assert list(label_sent["lines"]) == ["hello"]
    assert label_sent["reason"] == "field_wordless"


def test_a_note_with_nothing_to_say_is_not_sent_as_a_blank_label(
    server: MtaSandbox,
) -> None:
    """There is no such thing as an empty Text Label: an object wearing a blank
    line reads as broken. The row in the panel is where it is said."""
    showing_text(server, fields=[("Front", "[sound:hola.mp3]")])

    assert sent_labels(server) == []


def test_a_link_whose_words_were_never_read_says_so_on_its_row(
    server: MtaSandbox,
) -> None:
    """Silence would be indistinguishable from a note that says nothing."""
    seed_entity(server)
    seed_link(server)
    load_map(server)
    player = server.add_study_player()

    server.trigger(
        "ankigta:requestF7", server.lua.globals().resourceRoot, client=player
    )
    snapshot = server.to_python(
        [
            event
            for event in server.recorder.client_events
            if event.name == "ankigta:f7Snapshot"
        ][-1].args[0]
    )
    row = list(snapshot["entities"])[0]

    assert dict(row["textLabel"])["reason"] == "not_cached"


def test_an_unlinked_row_has_no_label_at_all(server: MtaSandbox) -> None:
    seed_entity(server)
    load_map(server)
    player = server.add_study_player()

    server.trigger(
        "ankigta:requestF7", server.lua.globals().resourceRoot, client=player
    )
    snapshot = server.to_python(
        [
            event
            for event in server.recorder.client_events
            if event.name == "ankigta:f7Snapshot"
        ][-1].args[0]
    )

    assert list(snapshot["entities"])[0]["textLabel"] is False


def test_the_row_carries_the_lines_the_world_draws(server: MtaSandbox) -> None:
    """Rather than a second rendering of the same note that could disagree
    with it."""
    player = showing_text(server, fields=[("Front", "hola amigo")])

    server.trigger(
        "ankigta:requestF7", server.lua.globals().resourceRoot, client=player
    )
    snapshot = server.to_python(
        [
            event
            for event in server.recorder.client_events
            if event.name == "ankigta:f7Snapshot"
        ][-1].args[0]
    )
    row = dict(list(snapshot["entities"])[0]["textLabel"])

    assert list(row["lines"]) == list(sent_labels(server)[0]["lines"])


# --- where the words live ----------------------------------------------------


def test_labels_are_drawn_with_anki_shut(server: MtaSandbox) -> None:
    """The cache is the whole of what a label is read from, so the mode works
    with the companion disconnected -- which is most of why the cache exists."""
    showing_text(server)
    before = len(server.recorder.remote_fetches)

    labels = sent_labels(server)

    assert list(labels[0]["lines"]) == ["hola"]
    assert len(server.recorder.remote_fetches) == before


def note_reads(sandbox: MtaSandbox) -> list[dict[str, Any]]:
    return [
        fetch
        for fetch in sandbox.recorder.remote_fetches
        if str(fetch["url"]).endswith("/v1/notes/read")
    ]


def answer(
    sandbox: MtaSandbox,
    fetch: dict[str, Any],
    payload: dict[str, Any],
    *,
    status: int = 200,
) -> None:
    """Answer one recorded request the way the companion really answers it.

    The envelope is the gateway's own: it refuses a reply whose `requestId` is
    not the one it sent, so a double that invented one would be answering a
    question nobody asked.
    """
    index = sandbox.recorder.remote_fetches.index(fetch)
    sent = json.loads(fetch["options"]["postData"])
    sandbox.complete_fetch(
        index,
        status=status,
        body=""
        if status != 200
        else json.dumps(
            {
                "protocol": "ankigta-control",
                "protocolVersion": 1,
                "requestId": sent["requestId"],
                "ok": True,
                "error": None,
                "payload": payload,
            }
        ),
    )


def test_making_a_link_writes_the_words_down(server: MtaSandbox) -> None:
    """So a Text Label is there from the moment the link is, and stays there
    once Anki is shut.

    Through the real Link path -- the stock Map Editor open on a saved map,
    which is the only arrangement in which a card can be linked at all."""
    editor_root = server.add_resource("editor_main")
    server.editor_map_name = "mymap"
    server.editor_working_dimension = 200
    server.write_file(":mymap/meta.xml", '<meta><map src="mymap.map" /></meta>')
    server.write_file(":mymap/mymap.map", "<map></map>")
    connection = server.connection.raw
    connection.execute(
        "INSERT OR IGNORE INTO maps (map_id, resource_name, map_name)"
        " VALUES ('mymap', 'mymap', 'mymap')"
    )
    connection.execute(
        "INSERT OR REPLACE INTO map_entities (map_id, entity_id, entity_type,"
        " model, authored_x, authored_y, authored_z, rotation_x, rotation_y,"
        " rotation_z, interior, dimension)"
        " VALUES ('mymap', 'object (bin) (1)', 'object', 1337,"
        " 0, 0, 0, 0, 0, 0, 0, 0)"
    )
    connection.commit()
    element = server.add_world_element(
        map_id="object (bin) (1)",
        dimension=200,
        ankigtaEntityId="object (bin) (1)",
    )
    element["__parent"] = editor_root
    server.add_edf_representation(element)
    player = server.add_study_player()
    player["x"], player["y"], player["z"] = 0, 0, 0
    player["dimension"] = 200
    before = len(note_reads(server))

    server.trigger(
        "ankigta:linkCardToEntity",
        server.lua.globals().resourceRoot,
        "mymap",
        "object (bin) (1)",
        to_lua(server, {"collectionUuid": UUID, "cardId": 42}),
        client=player,
    )

    failures = [
        server.to_python(event.args)
        for event in server.recorder.client_events
        if event.name == "ankigta:pendingMapSaveNotice"
    ]
    assert failures == [], failures
    asked = note_reads(server)[before:]
    assert len(asked) == 1
    assert json.loads(asked[-1]["options"]["postData"])["cardIdentities"] == [
        {"collectionUuid": UUID, "cardId": 42}
    ]


def test_arriving_in_the_mode_asks_anki_for_every_linked_note(
    server: MtaSandbox,
) -> None:
    """A note edited in Anki itself while the player was in another mode was
    never seen here, and the labels would open saying what the card stopped
    saying."""
    showing_text(server)

    asked = note_reads(server)
    assert len(asked) == 1
    assert json.loads(asked[-1]["options"]["postData"])["cardIdentities"] == [
        {"collectionUuid": UUID, "cardId": 42}
    ]


def test_the_words_read_back_from_anki_are_what_gets_cached_and_drawn(
    server: MtaSandbox,
) -> None:
    showing_text(server)

    answer(
        server,
        note_reads(server)[-1],
        {
            "notes": [
                {
                    "identity": {"collectionUuid": UUID, "cardId": 42},
                    "noteId": 3,
                    "fields": [{"name": "Front", "value": "nuevo"}],
                }
            ]
        },
    )

    cached = server.to_python(
        server.eval("function() return ANKIGTA.Store.cachedCardNotes() end")()
    )
    fields = list(cached[f"{UUID}/42"])
    assert dict(fields[0])["value"] == "nuevo"
    # And the world is told, rather than waiting for the next thing to happen.
    assert list(sent_labels(server)[0]["lines"]) == ["nuevo"]


def test_a_refusal_leaves_the_words_already_written_down_alone(
    server: MtaSandbox,
) -> None:
    """A stale line is a line the note really said once; an empty one would say
    the note is blank, which is a different and false claim."""
    showing_text(server)

    answer(server, note_reads(server)[-1], {}, status=503)

    assert list(sent_labels(server)[0]["lines"]) == ["hola"]


def test_saving_the_note_in_the_inspector_moves_the_label(
    server: MtaSandbox,
) -> None:
    """Taken from what Anki answered rather than from what was typed: Anki may
    rewrite a field on save, and a label showing the typed text would disagree
    with the card it came from."""
    player = showing_text(server)

    server.trigger(
        "ankigta:updateNote",
        server.lua.globals().resourceRoot,
        to_lua(server, {"collectionUuid": UUID, "cardId": 42}),
        to_lua(server, [{"name": "Front", "value": "typed"}]),
        to_lua(server, []),
        client=player,
    )
    answer(
        server,
        [
            fetch
            for fetch in server.recorder.remote_fetches
            if str(fetch["url"]).endswith("/v1/notes/update")
        ][-1],
        {
            "note": {
                "noteId": 3,
                "fields": [{"name": "Front", "value": "stored"}],
                "tags": [],
            }
        },
    )

    assert list(sent_labels(server)[0]["lines"]) == ["stored"]


def test_unlinking_drops_the_copy_of_the_card_it_kept(
    server: MtaSandbox,
) -> None:
    """Keeping it would be a copy of somebody's card held after they said to
    forget it (ADR 0017)."""
    player = showing_text(server)

    server.trigger(
        "ankigta:unlinkCardFromEntity",
        server.lua.globals().resourceRoot,
        MAP_ID,
        "gate-17",
        to_lua(server, {"collectionUuid": UUID, "cardId": 42}),
        client=player,
    )

    cached = server.to_python(
        server.eval("function() return ANKIGTA.Store.cachedCardNotes() end")()
    )
    assert dict(cached) == {}


def test_a_note_cached_for_one_card_serves_every_entity_holding_it(
    server: MtaSandbox,
) -> None:
    """Keyed by Anki Card Identity rather than by link: one card may hang on
    several Map Entity, and one copy of its words is enough for all of them."""
    seed_entity(server, "gate-17")
    seed_entity(server, "gate-18")
    seed_link(server, "gate-17", card_id=42)
    seed_link(server, "gate-18", card_id=42)
    load_map(server, "gate-17")
    load_map(server, "gate-18")
    player = server.add_study_player()
    cache_note(server, [("Front", "hola")], card_id=42)

    set_setting(server, player, "reviewMode", "show_text")

    assert sorted(entry["entityId"] for entry in sent_labels(server)) == [
        "gate-17",
        "gate-18",
    ]


# --- what an older database gains --------------------------------------------


def test_a_database_from_an_older_build_gains_the_three_override_columns(
    tmp_path: Path,
) -> None:
    """Ticket 05's migration probes the shape rather than the version number
    and covers every override the schema declares, so these three arrived by
    being declared -- not by being added to a list.

    Derived from the schema here too: a fourth setting gaining an override
    without gaining a column fails this rather than going unnoticed."""
    from tests.lua import shipped_schemas

    database = tmp_path / "ankigta.sqlite"
    shipped_schemas.build(database, "v7", history=True)
    sandbox = MtaSandbox(database_path=str(database))
    try:
        sandbox.load("shared/settings.lua")
        sandbox.load("server/backup.lua")
        sandbox.load("server/store.lua")
        assert (
            sandbox.eval("function() return ANKIGTA.Store.open() end")() is True
        )
        wanted = sandbox.to_python(
            sandbox.eval(
                """
                function()
                    local out = {}
                    for _, key in ipairs(
                        ANKIGTA.Settings.entityOverridableKeys()
                    ) do
                        out[#out + 1] =
                            ANKIGTA.Settings.entityOverrideColumn(key)
                    end
                    return out
                end
                """
            )()
        )
    finally:
        sandbox.close()

    import sqlite3

    columns = {
        row[1]
        for row in sqlite3.connect(database)
        .execute("PRAGMA table_info(map_entity_metadata)")
        .fetchall()
    }
    assert set(str(name) for name in wanted) <= columns
    assert "text_label_field_override" in columns


def test_a_database_from_an_older_build_gains_somewhere_to_cache_notes(
    tmp_path: Path,
) -> None:
    from tests.lua import shipped_schemas

    database = tmp_path / "ankigta.sqlite"
    shipped_schemas.build(database, "v7", history=True)
    sandbox = MtaSandbox(database_path=str(database))
    try:
        sandbox.load("shared/settings.lua")
        sandbox.load("server/backup.lua")
        sandbox.load("server/store.lua")
        assert (
            sandbox.eval("function() return ANKIGTA.Store.open() end")() is True
        )
        cached = sandbox.eval(
            "function() return ANKIGTA.Store.cachedCardNotes() end"
        )()
    finally:
        sandbox.close()

    assert cached is not False


def test_a_cached_note_outlives_nothing_that_still_points_at_it(
    server: MtaSandbox,
) -> None:
    """The prune is by link rather than by age: a copy of somebody's card is
    kept for exactly as long as something points at it."""
    seed_entity(server)
    seed_link(server)
    cache_note(server, [("Front", "hola")], card_id=42)
    cache_note(server, [("Front", "orphan")], card_id=99)

    server.eval("function() return ANKIGTA.Store.pruneCardNoteCache() end")()

    cached = dict(
        server.to_python(
            server.eval("function() return ANKIGTA.Store.cachedCardNotes() end")()
        )
    )
    assert sorted(cached) == [f"{UUID}/42"]


# --- nothing is presented and nothing is rated -------------------------------


def test_the_review_surface_refuses_to_open_in_this_mode(
    server: MtaSandbox,
) -> None:
    """The one door into Review Mode, so this is the one place that has to
    refuse. ADR 0027 lets a *badly* presented card be rated because the player
    saw it; here there is nothing to have seen."""
    player = showing_text(server)

    opened, reason = server.eval(
        """
        function(player, uuid)
            return openReviewModeFor(player, {collectionUuid = uuid, cardId = 42})
        end
        """
    )(player, UUID)

    assert opened is False
    assert reason == "show_text_mode"


def test_walking_into_a_zone_cannot_open_a_card_either(
    server: MtaSandbox,
) -> None:
    """Spatial opening is not a second way in, so it refuses through the same
    door rather than beside it."""
    player = showing_text(server)

    opened, reason = server.eval(
        """
        function(player)
            return openSpatialReview(player, "%s", "gate-17", false)
        end
        """
        % MAP_ID
    )(player)

    assert opened is False
    assert reason == "show_text_mode"


def test_no_session_is_built_so_no_filtered_deck_is_asked_for(
    server: MtaSandbox,
) -> None:
    """No filtered deck, no Exact Card Admission, no Review Transaction and no
    counters (ADR 0029). Building one would leave a filtered deck in somebody's
    collection for a mode that never rates a card in it."""
    player = showing_text(server)
    before = len(server.recorder.remote_fetches)

    server.trigger(
        "ankigta:startStudy",
        server.lua.globals().resourceRoot,
        None,
        client=player,
    )

    assert [
        fetch
        for fetch in server.recorder.remote_fetches[before:]
        if "/v1/session/" in fetch["url"]
    ] == []
    notices = [
        server.to_python(event.args)
        for event in server.recorder.client_events
        if event.name == "ankigta:pendingMapSaveNotice"
    ]
    assert notices[-1][1] == "show_text_mode"


def test_the_counters_are_empty_and_nothing_is_watched(
    server: MtaSandbox,
) -> None:
    """No progress counters, and no Activation Zone to walk into."""
    player = showing_text(server)

    server.trigger(
        "ankigta:sessionInvalidated",
        server.lua.globals().resourceRoot,
        player,
        False,
        False,
        "test",
    )

    watched = [
        server.to_python(event.args[0])
        for event in server.recorder.client_events
        if event.name == "ankigta:spatialCandidates"
    ]
    assert list(watched[-1]) == []
    counts = [
        server.to_python(event.args[0])
        for event in server.recorder.client_events
        if event.name == "ankigta:statistics"
    ]
    assert dict(counts[-1])["total"] == 0


def test_the_card_states_query_is_not_asked_in_this_mode(
    server: MtaSandbox,
) -> None:
    """Which is what makes the mode work with Anki shut: the one question this
    resource asks per refresh is one this mode has no use for."""
    player = showing_text(server)
    before = len(server.recorder.remote_fetches)

    server.trigger(
        "ankigta:sessionInvalidated",
        server.lua.globals().resourceRoot,
        player,
        False,
        False,
        "test",
    )

    assert [
        fetch
        for fetch in server.recorder.remote_fetches[before:]
        if fetch["url"].endswith("/v1/cards/states")
    ] == []


# --- the words the panel uses for its own rows -------------------------------


def test_the_card_row_no_longer_calls_its_heading_a_label(
    client: MtaSandbox,
) -> None:
    """`label` collided with **Text Label**, which is a line drawn on a Map
    Entity and a different thing entirely. The Card Picker's row is headed by
    what Anki lists the note by, so it is called what Anki calls it."""
    authorize(client)
    client.eval(
        """
        function()
            if not ANKIGTA.Panel.isOpen() then togglePanel() end
            triggerEvent("ankigta:panelAction", resourceRoot, "ready", "{}")
        end
        """
    )()
    client.eval(
        """
        function(uuid)
            triggerEvent("ankigta:cardPickerSnapshot", resourceRoot, {
                enabled = true,
                cards = {
                    {identity = {collectionUuid = uuid, cardId = 7},
                     deck = {name = "Deck"}, state = "review",
                     sortField = "Hola"},
                },
            })
        end
        """
    )(UUID)

    row = client.pushed_panel_state()["cardPicker"]["cards"][0]

    assert row["sortField"] == "Hola"
    assert "label" not in row


def test_the_panel_says_that_reading_does_not_rate_where_the_mode_is_chosen(
    client: MtaSandbox,
) -> None:
    """A player who reads a label, believes they have repeated the card and
    finds the scheduler never saw it is worse off than one who has no such
    mode. So it is said on the screen rather than implied."""
    authorize(client)
    client.eval(
        """
        function()
            if not ANKIGTA.Panel.isOpen() then togglePanel() end
            triggerEvent("ankigta:panelAction", resourceRoot, "ready", "{}")
            triggerEvent("ankigta:panelAction", resourceRoot, "openSettings", "{}")
        end
        """
    )()
    state = client.pushed_panel_state()
    row = [
        entry for entry in state["settings"]["rows"] if entry["key"] == "reviewMode"
    ][0]

    assert row["noteKey"] == "settings.reviewMode.note"
    words = state["locale"][row["noteKey"]]
    assert "not rated" in words or "no repetition" in words


def test_only_a_setting_with_something_to_say_carries_a_note(
    client: MtaSandbox,
) -> None:
    """A setting gains one by gaining the string, so the panel keeps no list of
    which rows have one -- and one that has nothing extra to say has none."""
    authorize(client)
    client.eval(
        """
        function()
            if not ANKIGTA.Panel.isOpen() then togglePanel() end
            triggerEvent("ankigta:panelAction", resourceRoot, "ready", "{}")
            triggerEvent("ankigta:panelAction", resourceRoot, "openSettings", "{}")
        end
        """
    )()
    rows = client.pushed_panel_state()["settings"]["rows"]

    with_note = {row["key"] for row in rows if row["noteKey"]}
    assert with_note == {"reviewMode"}


def test_the_size_a_row_reports_is_at_the_precision_its_rule_declares(
    client: MtaSandbox,
) -> None:
    """Every server-owned number crosses the wire as a 32-bit float, so a
    stored `1.15` arrives as `1.14999998`. Ticket 08 put that right at the
    boundary for every numeric setting; this is the new one going through it."""
    authorize(client)
    client.eval(
        """
        function()
            if not ANKIGTA.Panel.isOpen() then togglePanel() end
            triggerEvent("ankigta:panelAction", resourceRoot, "ready", "{}")
        end
        """
    )()
    push_snapshot(
        client,
        [
            {
                **snapshot_entry(),
                "metadata": {
                    "name": "",
                    "entityTag": "",
                    "textLabelSize": 1.1499999761581421,
                },
            }
        ],
    )

    row = client.pushed_panel_state()["entities"][0]

    assert row["textLabelSize"] == 1.15
    assert row["textLabelSizeInherited"] is False
