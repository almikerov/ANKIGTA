from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from .config import ResourceConfig
from .path_rules import IGNORED_DIRECTORIES


def discover_resource_paths(
    resources_root: Path, resource_names: Iterable[str]
) -> tuple[dict[str, ResourceConfig], tuple[str, ...]]:
    """Find editable resource directories by their MTA name (folder basename)."""
    wanted = set(resource_names)
    found: dict[str, ResourceConfig] = {}
    duplicates: set[str] = set()
    if not wanted:
        return found, ()

    for current, directory_names, file_names in os.walk(resources_root):
        directory_names[:] = [
            name for name in directory_names if name.casefold() not in IGNORED_DIRECTORIES
        ]
        if "meta.xml" not in {name.casefold() for name in file_names}:
            continue
        current_path = Path(current).resolve()
        name = current_path.name
        if name in wanted:
            if name in found and found[name].path != current_path:
                duplicates.add(name)
            else:
                found[name] = ResourceConfig(name=name, path=current_path)
        directory_names[:] = []

    problems: list[str] = []
    for name in sorted(wanted - set(found), key=str.casefold):
        problems.append(f"MTA allows '{name}', but no directory containing meta.xml was found under {resources_root}")
    for name in sorted(duplicates, key=str.casefold):
        found.pop(name, None)
        problems.append(f"Multiple resource directories named '{name}' were found; the mapping is ambiguous")
    return found, tuple(problems)
