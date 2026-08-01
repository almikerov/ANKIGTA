"""Ticket 31 — the release record has to agree with the evidence beside it.

`docs/release/v1-certification.md` is prose, and prose drifts. The numbers it
rests on live in `docs/release/v1-performance-report.json`, written by
`python -m tests.perf --report …` on the certifying machine, and these tests
hold the record to that file rather than to a remembered figure.

The record deliberately does not restate the numbers. What it does state is the
*verdict* — that the report is clear, that every threshold was measured, and
what the machine could not confirm — and each of those is checked here.

Every checklist the record lists is also checked to exist and to still say
`not run`, because a checklist quietly marked otherwise is exactly the failure
the spec's Release rule is about.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.perf.report import THRESHOLDS
from tools import package


REPO_ROOT = Path(__file__).resolve().parents[1]
RELEASE = REPO_ROOT / "docs" / "release"
RECORD = RELEASE / "v1-certification.md"
REPORT = RELEASE / "v1-performance-report.json"
SUPPORTED = RELEASE / "supported-versions.md"
CHECKLISTS = REPO_ROOT / "docs" / "checklists"


@pytest.fixture(scope="module")
def report() -> dict[str, object]:
    return dict(json.loads(REPORT.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def record() -> str:
    return RECORD.read_text(encoding="utf-8")


# --- the evidence ------------------------------------------------------------


def test_the_shipped_report_is_a_performance_report_that_did_not_block(
    report: dict[str, object],
) -> None:
    assert report["report"] == "ankigta-performance"
    assert report["blocksRelease"] is False
    assert report["blockingReasons"] == []


def test_the_shipped_report_measured_every_threshold(
    report: dict[str, object],
) -> None:
    """A report missing an entry reads as clear, which is when a gate must not
    open."""
    measurements = list(report["measurements"])  # type: ignore[arg-type]
    keys = {entry["key"] for entry in measurements}

    assert keys == {threshold.key for threshold in THRESHOLDS}
    assert all(entry["status"] == "passed" for entry in measurements)
    assert all(entry["sampleCount"] > 0 for entry in measurements)


def test_the_shipped_report_was_taken_over_the_reference_volume(
    report: dict[str, object],
) -> None:
    dataset = dict(report["dataset"])  # type: ignore[arg-type]

    assert dataset["mapEntities"] >= 10_000
    assert dataset["spatialLinks"] >= 5_000
    assert dataset["ankiCards"] >= 100_000


def test_the_shipped_report_names_what_the_run_could_not_confirm(
    report: dict[str, object],
) -> None:
    """The field the record's honesty rests on."""
    machine = dict(report["machine"])  # type: ignore[arg-type]
    unconfirmed = list(machine["unconfirmed"])  # type: ignore[arg-type]

    assert unconfirmed, "a run that confirmed everything would be a run that lied"
    assert "storage_is_ssd" in unconfirmed
    assert "anki_desktop_installed" in unconfirmed


def test_the_record_says_the_machine_did_not_match_when_it_did_not(
    report: dict[str, object],
    record: str,
) -> None:
    """The one claim in the record that could quietly become false."""
    machine = dict(report["machine"])  # type: ignore[arg-type]

    if machine["matchesReferenceEnvelope"] is True:
        return
    assert "matchesReferenceEnvelope" in record
    assert "not the documented reference machine" in record
    for fact in machine["unconfirmed"]:  # type: ignore[attr-defined]
        assert str(fact) in record, f"{fact} is unconfirmed but unmentioned"


# --- the version -------------------------------------------------------------


def test_the_record_and_the_artifacts_name_the_same_version() -> None:
    version = package.resource_version()

    assert version in RECORD.read_text(encoding="utf-8")
    assert version in SUPPORTED.read_text(encoding="utf-8")


# --- the checklists ----------------------------------------------------------


def _linked_checklists(record: str) -> list[Path]:
    return [
        (RELEASE / target).resolve()
        for target in re.findall(r"\]\((\.\./checklists/[^)]+)\)", record)
    ]


def test_every_checklist_the_record_links_to_exists(record: str) -> None:
    linked = _linked_checklists(record)

    assert linked
    missing = [path for path in linked if not path.exists()]
    assert missing == []


def test_no_checklist_has_been_marked_as_run(record: str) -> None:
    """An unexecuted runtime checklist is neither a pass nor a failure.

    Marking one otherwise from an implementation pass is the thing the spec's
    Release rule forbids by name, so it is checked rather than trusted.
    """
    for path in sorted(CHECKLISTS.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        assert "Status: not run" in text, f"{path.name} no longer says not run"


def test_the_record_leaves_the_release_decision_to_the_manual_pass(
    record: str,
) -> None:
    assert "not certified for publication" in record
