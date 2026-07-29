from __future__ import annotations

import json
import os
import traceback
from pathlib import Path
from typing import Any, Callable

from aqt import gui_hooks, mw
from aqt.qt import QTimer

from ankigta_companion.collection_identity import (
    COLLECTION_UUID_CONFIG_KEY,
    CollectionCopyDecision,
    CollectionIdentityService,
)


EVIDENCE_DIR = Path(os.environ["ANKIGTA_TICKET04_EVIDENCE"])
PHASE = os.environ["ANKIGTA_TICKET04_PHASE"]
RENAMED_PROFILE = "ANKIGTA_T04_B_RENAMED"

stage = "initial"
rename_before: dict[str, Any] | None = None


def write_evidence(name: str, payload: object) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_DIR / name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def finish_process() -> None:
    QTimer.singleShot(200, mw.app.quit)


def addon() -> Any:
    import ankigta_companion

    if ankigta_companion.addon is None:
        raise RuntimeError("production companion add-on did not start")
    return ankigta_companion.addon


def collection_snapshot() -> dict[str, Any]:
    identity = mw.col.get_config(COLLECTION_UUID_CONFIG_KEY)
    response = addon().server
    from .http import health_request

    health = health_request(response, f"{PHASE}-{stage}")
    return {
        "profileName": mw.pm.name,
        "collectionPath": mw.pm.collectionPath(),
        "collectionUuidInConfig": identity,
        "cardIds": sorted(int(card_id) for card_id in mw.col.find_cards("")),
        "health": health,
        "ankigtaSessionAbsent": "ANKIGTA Session"
        not in {
            item.name
            for item in mw.col.decks.all_names_and_ids(skip_empty_default=False)
        },
    }


def initialize_bound_collection(output_name: str) -> None:
    before = collection_snapshot()
    collection_uuid = before["health"]["body"]["payload"]["collection"][
        "collectionUuid"
    ]
    result = addon().bind_current_collection(collection_uuid)
    after = collection_snapshot()
    write_evidence(
        output_name,
        {
            "before": before,
            "bindResult": {
                "collectionUuid": result.collection_uuid,
                "identityState": result.state.value,
            },
            "after": after,
        },
    )
    finish_process()


def restart_a() -> None:
    write_evidence("restart-a.json", collection_snapshot())
    finish_process()


def collision_b_then_rename() -> None:
    global rename_before, stage
    if stage == "initial":
        rename_before = collection_snapshot()
        stage = "renaming"

        def after_unload() -> None:
            global stage
            mw.pm.rename(RENAMED_PROFILE)
            mw.pm.load(RENAMED_PROFILE)
            stage = "reopening"
            mw.loadProfile()

        mw.unloadProfile(after_unload)
        return
    if stage != "reopening":
        return

    after_rename_pending = collection_snapshot()
    collection = after_rename_pending["health"]["body"]["payload"]["collection"]
    decision = addon().decide_current_collection_copy(
        collection["collectionUuid"],
        CollectionCopyDecision.PREVIOUS_COLLECTION,
    )
    after_decision = collection_snapshot()
    write_evidence(
        "collision-b-rename.json",
        {
            "beforeRename": rename_before,
            "afterRenamePending": after_rename_pending,
            "decisionResult": {
                "collectionUuid": decision.collection_uuid,
                "identityState": decision.state.value,
            },
            "afterDecision": after_decision,
        },
    )
    stage = "finished"
    finish_process()


def present_copy() -> None:
    write_evidence("present-copy.json", collection_snapshot())
    finish_process()


def restore_decision(decision: CollectionCopyDecision, output_name: str) -> None:
    before = collection_snapshot()
    collection = before["health"]["body"]["payload"]["collection"]
    result = addon().decide_current_collection_copy(
        collection["collectionUuid"],
        decision,
    )
    after = collection_snapshot()
    write_evidence(
        output_name,
        {
            "before": before,
            "decision": decision.value,
            "result": {
                "collectionUuid": result.collection_uuid,
                "identityState": result.state.value,
            },
            "after": after,
        },
    )
    finish_process()


class FailingCollectionConfiguration:
    def get_config(self, key: str, default: object | None = None) -> object:
        return mw.col.get_config(key, default)

    def set_config(
        self,
        key: str,
        value: object,
        *,
        undoable: bool = False,
    ) -> object:
        raise OSError("injected real-Anki collection config failure")


def fault_injection() -> None:
    mw.col.remove_config(COLLECTION_UUID_CONFIG_KEY)
    assignment_registry = EVIDENCE_DIR / "fault-assignment-registry.json"
    assignment = CollectionIdentityService(
        assignment_registry
    ).observe_open_collection(
        FailingCollectionConfiguration(),
        Path(mw.pm.collectionPath()),
    )
    assignment_config = mw.col.get_config(COLLECTION_UUID_CONFIG_KEY)

    registry_path = EVIDENCE_DIR / "fault-registry.json"

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("injected real-Anki local registry failure")

    registry = CollectionIdentityService(
        registry_path,
        replace_file=fail_replace,
    ).observe_open_collection(
        mw.col,
        Path(mw.pm.collectionPath()),
    )
    registry_config = mw.col.get_config(COLLECTION_UUID_CONFIG_KEY)

    write_evidence(
        "fault-injection.json",
        {
            "assignment": {
                "identityState": assignment.state.value,
                "errorCategory": assignment.error_category,
                "collectionConfig": assignment_config,
                "registryExists": assignment_registry.exists(),
            },
            "registry": {
                "identityState": registry.state.value,
                "errorCategory": registry.error_category,
                "collectionConfig": registry_config,
                "registryExists": registry_path.exists(),
            },
            "ankigtaSessionAbsent": "ANKIGTA Session"
            not in {
                item.name
                for item in mw.col.decks.all_names_and_ids(skip_empty_default=False)
            },
        },
    )
    finish_process()


def run_phase() -> None:
    if PHASE == "initialize-a":
        initialize_bound_collection("initialize-a.json")
    elif PHASE == "restart-a":
        restart_a()
    elif PHASE == "collision-b-rename":
        collision_b_then_rename()
    elif PHASE == "present-copy":
        present_copy()
    elif PHASE == "initialize-restore-source":
        initialize_bound_collection("initialize-restore-source.json")
    elif PHASE == "restore-previous":
        restore_decision(
            CollectionCopyDecision.PREVIOUS_COLLECTION,
            "restore-previous.json",
        )
    elif PHASE == "restore-new":
        restore_decision(CollectionCopyDecision.NEW_COPY, "restore-new.json")
    elif PHASE == "fault-injection":
        fault_injection()
    else:
        raise RuntimeError(f"unknown ticket 04 phase: {PHASE}")


def fail() -> None:
    write_evidence(
        f"failure-{PHASE}.json",
        {
            "phase": PHASE,
            "stage": stage,
            "traceback": traceback.format_exc(),
        },
    )
    finish_process()


def guarded(action: Callable[[], None]) -> None:
    try:
        action()
    except Exception:
        fail()


def on_profile_did_open() -> None:
    QTimer.singleShot(0, lambda: guarded(run_phase))


gui_hooks.profile_did_open.append(on_profile_did_open)

if mw.col is not None:
    on_profile_did_open()
