"""Ticket 31 — what the two shipped artifacts are made of.

Three questions this answers, all of them about the archive rather than about
the source tree it came from:

- **Inventory.** Every file, with its digest, so "which build is installed"
  has an answer after the fact.
- **Reproducibility.** The same source produces the same bytes, so a diff
  between two releases is a diff of what changed.
- **Secrets.** Nothing shipped carries a token, a key or a credential. The one
  that would matter here is real: the companion keeps its connection token in
  `user_files`, inside the add-on folder it is built from.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pytest

from tools import package
from tools.package import (
    COMPANION_ROOT,
    MTA_RESOURCE_ROOT,
    build_companion_addon,
    build_mta_resource,
    inventory,
)


#: Text that would be a leak if it were in a shipped file.
#:
#: Written as patterns for the *shape* of a secret rather than as a list of
#: known values: a scan that only looks for today's token passes on tomorrow's.
SECRET_PATTERNS: tuple[tuple[str, str], ...] = (
    ("private key block", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("bearer literal", r"Bearer\s+[A-Za-z0-9_\-\.]{12,}"),
    (
        "assigned credential",
        r"""(?ix)
        \b(token|secret|password|passwd|api[_-]?key|apikey|credential)\b
        \s* [:=] \s*
        ["'][A-Za-z0-9_\-\.]{12,}["']
        """,
    ),
    ("aws access key", r"\bAKIA[0-9A-Z]{16}\b"),
)

#: Files that are allowed to talk about secrets without carrying one. The
#: connection token is a first-class product concept, so the word appears in
#: settings schemas, gateway code and localization; what must never appear is a
#: value assigned to it, which is what the patterns above look for.
TEXT_SUFFIXES = frozenset({".lua", ".py", ".json", ".xml", ".edf", ".map", ".md"})


def _text_entries(archive: Path) -> list[tuple[str, str]]:
    found = []
    with zipfile.ZipFile(archive) as opened:
        for name in opened.namelist():
            if Path(name).suffix not in TEXT_SUFFIXES:
                continue
            found.append((name, opened.read(name).decode("utf-8", "replace")))
    return found


@pytest.fixture
def built(tmp_path: Path) -> tuple[package.Artifact, package.Artifact]:
    return build_mta_resource(tmp_path), build_companion_addon(tmp_path)


# --- inventory ---------------------------------------------------------------


def test_the_mta_artifact_unpacks_as_the_resource_directory_mta_expects(
    built: tuple[package.Artifact, package.Artifact],
) -> None:
    """The directory name is part of the identity.

    A resource unpacked as `ankigta-1.0.0` is a different resource to MTA, and
    the ACL right the Study Player holds names `ankigta`.
    """
    resource, _companion = built

    with zipfile.ZipFile(resource.archive) as archive:
        names = archive.namelist()

    assert all(name.startswith("ankigta/") for name in names)
    assert "ankigta/meta.xml" in names


def test_the_companion_artifact_unpacks_as_ankis_own_add_on_folder(
    built: tuple[package.Artifact, package.Artifact],
) -> None:
    """Anki unpacks an `.ankiaddon` into the folder it creates, so a directory
    inside the archive would bury `__init__.py` one level too deep."""
    _resource, companion = built

    with zipfile.ZipFile(companion.archive) as archive:
        names = archive.namelist()

    assert "__init__.py" in names
    assert "manifest.json" in names
    assert not [name for name in names if name.startswith("ankigta_companion/")]


def test_every_script_the_manifest_names_is_in_the_artifact(
    built: tuple[package.Artifact, package.Artifact],
) -> None:
    """A resource missing a script it registers fails at start, on a server
    that is not this machine."""
    from xml.etree import ElementTree

    resource, _companion = built
    manifest = ElementTree.parse(MTA_RESOURCE_ROOT / "meta.xml")
    declared = {
        f"ankigta/{element.get('src')}" for element in manifest.iter("script")
    }
    declared |= {f"ankigta/{element.get('src')}" for element in manifest.iter("map")}

    with zipfile.ZipFile(resource.archive) as archive:
        names = set(archive.namelist())

    assert declared <= names


def test_the_inventory_lists_what_the_archive_holds(
    built: tuple[package.Artifact, package.Artifact],
) -> None:
    resource, companion = built

    for artifact in (resource, companion):
        with zipfile.ZipFile(artifact.archive) as archive:
            packed = {
                name.split("/", 1)[1] if name.startswith("ankigta/") else name
                for name in archive.namelist()
            }
        assert {entry.path for entry in artifact.entries} == packed
        assert all(len(entry.sha256) == 64 for entry in artifact.entries)


def test_nothing_generated_or_private_is_shipped() -> None:
    """`user_files` is the one that matters: it is where the add-on keeps the
    connection token and the collection registry."""
    for root in (MTA_RESOURCE_ROOT, COMPANION_ROOT):
        paths = [entry.path for entry in inventory(root)]
        assert not [path for path in paths if "user_files" in path]
        assert not [path for path in paths if "__pycache__" in path]
        assert not [path for path in paths if path.endswith((".pyc", ".sqlite"))]


def test_the_two_artifacts_declare_the_same_version() -> None:
    """One release, one number. A manifest carrying its own would fall behind
    silently, and the certification matrix names a version."""
    assert package.resource_version() == package.companion_version()


# --- reproducibility ---------------------------------------------------------


def test_the_same_source_builds_the_same_bytes(tmp_path: Path) -> None:
    first = build_mta_resource(tmp_path / "first")
    second = build_mta_resource(tmp_path / "second")

    assert first.sha256 == second.sha256
    assert first.archive.read_bytes() == second.archive.read_bytes()


def test_the_archive_carries_no_build_timestamp(tmp_path: Path) -> None:
    """The reason the bytes repeat: a real timestamp would make every build
    differ from every other one, and a digest would prove nothing."""
    artifact = build_companion_addon(tmp_path)

    with zipfile.ZipFile(artifact.archive) as archive:
        stamps = {info.date_time for info in archive.infolist()}

    assert stamps == {package.FIXED_TIMESTAMP}


# --- the secret scan ---------------------------------------------------------


@pytest.mark.parametrize("label,pattern", SECRET_PATTERNS)
def test_no_shipped_file_carries_a_secret(
    built: tuple[package.Artifact, package.Artifact],
    label: str,
    pattern: str,
) -> None:
    offenders = []
    for artifact in built:
        for name, text in _text_entries(artifact.archive):
            match = re.search(pattern, text)
            if match is not None:
                offenders.append(f"{artifact.name}:{name}: {match.group(0)[:40]}")

    assert offenders == [], f"{label} found in a shipped file: {offenders}"


def test_the_scan_would_catch_a_planted_secret(tmp_path: Path) -> None:
    """A scan nobody has seen fail is a scan nobody knows works."""
    planted = tmp_path / "planted.py"
    planted.write_text('TOKEN = "s3cr3t-value-that-is-long"\n', encoding="utf-8")
    archive = tmp_path / "planted.zip"
    with zipfile.ZipFile(archive, "w") as opened:
        opened.write(planted, "planted.py")

    hits = [
        label
        for label, pattern in SECRET_PATTERNS
        for _name, text in _text_entries(archive)
        if re.search(pattern, text)
    ]

    assert "assigned credential" in hits
