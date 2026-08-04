"""Ticket 31 — the Map Entity filter story 51 asks for.

Ticket 30 recorded that F7's list had no search or filter surface while story
51 requires one and story 58 puts 150 ms on it. This is that surface.

The rule under test is the one that is easy to get wrong: filtering is over the
stored record, so an entity whose Runtime Instance is gone is found by the same
words that find one standing in front of you.
"""

from __future__ import annotations

import json
from typing import Any, Iterator

import pytest

from tests.lua import MtaSandbox


UUID = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def f7() -> Iterator[MtaSandbox]:
    sandbox = MtaSandbox()
    sandbox.load("shared/settings.lua")
    sandbox.load("shared/locale.lua")
    sandbox.load("shared/entity_types.lua")
    sandbox.load("client/layout.lua")
    sandbox.load("client/panel.lua")
    sandbox.eval('function() ANKIGTA.Locale.setLanguage("en") end')()
    try:
        yield sandbox
    finally:
        sandbox.close()


def entry(
    entity_id: str,
    *,
    map_id: str = "m1",
    kind: str = "object",
    name: str = "",
    entity_tag: str = "",
    state: str = "Unlinked",
    available: bool = True,
) -> dict[str, Any]:
    return {
        "mapEntity": {
            "mapId": map_id,
            "entityId": entity_id,
            "type": kind,
            "model": 1337,
            "map": {"resourceName": "ankigta", "mapName": "Map"},
            "display": {
                "name": name,
                "entityTag": entity_tag,
                "radius": 3,
                "showCorona": False,
            },
            "authored": {
                "position": {"x": 0, "y": 0, "z": 0},
                "rotation": {"x": 0, "y": 0, "z": 0},
                "world": {"interior": 0, "dimension": 0},
            },
        },
        "runtimeInstance": {"available": available, "streamed": False},
        "metadata": {
            "name": name,
            "entityTag": entity_tag,
            "radius": 3,
            "showCorona": False,
        },
        "link": {"state": state},
    }


def to_lua(sandbox: MtaSandbox, value: Any) -> Any:
    if isinstance(value, dict):
        return sandbox.lua.table_from(
            {key: to_lua(sandbox, item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return sandbox.lua.table_from([to_lua(sandbox, item) for item in value])
    return value


def matching(
    sandbox: MtaSandbox,
    entries: list[dict[str, Any]],
    query: str,
) -> list[str]:
    result = sandbox.eval(
        """
        function(entities, query)
            local kept = {}
            for _, entry in ipairs(ANKIGTA.Panel.matching(entities, query)) do
                kept[#kept + 1] = entry.mapEntity.entityId
            end
            return kept
        end
        """
    )(to_lua(sandbox, entries), query)
    kept = sandbox.to_python(result)
    return list(kept) if isinstance(kept, list) else []


def render(sandbox: MtaSandbox, entries: list[dict[str, Any]]) -> None:
    sandbox.eval(
        """
        function(entities)
            triggerEvent("ankigta:setAuthorized", resourceRoot, true)
            if not isPanelOpen() then
                togglePanel()
                triggerEvent(
                    "ankigta:panelAction", resourceRoot, "ready", "{}"
                )
            end
            triggerEvent("ankigta:f7Snapshot", resourceRoot, {
                contractVersion = 1,
                visible = true,
                cardPicker = {enabled = true},
                entities = entities,
                history = {entryCount = 0, canUndo = false, canRedo = false},
            })
        end
        """
    )(to_lua(sandbox, entries))


def act(
    sandbox: MtaSandbox, action: str, payload: dict[str, Any] | None = None
) -> None:
    sandbox.eval(
        """
        function(name, payload)
            triggerEvent("ankigta:panelAction", resourceRoot, name, payload)
        end
        """
    )(action, json.dumps(payload or {}))


def select(sandbox: MtaSandbox, entity_id: str, *, map_id: str = "m1") -> None:
    act(sandbox, "select", {"mapId": map_id, "entityId": entity_id})


def panel_state(sandbox: MtaSandbox) -> dict[str, Any]:
    """The last whole state Lua pushed into the page."""
    return sandbox.pushed_panel_state()


def grid_entity_ids(sandbox: MtaSandbox) -> list[str]:
    """The `mapId / entityId` of every row the page was given."""
    return [
        f"{row['mapId']} / {row['entityId']}"
        for row in panel_state(sandbox)["entities"]
    ]


def apply_filter(sandbox: MtaSandbox, query: str) -> None:
    """Type into the filter box and press the button, as the player does."""
    sandbox.eval(
        """
        function(payload)
            triggerEvent(
                "ankigta:panelAction", resourceRoot, "filter", payload
            )
        end
        """
    )(json.dumps({"text": query}))


def filter_box_text(sandbox: MtaSandbox) -> str:
    return str(panel_state(sandbox)["entityFilter"])


def selected_entity_id(sandbox: MtaSandbox) -> str | None:
    """The `mapId / entityId` the panel holds as selected, or `None`."""
    selected = panel_state(sandbox)["selected"]
    if not selected.get("entityId"):
        return None
    return f"{selected['mapId']} / {selected['entityId']}"


def pick_entity_finished(
    sandbox: MtaSandbox,
    entity_id: str,
    *,
    map_id: str = "m1",
    mode: str = "link",
) -> None:
    """The world-click that Pick Entity turns into a selection."""
    sandbox.eval(
        """
        function(mapId, entityId, mode)
            triggerEvent(
                "ankigta:pickEntityFinished",
                resourceRoot,
                true,
                nil,
                mapId,
                entityId,
                mode
            )
        end
        """
    )(map_id, entity_id, mode)


def pick_entity_cancelled(sandbox: MtaSandbox, *, mode: str = "link") -> None:
    """Escape out of Pick Entity, which selects nothing."""
    sandbox.eval(
        """
        function(mode)
            triggerEvent(
                "ankigta:pickEntityFinished",
                resourceRoot,
                false,
                "cancelled",
                nil,
                nil,
                mode
            )
        end
        """
    )(mode)


# --- the rule ----------------------------------------------------------------


def test_an_empty_query_keeps_everything(f7: MtaSandbox) -> None:
    assert matching(f7, [entry("a"), entry("b")], "") == ["a", "b"]


def test_the_identity_the_list_shows_is_searchable(f7: MtaSandbox) -> None:
    assert matching(f7, [entry("gate-north"), entry("gate-south")], "north") == [
        "gate-north"
    ]


def test_the_name_and_the_entity_tag_are_searchable(f7: MtaSandbox) -> None:
    entries = [
        entry("a", name="Kitchen door"),
        entry("b", entity_tag="verbs"),
        entry("c"),
    ]

    assert matching(f7, entries, "door") == ["a"]
    assert matching(f7, entries, "verbs") == ["b"]


def test_a_filter_does_not_depend_on_current_streaming(f7: MtaSandbox) -> None:
    """Story 51 in one assertion: a destroyed Runtime Instance is still found.

    A filter that reached into the world would hide exactly the entities a
    player opens F7 to repair.
    """
    entries = [
        entry("a", name="ruined", available=False, state="Entity missing"),
        entry("b", name="present"),
    ]

    assert matching(f7, entries, "ruined") == ["a"]


def test_the_query_is_a_substring_and_not_a_pattern(f7: MtaSandbox) -> None:
    """A name may contain `-`, `(` or `%`, and a player typing one means it."""
    entries = [entry("a", name="door (rear)"), entry("b", name="doorXrear")]

    assert matching(f7, entries, "(rear)") == ["a"]


def test_ascii_case_does_not_matter(f7: MtaSandbox) -> None:
    assert matching(f7, [entry("a", name="Kitchen")], "KITCHEN") == ["a"]


def test_the_link_state_narrows_the_list(f7: MtaSandbox) -> None:
    entries = [
        entry("a", state="Active Spatial Link"),
        entry("b", state="Pending Map Save"),
    ]

    assert matching(f7, entries, "pending") == ["b"]


def test_nothing_matching_is_an_empty_list_rather_than_everything(
    f7: MtaSandbox,
) -> None:
    assert matching(f7, [entry("a"), entry("b")], "zzz") == []


# --- the window --------------------------------------------------------------


def test_the_grid_shows_only_the_rows_the_filter_keeps(f7: MtaSandbox) -> None:
    render(f7, [entry("gate-north"), entry("gate-south")])
    assert len(grid_entity_ids(f7)) == 2

    apply_filter(f7, "north")

    assert grid_entity_ids(f7) == ["m1 / gate-north"]


def test_the_window_says_how_much_it_is_hiding(f7: MtaSandbox) -> None:
    """A list that quietly shows two of ten thousand rows reads as a list with
    two rows in it."""
    render(f7, [entry("a", name="keep"), entry("b"), entry("c")])

    apply_filter(f7, "keep")

    state = panel_state(f7)
    assert len(state["entities"]) == 1
    assert state["entityTotal"] == 3
    # The page turns the pair into "Showing 1 of 3"; the key is in the table.
    assert state["locale"]["f7.filterResult"]


def test_clearing_the_filter_brings_the_rows_back(f7: MtaSandbox) -> None:
    render(f7, [entry("a", name="keep"), entry("b")])
    apply_filter(f7, "keep")
    assert len(grid_entity_ids(f7)) == 1

    apply_filter(f7, "")

    assert len(grid_entity_ids(f7)) == 2


def test_a_selection_made_in_the_world_outranks_the_filter(
    f7: MtaSandbox,
) -> None:
    """Pick Entity closes F7 and reopens it, so the filter is still there.

    The player pointed at the entity; a query they typed before that must not
    be what leaves the reopened window showing nothing selected and no reason.
    """
    entities = [entry("a", name="keep"), entry("b", name="other")]
    render(f7, entities)
    apply_filter(f7, "keep")
    assert grid_entity_ids(f7) == ["m1 / a"]

    pick_entity_finished(f7, "b")
    render(f7, entities)

    assert selected_entity_id(f7) == "m1 / b"
    assert grid_entity_ids(f7) == ["m1 / a", "m1 / b"]


def test_the_dropped_filter_leaves_the_box_and_the_grid_agreeing(
    f7: MtaSandbox,
) -> None:
    """A box still reading `keep` over a list showing everything is a lie the
    next press of `Filter` would make true again."""
    entities = [entry("a", name="keep"), entry("b", name="other")]
    render(f7, entities)
    apply_filter(f7, "keep")

    pick_entity_finished(f7, "b")
    render(f7, entities)

    assert filter_box_text(f7) == ""
    assert len(panel_state(f7)["entities"]) == 2


def test_a_filter_that_keeps_the_selection_survives(f7: MtaSandbox) -> None:
    """Only a filter that hides the target is dropped. One that would have
    shown it anyway is still the player's own narrowing of a long list."""
    entities = [entry("a", name="keep"), entry("b", name="keep too")]
    render(f7, entities)
    apply_filter(f7, "keep")

    pick_entity_finished(f7, "b")
    render(f7, entities)

    assert filter_box_text(f7) == "keep"
    assert selected_entity_id(f7) == "m1 / b"


def test_a_filter_typed_after_the_pick_survives_the_next_refresh(
    f7: MtaSandbox,
) -> None:
    """The drop answers the selection that just arrived, and only that one.

    A selection outlives the window it was made in, so re-reading it on every
    refresh would keep discarding filters the player typed since.
    """
    entities = [entry("a", name="keep"), entry("b", name="other")]
    render(f7, entities)
    pick_entity_finished(f7, "b")
    render(f7, entities)

    apply_filter(f7, "keep")
    render(f7, entities)  # any mutating action refreshes the window

    assert filter_box_text(f7) == "keep"
    assert grid_entity_ids(f7) == ["m1 / a"]


def test_a_cancelled_pick_leaves_the_filter_alone(f7: MtaSandbox) -> None:
    """Cancelling selects nothing, so there is nothing for the filter to hide.

    Ticket 24 asks that cancelling restore the state the player left; wiping
    what they had typed is the opposite of restoring it.
    """
    entities = [entry("a", name="keep"), entry("b", name="other")]
    render(f7, entities)
    pick_entity_finished(f7, "b")
    render(f7, entities)
    apply_filter(f7, "keep")

    pick_entity_cancelled(f7)
    render(f7, entities)

    assert filter_box_text(f7) == "keep"
    assert grid_entity_ids(f7) == ["m1 / a"]


def test_a_cancelled_relink_pick_leaves_the_filter_alone(f7: MtaSandbox) -> None:
    """`Pick target` is not itself a selection — the pick it starts may be
    escaped, and then nothing arrived for the filter to be hiding."""
    missing = entry("gone", name="ruined", available=False, state="Entity missing")
    missing["link"]["relinkAvailable"] = True
    entities = [missing, entry("free", name="spare")]
    render(f7, entities)
    pick_entity_finished(f7, "gone")
    render(f7, entities)

    select(f7, "gone")
    apply_filter(f7, "spare")
    act(f7, "pickEntity", {"mode": "relink"})

    pick_entity_cancelled(f7, mode="relink")
    render(f7, entities)

    assert filter_box_text(f7) == "spare"
    assert grid_entity_ids(f7) == ["m1 / free"]


def test_a_relink_in_progress_reveals_its_hidden_source(f7: MtaSandbox) -> None:
    """The relink source is read back off the grid, so a filter hiding it
    leaves `Confirm` disabled with nothing on screen explaining why."""
    missing = entry("gone", name="ruined", available=False, state="Entity missing")
    missing["link"]["relinkAvailable"] = True
    entities = [missing, entry("free", name="spare")]
    render(f7, entities)

    select(f7, "gone")
    act(f7, "pickEntity", {"mode": "relink"})

    # The player typed this before the target came back; it hides the source.
    apply_filter(f7, "spare")
    pick_entity_finished(f7, "free", mode="relink")
    render(f7, entities)

    # Both are on screen: the source the relink came from and the target it is
    # going to. Hiding either strands the operation half-done.
    assert set(grid_entity_ids(f7)) == {"m1 / gone", "m1 / free"}


def test_a_hidden_pending_entity_still_has_its_action(f7: MtaSandbox) -> None:
    """`Check again` acts on the pending entity, which the filter may hide.

    Disabling the action because a row is not on screen would leave the player
    unable to finish a Save they can see the consequence of.
    """
    pending = entry("b", state="Pending Map Save")
    pending["link"]["recheckAvailable"] = True
    render(f7, [entry("a", name="keep"), pending])

    apply_filter(f7, "keep")

    # The row is visible, so the page can offer its action: enabling lives on
    # the page now, and what Lua owes it is the row and its recheckAvailable.
    # The filter hides the pending row, and the action still knows its target:
    # `recheck` acts on the selection, not on what happens to be listed.
    select(f7, "b")
    act(f7, "recheck")
    assert [
        event
        for event in f7.recorder.server_events
        if event.name == "ankigta:recheckPendingMapSave"
    ]
