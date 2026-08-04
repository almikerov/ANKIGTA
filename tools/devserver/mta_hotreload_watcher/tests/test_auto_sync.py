from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hotreload.config import (
    AppConfig,
    MTAConfig,
    ValidationConfig,
    WatchConfig,
)
from hotreload.file_client import EndpointResult
from hotreload.runtime import WatcherApplication


class FakeClient:
    def __init__(self, allowed: list[str]) -> None:
        self.allowed = allowed

    def check(self) -> EndpointResult:
        return EndpointResult(True, {"allowedResources": self.allowed}, [True])


class FakeObserver:
    def __init__(self) -> None:
        self.scheduled: list[tuple[str, bool]] = []
        self.unscheduled: list[object] = []

    def schedule(self, _handler, path: str, recursive: bool):
        token = object()
        self.scheduled.append((path, recursive))
        return token

    def unschedule(self, token: object) -> None:
        self.unscheduled.append(token)


class AutoSyncTests(unittest.TestCase):
    def test_mta_allow_and_ignore_updates_observer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            resource = root / "[dev]" / "my_resource"
            resource.mkdir(parents=True)
            (resource / "meta.xml").write_text("<meta />", encoding="utf-8")
            config = AppConfig(
                mta=MTAConfig(Path("."), "dev_hotreload", 1),
                watch=WatchConfig(100, True, (), root, True, 3),
                validation=ValidationConfig(True, None, True, True),
                source_path=root / "config.json",
            )
            client = FakeClient(["my_resource"])
            observer = FakeObserver()
            app = WatcherApplication(config)
            app.client = client
            app._observer = observer

            app._sync_from_mta()
            self.assertEqual(observer.scheduled, [(str(resource.resolve()), True)])
            self.assertIn("my_resource", app._watches)

            client.allowed = []
            app._sync_from_mta()
            self.assertEqual(len(observer.unscheduled), 1)
            self.assertNotIn("my_resource", app._watches)
            app.debouncer.shutdown()


if __name__ == "__main__":
    unittest.main()
