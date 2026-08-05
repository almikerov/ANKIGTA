from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tests.lua.constants import string_constants

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
RESOURCE = REPO_ROOT / "mta" / "ankigta"
CLIENT_PICK = RESOURCE / "client" / "pick_entity.lua"
CLIENT_F7 = RESOURCE / "client" / "panel.lua"
SERVER_MAIN = RESOURCE / "server" / "main.lua"
SERVER_STORE = RESOURCE / "server" / "store.lua"
META = RESOURCE / "meta.xml"
CHECKLIST = REPO_ROOT / "docs" / "checklists" / "ticket24-pick-entity.md"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def function_body(lua: str, name: str) -> str:
    match = re.search(
        rf"(?:local )?function {re.escape(name)}\([^)]*\)(.*?)"
        rf"(?=\n(?:local function |function |[A-Za-z][A-Za-z.]* = |addEvent\())",
        lua,
        flags=re.DOTALL,
    )
    assert match, f"Lua function not found: {name}"
    return match.group(1)


def test_pick_entity_resource_and_manual_checklist_are_declared() -> None:
    meta = source(META)
    checklist = source(CHECKLIST)

    assert '<script src="client/pick_entity.lua"' in meta
    assert "Status: not run" in checklist
    for scenario in (
        "occlusion",
        "streaming boundary",
        "unmanaged",
        "destroyed",
        "Esc",
        "resource stop",
    ):
        assert scenario in checklist


def test_client_pick_entity_has_modal_aim_and_exact_cleanup_contract() -> None:
    """The aim is the cursor, and MTA is the one that casts the ray.

    This used to require `processLineOfSight` and `getCameraMatrix`, which
    aimed down the camera's own axis: usable while standing in the Map Editor
    and nowhere else. `onClientClick` already casts from the camera through the
    cursor and hands back what it hit, so a second cast here would be a second
    answer to a question MTA has answered -- and the two would disagree the
    moment the cursor left the centre of the screen.
    """
    pick = source(CLIENT_PICK)

    assert 'local PICK_ENTITY_REQUEST_EVENT = "ankigta:pickEntity"' in pick
    assert 'local PICK_ENTITY_RESULT_EVENT = "ankigta:pickEntityResult"' in pick
    assert "processLineOfSight(" not in pick, "MTA already cast this ray"
    assert 'addEventHandler("onClientClick"' in pick
    assert "isElementStreamedIn(element)" in pick
    assert '"object"' in pick and '"vehicle"' in pick and '"ped"' in pick
    assert 'nonEmptyData(element, "ankigtaEntityId")' in pick
    assert "toggleControl(" in pick
    assert "isControlEnabled(" in pick
    assert "showCursor(" in pick
    assert "restoreInputState" in pick
    assert "clickedElement" in function_body(pick, "targetUnderCursor")
    assert "isElementStreamedIn" in function_body(pick, "isEligibleTarget")
    assert "restoreInputState" in function_body(pick, "finishPickEntity")
    # Escape still cancels, but it is named by the shared schema rather than
    # spelt here: `activationKey` is refused for naming a key ANKIGTA already
    # answers to, and that refusal reads the same list this binds from.
    assert 'bindKey(dismissKey(), "down"' in pick
    assert "reservedKeys.dismiss" in function_body(pick, "dismissKey")
    assert 'addEventHandler("onClientResourceStop"' in pick


def test_f7_exposes_pick_action_and_focuses_successful_target() -> None:
    f7 = source(CLIENT_F7)
    pick = source(CLIENT_PICK)

    assert "ankigta:pickEntityFinished" in f7
    assert "ankigta:pickEntityStart" in string_constants(CLIENT_F7)
    assert "selectedMapId" in f7
    assert "selectedEntityId" in f7
    assert "selectedMapId = mapId" in f7
    assert "PICK_ENTITY_FINISHED_EVENT" in f7
    assert "triggerServerEvent(\n        PICK_ENTITY_REQUEST_EVENT" in pick
    assert "PICK_ENTITY_START_EVENT" in f7


def test_relink_preview_can_handoff_to_pick_entity_mode() -> None:
    f7 = source(CLIENT_F7)
    preview = function_body(f7, "actions.pickEntity")
    snapshot = function_body(f7, "entityRows")

    assert "relinkSourceMapId" in preview
    assert "triggerEvent(PICK_ENTITY_START_EVENT, resourceRoot, mode)" in preview
    assert "relinkSourceMapId" in preview
    assert "relinkSourceEntityId" in preview
    assert "relinkSourceMapId" in source(CLIENT_F7)
    assert "actions.relink" in source(CLIENT_F7)
    # Ticket 10 moved target selection inside the preview: Relink opens with a
    # source alone, and it is confirmation that gates on a chosen target.
    assert "selectedEntry()" in source(CLIENT_F7)
    assert "relinkSourceEntityId = entry.mapEntity.entityId" in preview


def test_f7_does_not_reopen_while_pick_modal_is_active() -> None:
    f7 = source(CLIENT_F7)
    request = function_body(f7, "togglePanel")

    assert "isPickEntityActive()" in request


def test_server_pick_validation_is_acl_bound_and_rejects_invalid_runtime_targets() -> None:
    server = source(SERVER_MAIN)

    assert 'local PICK_ENTITY_REQUEST_EVENT = "ankigta:pickEntity"' in server
    assert 'local PICK_ENTITY_RESULT_EVENT = "ankigta:pickEntityResult"' in server
    assert "validatePickEntity" in server
    validation = function_body(server, "validatePickEntity")
    assert "playerAuthorization(player)" in validation
    assert "isElement(entityElement)" in validation
    assert "getElementType(entityElement)" in validation
    assert "SUPPORTED_ENTITY_TYPES" in validation
    assert 'getElementData(entityElement, "ankigtaEntityId")' in validation
    assert "isElementStreamedIn(entityElement)" in validation
    assert "Store.getMapEntity" in validation
    assert "entity_not_managed" in validation
    assert "entity_not_streamed" in validation
    assert "map_entity_not_loaded" in validation
    assert "relink_target_already_linked" in validation
    assert "isIdentityCollision" in validation
    assert "addEventHandler(PICK_ENTITY_REQUEST_EVENT" in server


def test_runtime_lookup_requires_one_persisted_match_and_loaded_resource_owner() -> None:
    store = source(SERVER_STORE)
    lookup = function_body(store, "Store.findMapEntityByRuntimeElement")

    assert "Store.listMapEntities()" in lookup
    # Three durable names, not two. `me:ID` is only written while the stock
    # editor has the map open, so an object in a map that is merely *loaded*
    # is known by the `id` its `.map` file gave it.
    assert "persistentId" in lookup
    assert "editorId" in lookup
    assert "getElementID(entityElement)" in lookup
    assert "names[row.entity_id]" in lookup
    assert "map_entity_ambiguous" in lookup
    assert "getResourceFromName" in lookup
    assert "getResourceRootElement" in lookup
    assert "getElementParent" in lookup
    assert "belongsToOwner" in lookup
    assert "embeddedMapId" in lookup


@dataclass(frozen=True)
class Candidate:
    managed: bool
    streamed: bool
    blocked_by_wall: bool = False


def first_visible_managed(candidates: list[Candidate]) -> Candidate:
    """Small deterministic seam model for the client raycast contract."""
    for candidate in candidates:
        if candidate.blocked_by_wall:
            return None  # type: ignore[return-value]
        return candidate if candidate.managed and candidate.streamed else None  # type: ignore[return-value]
    return None  # type: ignore[return-value]


def test_raycast_simulation_stops_at_occluder_and_ignores_invalid_candidates() -> None:
    target = Candidate(managed=True, streamed=True)
    assert first_visible_managed([target]) == target
    assert first_visible_managed([Candidate(managed=False, streamed=True)]) is None
    assert (
        first_visible_managed(
            [Candidate(managed=False, streamed=True, blocked_by_wall=True), target]
        )
        is None
    )
    assert first_visible_managed([Candidate(managed=True, streamed=False)]) is None


@pytest.mark.parametrize(
    "exit_name",
    ["cancelPickEntity", "finishPickEntity", "handlePickEntityError"],
)
def test_every_modal_exit_uses_one_cleanup_path(exit_name: str) -> None:
    pick = source(CLIENT_PICK)
    body = function_body(pick, exit_name)
    assert "finishPickEntity" in body or exit_name == "finishPickEntity"
    assert "restoreInputState" in pick
