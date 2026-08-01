"""Ticket 23 — session statistics.

The counts describe cards, not links. One card linked to five entities is one
card to study, and showing five would tell the player they have more work than
they do. Everything else here is about which cards are excluded, and why.
"""

from __future__ import annotations

from typing import Any, Iterator

import pytest

from tests.lua import MtaSandbox


from ankigta_companion.cards import CardState

UUID = "11111111-1111-4111-8111-111111111111"
OTHER_UUID = "22222222-2222-4222-8222-222222222222"


@pytest.fixture
def statistics() -> Iterator[MtaSandbox]:
    sandbox = MtaSandbox()
    sandbox.load("server/statistics.lua")
    try:
        yield sandbox
    finally:
        sandbox.close()


def link(
    card_id: int,
    *,
    collection_uuid: str = UUID,
    map_id: str = "m1",
    entity_id: str | None = None,
    state: str = "active",
    pending: bool = False,
) -> dict[str, Any]:
    # Shaped exactly as Store hands rows back: raw snake_case SQLite columns.
    # Building camelCase here would let the counter pass on a shape the
    # producer never emits.
    return {
        "collection_uuid": collection_uuid,
        "card_id": card_id,
        "map_id": map_id,
        "entity_id": entity_id or f"e{card_id}",
        "link_state": "Pending Map Save" if pending else state,
    }


def count(
    sandbox: MtaSandbox,
    links: list[dict[str, Any]],
    card_states: dict[int, str],
    *,
    included_maps: list[str] | None = None,
    allow_early_review: bool = False,
) -> Any:
    lua_links = sandbox.lua.table_from(
        [sandbox.lua.table_from(item) for item in links]
    )
    lua_states = sandbox.lua.table_from(
        {f"{UUID}/{card_id}": state for card_id, state in card_states.items()}
    )
    lua_maps = sandbox.lua.table_from(
        {map_id: True for map_id in (included_maps if included_maps is not None else ["m1"])}
    )
    return sandbox.eval(
        "function(links, states, maps, early)"
        " return ANKIGTA.Statistics.summarize(links, states, maps, early) end"
    )(lua_links, lua_states, lua_maps, allow_early_review)


def test_one_card_linked_to_many_entities_counts_once(
    statistics: MtaSandbox,
) -> None:
    links = [
        link(7, entity_id="e1"),
        link(7, entity_id="e2"),
        link(7, entity_id="e3"),
    ]

    result = count(statistics, links, {7: "review"})

    assert result["total"] == 1
    assert result["due"] == 1


def test_total_is_the_union_of_the_four_buckets(statistics: MtaSandbox) -> None:
    links = [link(1), link(2), link(3), link(4)]
    states = {1: "new", 2: "learning", 3: "review", 4: "not_due"}

    result = count(statistics, links, states, allow_early_review=True)

    assert result["new"] == 1
    assert result["learning"] == 1
    assert result["due"] == 1
    assert result["early"] == 1
    assert result["total"] == 4


def test_early_is_always_present_and_zero_when_disabled(
    statistics: MtaSandbox,
) -> None:
    result = count(statistics, [link(1)], {1: "not_due"}, allow_early_review=False)

    assert result["early"] == 0
    # A not-due card with early review off is not studied at all.
    assert result["total"] == 0


def test_early_is_zero_rather_than_absent_when_empty(
    statistics: MtaSandbox,
) -> None:
    result = count(statistics, [link(1)], {1: "review"}, allow_early_review=True)

    assert result["early"] == 0
    assert result["total"] == 1


@pytest.mark.parametrize("state", ["suspended", "buried"])
def test_unavailable_cards_do_not_count(
    statistics: MtaSandbox,
    state: str,
) -> None:
    result = count(statistics, [link(1), link(2)], {1: "review", 2: state})

    assert result["total"] == 1


def test_a_missing_card_does_not_count(statistics: MtaSandbox) -> None:
    result = count(
        statistics,
        [link(1), link(2, state="card_missing")],
        {1: "review", 2: "review"},
    )

    assert result["total"] == 1


def test_a_card_anki_does_not_report_does_not_count(
    statistics: MtaSandbox,
) -> None:
    # No observed state means no basis for counting it; guessing would be
    # reimplementing the scheduler.
    result = count(statistics, [link(1), link(2)], {1: "review"})

    assert result["total"] == 1


def test_a_pending_map_save_does_not_count(statistics: MtaSandbox) -> None:
    result = count(
        statistics,
        [link(1), link(2, pending=True)],
        {1: "review", 2: "review"},
    )

    assert result["total"] == 1


def test_an_excluded_map_does_not_count(statistics: MtaSandbox) -> None:
    result = count(
        statistics,
        [link(1), link(2, map_id="m2")],
        {1: "review", 2: "review"},
        included_maps=["m1"],
    )

    assert result["total"] == 1


def test_a_card_still_counts_when_one_of_its_entities_is_excluded(
    statistics: MtaSandbox,
) -> None:
    """The card is reachable through the entity that is still included."""
    result = count(
        statistics,
        [link(7, map_id="m1", entity_id="a"), link(7, map_id="m2", entity_id="b")],
        {7: "review"},
        included_maps=["m1"],
    )

    assert result["total"] == 1


def test_the_same_card_id_in_another_collection_is_a_different_card(
    statistics: MtaSandbox,
) -> None:
    links = [link(7), link(7, collection_uuid=OTHER_UUID)]

    # Only the bound collection's states are supplied, so the other is unknown
    # and uncounted rather than merged into the same card.
    result = count(statistics, links, {7: "review"})

    assert result["total"] == 1


def test_statistics_do_not_reimplement_the_scheduler() -> None:
    """Counts follow observed Anki state (ADR 0017)."""
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "mta"
        / "ankigta"
        / "server"
        / "statistics.lua"
    ).read_text(encoding="utf-8")

    for forbidden in ("os.time", "getRealTime", "interval", "ease", "perDay"):
        assert forbidden not in source, f"statistics must not compute {forbidden}"


def test_an_empty_world_reports_zeroes_not_nothing(statistics: MtaSandbox) -> None:
    result = count(statistics, [], {})

    assert result["total"] == 0
    assert result["new"] == 0
    assert result["learning"] == 0
    assert result["due"] == 0
    assert result["early"] == 0


def test_the_state_names_match_the_companion_enum(statistics: MtaSandbox) -> None:
    """The Lua counter and the Python classifier must not drift apart."""
    for state, expected_bucket in (
        (CardState.NEW, "new"),
        (CardState.LEARNING, "learning"),
        (CardState.REVIEW, "due"),
        (CardState.NOT_DUE, "early"),
    ):
        result = count(
            statistics,
            [link(1)],
            {1: state.value},
            allow_early_review=True,
        )
        assert result[expected_bucket] == 1, f"{state.value} -> {expected_bucket}"
        assert result["total"] == 1

    for state in (CardState.SUSPENDED, CardState.BURIED):
        result = count(statistics, [link(1)], {1: state.value})
        assert result["total"] == 0


def test_a_camelcase_row_the_store_never_emits_is_not_relied_on(
    statistics: MtaSandbox,
) -> None:
    """Guards the bug this ticket shipped once: reading the wrong column names.

    Store hands back raw SQLite rows. A counter reading camelCase would match
    nothing and report zero, which is indistinguishable from "no work to do".
    """
    store_shaped = statistics.lua.table_from(
        [
            statistics.lua.table_from(
                {
                    "collection_uuid": UUID,
                    "card_id": 7,
                    "map_id": "m1",
                    "link_state": "active",
                }
            )
        ]
    )
    states = statistics.lua.table_from({f"{UUID}/7": "review"})
    maps = statistics.lua.table_from({"m1": True})

    result = statistics.eval(
        "function(l, s, m) return ANKIGTA.Statistics.summarize(l, s, m, false) end"
    )(store_shaped, states, maps)

    assert result["total"] == 1, "the store's own row shape must count"


def test_link_order_does_not_change_the_counts(
    statistics: MtaSandbox,
) -> None:
    """A card reachable through an included and an excluded map counts once,
    whichever order its links arrive in."""
    excluded_first = count(
        statistics,
        [link(7, map_id="m2", entity_id="b"), link(7, map_id="m1", entity_id="a")],
        {7: "review"},
        included_maps=["m1"],
    )
    included_first = count(
        statistics,
        [link(7, map_id="m1", entity_id="a"), link(7, map_id="m2", entity_id="b")],
        {7: "review"},
        included_maps=["m1"],
    )

    assert excluded_first["total"] == 1
    assert included_first["total"] == 1


def test_a_card_without_an_observed_state_does_not_block_a_later_link(
    statistics: MtaSandbox,
) -> None:
    # Reached first through a link whose card Anki has not reported on.
    result = count(statistics, [link(7, entity_id="a"), link(7, entity_id="b")], {})

    assert result["total"] == 0


# --- the companion query that feeds the counter -------------------------------


def test_the_companion_reports_observed_card_states() -> None:
    """The counter needs states from Anki; guessing them is not an option."""
    import json
    from http.client import HTTPConnection

    from ankigta_companion.cards import CardPickerError, CardState, CardView
    from ankigta_companion.collection_identity import (
        AnkiCardIdentity,
        CollectionIdentityObservation,
        CollectionIdentityState,
    )
    from ankigta_companion.contract import (
        CollectionObservation,
        CollectionState,
        RuntimeObservation,
    )
    from ankigta_companion.http_server import HealthServer

    known = {1: CardState.NEW, 2: CardState.REVIEW, 3: CardState.SUSPENDED}

    class Picker:
        def read_identity(self, identity: AnkiCardIdentity) -> CardView:
            state = known.get(identity.card_id)
            if state is None:
                raise CardPickerError("card_missing", "gone")
            return CardView(
                identity=identity,
                deck_id=10,
                deck_name="Source",
                state=state,
                due=0,
                tags=(),
            )

    def observation() -> RuntimeObservation:
        return RuntimeObservation(
            anki_version="26.05",
            v3_scheduler=True,
            fsrs_enabled=True,
            collection=CollectionObservation(
                state=CollectionState.OPEN,
                identity=CollectionIdentityObservation(
                    CollectionIdentityState.BOUND,
                    UUID,
                ),
            ),
        )

    with HealthServer(observation, card_picker=Picker()) as server:  # type: ignore[arg-type]
        connection = HTTPConnection(server.host, server.port, timeout=2)
        connection.request(
            "POST",
            "/v1/cards/states",
            body=json.dumps(
                {
                    "protocol": "ankigta-control",
                    "protocolVersion": 1,
                    "requestId": "stats-1",
                    "cardIdentities": [
                        {"collectionUuid": UUID, "cardId": card_id}
                        for card_id in (1, 2, 3, 99)
                    ],
                }
            ),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()

    assert response.status == 200
    states = payload["payload"]["cardStates"]
    assert states[f"{UUID}/1"] == "new"
    assert states[f"{UUID}/2"] == "review"
    assert states[f"{UUID}/3"] == "suspended"
    # A card that cannot be read is omitted, not invented.
    assert f"{UUID}/99" not in states
