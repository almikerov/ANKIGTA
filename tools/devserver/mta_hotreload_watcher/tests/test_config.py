from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hotreload.config import ConfigError, load_config


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "resource_one").mkdir()
        (self.root / "resource_two").mkdir()
        (self.root / "dev_hotreload").mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def valid_data(self) -> dict:
        return {
            "mta": {
                "hotreload_resource": "dev_hotreload",
                "resource_dir": str(self.root / "dev_hotreload"),
                "timeout_seconds": 5,
            },
            "watch": {
                "debounce_ms": 100,
                "ignore_initial_events": True,
                "resources": [
                    {"name": "one", "path": str(self.root / "resource_one")}
                ],
            },
            "validation": {
                "enabled": True,
                "lua_compiler": "",
                "validate_xml": True,
                "block_reload_on_error": True,
            },
        }

    def write(self, data: dict, name: str = "config.json") -> Path:
        path = self.root / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_valid_configuration(self) -> None:
        config = load_config(self.write(self.valid_data()))
        self.assertEqual(config.mta.resource_dir.name, "dev_hotreload")
        self.assertEqual(config.watch.resources[0].name, "one")
        self.assertEqual(config.watch.resources[0].path.name, "resource_one")

    def test_missing_required_configuration(self) -> None:
        data = self.valid_data()
        del data["mta"]["hotreload_resource"]
        with self.assertRaisesRegex(ConfigError, "mta.hotreload_resource"):
            load_config(self.write(data))

    def test_a_leftover_password_is_refused_by_name(self) -> None:
        # Silently ignoring it would leave the secret sitting on disk while
        # everything looked migrated. The error is the thing that gets it
        # deleted.
        data = self.valid_data()
        data["mta"]["password"] = "secret"
        with self.assertRaisesRegex(ConfigError, "mta.password"):
            load_config(self.write(data))

    def test_resource_dir_defaults_to_beside_the_watched_resources(self) -> None:
        data = self.valid_data()
        del data["mta"]["resource_dir"]
        data["watch"]["resources_root"] = str(self.root)
        config = load_config(self.write(data))
        self.assertEqual(config.mta.resource_dir.name, "dev_hotreload")

    def test_missing_file_is_actionable(self) -> None:
        with self.assertRaisesRegex(ConfigError, "Copy config.example.json"):
            load_config(self.root / "missing.json")

    def test_duplicate_paths(self) -> None:
        data = self.valid_data()
        data["watch"]["resources"].append(
            {"name": "two", "path": str(self.root / "resource_one" / ".")}
        )
        with self.assertRaisesRegex(ConfigError, "Duplicate watched resource path"):
            load_config(self.write(data))

    def test_duplicate_resource_names_case_insensitive(self) -> None:
        data = self.valid_data()
        data["watch"]["resources"].append(
            {"name": "ONE", "path": str(self.root / "resource_two")}
        )
        with self.assertRaisesRegex(ConfigError, "Duplicate watched resource name"):
            load_config(self.write(data))

    def test_malformed_json_reports_location(self) -> None:
        path = self.root / "bad.json"
        path.write_text('{"mta":', encoding="utf-8")
        with self.assertRaisesRegex(ConfigError, "line 1"):
            load_config(path)

    def test_auto_sync_allows_empty_explicit_resource_list(self) -> None:
        data = self.valid_data()
        data["watch"]["resources"] = []
        data["watch"]["resources_root"] = str(self.root)
        data["watch"]["auto_sync_from_mta"] = True
        data["watch"]["sync_interval_seconds"] = 3
        config = load_config(self.write(data))
        self.assertTrue(config.watch.auto_sync_from_mta)
        self.assertEqual(config.watch.resources, ())
        self.assertEqual(config.watch.resources_root, self.root.resolve())


if __name__ == "__main__":
    unittest.main()
