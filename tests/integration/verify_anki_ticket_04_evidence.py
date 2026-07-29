from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from uuid import UUID


def load(evidence: Path, name: str) -> dict[str, Any]:
    return json.loads((evidence / name).read_text(encoding="utf-8"))


def collection(snapshot: dict[str, Any]) -> dict[str, Any]:
    return snapshot["health"]["body"]["payload"]["collection"]


def valid_uuid(value: object) -> str:
    assert isinstance(value, str)
    return str(UUID(value))


def main() -> None:
    evidence = Path(sys.argv[1])
    initial = load(evidence, "initialize-a.json")
    restart = load(evidence, "restart-a.json")
    exported = load(evidence, "export-package.json")
    imported = load(evidence, "import-collision.json")
    collision = load(evidence, "collision-b-rename.json")
    present_copy = load(evidence, "present-copy.json")
    restore_source = load(evidence, "initialize-restore-source.json")
    restore_previous = load(evidence, "restore-previous.json")
    restore_new = load(evidence, "restore-new.json")
    faults = load(evidence, "fault-injection.json")

    a_uuid = valid_uuid(collection(initial["after"])["collectionUuid"])
    assert initial["bindResult"] == {
        "collectionUuid": a_uuid,
        "identityState": "bound",
    }
    assert collection(initial["before"])["identityState"] == "unbound"
    assert collection(initial["after"])["identityState"] == "bound"
    assert initial["after"]["collectionSettingsAction"] == (
        "ANKIGTA: Bound Anki Collection…"
    )
    assert valid_uuid(collection(restart)["collectionUuid"]) == a_uuid
    assert collection(restart)["identityState"] == "bound"
    assert restart["collectionUuidInConfig"] == a_uuid
    assert initial["after"]["cardIds"] == restart["cardIds"]
    assert exported["packageExists"] is True
    assert exported["packageBytes"] > 0
    assert imported["usedAnkiImportOperation"] is True
    import_before_uuid = valid_uuid(
        collection(imported["beforeImport"])["collectionUuid"]
    )
    import_after_uuid = valid_uuid(
        collection(imported["afterImport"])["collectionUuid"]
    )
    assert import_before_uuid != a_uuid
    assert import_after_uuid not in {a_uuid, import_before_uuid}
    assert collection(imported["afterImport"])["identityState"] == (
        "wrong_collection"
    )
    assert imported["afterImport"]["cardIds"] == initial["after"]["cardIds"]

    before_rename = collision["beforeRename"]
    b_uuid = valid_uuid(collection(before_rename)["collectionUuid"])
    assert b_uuid != a_uuid
    assert collection(before_rename)["identityState"] == "wrong_collection"
    assert before_rename["cardIds"] == initial["after"]["cardIds"]
    pending = collision["afterRenamePending"]
    assert valid_uuid(collection(pending)["collectionUuid"]) == b_uuid
    assert collection(pending)["identityState"] == "wrong_collection"
    assert collision["decisionResult"] is None
    assert collection(collision["afterDecision"])["collectionUuid"] == b_uuid
    assert collision["afterDecision"]["profileName"] == "ANKIGTA_T04_B_RENAMED"

    present_uuid = valid_uuid(collection(present_copy)["collectionUuid"])
    assert present_uuid != a_uuid
    assert collection(present_copy)["identityState"] == "wrong_collection"

    restore_uuid = valid_uuid(collection(restore_source["after"])["collectionUuid"])
    assert collection(restore_previous["before"])["identityState"] == (
        "copy_decision_required"
    )
    assert restore_previous["result"] == {
        "collectionUuid": restore_uuid,
        "identityState": "bound",
    }
    assert collection(restore_previous["after"])["collectionUuid"] == restore_uuid
    assert collection(restore_previous["after"])["identityState"] == "bound"

    assert collection(restore_new["before"])["identityState"] == (
        "copy_decision_required"
    )
    new_copy_uuid = valid_uuid(restore_new["result"]["collectionUuid"])
    assert new_copy_uuid != restore_uuid
    assert restore_new["decision"] == "new_copy"
    assert restore_new["result"]["identityState"] == "wrong_collection"
    assert collection(restore_new["after"])["collectionUuid"] == new_copy_uuid

    assert faults["assignment"] == {
        "identityState": "identity_error",
        "errorCategory": "collection_identity_persistence_failed",
        "collectionConfig": None,
        "registryExists": False,
    }
    assert faults["registry"]["identityState"] == "identity_error"
    assert faults["registry"]["errorCategory"] == (
        "collection_identity_persistence_failed"
    )
    valid_uuid(faults["registry"]["collectionConfig"])
    assert faults["registry"]["registryExists"] is False
    assert faults["ankigtaSessionAbsent"] is True

    for name in (
        "initial",
        "restart",
        "before_rename",
        "pending",
        "present_copy",
    ):
        snapshot = locals()[name]
        if name == "initial":
            snapshot = snapshot["after"]
        assert snapshot["ankigtaSessionAbsent"] is True

    print("Anki 26.05 ticket 04 identity evidence passed")


if __name__ == "__main__":
    main()
