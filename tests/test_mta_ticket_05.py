from __future__ import annotations

from functools import lru_cache

import pytest

from integration.mta_ticket_05.runner import (
    configured_mta_server_root,
    run_acceptance_suite,
)


@lru_cache(maxsize=1)
def acceptance_evidence() -> dict[str, object]:
    try:
        server_root = configured_mta_server_root()
    except RuntimeError as error:
        pytest.skip(str(error))
    return run_acceptance_suite(server_root)


def test_real_mta_acl_allows_only_the_study_player() -> None:
    evidence = acceptance_evidence()
    fresh = evidence["fresh"]["mta"]

    assert fresh["admin"]["denial"] is False
    assert fresh["admin"]["payload"]["visible"] is True
    assert fresh["ordinary"] == {
        "payload": False,
        "denial": {"category": "forbidden"},
    }
    assert fresh["guest"] == {
        "payload": False,
        "denial": {"category": "authentication_required"},
    }


def test_sqlite_create_restart_and_minimal_migration_are_durable() -> None:
    evidence = acceptance_evidence()
    fresh = evidence["fresh"]
    migrated = evidence["migration"]
    failed = evidence["migration_failure"]

    assert fresh["database"]["version"] == 2
    assert fresh["mta"]["afterResourceRestart"]["payload"]["entities"] == (
        fresh["mta"]["admin"]["payload"]["entities"]
    )

    assert migrated["database"]["version"] == 2
    assert migrated["database"]["entity"] == {
        "map_id": "ticket05-map",
        "entity_id": "ticket05-entity",
        "entity_type": "object",
        "model": 1337,
        "authored_x": 10.5,
        "authored_y": -20.25,
        "authored_z": 4.75,
        "authored_heading": 135.0,
        "interior": 3,
        "dimension": 17,
    }
    assert migrated["backup"]["version"] == 1
    assert migrated["backup"]["entity"] == migrated["database"]["entity"]

    assert failed["database"]["version"] == 1
    assert failed["database"]["entity"] == migrated["database"]["entity"]
    assert failed["mta"]["storeStatus"]["ready"] is False
    assert failed["mta"]["admin"]["payload"] is False


def test_f7_contract_keeps_map_entity_when_runtime_instance_is_absent() -> None:
    evidence = acceptance_evidence()
    fresh = evidence["fresh"]["mta"]
    available = fresh["admin"]["payload"]["entities"][0]
    unavailable = fresh["withoutRuntimeInstance"]["payload"]["entities"][0]

    assert fresh["clientLuaSyntax"] is True, {
        "error": fresh.get("clientLuaSyntaxError"),
        "detail": fresh.get("clientLuaSyntaxDetail"),
    }
    assert fresh["runtimeInitiallyPresent"] is True
    assert available["mapEntity"] == unavailable["mapEntity"]
    assert available["runtimeInstance"]["available"] is True
    assert unavailable["runtimeInstance"] == {
        "available": False,
        "streamed": False,
    }
    assert fresh["withoutRuntimeInstance"]["payload"]["visible"] is True
