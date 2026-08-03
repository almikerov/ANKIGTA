from __future__ import annotations

import re
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .config import ValidationConfig


@dataclass(frozen=True)
class ValidationIssue:
    relative_path: str
    message: str
    line: int | None = None
    column: int | None = None

    def display(self) -> str:
        location = self.relative_path
        if self.line is not None:
            location += f":{self.line}"
            if self.column is not None:
                location += f":{self.column}"
        return f"{location}: {self.message}"


@dataclass(frozen=True)
class ValidationReport:
    issues: tuple[ValidationIssue, ...]
    checked_files: int
    skipped_lua_files: int

    @property
    def passed(self) -> bool:
        return not self.issues


def validate_xml_file(path: Path, relative_name: str) -> ValidationIssue | None:
    try:
        ET.parse(path)
    except ET.ParseError as exc:
        line, column = exc.position
        return ValidationIssue(relative_name, str(exc), line, column)
    except OSError as exc:
        return ValidationIssue(relative_name, f"Cannot read XML file: {exc}")
    return None


def validate_lua_file(
    path: Path, relative_name: str, compiler: Path
) -> ValidationIssue | None:
    try:
        result = subprocess.run(
            [str(compiler), "-p", str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            shell=False,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return ValidationIssue(relative_name, f"Lua compiler could not run: {exc}")
    if result.returncode == 0:
        return None

    message = (result.stderr or result.stdout or "Lua compiler reported a syntax error").strip()
    match = re.search(r":(\d+):\s*(.*)", message, flags=re.DOTALL)
    if match:
        return ValidationIssue(relative_name, match.group(2).strip(), int(match.group(1)))
    return ValidationIssue(relative_name, message)


def validate_changed_files(
    resource_root: Path,
    relative_names: Iterable[str],
    config: ValidationConfig,
) -> ValidationReport:
    if not config.enabled:
        return ValidationReport(issues=(), checked_files=0, skipped_lua_files=0)

    issues: list[ValidationIssue] = []
    checked = 0
    skipped_lua = 0
    for relative_name in sorted(set(relative_names), key=str.casefold):
        path = resource_root / Path(relative_name)
        if not path.is_file():
            continue
        extension = path.suffix.casefold()
        issue: ValidationIssue | None = None
        if extension in {".xml", ".edf", ".map"} and config.validate_xml:
            checked += 1
            issue = validate_xml_file(path, relative_name)
        elif extension == ".lua":
            if config.lua_compiler is None:
                skipped_lua += 1
                continue
            checked += 1
            issue = validate_lua_file(path, relative_name, config.lua_compiler)
        if issue:
            issues.append(issue)

    return ValidationReport(tuple(issues), checked, skipped_lua)
