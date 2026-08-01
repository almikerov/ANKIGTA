"""Ticket 15 — the MTA gateway's rating path, executed in a real Lua VM.

These drive `server/companion.lua` directly: call the rating export, inspect the
HTTP request it produced, hand it a response, and assert on the outcome it
settled. The point is the failure paths — a lost, malformed or mismatched
response must leave the outcome unknown rather than claim success or failure.
"""

from __future__ import annotations

import json
from typing import Any, Iterator

import pytest

from tests.lua import MtaSandbox


UUID = "11111111-1111-4111-8111-111111111111"
PORT = 51000
TOKEN = "disposable-token"


@pytest.fixture
def gateway() -> Iterator[MtaSandbox]:
    sandbox = MtaSandbox()
    # The gateway reads its port and token through ConnectionConfig; stub that
    # rather than the filesystem, which ticket 03 already covers.
    sandbox.execute(
        f"""
        ANKIGTA = ANKIGTA or {{}}
        ANKIGTA.ConnectionConfig = {{
            loadEffective = function()
                return {{port = {PORT}, token = "{TOKEN}"}}, false, false
            end,
        }}
        """
    )
    sandbox.load("server/companion.lua")
    try:
        yield sandbox
    finally:
        sandbox.close()


def rate(sandbox: MtaSandbox, card_id: int = 7, rating: str = "good") -> Any:
    return sandbox.eval(
        """
        function(cardId, rating, uuid)
            return ANKIGTA.CompanionGateway.requestRating(
                false,
                {collectionUuid = uuid, cardId = cardId},
                rating
            )
        end
        """
    )(card_id, rating, UUID)


def outcome(sandbox: MtaSandbox, transaction_id: str) -> Any:
    return sandbox.eval(
        "function(id) return ANKIGTA.CompanionGateway.reviewOutcome(id) end"
    )(transaction_id)


def response_body(
    transaction_id: str,
    *,
    request_id: str,
    card_id: int = 7,
    rating: str = "good",
    state: str = "applied",
    collection_uuid: str = UUID,
) -> str:
    return json.dumps(
        {
            "protocol": "ankigta-control",
            "protocolVersion": 1,
            "requestId": request_id,
            "ok": True,
            "error": None,
            "payload": {
                "review": {
                    "reviewTransactionId": transaction_id,
                    "collectionUuid": collection_uuid,
                    "cardId": card_id,
                    "rating": rating,
                    "state": state,
                    "replayed": False,
                    "reason": None,
                }
            },
        }
    )


def sent_request(sandbox: MtaSandbox) -> dict[str, Any]:
    fetch = sandbox.recorder.remote_fetches[-1]
    options = fetch["options"]
    return json.loads(options["postData"])


def test_a_rating_posts_to_the_companion_with_its_own_transaction_id(
    gateway: MtaSandbox,
) -> None:
    accepted, transaction_id = rate(gateway)

    assert accepted is True
    assert transaction_id.startswith("review-")

    fetch = gateway.recorder.remote_fetches[-1]
    assert fetch["url"] == f"http://127.0.0.1:{PORT}/v1/review/rate"

    body = sent_request(gateway)
    assert body["reviewTransactionId"] == transaction_id
    # The transport request id is a separate identifier from the transaction.
    assert body["requestId"] != transaction_id
    assert body["cardIdentity"]["cardId"] == 7
    assert body["rating"] == "good"


def test_the_connection_token_is_sent_and_never_leaves_the_server(
    gateway: MtaSandbox,
) -> None:
    rate(gateway)

    options = gateway.recorder.remote_fetches[-1]["options"]
    assert options["headers"]["Authorization"] == f"Bearer {TOKEN}"


def test_a_confirmed_result_settles_the_transaction_as_applied(
    gateway: MtaSandbox,
) -> None:
    _accepted, transaction_id = rate(gateway)
    request_id = sent_request(gateway)["requestId"]

    gateway.complete_fetch(
        body=response_body(transaction_id, request_id=request_id)
    )

    settled = outcome(gateway, transaction_id)
    assert settled.state == "applied"
    assert settled.category is False


def test_a_second_click_reuses_the_same_transaction(gateway: MtaSandbox) -> None:
    _accepted, first = rate(gateway)
    accepted, second = rate(gateway)

    assert accepted is True
    assert second == first
    # One logical request means one HTTP request.
    assert len(gateway.recorder.remote_fetches) == 1


def test_a_click_on_a_different_card_while_one_is_in_flight_is_refused(
    gateway: MtaSandbox,
) -> None:
    rate(gateway, card_id=7)
    accepted, reason = rate(gateway, card_id=8)

    assert accepted is False
    assert reason == "review_in_flight"
    assert len(gateway.recorder.remote_fetches) == 1


def test_a_malformed_response_leaves_the_outcome_unknown(
    gateway: MtaSandbox,
) -> None:
    _accepted, transaction_id = rate(gateway)

    gateway.complete_fetch(body="{not json")

    settled = outcome(gateway, transaction_id)
    assert settled.state == "outcome_unknown"
    assert settled.category == "protocol_error"


def test_an_http_error_alone_does_not_declare_the_rating_unapplied(
    gateway: MtaSandbox,
) -> None:
    _accepted, transaction_id = rate(gateway)

    gateway.complete_fetch(body="", status=500)

    settled = outcome(gateway, transaction_id)
    assert settled.state == "outcome_unknown", (
        "a transport failure proves nothing about what Anki did"
    )


def test_a_response_for_another_transaction_is_not_accepted(
    gateway: MtaSandbox,
) -> None:
    _accepted, transaction_id = rate(gateway)
    request_id = sent_request(gateway)["requestId"]

    gateway.complete_fetch(
        body=response_body("review-someone-else", request_id=request_id)
    )

    settled = outcome(gateway, transaction_id)
    assert settled.state == "outcome_unknown"
    assert settled.category == "identity_mismatch"


def test_a_response_for_another_card_is_not_accepted(gateway: MtaSandbox) -> None:
    _accepted, transaction_id = rate(gateway, card_id=7)
    request_id = sent_request(gateway)["requestId"]

    gateway.complete_fetch(
        body=response_body(transaction_id, request_id=request_id, card_id=8)
    )

    settled = outcome(gateway, transaction_id)
    assert settled.state == "outcome_unknown"
    assert settled.category == "identity_mismatch"


def test_the_same_card_id_from_another_collection_is_not_accepted(
    gateway: MtaSandbox,
) -> None:
    _accepted, transaction_id = rate(gateway, card_id=7)
    request_id = sent_request(gateway)["requestId"]

    gateway.complete_fetch(
        body=response_body(
            transaction_id,
            request_id=request_id,
            collection_uuid="22222222-2222-4222-8222-222222222222",
        )
    )

    settled = outcome(gateway, transaction_id)
    assert settled.state == "outcome_unknown"
    assert settled.category == "identity_mismatch"


def test_a_late_duplicate_callback_is_quarantined(gateway: MtaSandbox) -> None:
    _accepted, transaction_id = rate(gateway)
    request_id = sent_request(gateway)["requestId"]
    body = response_body(transaction_id, request_id=request_id)

    gateway.complete_fetch(body=body)
    before = gateway.eval("ANKIGTA.CompanionGateway.quarantinedCallbacks")
    gateway.complete_fetch(body=body)
    after = gateway.eval("ANKIGTA.CompanionGateway.quarantinedCallbacks")

    assert after == before + 1
    assert outcome(gateway, transaction_id).state == "applied"


def test_an_invalid_card_identity_never_reaches_the_network(
    gateway: MtaSandbox,
) -> None:
    accepted, reason = gateway.eval(
        """
        function()
            return ANKIGTA.CompanionGateway.requestRating(
                false,
                {collectionUuid = "", cardId = 0},
                "good"
            )
        end
        """
    )()

    assert accepted is False
    assert reason == "invalid_card_identity"
    assert gateway.recorder.remote_fetches == []


def test_an_empty_rating_never_reaches_the_network(gateway: MtaSandbox) -> None:
    accepted, reason = rate(gateway, rating="")

    assert accepted is False
    assert reason == "invalid_rating"
    assert gateway.recorder.remote_fetches == []
