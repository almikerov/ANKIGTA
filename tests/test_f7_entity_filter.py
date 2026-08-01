"""Ticket 31 — the Map Entity filter story 51 asks for.

Ticket 30 recorded that F7's list had no search or filter surface while story
51 requires one and story 58 puts 150 ms on it. This is that surface.

The rule under test is the one that is easy to get wrong: filtering is over the
stored record, so an entity whose Runtime Instance is gone is found by the same
words that find one standing in front of you.
"""

from __future__ import annotations

from typing import Any, Iterator

import pytest

from tests.lua import MtaSandbox


UUID = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def f7() -> Iterator[MtaSandbox]:
    sandbox = MtaSandbox()
    sandbox.load("shared/settings.lua")
    sandbox.load("shared/locale.lua")
    sandbox.load("client/layout.lua")
    sandbox.load("client/f7.lua")
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
                "showRadius": False,
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
            "showRadius": False,
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
            for _, entry in ipairs(ANKIGTA.F7.matching(entities, query)) do
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


def grid_entity_ids(sandbox: MtaSandbox) -> list[str]:
    """The `mapId / entityId` cell of every live grid row.

    Matched on the map's own id, because one of the column headings also
    contains a slash.
    """
    return [cell for cell in sandbox.grid_texts() if cell.startswith("m1 / ")]


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

    f7.widgets[f7.find_widget("", "edit")].text = "north"
    f7.click_widget("Filter")

    assert grid_entity_ids(f7) == ["m1 / gate-north"]


def test_the_window_says_how_much_it_is_hiding(f7: MtaSandbox) -> None:
    """A list that quietly shows two of ten thousand rows reads as a list with
    two rows in it."""
    render(f7, [entry("a", name="keep"), entry("b"), entry("c")])

    f7.widgets[f7.find_widget("", "edit")].text = "keep"
    f7.click_widget("Filter")

    assert "Showing 1 of 3" in f7.widget_texts()


def test_clearing_the_filter_brings_the_rows_back(f7: MtaSandbox) -> None:
    render(f7, [entry("a", name="keep"), entry("b")])
    f7.widgets[f7.find_widget("", "edit")].text = "keep"
    f7.click_widget("Filter")
    assert len(grid_entity_ids(f7)) == 1

    f7.widgets[f7.find_widget("keep", "edit")].text = ""
    f7.click_widget("Filter")

    assert len(grid_entity_ids(f7)) == 2


def test_a_hidden_pending_entity_still_has_its_action(f7: MtaSandbox) -> None:
    """`Check again` acts on the pending entity, which the filter may hide.

    Disabling the action because a row is not on screen would leave the player
    unable to finish a Save they can see the consequence of.
    """
    pending = entry("b", state="Pending Map Save")
    pending["link"]["recheckAvailable"] = True
    render(f7, [entry("a", name="keep"), pending])

    f7.widgets[f7.find_widget("", "edit")].text = "keep"
    f7.click_widget("Filter")

    recheck = f7.widgets[f7.find_widget("Check again", "button")]
    assert recheck.enabled is True
