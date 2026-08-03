from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hotreload.config import ValidationConfig
from hotreload.validation import validate_changed_files, validate_xml_file


class ValidationTests(unittest.TestCase):
    def test_xml_validation_success(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "meta.xml"
            path.write_text("<meta><script src='server.lua' /></meta>", encoding="utf-8")
            self.assertIsNone(validate_xml_file(path, "meta.xml"))

    def test_xml_validation_failure_has_line_and_column(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "meta.xml"
            path.write_text("<meta>\n<broken></meta>", encoding="utf-8")
            issue = validate_xml_file(path, "meta.xml")
            self.assertIsNotNone(issue)
            self.assertEqual(issue.line, 2)
            self.assertIsNotNone(issue.column)

    def test_lua_validator_skipped_without_compiler(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "server.lua").write_text("this is not lua ???", encoding="utf-8")
            config = ValidationConfig(
                enabled=True,
                lua_compiler=None,
                validate_xml=True,
                block_reload_on_error=True,
            )
            report = validate_changed_files(root, ["server.lua"], config)
            self.assertTrue(report.passed)
            self.assertEqual(report.checked_files, 0)
            self.assertEqual(report.skipped_lua_files, 1)


if __name__ == "__main__":
    unittest.main()
