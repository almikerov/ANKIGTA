"""Ticket 29 — the recovery state is something the user is actually shown.

`Store.recovery()` already refuses to replace a damaged database on its own.
That refusal is only worth something if it reaches a person: a store that holds
a recovery state nobody is offered is indistinguishable from a server that
simply will not start.

So these tests drive the seam end to end. The server side is started the way
MTA starts it, the payload it sends is the payload the client side is given —
no second guess at its shape — and the choice the player makes on the screen is
followed back until a Spatial Link that only the backup held is readable again.

What a human still has to look at (that the screen is legible, that the wording
reads as an offer rather than a report) stays in
`docs/checklists/ticket29-migrations-backups-recovery.md`.
"""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from typing import Any, Iterator

import pytest

from tests.lua import MtaSandbox
from tests.lua import shipped_schemas


RESOURCE = Path(__file__).resolve().parents[1] / "mta" / "ankigta"
UUID = shipped_schemas.UUID

RECOVERY_STATE_EVENT = "ankigta:databaseRecovery"
RECOVERY_REQUEST_EVENT = "ankigta:requestDatabaseRecovery"
RESTORE_REQUEST_EVENT = "ankigta:restoreDatabaseBackup"
NOTICE_EVENT = "ankigta:pendingMapSaveNotice"


# --- harness ------------------------------------------------------------------


def manifest_scripts(*kinds: str) -> list[str]:
    """The scripts meta.xml declares, in declared order.

    Read rather than repeated, so a recovery screen that never got registered
    fails here instead of working in tests only.
    """
    manifest = ElementTree.parse(RESOURCE / "meta.xml")
    return [
        str(element.get("src"))
        for element in manifest.iter("script")
        if element.get("type") in kinds
    ]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def call(sandbox: MtaSandbox, expression: str, *args: Any) -> Any:
    return sandbox.eval(expression)(*args)


def as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def start_server(directory: Path) -> MtaSandbox:
    """The whole server side, started through `onResourceStart` as MTA does."""
    sandbox = MtaSandbox(database_path=str(directory / "ankigta.sqlite"))
    for script in manifest_scripts("shared", "server"):
        sandbox.load(script)
    # These tests need a Map Entity to survive a restore, and the tracer is a
    # convenient one. Asked for rather than seeded into every database: a
    # player's first F7 listing entities they never placed was that fixture
    # leaking out of the tests it was written for.
    sandbox.eval("function() ANKIGTA.Store.seedTracerFixtures = true end")()
    sandbox.trigger("onResourceStart")
    return sandbox


def start_client() -> MtaSandbox:
    """The whole client side, started through `onClientResourceStart`."""
    sandbox = MtaSandbox()
    for script in manifest_scripts("shared", "client"):
        sandbox.load(script)
    sandbox.trigger("onClientResourceStart")
    return sandbox


def seed(directory: Path) -> None:
    """Leave a database holding one Spatial Link and one verified backup."""
    sandbox = start_server(directory)
    try:
        linked = call(
            sandbox,
            """
            function(uuid)
                return ANKIGTA.Store.activateSpatialLink({
                    mapId = "ticket05-map",
                    entityId = "ticket05-entity",
                    cardIdentity = {collectionUuid = uuid, cardId = 4242},
                    mapLocator = {
                        resourceName = "ankigta",
                        mapFile = "Ticket 05 tracer map",
                    },
                    verifiedMapSha256 = string.rep("b", 64),
                })
            end
            """,
            UUID,
        )
        assert linked is not False, "the fixture must have data worth restoring"
        assert (
            call(sandbox, "function() return ANKIGTA.Backup.createDaily() end")
            is not False
        )
        call(sandbox, "function() return ANKIGTA.Store.close() end")
    finally:
        sandbox.close()


def corrupt(path: Path) -> None:
    path.write_bytes(b"this is not a database, it is a note to self." * 40)


def authorize(sandbox: MtaSandbox) -> Any:
    """A logged-in Study Player, announced the way `onPlayerLogin` does."""
    player = sandbox.add_study_player()
    sandbox.trigger("onPlayerLogin", player)
    return player


def sent(sandbox: MtaSandbox, event: str) -> list[Any]:
    return [
        entry.args for entry in sandbox.recorder.client_events if entry.name == event
    ]


def last_state(sandbox: MtaSandbox) -> Any:
    payloads = sent(sandbox, RECOVERY_STATE_EVENT)
    assert payloads, f"the server never sent {RECOVERY_STATE_EVENT}"
    return sandbox.to_python(payloads[-1][0])


@pytest.fixture
def workspace(tmp_path: Path) -> Iterator[Path]:
    yield tmp_path


# --- the state reaches the player ---------------------------------------------


def test_a_corrupt_database_offers_the_player_the_recovery_state(
    workspace: Path,
) -> None:
    """Opening damage does not merely fail: it produces something to choose from."""
    primary = workspace / "ankigta.sqlite"
    seed(workspace)
    corrupt(primary)
    damaged = digest(primary)

    sandbox = start_server(workspace)
    try:
        authorize(sandbox)

        state = last_state(sandbox)
        assert isinstance(state, dict)
        assert state["state"] == "recovery"
        assert state["awaitingChoice"] is True
        assert state["reason"] == "database_corrupt"
        assert [entry["verified"] for entry in as_list(state["backups"])] == [True]
        # Publishing the state is a read; it must not have touched the file.
        assert digest(primary) == damaged
    finally:
        sandbox.close()


def test_a_healthy_database_offers_no_recovery_state(workspace: Path) -> None:
    sandbox = start_server(workspace)
    try:
        authorize(sandbox)

        payloads = sent(sandbox, RECOVERY_STATE_EVENT)
        assert payloads, "the client is told there is nothing to recover from"
        assert sandbox.to_python(payloads[-1][0]) is False
    finally:
        sandbox.close()


def test_a_player_without_the_study_right_is_offered_nothing(
    workspace: Path,
) -> None:
    """Recovery names files on the server's disk; it is not for a guest."""
    primary = workspace / "ankigta.sqlite"
    seed(workspace)
    corrupt(primary)

    sandbox = start_server(workspace)
    try:
        stranger = sandbox.eval(
            "function() return {__element = true, type = 'player'} end"
        )()
        sandbox.world_elements.append(stranger)
        sandbox.trigger("onPlayerLogin", stranger)

        assert sent(sandbox, RECOVERY_STATE_EVENT) == []

        # Nor by asking for it directly, which is the path a client controls.
        sandbox.trigger(
            RECOVERY_REQUEST_EVENT, sandbox.eval("resourceRoot"), client=stranger
        )

        assert sent(sandbox, RECOVERY_STATE_EVENT) == []
    finally:
        sandbox.close()


# --- the screen ---------------------------------------------------------------


def recovery_state(sandbox: MtaSandbox) -> Any:
    """A recovery payload of exactly the shape the server produces."""
    return call(
        sandbox,
        """
        function()
            return {
                state = "recovery",
                reason = "database_corrupt",
                detail = "database disk image is malformed",
                databasePath = "ankigta.sqlite",
                awaitingChoice = true,
                backups = {
                    {
                        id = 2,
                        kind = "daily",
                        day = "2026-07-31",
                        path = "backups/ankigta-daily-2.sqlite",
                        createdAt = 120,
                        schemaVersion = 4,
                        verified = true,
                        reason = false,
                    },
                    {
                        id = 1,
                        kind = "premigration",
                        day = "2026-07-30",
                        path = "backups/ankigta-premigration-1.sqlite",
                        createdAt = 60,
                        schemaVersion = 4,
                        verified = false,
                        reason = "backup_integrity_failed",
                    },
                },
                quarantine = {
                    {
                        path = "backups/quarantine-3.sqlite",
                        reason = "database_corrupt",
                        quarantinedAt = 130,
                    },
                },
            }
        end
        """,
    )


def show_recovery(sandbox: MtaSandbox) -> None:
    sandbox.trigger("ankigta:setAuthorized", sandbox.eval("resourceRoot"), True)
    sandbox.trigger(
        RECOVERY_STATE_EVENT, sandbox.eval("resourceRoot"), recovery_state(sandbox)
    )


def control(sandbox: MtaSandbox, name: str) -> Any:
    """One named control of the recovery screen, as the screen itself sees it."""
    handle = call(
        sandbox, "function(n) return ANKIGTA.Recovery.control(n) end", name
    )
    assert handle is not False, f"the recovery screen has no {name!r} control"
    return handle


def enabled(sandbox: MtaSandbox, name: str) -> bool:
    return bool(sandbox.eval("guiGetEnabled")(control(sandbox, name)))


def select_backup(sandbox: MtaSandbox, row: int) -> None:
    grid = control(sandbox, "backups")
    sandbox.eval("guiGridListSetSelectedItem")(grid, row, 1)
    sandbox.click(grid)


def label(sandbox: MtaSandbox, key: str) -> str:
    return str(call(sandbox, "function(k) return ANKIGTA.Locale.text(k) end", key))


def test_the_recovery_screen_lists_every_copy_and_what_is_wrong_with_it() -> None:
    sandbox = start_client()
    try:
        show_recovery(sandbox)

        cells = sandbox.grid_texts()
        assert "backups/ankigta-daily-2.sqlite" in cells
        assert "backups/ankigta-premigration-1.sqlite" in cells
        # The unusable copy is shown with its reason rather than hidden, so the
        # user can see there was a copy and why it is not on offer.
        assert any("backup_integrity_failed" in cell for cell in cells)
        # And the damaged original is named, not merely alluded to.
        assert "backups/quarantine-3.sqlite" in cells
        assert "ankigta.sqlite" in " ".join(sandbox.widget_texts())
    finally:
        sandbox.close()


def test_restore_stays_out_of_reach_until_a_verified_copy_is_chosen() -> None:
    sandbox = start_client()
    try:
        show_recovery(sandbox)

        assert label(sandbox, "recovery.restore") in sandbox.widget_texts()
        assert enabled(sandbox, "restore") is False

        select_backup(sandbox, 1)  # the unverified premigration copy
        assert enabled(sandbox, "restore") is False

        select_backup(sandbox, 0)  # the verified daily copy
        assert enabled(sandbox, "restore") is True
    finally:
        sandbox.close()


def test_choosing_a_copy_asks_the_server_for_that_copy_by_id() -> None:
    sandbox = start_client()
    try:
        show_recovery(sandbox)
        select_backup(sandbox, 0)

        sandbox.click(control(sandbox, "restore"))

        requests = [
            tuple(entry.args)
            for entry in sandbox.recorder.server_events
            if entry.name == RESTORE_REQUEST_EVENT
        ]
        assert requests == [(2,)]
    finally:
        sandbox.close()


def test_an_unverified_copy_is_never_asked_for_even_by_a_stray_click() -> None:
    """The disabled button is the hint; the guard is what makes it true."""
    sandbox = start_client()
    try:
        show_recovery(sandbox)
        select_backup(sandbox, 1)

        sandbox.click(control(sandbox, "restore"))

        assert [
            entry.name
            for entry in sandbox.recorder.server_events
            if entry.name == RESTORE_REQUEST_EVENT
        ] == []
    finally:
        sandbox.close()


def test_the_screen_closes_itself_when_the_server_says_recovery_is_over() -> None:
    sandbox = start_client()
    try:
        show_recovery(sandbox)
        assert label(sandbox, "recovery.title") in sandbox.widget_texts()

        sandbox.trigger(
            RECOVERY_STATE_EVENT, sandbox.eval("resourceRoot"), False
        )

        assert label(sandbox, "recovery.title") not in sandbox.widget_texts()
    finally:
        sandbox.close()


def test_the_recovery_screen_follows_a_language_switch() -> None:
    sandbox = start_client()
    try:
        call(
            sandbox,
            'function() ANKIGTA.ClientSettings.set("language", "ru") end',
        )
        show_recovery(sandbox)
        russian = label(sandbox, "recovery.restore")
        assert russian in sandbox.widget_texts()

        call(
            sandbox,
            'function() ANKIGTA.ClientSettings.set("language", "en") end',
        )

        english = sandbox.widget_texts()
        assert "Restore selected backup" in english
        assert russian not in english
    finally:
        sandbox.close()


# --- the choice reaches the restore -------------------------------------------


def test_the_choice_made_on_the_screen_restores_that_backup(
    workspace: Path,
) -> None:
    """The end of the whole ticket: a person picks, and the data comes back."""
    primary = workspace / "ankigta.sqlite"
    seed(workspace)
    corrupt(primary)
    damaged = digest(primary)

    sandbox = start_server(workspace)
    try:
        player = authorize(sandbox)
        offered = as_list(last_state(sandbox)["backups"])
        assert [entry["verified"] for entry in offered] == [True]

        sandbox.trigger(
            RESTORE_REQUEST_EVENT,
            sandbox.eval("resourceRoot"),
            offered[0]["id"],
            client=player,
        )

        # The store is open again and holds the link only the backup had.
        assert dict(
            sandbox.to_python(
                call(sandbox, "function() return ANKIGTA.Store.status() end")
            )
        )["ready"] is True
        entity = sandbox.to_python(
            call(
                sandbox,
                'function() return ANKIGTA.Store.getMapEntity('
                '"ticket05-map", "ticket05-entity") end',
            )
        )
        assert entity["card_id"] == 4242

        # The screen is told the state is over, and the damaged file is kept.
        assert last_state(sandbox) is False
        kept = [
            path
            for path in workspace.rglob("*")
            if path.is_file() and digest(path) == damaged
        ]
        assert kept, "the damaged original was thrown away"
    finally:
        sandbox.close()


def test_a_refused_restore_leaves_the_state_armed_and_the_files_alone(
    workspace: Path,
) -> None:
    primary = workspace / "ankigta.sqlite"
    seed(workspace)
    corrupt(primary)
    before = {path: digest(path) for path in workspace.rglob("*") if path.is_file()}

    sandbox = start_server(workspace)
    try:
        player = authorize(sandbox)

        sandbox.trigger(
            RESTORE_REQUEST_EVENT,
            sandbox.eval("resourceRoot"),
            9999,
            client=player,
        )

        after = {path: digest(path) for path in workspace.rglob("*") if path.is_file()}
        assert after == before, "a refused restore rewrote a file"
        state = last_state(sandbox)
        assert isinstance(state, dict)
        assert state["awaitingChoice"] is True
        notices = [
            tuple(entry.args)
            for entry in sandbox.recorder.client_events
            if entry.name == NOTICE_EVENT
        ]
        assert ("notice.restoreFailed", "backup_not_found") in notices
    finally:
        sandbox.close()


def test_a_healthy_database_cannot_be_replaced_by_a_restore_request(
    workspace: Path,
) -> None:
    """No recovery state, no restore. Otherwise the screen becomes a weapon."""
    primary = workspace / "ankigta.sqlite"
    seed(workspace)
    before = {path: digest(path) for path in workspace.rglob("*") if path.is_file()}

    sandbox = start_server(workspace)
    try:
        player = authorize(sandbox)
        listed = as_list(
            sandbox.to_python(
                call(sandbox, "function() return ANKIGTA.Backup.list() end")
            )
        )
        assert listed, "there is a real backup it could have restored"

        sandbox.trigger(
            RESTORE_REQUEST_EVENT,
            sandbox.eval("resourceRoot"),
            listed[0]["id"],
            client=player,
        )

        after = {path: digest(path) for path in workspace.rglob("*") if path.is_file()}
        assert after == before
        assert digest(primary) == before[primary]
    finally:
        sandbox.close()


def test_a_stranger_cannot_ask_for_a_restore(workspace: Path) -> None:
    primary = workspace / "ankigta.sqlite"
    seed(workspace)
    corrupt(primary)
    before = {path: digest(path) for path in workspace.rglob("*") if path.is_file()}

    sandbox = start_server(workspace)
    try:
        authorize(sandbox)
        offered = as_list(last_state(sandbox)["backups"])
        stranger = sandbox.eval(
            "function() return {__element = true, type = 'player'} end"
        )()

        sandbox.trigger(
            RESTORE_REQUEST_EVENT,
            sandbox.eval("resourceRoot"),
            offered[0]["id"],
            client=stranger,
        )

        after = {path: digest(path) for path in workspace.rglob("*") if path.is_file()}
        assert after == before
    finally:
        sandbox.close()


def test_asking_for_the_state_returns_the_copies_as_they_are_now(
    workspace: Path,
) -> None:
    """The list is re-read on request: a copy can rot between two glances."""
    primary = workspace / "ankigta.sqlite"
    seed(workspace)
    corrupt(primary)

    sandbox = start_server(workspace)
    try:
        player = authorize(sandbox)
        assert [
            entry["verified"] for entry in as_list(last_state(sandbox)["backups"])
        ] == [True]

        copy = next(
            path
            for path in workspace.rglob("*.sqlite")
            if path != primary and "quarantine" not in path.name
        )
        corrupt(copy)
        sandbox.trigger(
            RECOVERY_REQUEST_EVENT, sandbox.eval("resourceRoot"), client=player
        )

        assert [
            entry["verified"] for entry in as_list(last_state(sandbox)["backups"])
        ] == [False]
    finally:
        sandbox.close()
