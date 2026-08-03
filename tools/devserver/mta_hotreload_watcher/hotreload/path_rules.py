from __future__ import annotations

import fnmatch
import os
from pathlib import Path

WATCHED_EXTENSIONS = frozenset(
    {
        ".lua", ".xml", ".map", ".edf", ".html", ".htm", ".css", ".js",
        ".json", ".txt", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif",
        ".mp3", ".ogg", ".wav", ".ttf", ".woff", ".woff2",
    }
)

IGNORED_DIRECTORIES = frozenset(
    {
        ".git", ".github", ".idea", ".vscode", "__pycache__", "node_modules",
        ".venv", "venv", "dist", "build",
    }
)

IGNORED_FILE_PATTERNS = ("*.tmp", "*.temp", "*.swp", "*.swo", "*~", "Thumbs.db", ".DS_Store", "*.pyc", "*.pyo", "*.log")


def relative_path(root: Path, candidate: str | os.PathLike[str]) -> str | None:
    try:
        return Path(candidate).resolve(strict=False).relative_to(root.resolve(strict=False)).as_posix()
    except (OSError, ValueError):
        return None


def is_ignored(relative_name: str) -> bool:
    normalized = relative_name.replace("\\", "/").strip("/")
    parts = [part for part in normalized.split("/") if part]
    if any(part.casefold() in IGNORED_DIRECTORIES for part in parts[:-1]):
        return True
    if not parts:
        return False
    filename = parts[-1]
    if filename.casefold() in IGNORED_DIRECTORIES:
        return True
    return any(fnmatch.fnmatch(filename, pattern) for pattern in IGNORED_FILE_PATTERNS)


def is_watched_path(relative_name: str, *, is_directory: bool = False) -> bool:
    if is_ignored(relative_name):
        return False
    if is_directory:
        return True
    return Path(relative_name).suffix.casefold() in WATCHED_EXTENSIONS
