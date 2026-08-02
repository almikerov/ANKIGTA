"""Ticket 31 — install, upgrade, uninstall and reinstall, on the real artifact.

Everything here runs against the *unpacked archive* rather than against the
working tree it was built from, because that is the copy an operator gets. The
scripts are loaded out of the unpacked directory and the database is opened
inside it, which is where MTA puts a resource's database: `dbConnect("sqlite",
"ankigta.sqlite")` resolves against the resource's own directory.

That last fact is why the uninstall scenario exists in this form. The user's
Spatial Links live *inside* the folder the instructions tell them to delete, so
"delete the resource folder" is only a safe instruction if the shipped files
and the user's data are distinguishable — which is what the inventory makes
them, and what these tests hold to.

No installed MTA, GTA or Anki tree is touched: every scenario builds its own
throwaway server directory under pytest's temporary path.
"""

from __future__ import annotations

import sqlite3
import zipfile
from pathlib import Path
from typing import Any, Iterator
from xml.etree import ElementTree

import pytest

from tests.lua import MtaSandbox
from tests.lua import shipped_schemas
from tests.lua.shipped_schemas import SHIPPED_VERSIONS, rows
from tools.package import build_mta_resource


CURRENT_SCHEMA_VERSION = 4
DATABASE = "ankigta.sqlite"


@pytest.fixture(scope="module")
def artifact(tmp_path_factory: pytest.TempPathFactory) -> Any:
    """One build for the whole suite: every scenario installs the same bytes."""
    return build_mta_resource(tmp_path_factory.mktemp("ankigta-dist"))


def install(artifact: Any, server_root: Path) -> Path:
    """Unpack the artifact into a disposable MTA `resources/` directory."""
    resources = server_root / "mods" / "deathmatch" / "resources"
    resources.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(artifact.archive) as archive:
        archive.extractall(resources)
    return resources / "ankigta"


def uninstall(artifact: Any, installed: Path) -> list[str]:
    """Remove exactly what was shipped, and nothing else.

    The inventory is the list. Anything left behind afterwards is something the
    release did not put there, which is the property the removal instructions
    rest on.
    """
    for entry in artifact.entries:
        (installed / entry.path).unlink()
    for directory in sorted(
        (path for path in installed.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        if not any(directory.iterdir()):
            directory.rmdir()
    return sorted(
        path.relative_to(installed).as_posix()
        for path in installed.rglob("*")
        if path.is_file()
    )


def scripts(installed: Path, *kinds: str) -> list[str]:
    manifest = ElementTree.parse(installed / "meta.xml")
    return [
        str(element.get("src"))
        for element in manifest.iter("script")
        if element.get("type") in kinds
    ]


def run(installed: Path) -> MtaSandbox:
    """Start the installed copy, the way `onResourceStart` does."""
    sandbox = MtaSandbox(database_path=str(installed / DATABASE))
    for script in scripts(installed, "shared", "server"):
        sandbox.load(script, root=installed)
    sandbox.trigger("onResourceStart")
    return sandbox


def store_status(sandbox: MtaSandbox) -> dict[str, Any]:
    return dict(
        sandbox.to_python(
            sandbox.eval("function() return ANKIGTA.Store.status() end")()
        )
    )


def link_count(database: Path) -> int:
    """How many Spatial Links the database holds, or zero before it could.

    `spatial_links` arrived with schema v3, so a v1 or v2 database has none to
    lose — which is a different statement from having lost them.
    """
    try:
        return len(rows(database, "SELECT * FROM spatial_links"))
    except sqlite3.OperationalError:
        return 0


def entity_keys(database: Path) -> set[tuple[str, str]]:
    return {
        (str(row["map_id"]), str(row["entity_id"]))
        for row in rows(database, "SELECT map_id, entity_id FROM map_entities")
    }


#: What a clean install puts in the database before the user does anything.
#:
#: Nothing, and that is the point.
#:
#: It used to seed `ticket05-map/ticket05-entity`, so a player's first F7
#: listed a Map Entity they had never placed, in a dimension they could not
#: reach. The v1 record carried that as an open criterion. The fixture is a
#: test fixture now: `Store.seedTracerFixtures` asks for it, and only tests do.
#:
#: Pinned as empty so it cannot come back quietly.
SEEDED_ENTITIES: set[tuple[str, str]] = set()


def integrity(database: Path) -> str:
    connection = sqlite3.connect(database)
    try:
        return str(connection.execute("PRAGMA integrity_check").fetchone()[0])
    finally:
        connection.close()


@pytest.fixture
def server_root(tmp_path: Path) -> Iterator[Path]:
    yield tmp_path / "MTA Server"


# --- clean install -----------------------------------------------------------


def test_a_clean_install_starts_and_creates_its_database(
    artifact: Any,
    server_root: Path,
) -> None:
    installed = install(artifact, server_root)

    sandbox = run(installed)
    try:
        status = store_status(sandbox)
    finally:
        sandbox.close()

    assert status["ready"] is True
    assert status["schemaVersion"] == CURRENT_SCHEMA_VERSION
    assert (installed / DATABASE).exists()


def test_the_installed_copy_is_the_artifact_and_nothing_else(
    artifact: Any,
    server_root: Path,
) -> None:
    installed = install(artifact, server_root)

    present = sorted(
        path.relative_to(installed).as_posix()
        for path in installed.rglob("*")
        if path.is_file()
    )

    assert present == sorted(entry.path for entry in artifact.entries)


def test_a_clean_install_seeds_exactly_the_fixtures_it_ships(
    artifact: Any,
    server_root: Path,
) -> None:
    """What a fresh database contains before the user does anything.

    It is not empty, and that is a finding rather than a design: the release
    ships two tracer maps and seeds a Map Entity of its own. The v1
    certification record carries it as an open criterion with the reason.
    Pinned here so the set cannot grow quietly.
    """
    installed = install(artifact, server_root)

    sandbox = run(installed)
    try:
        assert store_status(sandbox)["ready"] is True
    finally:
        sandbox.close()

    assert entity_keys(installed / DATABASE) == SEEDED_ENTITIES
    assert link_count(installed / DATABASE) == 0


def test_a_clean_install_needs_no_sqlite_or_map_editing(
    artifact: Any,
    server_root: Path,
) -> None:
    """The whole first run, from unpacking to a store that is ready, with no
    step in between that opens a database or a `.map` by hand."""
    installed = install(artifact, server_root)
    before = {path.name for path in installed.rglob("*") if path.is_file()}

    sandbox = run(installed)
    try:
        assert store_status(sandbox)["ready"] is True
    finally:
        sandbox.close()

    # The only thing the first run added is the database it created itself.
    after = {path.name for path in installed.rglob("*") if path.is_file()}
    assert after - before == {DATABASE}


# --- upgrade -----------------------------------------------------------------


@pytest.mark.parametrize("version", SHIPPED_VERSIONS)
def test_upgrading_over_a_prior_schema_keeps_the_links(
    artifact: Any,
    server_root: Path,
    version: str,
) -> None:
    """An upgrade is a copy over the top; the database that was there stays.

    Migration itself is ticket 29's; what this adds is that the migration runs
    from an installed artifact rather than from the working tree, and that the
    operator's rows are still there afterwards.
    """
    installed = install(artifact, server_root)
    database = installed / DATABASE
    shipped_schemas.build(database, version)
    entities, links = entity_keys(database), link_count(database)
    assert entities

    sandbox = run(installed)
    try:
        status = store_status(sandbox)
    finally:
        sandbox.close()

    assert status["ready"] is True
    assert status["schemaVersion"] == CURRENT_SCHEMA_VERSION
    # Every Map Entity that was there is still there. Compared as keys rather
    # than as a count, so a migration that dropped one and the clean-install
    # seed that adds one cannot cancel each other out.
    assert entities <= entity_keys(database)
    assert entity_keys(database) - entities == SEEDED_ENTITIES
    assert link_count(database) == links
    assert integrity(database) == "ok"


@pytest.mark.parametrize("version", ("v1", "v3legacy"))
def test_an_upgrade_leaves_a_copy_of_what_it_migrated(
    artifact: Any,
    server_root: Path,
    version: str,
) -> None:
    """ADR 0016: a verified backup before every migration. An upgrade is the
    moment that promise is worth anything."""
    installed = install(artifact, server_root)
    shipped_schemas.build(installed / DATABASE, version)

    sandbox = run(installed)
    try:
        backups = sorted(
            path.name for path in (installed / "backups").glob("*.sqlite")
        )
    finally:
        sandbox.close()

    assert backups, "no pre-migration backup was written"


def test_an_upgrade_replaces_only_shipped_files(
    artifact: Any,
    server_root: Path,
) -> None:
    """The operator's own files survive the copy-over.

    Written as the update instructions describe it: unpack the new artifact
    over the old install without deleting anything first.
    """
    installed = install(artifact, server_root)
    sandbox = run(installed)
    sandbox.close()
    (installed / "operator-notes.txt").write_text("mine", encoding="utf-8")

    install(artifact, server_root)

    assert (installed / "operator-notes.txt").read_text(encoding="utf-8") == "mine"
    assert (installed / DATABASE).exists()


# --- uninstall ---------------------------------------------------------------


def test_removing_the_shipped_files_leaves_the_users_data_behind(
    artifact: Any,
    server_root: Path,
) -> None:
    """The property the removal instructions rest on.

    A Spatial Link the user made lives in a database inside the folder they are
    told to delete. Being able to remove exactly what was shipped is what makes
    "take your database out first" an instruction rather than a hope.
    """
    installed = install(artifact, server_root)
    sandbox = run(installed)
    sandbox.close()
    database = installed / DATABASE
    assert database.exists()

    left = uninstall(artifact, installed)

    assert DATABASE in left
    assert not (installed / "meta.xml").exists()
    assert integrity(database) == "ok"


def test_the_database_still_reads_after_the_resource_is_gone(
    artifact: Any,
    server_root: Path,
) -> None:
    """Post-removal data integrity: the links are readable with no ANKIGTA in
    the picture at all."""
    installed = install(artifact, server_root)
    shipped_schemas.build(installed / DATABASE, "v4")
    sandbox = run(installed)
    sandbox.close()
    database = installed / DATABASE
    before = link_count(database)

    uninstall(artifact, installed)

    assert integrity(database) == "ok"
    assert link_count(database) == before
    assert before > 0


def test_stopping_the_resource_asks_anki_to_empty_the_owned_deck(
    artifact: Any,
    server_root: Path,
) -> None:
    """Story 46, at the moment removal begins.

    A stop that only closed SQLite would leave the session's cards sitting in a
    filtered deck the user did not put them in, with nothing left running to
    take them out.
    """
    installed = install(artifact, server_root)
    sandbox = run(installed)
    try:
        sandbox.execute(
            'ANKIGTA.ConnectionConfig.loadEffective = function()'
            ' return {port = 51600, token = "t"}, false, false end'
        )
        sandbox.add_study_player()

        sandbox.trigger("onResourceStop", sandbox.eval("resourceRoot"))

        asked = [
            fetch["url"]
            for fetch in sandbox.recorder.remote_fetches
            if fetch["url"].endswith("/v1/session/stop")
        ]
    finally:
        sandbox.close()

    assert asked, "the resource stopped without asking the companion to stop"


# --- reinstall ---------------------------------------------------------------


def test_reinstalling_adopts_the_database_that_was_left_in_place(
    artifact: Any,
    server_root: Path,
) -> None:
    installed = install(artifact, server_root)
    shipped_schemas.build(installed / DATABASE, "v4")
    sandbox = run(installed)
    sandbox.close()
    database = installed / DATABASE
    before = link_count(database)

    uninstall(artifact, installed)
    install(artifact, server_root)
    sandbox = run(installed)
    try:
        status = store_status(sandbox)
    finally:
        sandbox.close()

    assert status["ready"] is True
    assert status["schemaVersion"] == CURRENT_SCHEMA_VERSION
    assert link_count(database) == before


def test_reinstalling_after_taking_the_database_away_starts_empty(
    artifact: Any,
    server_root: Path,
) -> None:
    """The other half of removal: a user who wanted a clean slate gets one, and
    gets it by moving a file rather than by editing SQLite."""
    installed = install(artifact, server_root)
    shipped_schemas.build(installed / DATABASE, "v4")
    sandbox = run(installed)
    sandbox.close()

    uninstall(artifact, installed)
    (installed / DATABASE).rename(server_root / "kept-ankigta.sqlite")
    install(artifact, server_root)
    sandbox = run(installed)
    try:
        status = store_status(sandbox)
    finally:
        sandbox.close()

    assert status["ready"] is True
    assert link_count(installed / DATABASE) == 0
    # And the copy they moved aside is still a database.
    assert integrity(server_root / "kept-ankigta.sqlite") == "ok"
