"""Ticket 19 — the read-only card content capability.

Card HTML is hostile input: it is arbitrary markup, CSS and JavaScript that the
user's own notes happen to contain. It is served from a separate endpoint that
can do nothing but hand back bytes for one render, so that a card which
misbehaves has nothing to reach for.

The contract is prototype 0006's, restated as tests: 256-bit capabilities bound
to collection, card, side and generation; a 15-second lifetime; per-render
budgets; and one uniform denial for every way of being wrong, so that probing
teaches nothing.
"""

from __future__ import annotations

import time
from http.client import HTTPConnection
from typing import Iterator

import pytest

from ankigta_companion import content
from ankigta_companion.collection_identity import AnkiCardIdentity
from ankigta_companion.content import (
    CAPABILITY_LIFETIME_SECONDS,
    MAX_HTML_BYTES,
    MAX_MEDIA_BYTES,
    MAX_REQUESTS_PER_RENDER,
    MAX_UNIQUE_BYTES,
    ContentServer,
    RenderedCard,
)


UUID = "11111111-1111-4111-8111-111111111111"
OTHER_UUID = "22222222-2222-4222-8222-222222222222"
CARD = AnkiCardIdentity(UUID, 7)
HTML = "<p>front</p><img src='media/picture.png'>"


def rendered(
    html: str = HTML,
    media: dict[str, bytes] | None = None,
) -> RenderedCard:
    return RenderedCard(
        html=html,
        media=media if media is not None else {"picture.png": b"\x89PNG" + b"0" * 64},
    )


@pytest.fixture
def server() -> Iterator[ContentServer]:
    def render(identity: AnkiCardIdentity, side: str) -> RenderedCard | None:
        if identity.collection_uuid != UUID or identity.card_id != 7:
            return None
        return rendered(f"<p>{side}</p><img src='media/picture.png'>")

    instance = ContentServer(render)
    instance.start()
    try:
        yield instance
    finally:
        instance.stop()


def get(
    server: ContentServer,
    path: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
) -> tuple[int, bytes, dict[str, str]]:
    connection = HTTPConnection(server.host, server.port, timeout=3)
    connection.request(method, path, headers=headers or {})
    response = connection.getresponse()
    body = response.read()
    received = {key.lower(): value for key, value in response.getheaders()}
    connection.close()
    return response.status, body, received


def test_a_capability_is_long_and_unguessable(server: ContentServer) -> None:
    first = server.issue(CARD, "question")
    second = server.issue(CARD, "question")

    # 256 bits, URL-safe base64: comfortably over 40 characters.
    assert len(first.token) >= 40
    assert first.token != second.token


def test_the_issued_render_is_served(server: ContentServer) -> None:
    capability = server.issue(CARD, "question")

    status, body, headers = get(server, capability.document_path)

    assert status == 200
    assert b"question" in body
    assert headers["content-type"].startswith("text/html")


def test_head_is_allowed_and_returns_no_body(server: ContentServer) -> None:
    capability = server.issue(CARD, "question")

    status, body, _headers = get(server, capability.document_path, method="HEAD")

    assert status == 200
    assert body == b""


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
def test_only_read_methods_are_accepted(
    server: ContentServer,
    method: str,
) -> None:
    capability = server.issue(CARD, "question")

    status, _body, _headers = get(server, capability.document_path, method=method)

    assert status == 405


def test_the_content_endpoint_dispatches_no_control_operation(
    server: ContentServer,
) -> None:
    server.issue(CARD, "question")

    for path in (
        "/v1/health",
        "/v1/session/start",
        "/v1/review/rate",
        "/v1/cards/read",
    ):
        status, _body, _headers = get(server, path)
        assert status in {404, 405}, f"{path} must not be served here"


def test_responses_carry_the_hardening_headers(server: ContentServer) -> None:
    capability = server.issue(CARD, "question")

    _status, _body, headers = get(server, capability.document_path)

    assert headers["cache-control"] == "no-store"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["x-content-type-options"] == "nosniff"


def test_media_is_served_for_the_issued_render(server: ContentServer) -> None:
    capability = server.issue(CARD, "question")

    status, body, _headers = get(server, capability.media_path("picture.png"))

    assert status == 200
    assert body.startswith(b"\x89PNG")


def test_missing_media_becomes_a_warning_not_a_failure(
    server: ContentServer,
) -> None:
    capability = server.issue(CARD, "question")

    status, body, headers = get(server, capability.media_path("absent.png"))

    # A missing file is the user's note being incomplete, not a reason to break
    # the render or, later, the rating controls.
    assert status == 200
    assert headers["x-ankigta-warning"] == "missing-media"
    assert b"svg" in body.lower()


def test_a_range_request_returns_exactly_that_range(server: ContentServer) -> None:
    capability = server.issue(CARD, "question")

    status, body, headers = get(
        server,
        capability.media_path("picture.png"),
        headers={"Range": "bytes=0-9"},
    )

    assert status == 206
    assert len(body) == 10
    assert headers["content-range"].startswith("bytes 0-9/")


def test_an_identical_retry_does_not_spend_the_byte_budget_twice(
    server: ContentServer,
) -> None:
    capability = server.issue(CARD, "question")

    get(server, capability.media_path("picture.png"))
    spent_once = server.usage(capability.token).unique_bytes
    get(server, capability.media_path("picture.png"))
    spent_twice = server.usage(capability.token).unique_bytes

    assert spent_once == spent_twice
    # Requests still count, even when bytes do not.
    assert server.usage(capability.token).requests == 2


def test_the_request_budget_is_enforced(server: ContentServer) -> None:
    capability = server.issue(CARD, "question")

    for _ in range(MAX_REQUESTS_PER_RENDER):
        status, _body, _headers = get(server, capability.document_path)
        assert status == 200

    status, _body, _headers = get(server, capability.document_path)
    assert status == 429


def test_an_oversized_medium_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(content, "MAX_MEDIA_BYTES", 1024)

    def render(_identity: AnkiCardIdentity, _side: str) -> RenderedCard:
        return rendered(media={"huge.bin": b"0" * 1025})

    instance = ContentServer(render)
    instance.start()
    try:
        capability = instance.issue(CARD, "question")
        status, _body, _headers = get(instance, capability.media_path("huge.bin"))
        assert status == 413
    finally:
        instance.stop()


def test_oversized_html_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(content, "MAX_HTML_BYTES", 1024)

    def render(_identity: AnkiCardIdentity, _side: str) -> RenderedCard:
        return rendered(html="x" * 1025, media={})

    instance = ContentServer(render)
    instance.start()
    try:
        capability = instance.issue(CARD, "question")
        status, _body, _headers = get(instance, capability.document_path)
        assert status == 413
    finally:
        instance.stop()


def test_the_unique_byte_budget_is_enforced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Shrink the budget rather than pushing 32 MiB through a socket; the rule
    # under test is the accounting, not the constant.
    budget = 4096
    monkeypatch.setattr(content, "MAX_UNIQUE_BYTES", budget)
    media = {
        f"file{index}.bin": bytes([index]) * 2048 for index in range(4)
    }

    def render(_identity: AnkiCardIdentity, _side: str) -> RenderedCard:
        return rendered(html="<p>x</p>", media=media)

    instance = ContentServer(render)
    instance.start()
    try:
        capability = instance.issue(CARD, "question")
        statuses = [
            get(instance, capability.media_path(name))[0] for name in sorted(media)
        ]
        assert 413 in statuses, "the unique-byte budget must eventually refuse"
        assert instance.usage(capability.token).unique_bytes <= budget
    finally:
        instance.stop()


def test_a_guessed_token_is_denied(server: ContentServer) -> None:
    server.issue(CARD, "question")

    status, body, _headers = get(server, "/render/not-a-real-token/index.html")

    assert status == 404
    assert body == b"", "a denial must not describe what was wrong"


def test_every_denial_looks_identical(server: ContentServer) -> None:
    capability = server.issue(CARD, "question")
    valid = capability.document_path

    server.close(capability.token)
    closed = get(server, valid)
    guessed = get(server, "/render/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/index.html")
    wrong_file = get(server, valid.replace("index.html", "other.html"))

    # Same status, same body, so probing cannot distinguish the cases.
    assert closed[0] == guessed[0] == wrong_file[0] == 404
    assert closed[1] == guessed[1] == wrong_file[1] == b""


def test_closing_a_render_revokes_it(server: ContentServer) -> None:
    capability = server.issue(CARD, "question")
    assert get(server, capability.document_path)[0] == 200

    server.close(capability.token)

    assert get(server, capability.document_path)[0] == 404


def test_a_new_generation_revokes_the_previous_one(server: ContentServer) -> None:
    first = server.issue(CARD, "question")
    second = server.issue(CARD, "answer")

    assert second.generation > first.generation
    assert get(server, first.document_path)[0] == 404
    assert get(server, second.document_path)[0] == 200


def test_a_capability_expires(server: ContentServer) -> None:
    capability = server.issue(CARD, "question")
    assert capability.lifetime_seconds == CAPABILITY_LIFETIME_SECONDS

    server.expire_now(capability.token)

    assert get(server, capability.document_path)[0] == 404


def test_a_card_that_cannot_be_rendered_is_refused_at_issue(
    server: ContentServer,
) -> None:
    with pytest.raises(LookupError):
        server.issue(AnkiCardIdentity(OTHER_UUID, 7), "question")


def test_the_endpoint_listens_only_on_loopback(server: ContentServer) -> None:
    assert server.host == "127.0.0.1"


def test_no_permanent_token_or_control_gateway_reaches_the_content_path() -> None:
    """The content path must not be able to do anything but return bytes."""
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "companion"
        / "ankigta_companion"
        / "content.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "answerCard",
        "answer_card",
        "SessionCoordinator",
        "ReviewCoordinator",
        "Authorization",
        "Bearer",
        "/v1/session",
        "/v1/review",
    ):
        assert forbidden not in source, f"content path must not reference {forbidden}"


def test_excess_concurrency_gets_bounded_backpressure() -> None:
    """Beyond the in-flight limit, refuse fast rather than queue without end."""
    from threading import Barrier, BrokenBarrierError
    from concurrent.futures import ThreadPoolExecutor

    release = Barrier(content.MAX_CONCURRENT_REQUESTS + 1, timeout=5)

    def render(_identity: AnkiCardIdentity, _side: str) -> RenderedCard:
        return rendered(html="<p>x</p>", media={"slow.bin": b"0" * 16})

    instance = ContentServer(render)

    original_charge = instance._charge

    def blocking_charge(key: str, size: int) -> str:
        result = original_charge(key, size)
        if key.startswith("media/"):
            try:
                release.wait()
            except BrokenBarrierError:
                pass
        return result

    instance._charge = blocking_charge  # type: ignore[method-assign]
    instance.start()
    try:
        capability = instance.issue(CARD, "question")
        path = capability.media_path("slow.bin")
        with ThreadPoolExecutor(max_workers=8) as pool:
            in_flight = [
                pool.submit(get, instance, path)
                for _ in range(content.MAX_CONCURRENT_REQUESTS)
            ]
            # Give the held requests time to occupy every slot.
            time.sleep(0.3)
            overflow = get(instance, path)
            release.wait()
            statuses = [future.result()[0] for future in in_flight]

        assert overflow[0] == 503
        assert overflow[2]["retry-after"] == "1"
        assert all(status in {200, 206} for status in statuses)
    finally:
        release.abort()
        instance.stop()
