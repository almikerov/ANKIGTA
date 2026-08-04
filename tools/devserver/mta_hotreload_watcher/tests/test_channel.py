from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from hotreload.config import MTAConfig
from hotreload.file_client import (
    EndpointRejected,
    FileChannel,
    HotReloadChannelError,
    HotReloadClient,
    encode_request,
)


class FakeResource:
    """Stands in for dev_hotreload: reads command.txt, appends to result.txt.

    Deliberately the same shape as the Lua side -- truncate the command file
    before answering, one JSON object per line -- so that a change to the
    protocol breaks here rather than only on a live server.
    """

    def __init__(self, resource_dir: Path, answer):
        self.dir = resource_dir
        self.answer = answer
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def _run(self) -> None:
        command_path = self.dir / "command.txt"
        result_path = self.dir / "result.txt"
        while not self.stop.is_set():
            try:
                text = command_path.read_text(encoding="utf-8")
            except OSError:
                text = ""
            if text.strip():
                command_path.write_text("", encoding="utf-8")
                for line in text.splitlines():
                    if not line.strip():
                        continue
                    name, _, body = line.partition(" ")
                    payload = json.loads(body) if body.strip() else {}
                    reply = dict(self.answer(name, payload))
                    if "requestId" in payload:
                        reply["requestId"] = payload["requestId"]
                    with result_path.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(reply) + "\n")
            time.sleep(0.02)


class EncodeTests(unittest.TestCase):
    def test_a_bare_command_carries_no_payload(self) -> None:
        self.assertEqual(encode_request("status"), "status")

    def test_a_payload_is_one_json_object_on_the_same_line(self) -> None:
        line = encode_request("reload", {"resource": "one"})
        name, _, body = line.partition(" ")
        self.assertEqual(name, "reload")
        self.assertEqual(json.loads(body), {"resource": "one"})
        self.assertNotIn("\n", line)


class ChannelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.dir = Path(self.temporary.name)
        self.config = MTAConfig(
            resource_dir=self.dir, hotreload_resource="dev_hotreload", timeout_seconds=2
        )
        self.resource: FakeResource | None = None

    def tearDown(self) -> None:
        if self.resource:
            self.resource.stop.set()
        self.temporary.cleanup()

    def serve(self, answer) -> None:
        self.resource = FakeResource(self.dir, answer)
        self.resource.start()

    def test_a_reload_is_accepted(self) -> None:
        self.serve(lambda name, payload: {"ok": True, "result": {"resource": payload["resource"], "action": "restart"}})
        result = HotReloadClient(self.config).reload("one")
        self.assertTrue(result.accepted)
        self.assertEqual(result.payload["action"], "restart")

    def test_a_refusal_carries_its_reason(self) -> None:
        self.serve(lambda name, payload: {"ok": False, "error": "RESOURCE_NOT_ALLOWED", "message": "ignored"})
        with self.assertRaises(EndpointRejected) as caught:
            HotReloadClient(self.config, attempts=1).reload("one")
        self.assertEqual(caught.exception.kind, "RESOURCE_NOT_ALLOWED")

    def test_silence_times_out_rather_than_hanging(self) -> None:
        self.config = MTAConfig(
            resource_dir=self.dir, hotreload_resource="dev_hotreload", timeout_seconds=0.2
        )
        with self.assertRaises(HotReloadChannelError) as caught:
            HotReloadClient(self.config, attempts=1, sleeper=lambda _s: None).check()
        self.assertEqual(caught.exception.kind, "CHANNEL_TIMEOUT")

    def test_an_older_answer_is_not_mistaken_for_this_one(self) -> None:
        # The answer file keeps every answer. Matching on anything but the id
        # this request carried would return the previous reload's verdict.
        (self.dir / "result.txt").write_text(
            json.dumps({"ok": True, "requestId": "stale", "result": {"action": "stale"}}) + "\n",
            encoding="utf-8",
        )
        self.serve(lambda name, payload: {"ok": True, "result": {"action": "fresh"}})
        result = HotReloadClient(self.config).reload("one")
        self.assertEqual(result.payload["action"], "fresh")

    def test_a_missing_resource_folder_is_named(self) -> None:
        config = MTAConfig(
            resource_dir=self.dir / "absent",
            hotreload_resource="dev_hotreload",
            timeout_seconds=0.2,
        )
        with self.assertRaises(HotReloadChannelError) as caught:
            FileChannel(config.resource_dir, config.timeout_seconds).request("status")
        self.assertEqual(caught.exception.kind, "RESOURCE_MISSING")


if __name__ == "__main__":
    unittest.main()
