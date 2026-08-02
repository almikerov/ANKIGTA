"""Build the two artifacts a release ships, and say what is in them.

ANKIGTA ships two things and no installer: the MTA resource directory, which
the operator copies into their own server, and the companion add-on folder,
which the user installs into Anki by hand (ADR 0023). Both are plain zip
archives of a directory that is already in this repository, so packaging is
mostly a question of what is *left out* and of being able to prove afterwards
what went in.

Two properties this module exists for:

- **The inventory is the evidence.** Every entry is listed with its SHA-256, so
  "which build is installed" and "was anything else in there" have answers
  after the fact rather than only at build time.
- **The same source produces the same bytes.** Timestamps and permissions are
  fixed, entries are sorted, and compression is stored-deflate at a fixed
  level, so two builds of one commit are byte-identical and a diff between two
  releases is a diff of what changed rather than of when it was built.

Nothing here reaches outside the repository, and nothing writes into an
installed MTA, GTA or Anki tree: it writes archives into a directory it is
told about, and installing them is a documented manual step
(`docs/operations/installation.md`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence
from xml.etree import ElementTree


REPO_ROOT = Path(__file__).resolve().parents[1]
MTA_RESOURCE_ROOT = REPO_ROOT / "mta" / "ankigta"
COMPANION_ROOT = REPO_ROOT / "companion" / "ankigta_companion"

#: A fixed timestamp for every entry. Zip stores local time with no zone, so
#: the alternative is an archive whose bytes depend on when and where it was
#: built. 1980-01-01 is the earliest a zip entry can carry.
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)

#: Never shipped, whatever the source tree happens to hold at build time.
#:
#: `user_files` is the one that matters: Anki keeps add-on state there, and
#: this is the directory the collection registry and the connection settings —
#: which carry the token — live in. Shipping it would publish a secret and
#: overwrite the user's own state on update.
EXCLUDED_DIRECTORIES = frozenset(
    {
        "__pycache__",
        "user_files",
        ".mypy_cache",
        ".pytest_cache",
    }
)
EXCLUDED_SUFFIXES = frozenset({".pyc", ".pyo", ".sqlite", ".log"})
EXCLUDED_NAMES = frozenset({".DS_Store", "Thumbs.db"})


@dataclass(frozen=True)
class ArtifactEntry:
    """One file inside an artifact, and the digest of what it holds."""

    path: str
    size: int
    sha256: str

    def payload(self) -> dict[str, object]:
        return {"path": self.path, "size": self.size, "sha256": self.sha256}


@dataclass(frozen=True)
class Artifact:
    """One shipped archive: where it goes, what it holds, and its digest."""

    name: str
    #: Where an installed copy of this artifact lives, as documentation states
    #: it. Carried with the artifact so the record and the instructions cannot
    #: drift into naming two different places.
    install_target: str
    version: str
    archive: Path
    sha256: str
    entries: tuple[ArtifactEntry, ...]

    def payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "installTarget": self.install_target,
            "version": self.version,
            "archive": self.archive.name,
            "sha256": self.sha256,
            "fileCount": len(self.entries),
            "files": [entry.payload() for entry in self.entries],
        }


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _shipped_files(root: Path) -> Iterator[Path]:
    """Every file under `root` a release ships, in a stable order."""
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        relative = path.relative_to(root)
        if any(part in EXCLUDED_DIRECTORIES for part in relative.parts):
            continue
        if path.suffix in EXCLUDED_SUFFIXES or path.name in EXCLUDED_NAMES:
            continue
        yield path


def inventory(root: Path) -> tuple[ArtifactEntry, ...]:
    """What a build from this directory would contain, without building it."""
    entries = []
    for path in _shipped_files(root):
        data = path.read_bytes()
        entries.append(
            ArtifactEntry(
                path=path.relative_to(root).as_posix(),
                size=len(data),
                sha256=_digest(data),
            )
        )
    return tuple(entries)


def resource_version() -> str:
    """The version `meta.xml` declares.

    One source of truth: the add-on manifest is checked against this rather
    than carrying a second number that can fall behind.
    """
    manifest = ElementTree.parse(MTA_RESOURCE_ROOT / "meta.xml")
    info = manifest.find("info")
    if info is None or info.get("version") is None:
        raise ValueError("meta.xml declares no version")
    return str(info.get("version"))


def companion_version() -> str:
    manifest = json.loads((COMPANION_ROOT / "manifest.json").read_text("utf-8"))
    version = manifest.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("the companion manifest declares no version")
    return version


def _write_archive(
    destination: Path,
    root: Path,
    entries: Sequence[ArtifactEntry],
    *,
    prefix: str = "",
) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for entry in entries:
            info = zipfile.ZipInfo(prefix + entry.path, FIXED_TIMESTAMP)
            # Fixed mode as well as fixed time: a checkout on a different
            # umask would otherwise change the bytes.
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, (root / entry.path).read_bytes())
    return _digest(destination.read_bytes())


def build_mta_resource(destination: Path) -> Artifact:
    """The MTA resource, as a directory the operator drops into `resources/`.

    Entries are prefixed with `ankigta/`, so unpacking it anywhere produces the
    directory name the resource must have — a resource unpacked as `ankigta-1`
    is a different resource to MTA, and its ACL right would not apply.
    """
    version = resource_version()
    entries = inventory(MTA_RESOURCE_ROOT)
    archive = destination / f"ankigta-mta-resource-{version}.zip"
    digest = _write_archive(
        archive,
        MTA_RESOURCE_ROOT,
        entries,
        prefix="ankigta/",
    )
    return Artifact(
        name="ankigta-mta-resource",
        install_target=(
            "<MTA Server>/mods/deathmatch/resources/ankigta"
        ),
        version=version,
        archive=archive,
        sha256=digest,
        entries=entries,
    )


def build_companion_addon(destination: Path) -> Artifact:
    """The companion add-on, as Anki's own add-on folder.

    No prefix: Anki's add-on manager unpacks an `.ankiaddon` file *into* the
    folder it creates, so a top-level directory inside the archive would give
    the user an add-on whose `__init__.py` is one level too deep.
    """
    version = companion_version()
    entries = inventory(COMPANION_ROOT)
    archive = destination / f"ankigta-companion-{version}.ankiaddon"
    digest = _write_archive(archive, COMPANION_ROOT, entries)
    return Artifact(
        name="ankigta-companion",
        install_target="<Anki data folder>/addons21/ankigta_companion",
        version=version,
        archive=archive,
        sha256=digest,
        entries=entries,
    )


def build_all(destination: Path) -> tuple[Artifact, ...]:
    return (
        build_mta_resource(destination),
        build_companion_addon(destination),
    )


def manifest(artifacts: Iterable[Artifact]) -> dict[str, object]:
    return {
        "report": "ankigta-artifacts",
        "reportVersion": 1,
        "artifacts": [artifact.payload() for artifact in artifacts],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.package")
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "dist",
        help="where to write the archives (default: ./dist)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="where to write the artifact inventory as JSON",
    )
    arguments = parser.parse_args(argv)

    artifacts = build_all(arguments.out)
    for artifact in artifacts:
        print(
            f"{artifact.name} {artifact.version}"
            f" -> {artifact.archive}"
            f" ({len(artifact.entries)} files, sha256 {artifact.sha256})"
        )
        print(f"  installs to {artifact.install_target}")
    if arguments.manifest is not None:
        arguments.manifest.parent.mkdir(parents=True, exist_ok=True)
        arguments.manifest.write_text(
            json.dumps(manifest(artifacts), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\ninventory written to {arguments.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
