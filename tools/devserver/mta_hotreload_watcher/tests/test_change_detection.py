from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hotreload.config import normalize_windows_path
from hotreload.discovery import discover_resource_paths
from hotreload.path_rules import is_ignored, is_watched_path, relative_path


class ChangeDetectionTests(unittest.TestCase):
    def test_ignored_patterns(self) -> None:
        ignored = [
            ".git/config", ".github/workflows/test.yml", "node_modules/a.js",
            "build/output.js", "script.lua.tmp", "swap.swp", "notes~",
            "Thumbs.db", "cache.pyc", "watcher.log",
        ]
        for path in ignored:
            with self.subTest(path=path):
                self.assertTrue(is_ignored(path))

    def test_watched_extensions(self) -> None:
        watched = [
            "server.lua", "meta.xml", "maps/arena.map", "editor.edf", "web/index.html",
            "web/style.css", "web/app.js", "image.webp", "sound.ogg", "font.woff2",
        ]
        for path in watched:
            with self.subTest(path=path):
                self.assertTrue(is_watched_path(path))
        self.assertFalse(is_watched_path("model.dff"))
        self.assertFalse(is_watched_path(".git/client.lua"))

    def test_windows_path_normalization_preserves_bracketed_names(self) -> None:
        normalized = normalize_windows_path(r"C:\MTA\resources\[dev]\example\..\example")
        self.assertIn("[dev]", normalized)
        self.assertTrue(normalized.casefold().endswith("example"))

    def test_resource_mapping_relative_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "[dev]" / "example"
            child = root / "web" / "index.html"
            child.parent.mkdir(parents=True)
            child.touch()
            self.assertEqual(relative_path(root, child), "web/index.html")
            self.assertIsNone(relative_path(root, Path(temporary) / "outside.lua"))

    def test_directory_changes_are_watched_except_ignored_directories(self) -> None:
        self.assertTrue(is_watched_path("new_folder", is_directory=True))
        self.assertFalse(is_watched_path("dist", is_directory=True))

    def test_discovers_allowed_resource_below_bracketed_category(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            resource = root / "[dev]" / "my_resource"
            resource.mkdir(parents=True)
            (resource / "meta.xml").write_text("<meta />", encoding="utf-8")
            found, problems = discover_resource_paths(root, {"my_resource", "missing"})
            self.assertEqual(found["my_resource"].path, resource.resolve())
            self.assertEqual(len(problems), 1)
            self.assertIn("missing", problems[0])


if __name__ == "__main__":
    unittest.main()
