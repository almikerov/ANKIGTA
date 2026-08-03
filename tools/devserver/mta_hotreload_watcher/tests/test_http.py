from __future__ import annotations

import base64
import json
import unittest

from hotreload.config import MTAConfig
from hotreload.http_client import (
    EndpointRejected,
    MTAHttpClient,
    build_basic_auth_header,
    build_call_url,
    build_request,
    parse_response,
)


class FakeResponse:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self.body


class HTTPTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = MTAConfig(
            base_url="http://127.0.0.1:22005",
            username="hotreload",
            password="super-secret",
            hotreload_resource="dev_hotreload",
            timeout_seconds=5,
        )

    def test_url_construction(self) -> None:
        self.assertEqual(
            build_call_url(self.config.base_url, "dev_hotreload", "reloadResourceByName"),
            "http://127.0.0.1:22005/dev_hotreload/call/reloadResourceByName",
        )

    def test_request_body_is_json_argument_array(self) -> None:
        request = build_request(self.config, "reloadResourceByName", ["example_resource"])
        self.assertEqual(json.loads(request.data.decode("utf-8")), ["example_resource"])

    def test_authentication_header(self) -> None:
        header = build_basic_auth_header("hotreload", "super-secret")
        self.assertEqual(
            base64.b64decode(header.removeprefix("Basic ")).decode("utf-8"),
            "hotreload:super-secret",
        )
        self.assertNotIn("super-secret", repr(self.config))  # Dataclass repr is not logged by the client.

    def test_response_parsing(self) -> None:
        result = parse_response(b'[true,{"action":"restart","accepted":true}]')
        self.assertEqual(result.payload["action"], "restart")

    def test_false_response_is_distinct(self) -> None:
        with self.assertRaisesRegex(EndpointRejected, "RESOURCE_NOT_ALLOWED"):
            parse_response(b'[false,{"error":"RESOURCE_NOT_ALLOWED","message":"denied"}]')

    def test_mocked_http_call(self) -> None:
        seen = {}

        def opener(request, timeout):
            seen["body"] = request.data
            seen["timeout"] = timeout
            return FakeResponse(b'[true,{"action":"restart"}]')

        result = MTAHttpClient(self.config, opener=opener).reload("example_resource")
        self.assertEqual(result.payload["action"], "restart")
        self.assertEqual(json.loads(seen["body"]), ["example_resource"])
        self.assertEqual(seen["timeout"], 5)


if __name__ == "__main__":
    unittest.main()
