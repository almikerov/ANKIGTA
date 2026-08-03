from __future__ import annotations

import threading
import time
import unittest

from hotreload.debounce import DebounceManager


def wait_until(predicate, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class DebounceTests(unittest.TestCase):
    def test_combines_multiple_changes(self) -> None:
        batches: list[tuple[str, tuple[str, ...]]] = []
        manager = DebounceManager(0.05, lambda resource, files: batches.append((resource, files)))
        try:
            manager.record("one", "client.lua")
            manager.record("one", "meta.xml")
            manager.record("one", "client.lua")
            self.assertTrue(wait_until(lambda: len(batches) == 1))
            self.assertEqual(batches, [("one", ("client.lua", "meta.xml"))])
        finally:
            manager.shutdown()

    def test_keeps_resources_separate(self) -> None:
        batches: list[tuple[str, tuple[str, ...]]] = []
        manager = DebounceManager(0.04, lambda resource, files: batches.append((resource, files)))
        try:
            manager.record("one", "one.lua")
            manager.record("two", "two.lua")
            self.assertTrue(wait_until(lambda: len(batches) == 2))
            self.assertEqual({item[0] for item in batches}, {"one", "two"})
        finally:
            manager.shutdown()

    def test_change_during_reload_schedules_one_additional_batch(self) -> None:
        started = threading.Event()
        release = threading.Event()
        batches: list[tuple[str, ...]] = []

        def callback(_resource: str, files: tuple[str, ...]) -> None:
            batches.append(files)
            if len(batches) == 1:
                started.set()
                release.wait(1)

        manager = DebounceManager(0.03, callback)
        try:
            manager.record("one", "first.lua")
            self.assertTrue(started.wait(1))
            manager.record("one", "second.lua")
            manager.record("one", "third.lua")
            release.set()
            self.assertTrue(wait_until(lambda: len(batches) == 2))
            self.assertEqual(batches[0], ("first.lua",))
            self.assertEqual(batches[1], ("second.lua", "third.lua"))
        finally:
            release.set()
            manager.shutdown()


if __name__ == "__main__":
    unittest.main()
