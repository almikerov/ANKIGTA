"""Ticket 20 — Minimal Review Mode, executed in a real Lua VM.

The modal is mostly a discipline problem rather than a drawing problem: exactly
one transaction per open card, no game action while a card is up, no rating
caused by regaining focus, and whatever client state was captured on open put
back exactly as it was on close.
"""

from __future__ import annotations

from typing import Any, Iterator

import pytest

from tests.lua import MtaSandbox


UUID = "11111111-1111-4111-8111-111111111111"
URL = "http://127.0.0.1:51234/render/token/index.html"


@pytest.fixture
def client() -> Iterator[MtaSandbox]:
    sandbox = MtaSandbox()
    sandbox.load("client/review_mode.lua")
    try:
        yield sandbox
    finally:
        sandbox.close()


def state(sandbox: MtaSandbox) -> Any:
    return sandbox.eval("function() return reviewModeState() end")()


def open_card(
    sandbox: MtaSandbox,
    *,
    side: str = "question",
    close_after_rating: bool = True,
    url: str = URL,
) -> None:
    sandbox.eval(
        """
        function(url, side, closeAfter, uuid)
            triggerEvent("ankigta:openReviewMode", resourceRoot, {
                url = url,
                side = side,
                closeAfterRating = closeAfter,
                cardIdentity = {collectionUuid = uuid, cardId = 7},
            })
        end
        """
    )(url, side, close_after_rating, UUID)


def reveal(sandbox: MtaSandbox, url: str = URL) -> None:
    sandbox.eval(
        """
        function(url)
            triggerEvent("ankigta:reviewSide", resourceRoot, {
                url = url,
                side = "answer",
            })
        end
        """
    )(url)


def click(sandbox: MtaSandbox, x: float, y: float) -> None:
    sandbox.eval(
        "function(x, y) handleReviewClick('left', 'down', 0, 0, x, y) end"
    )(x, y)


def rating_centre(sandbox: MtaSandbox, rating: str) -> tuple[float, float]:
    bounds = sandbox.eval(
        "function(name) return ANKIGTA.ReviewMode.ratingBounds[name] end"
    )(rating)
    assert bounds is not None, f"no bounds recorded for {rating}"
    return bounds[1] + bounds[3] / 2, bounds[2] + bounds[4] / 2


def render(sandbox: MtaSandbox) -> None:
    """Bounds are computed while drawing, so a frame must be drawn first."""
    sandbox.eval("function() renderReviewMode() end")()


def result(sandbox: MtaSandbox, state_name: str, category: str | None = None) -> None:
    sandbox.eval(
        """
        function(stateName, category)
            triggerEvent("ankigta:reviewResult", resourceRoot, {
                state = stateName,
                category = category,
            })
        end
        """
    )(state_name, category)


def test_opening_shows_the_question_and_creates_a_browser(
    client: MtaSandbox,
) -> None:
    open_card(client)

    assert state(client).active is True
    assert state(client).side == "question"
    assert len(client.browsers) == 1
    assert client.browsers[0]["isLocal"] is False


def test_the_browser_is_only_told_about_loopback(client: MtaSandbox) -> None:
    open_card(client)
    # MTA fires this with the browser as the event source.
    client.trigger("onClientBrowserCreated", client.browsers[0])

    # Nothing but the loopback content endpoint is ever whitelisted.
    assert client.requested_domains == ["127.0.0.1"]


def test_the_answer_is_revealed_only_on_request(client: MtaSandbox) -> None:
    open_card(client)
    assert state(client).side == "question"

    reveal(client, "http://127.0.0.1:51234/render/token2/index.html")

    assert state(client).side == "answer"
    assert client.loaded_urls[-1].endswith("token2/index.html")


def test_rating_controls_appear_only_after_the_answer(client: MtaSandbox) -> None:
    open_card(client)
    render(client)
    assert client.eval("ANKIGTA.ReviewMode.ratingBounds.again") is None
    assert client.eval("ANKIGTA.ReviewMode.ratingBounds.reveal") is not None

    reveal(client)
    render(client)
    for rating in ("again", "hard", "good", "easy"):
        assert client.eval(f"ANKIGTA.ReviewMode.ratingBounds.{rating}") is not None


@pytest.mark.parametrize("rating", ["again", "hard", "good", "easy"])
def test_each_rating_submits_exactly_one_request(
    client: MtaSandbox,
    rating: str,
) -> None:
    open_card(client)
    reveal(client)
    render(client)

    click(client, *rating_centre(client, rating))

    submissions = [
        event
        for event in client.recorder.server_events
        if event.name == "ankigta:submitRating"
    ]
    assert len(submissions) == 1
    assert submissions[0].args[-1] == rating


def test_a_second_click_does_not_create_a_second_transaction(
    client: MtaSandbox,
) -> None:
    open_card(client)
    reveal(client)
    render(client)
    centre = rating_centre(client, "good")

    click(client, *centre)
    click(client, *centre)
    click(client, *centre)

    submissions = [
        event
        for event in client.recorder.server_events
        if event.name == "ankigta:submitRating"
    ]
    assert len(submissions) == 1, "one accepted rating per open card"


def test_clicking_again_after_a_confirmed_result_submits_nothing(
    client: MtaSandbox,
) -> None:
    open_card(client, close_after_rating=False)
    reveal(client)
    render(client)
    centre = rating_centre(client, "good")
    click(client, *centre)
    result(client, "applied")

    render(client)
    click(client, *centre)

    submissions = [
        event
        for event in client.recorder.server_events
        if event.name == "ankigta:submitRating"
    ]
    assert len(submissions) == 1


def test_close_after_rating_closes_on_every_accepted_rating(
    client: MtaSandbox,
) -> None:
    for rating in ("again", "hard", "good", "easy"):
        sandbox = MtaSandbox()
        sandbox.load("client/review_mode.lua")
        try:
            open_card(sandbox)
            reveal(sandbox)
            render(sandbox)
            click(sandbox, *rating_centre(sandbox, rating))
            result(sandbox, "applied")

            assert state(sandbox).active is False, f"{rating} must close the modal"
        finally:
            sandbox.close()


def test_close_after_rating_disabled_keeps_the_card_open(
    client: MtaSandbox,
) -> None:
    open_card(client, close_after_rating=False)
    reveal(client)
    render(client)
    click(client, *rating_centre(client, "good"))
    result(client, "applied")

    assert state(client).active is True
    assert state(client).submitted is True


def test_escape_closes_when_nothing_was_submitted(client: MtaSandbox) -> None:
    open_card(client)

    closed = client.eval("function() return requestCloseReviewMode() end")()

    assert closed is True
    assert state(client).active is False


def test_escape_is_refused_while_a_rating_is_in_flight(client: MtaSandbox) -> None:
    open_card(client)
    reveal(client)
    render(client)
    click(client, *rating_centre(client, "good"))

    closed = client.eval("function() return requestCloseReviewMode() end")()

    assert closed is False
    assert state(client).active is True, (
        "closing mid-flight would leave the player unsure whether it counted"
    )


def test_an_unknown_outcome_keeps_the_card_open_and_says_so(
    client: MtaSandbox,
) -> None:
    open_card(client)
    reveal(client)
    render(client)
    click(client, *rating_centre(client, "good"))

    result(client, "outcome_unknown")

    assert state(client).active is True
    # Ticket 27 moved these strings into the locale; without it loaded the key
    # itself surfaces, which is the visible-gap behaviour the locale specifies.
    assert state(client).warning == "review.outcomeUnknown"


def test_regaining_focus_costs_a_click_and_rates_nothing(
    client: MtaSandbox,
) -> None:
    open_card(client)
    reveal(client)
    render(client)
    centre = rating_centre(client, "good")

    client.trigger("onClientMainMenuOpen", None)
    assert state(client).focused is False

    click(client, *centre)  # the click that restores focus
    assert [
        event
        for event in client.recorder.server_events
        if event.name == "ankigta:submitRating"
    ] == []
    assert state(client).focused is True

    click(client, *centre)  # now it rates
    assert len(
        [
            event
            for event in client.recorder.server_events
            if event.name == "ankigta:submitRating"
        ]
    ) == 1


def test_focus_loss_neither_closes_nor_rates(client: MtaSandbox) -> None:
    open_card(client)

    client.trigger("onClientMainMenuOpen", None)

    assert state(client).active is True
    assert client.recorder.server_events == []


def test_game_actions_are_suppressed_while_a_card_is_open(
    client: MtaSandbox,
) -> None:
    open_card(client)

    for control in ("fire", "enter_exit", "action", "next_weapon", "previous_weapon"):
        assert client.controls[control] is False, f"{control} must be blocked"


def test_closing_restores_the_captured_state_not_defaults(
    client: MtaSandbox,
) -> None:
    # The player already had the cursor up and `action` disabled by something
    # else; both must come back as they were, not as ANKIGTA would prefer.
    client.cursor_visible = True
    client.controls["action"] = False
    client.radio_channel = 5

    open_card(client)
    assert client.cursor_visible is True

    client.eval("function() return requestCloseReviewMode() end")()

    assert client.controls["action"] is False
    assert client.cursor_visible is True
    assert client.radio_channel == 5


def test_a_browser_that_cannot_be_created_closes_cleanly(client: MtaSandbox) -> None:
    client.controls["fire"] = True
    client.browser_available = False

    open_card(client)

    assert state(client).active is False
    assert client.controls["fire"] is True, "a failed open must still restore state"


def test_losing_authorization_closes_the_card(client: MtaSandbox) -> None:
    open_card(client)

    client.eval(
        'function() triggerEvent("ankigta:setAuthorized", resourceRoot, false) end'
    )()

    assert state(client).active is False


def test_closing_reports_back_to_the_server(client: MtaSandbox) -> None:
    open_card(client)
    client.eval("function() return requestCloseReviewMode() end")()

    closed = [
        event
        for event in client.recorder.server_events
        if event.name == "ankigta:reviewClosed"
    ]
    assert len(closed) == 1
    assert closed[0].args[-1] == "cancelled"


def test_a_second_open_while_active_is_ignored(client: MtaSandbox) -> None:
    open_card(client)
    open_card(client)

    assert len(client.browsers) == 1


def test_the_client_never_holds_the_control_token_or_paths() -> None:
    """CEF gets a content capability; the control API stays server-side."""
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "mta"
        / "ankigta"
        / "client"
        / "review_mode.lua"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "fetchRemote",
        "Authorization",
        "Bearer",
        "connectionToken",
        "/v1/review",
        "/v1/session",
    ):
        assert forbidden not in source, f"client must not reference {forbidden}"


# --- server side -------------------------------------------------------------


@pytest.fixture
def server() -> Iterator[MtaSandbox]:
    sandbox = MtaSandbox()
    sandbox.execute(
        """
        ANKIGTA = ANKIGTA or {}
        ANKIGTA.ConnectionConfig = {
            loadEffective = function()
                return {port = 51234, token = "t"}, false, false
            end,
        }
        """
    )
    sandbox.load("server/companion.lua")
    try:
        yield sandbox
    finally:
        sandbox.close()


def test_the_server_asks_the_companion_for_a_capability(server: MtaSandbox) -> None:
    import json

    accepted, _request_id = server.eval(
        """
        function(uuid)
            return ANKIGTA.CompanionGateway.requestRender(
                false,
                {collectionUuid = uuid, cardId = 7},
                "question"
            )
        end
        """
    )(UUID)

    assert accepted is True
    fetch = server.recorder.remote_fetches[-1]
    assert fetch["url"] == "http://127.0.0.1:51234/v1/render/issue"
    body = json.loads(fetch["options"]["postData"])
    assert body["side"] == "question"
    assert body["cardIdentity"]["cardId"] == 7


@pytest.mark.parametrize("side", ["question", "answer"])
def test_only_the_two_real_sides_are_accepted(
    server: MtaSandbox,
    side: str,
) -> None:
    accepted, _ = server.eval(
        """
        function(uuid, side)
            return ANKIGTA.CompanionGateway.requestRender(
                false, {collectionUuid = uuid, cardId = 7}, side
            )
        end
        """
    )(UUID, side)
    assert accepted is True


def test_an_invented_side_never_reaches_the_network(server: MtaSandbox) -> None:
    accepted, reason = server.eval(
        """
        function(uuid)
            return ANKIGTA.CompanionGateway.requestRender(
                false, {collectionUuid = uuid, cardId = 7}, "hint"
            )
        end
        """
    )(UUID)

    assert accepted is False
    assert reason == "invalid_side"
    assert server.recorder.remote_fetches == []


def test_a_capability_response_is_published_to_the_server(
    server: MtaSandbox,
) -> None:
    import json

    server.eval(
        """
        function(uuid)
            return ANKIGTA.CompanionGateway.requestRender(
                false, {collectionUuid = uuid, cardId = 7}, "question"
            )
        end
        """
    )(UUID)
    request_id = json.loads(
        server.recorder.remote_fetches[-1]["options"]["postData"]
    )["requestId"]

    server.complete_fetch(
        body=json.dumps(
            {
                "protocol": "ankigta-control",
                "protocolVersion": 1,
                "requestId": request_id,
                "ok": True,
                "error": None,
                "payload": {
                    "render": {
                        "url": URL,
                        "side": "question",
                        "generation": 1,
                        "expiresInSeconds": 15.0,
                    }
                },
            }
        )
    )

    issued = [
        event
        for event in server.recorder.local_events
        if event.name == "ankigta:renderIssued"
    ]
    assert len(issued) == 1
    assert issued[0].args[1]["url"] == URL


def test_a_failed_capability_is_reported_without_a_url(server: MtaSandbox) -> None:
    server.eval(
        """
        function(uuid)
            return ANKIGTA.CompanionGateway.requestRender(
                false, {collectionUuid = uuid, cardId = 7}, "question"
            )
        end
        """
    )(UUID)

    server.complete_fetch(body="{not json")

    issued = [
        event
        for event in server.recorder.local_events
        if event.name == "ankigta:renderIssued"
    ]
    assert len(issued) == 1
    assert issued[0].args[1] is False
    assert issued[0].args[2] == "protocol_error"


# --- ticket 21: best-effort CEF, media and the External Card Page -------------


def navigate(sandbox: MtaSandbox, url: str, blocked: bool = False) -> None:
    sandbox.trigger("onClientBrowserNavigate", sandbox.browsers[0], url, blocked)


def test_navigating_away_creates_an_external_page_but_keeps_rating(
    client: MtaSandbox,
) -> None:
    open_card(client)
    reveal(client)

    navigate(client, "https://example.org/reference")
    render(client)

    assert state(client).externalPage is True
    # The player still knows which card they were answering.
    for rating in ("again", "hard", "good", "easy"):
        assert client.eval(f"ANKIGTA.ReviewMode.ratingBounds.{rating}") is not None
    click(client, *rating_centre(client, "good"))
    assert [
        event
        for event in client.recorder.server_events
        if event.name == "ankigta:submitRating"
    ]


def test_staying_on_the_issued_render_is_not_an_external_page(
    client: MtaSandbox,
) -> None:
    open_card(client)

    navigate(client, "http://127.0.0.1:51234/render/token/index.html")

    assert state(client).externalPage is False


def test_a_blocked_navigation_is_reported_as_a_warning(client: MtaSandbox) -> None:
    open_card(client)

    navigate(client, "https://blocked.example", blocked=True)

    assert state(client).externalPage is False
    assert state(client).warning == "Переход заблокирован настройками MTA"


def test_return_to_card_is_offered_only_after_navigating_away(
    client: MtaSandbox,
) -> None:
    open_card(client)
    render(client)
    assert client.eval("ANKIGTA.ReviewMode.ratingBounds.returnToCard") is None

    navigate(client, "https://example.org")
    render(client)
    assert client.eval("ANKIGTA.ReviewMode.ratingBounds.returnToCard") is not None


def test_return_to_card_asks_for_a_fresh_capability_for_the_current_side(
    client: MtaSandbox,
) -> None:
    open_card(client)
    reveal(client)
    navigate(client, "https://example.org")
    render(client)

    bounds = client.eval("ANKIGTA.ReviewMode.ratingBounds.returnToCard")
    click(client, bounds[1] + bounds[3] / 2, bounds[2] + bounds[4] / 2)

    requests = [
        event
        for event in client.recorder.server_events
        if event.name == "ankigta:returnToCard"
    ]
    assert len(requests) == 1
    assert requests[0].args[-1] == "answer", "the side must survive the detour"


def test_a_fresh_capability_clears_the_external_page_state(
    client: MtaSandbox,
) -> None:
    open_card(client)
    navigate(client, "https://example.org")
    assert state(client).externalPage is True

    reveal(client, "http://127.0.0.1:51234/render/token3/index.html")

    assert state(client).externalPage is False


def test_a_failed_load_warns_without_disabling_rating(client: MtaSandbox) -> None:
    open_card(client)
    reveal(client)

    client.trigger(
        "onClientBrowserLoadingFailed",
        client.browsers[0],
        "http://127.0.0.1:51234/render/token/index.html",
        -105,
    )
    render(client)

    assert "load" in state(client).warning.lower() or "загруз" in state(client).warning.lower()
    click(client, *rating_centre(client, "good"))
    assert [
        event
        for event in client.recorder.server_events
        if event.name == "ankigta:submitRating"
    ], "a card that fails to render is still a card that can be rated"


def test_card_audio_and_world_audio_are_separate_controls(
    client: MtaSandbox,
) -> None:
    open_card(client)

    client.eval("function() return setReviewAudio(false, false) end")()
    assert client.browser_volume == 0.0
    assert client.world_sound_enabled is True, "muting the card must not mute GTA"

    client.eval("function() return setReviewAudio(true, true) end")()
    assert client.browser_volume == 1.0
    assert client.world_sound_enabled is False


# --- ticket 26: Review Protection and exact restoration ----------------------


def protection(sandbox: MtaSandbox, enabled: bool, disable_controls: bool) -> None:
    sandbox.eval("function(p, c) return setReviewProtection(p, c) end")(
        enabled, disable_controls
    )


def test_protection_and_control_disabling_default_on_and_are_independent(
    client: MtaSandbox,
) -> None:
    assert client.eval("ANKIGTA.ReviewMode.reviewProtection") is True
    assert client.eval("ANKIGTA.ReviewMode.disablePlayerControls") is True

    protection(client, True, False)
    open_card(client)

    # Protection without taking the controls away.
    assert client.damage_proof["player"] is True
    assert client.controls.get("fire") is not False


def test_controls_can_be_disabled_without_damage_protection(
    client: MtaSandbox,
) -> None:
    protection(client, False, True)

    open_card(client)

    assert client.damage_proof.get("player", False) is False
    assert client.controls["fire"] is False


def test_the_occupied_vehicle_is_protected_too(client: MtaSandbox) -> None:
    client.occupied_vehicle = client.lua.table_from(
        {"__element": True, "type": "vehicle"}
    )

    open_card(client)

    assert client.damage_proof["player"] is True
    assert client.damage_proof["vehicle"] is True


def test_protection_is_not_a_heal_and_does_not_freeze_the_world(
    client: MtaSandbox,
) -> None:
    """Only new damage is prevented; nothing is restored or paused."""
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "mta"
        / "ankigta"
        / "client"
        / "review_mode.lua"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "setElementHealth",
        "setPedArmor",
        "setGameSpeed",
        "setElementFrozen",
        "setWorldSpecialPropertyEnabled",
    ):
        assert forbidden not in source, f"protection must not call {forbidden}"


def test_protection_that_was_already_on_survives_the_review(
    client: MtaSandbox,
) -> None:
    # Another resource had already made the player damage-proof.
    client.damage_proof["player"] = True

    open_card(client)
    client.eval("function() return requestCloseReviewMode() end")()

    assert client.damage_proof["player"] is True, (
        "restoration must return the captured value, not ANKIGTA's default"
    )


def test_protection_is_lifted_on_close_when_it_was_not_set_before(
    client: MtaSandbox,
) -> None:
    client.damage_proof["player"] = False

    open_card(client)
    assert client.damage_proof["player"] is True
    client.eval("function() return requestCloseReviewMode() end")()

    assert client.damage_proof["player"] is False


def test_world_muting_is_restored_on_close(client: MtaSandbox) -> None:
    open_card(client)
    client.eval("function() return setReviewAudio(true, true) end")()
    assert client.world_sound_enabled is False

    client.eval("function() return requestCloseReviewMode() end")()

    assert client.world_sound_enabled is True


@pytest.mark.parametrize(
    "failure",
    ["authorization", "resource_stop"],
)
def test_no_failure_leaves_protection_or_the_cursor_stuck(
    client: MtaSandbox,
    failure: str,
) -> None:
    client.damage_proof["player"] = False
    client.cursor_visible = False
    open_card(client)
    assert client.damage_proof["player"] is True

    if failure == "authorization":
        client.eval(
            'function() triggerEvent("ankigta:setAuthorized", resourceRoot, false) end'
        )()
    else:
        client.trigger("onClientResourceStop", None)

    assert state(client).active is False
    assert client.damage_proof["player"] is False
    assert client.cursor_visible is False


def test_a_browser_failure_restores_protection(client: MtaSandbox) -> None:
    client.damage_proof["player"] = False
    client.browser_available = False

    open_card(client)

    assert state(client).active is False
    assert client.damage_proof["player"] is False


def test_review_labels_come_from_the_locale_in_both_languages() -> None:
    """Ticket 27: no user-facing string is hard-coded in one language."""
    for language, expected_reveal, expected_applied in (
        ("en", "Show answer", "Rating applied"),
        ("ru", "Показать ответ", "Оценка принята"),
    ):
        sandbox = MtaSandbox()
        try:
            sandbox.load("shared/locale.lua")
            sandbox.load("client/review_mode.lua")
            sandbox.eval("function(l) ANKIGTA.Locale.setLanguage(l) end")(language)

            open_card(sandbox)
            reveal(sandbox)
            render(sandbox)
            click(sandbox, *rating_centre(sandbox, "good"))
            result(sandbox, "applied")

            assert sandbox.eval(
                'ANKIGTA.Locale.text("review.showAnswer")'
            ) == expected_reveal
            assert sandbox.eval(
                'ANKIGTA.Locale.text("review.applied")'
            ) == expected_applied
        finally:
            sandbox.close()


def test_switching_language_needs_no_resource_restart() -> None:
    sandbox = MtaSandbox()
    try:
        sandbox.load("shared/locale.lua")
        sandbox.load("client/review_mode.lua")
        open_card(sandbox)
        reveal(sandbox)

        sandbox.eval('function() ANKIGTA.Locale.setLanguage("ru") end')()
        result(sandbox, "outcome_unknown")
        russian = state(sandbox).warning

        sandbox.eval('function() ANKIGTA.Locale.setLanguage("en") end')()
        result(sandbox, "outcome_unknown")
        english = state(sandbox).warning

        assert "неизвест" in russian.lower()
        assert "unknown" in english.lower()
    finally:
        sandbox.close()
