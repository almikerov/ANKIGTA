"""Ticket 30 — the release benchmark and the gate it feeds.

Two kinds of test live here. The first kind is about the gate itself and is
fast: that a measurement which was never taken cannot look like one that
passed, that a report names what it lacked, and that the generated world is the
one the ticket describes and comes out the same twice. The second kind runs the
real benchmark and holds each number against the threshold it belongs to.

No threshold is currently marked as an expected failure. Four were, and the
rule that got them from there to here is the one worth keeping: the threshold
is the ticket's and is never moved to fit the result, so a number over its
limit is a defect to find rather than a limit to loosen. `KNOWN_OVER_LIMIT`
records what each of them turned out to be.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import pytest

from tests.perf import dataset as dataset_module
from tests.perf.benchmark import run_benchmark
from tests.perf.environment import describe_machine
from tests.perf.report import (
    FAILED,
    NOT_MEASURED,
    PASSED,
    THRESHOLDS,
    Measurement,
    PerformanceReport,
    build_report,
    percentile,
)


# --- the gate ----------------------------------------------------------------


def sample_report(*measurements: Measurement) -> PerformanceReport:
    return build_report(
        measurements,
        machine=describe_machine(),
        dataset={"mapEntities": 0, "spatialLinks": 0, "ankiCards": 0},
    )


def test_a_measurement_with_no_samples_must_say_why() -> None:
    """The constructor is the guard.

    A `Measurement` that carries neither samples nor a reason would report as
    something, and whatever it reported as would be a lie about a number nobody
    took.
    """
    with pytest.raises(ValueError):
        Measurement(key="f7_available")


def test_a_measurement_that_was_not_taken_is_not_a_measurement_that_passed() -> None:
    report = sample_report(
        *(
            Measurement(
                key=threshold.key,
                unavailable_reason="no MTA Server package on this machine",
            )
            for threshold in THRESHOLDS
        )
    )

    assert report.blocks_release is True
    assert all(
        measurement.status == NOT_MEASURED for measurement in report.measurements
    )
    assert all(
        "no MTA Server package on this machine" in reason
        for reason in report.blocking_reasons()
    )


def test_a_threshold_absent_from_the_report_blocks_the_release() -> None:
    """The failure mode this exists for: a harness that stopped early.

    A report holding only the measurements that happened to be taken would read
    as clear, which is exactly when a gate must not open.
    """
    report = sample_report(
        Measurement(key="card_open", samples=(10.0,)),
    )

    assert report.blocks_release is True
    assert set(report.missing_keys) == {
        threshold.key for threshold in THRESHOLDS if threshold.key != "card_open"
    }
    assert any("absent from the report" in reason for reason in report.blocking_reasons())


def test_a_report_where_every_threshold_passes_does_not_block() -> None:
    report = sample_report(
        *(
            Measurement(key=threshold.key, samples=(threshold.limit / 2,))
            for threshold in THRESHOLDS
        )
    )

    assert report.blocks_release is False
    assert report.blocking_reasons() == ()


def test_one_number_over_its_limit_blocks_the_release() -> None:
    measurements = [
        Measurement(key=threshold.key, samples=(threshold.limit / 2,))
        for threshold in THRESHOLDS
    ]
    measurements[0] = Measurement(
        key=THRESHOLDS[0].key,
        samples=(THRESHOLDS[0].limit * 1.5,),
    )

    report = sample_report(*measurements)

    assert report.blocks_release is True
    assert [measurement.key for measurement in report.failed] == [THRESHOLDS[0].key]


def test_the_value_at_the_limit_passes_and_a_hair_over_it_does_not() -> None:
    """A boundary stated as `<=` is inclusive, and the gate has to agree."""
    threshold = THRESHOLDS[0]

    assert Measurement(key=threshold.key, samples=(threshold.limit,)).status == PASSED
    assert (
        Measurement(key=threshold.key, samples=(threshold.limit + 0.001,)).status
        == FAILED
    )


def test_the_percentile_is_a_value_that_was_actually_measured() -> None:
    """Nearest-rank, not interpolated.

    "95% of requests were under this" is a claim about real requests, so the
    number reported has to be one of them.
    """
    samples = [float(value) for value in range(1, 21)]

    result = percentile(samples, 0.95)

    assert result in samples
    assert result == 19.0
    assert sum(1 for sample in samples if sample <= result) >= 0.95 * len(samples)


def test_the_report_survives_being_written_and_read_back() -> None:
    report = sample_report(
        *(
            Measurement(key=threshold.key, samples=(threshold.limit / 2,))
            for threshold in THRESHOLDS
        )
    )

    restored = json.loads(report.as_json())

    assert restored["blocksRelease"] is False
    assert {entry["key"] for entry in restored["measurements"]} == {
        threshold.key for threshold in THRESHOLDS
    }
    # Every measurement says what it covers, because a number without that is a
    # number for a promise nobody made.
    assert all("status" in entry for entry in restored["measurements"])


def test_the_machine_names_what_it_could_not_confirm() -> None:
    """Ticket 30 asks for a documented environment. No harness can make a
    machine be that one, so it records which parts it could establish."""
    facts = describe_machine(mta_server_root=None)

    assert "mta_server_available" in facts.unconfirmed
    assert "storage_is_ssd" in facts.unconfirmed
    assert facts.logical_cores is None or facts.logical_cores >= 1
    payload = facts.payload()
    assert isinstance(payload["matchesReferenceEnvelope"], bool)


def test_a_configured_mta_server_is_no_longer_named_as_missing() -> None:
    facts = describe_machine(mta_server_root="/somewhere/mta/server")

    assert "mta_server_available" not in facts.unconfirmed


def test_the_release_gate_exits_non_zero_when_the_report_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exit code is what a release step reads.

    A gate that prints a failure and exits zero is a gate that opens. Driven
    with a stand-in report rather than a real run: what is under test is the
    entry point's verdict, and the numbers have their own tests.
    """
    from tests.perf import __main__ as entry_point

    blocked = sample_report(
        Measurement(key="f7_available", samples=(9_999.0,)),
        *(
            Measurement(key=threshold.key, samples=(threshold.limit / 2,))
            for threshold in THRESHOLDS
            if threshold.key != "f7_available"
        ),
    )
    written = tmp_path / "nested" / "report.json"
    monkeypatch.setattr(entry_point, "run_benchmark", lambda **_: blocked)

    assert entry_point.main(["--report", str(written)]) == 1
    assert json.loads(written.read_text(encoding="utf-8"))["blocksRelease"] is True


def test_the_release_gate_exits_zero_when_every_threshold_is_met(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.perf import __main__ as entry_point

    clear = sample_report(
        *(
            Measurement(key=threshold.key, samples=(threshold.limit / 2,))
            for threshold in THRESHOLDS
        )
    )
    monkeypatch.setattr(entry_point, "run_benchmark", lambda **_: clear)

    assert entry_point.main([]) == 0


# --- the generated world -----------------------------------------------------


def test_the_reference_world_is_the_volume_the_ticket_states() -> None:
    world = dataset_module.reference_dataset()

    assert world.map_entities >= 10_000
    assert world.spatial_links >= 5_000
    assert world.anki_cards >= 100_000


def test_one_card_linked_to_several_entities_is_counted_once() -> None:
    """The fixture has to contain the case, or a duplicate-counting bug in the
    session or the statistics would pass the benchmark unnoticed."""
    world = dataset_module.reference_dataset()

    assert len(world.linked_identities) < world.spatial_links
    assert len({identity.card_id for identity in world.linked_identities}) == len(
        world.linked_identities
    )


def test_the_generated_world_is_the_same_world_twice() -> None:
    """Reproducible means byte-comparable, not merely similar."""
    first = dataset_module.reference_dataset(
        map_entities=200, spatial_links=100, anki_cards=500
    )
    second = dataset_module.reference_dataset(
        map_entities=200, spatial_links=100, anki_cards=500
    )

    assert list(first.sql()) == list(second.sql())
    assert first.linked_identities == second.linked_identities
    assert [
        first.collection.get_card(identifier)
        for identifier in first.collection.find_cards("")
    ] == [
        second.collection.get_card(identifier)
        for identifier in second.collection.find_cards("")
    ]


def test_the_generated_cards_are_not_all_in_one_state() -> None:
    """A collection of a hundred thousand identical cards would take one branch
    through eligibility, which is not the collection the thresholds describe."""
    world = dataset_module.reference_dataset(
        map_entities=100, spatial_links=50, anki_cards=1_000
    )

    queues = {
        world.collection.get_card(identifier).queue  # type: ignore[union-attr]
        for identifier in world.collection.find_cards("")
    }

    assert len(queues) >= 3


def test_the_generated_collection_refuses_a_query_it_cannot_honestly_answer(
) -> None:
    """It stands in for Anki's search, and a stand-in that guesses would make
    the Card Picker measurement a measurement of the guess."""
    world = dataset_module.reference_dataset(
        map_entities=10, spatial_links=5, anki_cards=20
    )

    with pytest.raises(NotImplementedError):
        world.collection.find_cards("is:due prop:ivl>21")


# --- the run -----------------------------------------------------------------


@pytest.fixture(scope="module")
def benchmark_report(tmp_path_factory: pytest.TempPathFactory) -> PerformanceReport:
    report = run_benchmark()
    written = tmp_path_factory.mktemp("ankigta-performance") / "report.json"
    written.write_text(report.as_json(), encoding="utf-8")
    print("\n" + report.as_text())
    print(f"\nreport written to {written}")
    return report


def test_the_run_measures_every_threshold(
    benchmark_report: PerformanceReport,
) -> None:
    assert benchmark_report.missing_keys == ()
    assert benchmark_report.not_measured == (), benchmark_report.as_text()


def test_the_run_states_the_machine_and_the_world_it_measured(
    benchmark_report: PerformanceReport,
) -> None:
    payload = benchmark_report.payload()

    assert payload["dataset"]["mapEntities"] >= 10_000
    assert payload["dataset"]["spatialLinks"] >= 5_000
    assert payload["dataset"]["ankiCards"] >= 100_000
    assert "matchesReferenceEnvelope" in payload["machine"]


#: Thresholds known to be over their limit, as a reason carrying the numbers.
#:
#: Empty, and meant to stay that way. It was not: on 2026-08-01 four of the
#: seven were over, and each turned out to name a real defect rather than a
#: threshold that was too tight —
#:
#: - `f7_available` at 2405 ms: the snapshot asked the database whether each
#:   Map Entity was in an Identity Collision, one query per entity.
#: - `card_picker_first_page` at 1515 ms: a fifty-card page read and shaped
#:   every one of the hundred thousand cards the search matched.
#: - `spatial_frame` at 3.4 ms: the Activation Zone and the Next Card Indicator
#:   each walked every streamed candidate on every rendered frame.
#: - `search_filter` at 204 ms: measured against `Store.listMapEntities`, which
#:   is the F7 read rather than a filter — F7 has no filter to time, so the
#:   number was for a promise nobody had made.
#:
#: An entry added back here has to say what was measured and when, so a later
#: run that passes is a change worth noticing rather than a test going quietly
#: green.
KNOWN_OVER_LIMIT: dict[str, str] = {}


@pytest.mark.parametrize(
    "key",
    [
        pytest.param(
            threshold.key,
            marks=(
                [pytest.mark.xfail(reason=KNOWN_OVER_LIMIT[threshold.key])]
                if threshold.key in KNOWN_OVER_LIMIT
                else []
            ),
        )
        for threshold in THRESHOLDS
    ],
)
def test_the_threshold_is_met(
    benchmark_report: PerformanceReport,
    key: str,
) -> None:
    measurement = next(
        candidate
        for candidate in benchmark_report.measurements
        if candidate.key == key
    )
    threshold = measurement.threshold
    value = measurement.value

    assert measurement.status != NOT_MEASURED, measurement.unavailable_reason
    assert value is not None
    assert value <= threshold.limit, (
        f"{key}: {threshold.aggregate}={value:.1f} {threshold.unit}"
        f" over the {threshold.limit:.0f} {threshold.unit} limit"
        f" — {threshold.criterion}\n{measurement.context}"
    )


def test_every_measured_threshold_reports_its_spread(
    benchmark_report: PerformanceReport,
) -> None:
    """A single number hides whether the answer was marginal.

    Two of these thresholds land close enough to their limit that a busy
    machine moves them across it, so the report has to carry the range the
    verdict was drawn from.
    """
    for measurement in benchmark_report.measurements:
        spread = measurement.spread
        assert spread is not None, measurement.key
        assert spread["min"] <= spread["median"] <= spread["max"]
        assert measurement.value is not None
        assert spread["min"] <= measurement.value <= spread["max"]


def test_the_run_blocks_the_release_while_a_threshold_is_over_its_limit(
    benchmark_report: PerformanceReport,
) -> None:
    """The gate's own behaviour, on the real numbers.

    Whether it should be blocking today is the previous test's business. This
    one is that the report and the gate agree with each other: a failure that
    the report lists must be a failure that blocks.
    """
    over_limit = [measurement.key for measurement in benchmark_report.failed]

    assert benchmark_report.blocks_release == bool(
        over_limit or benchmark_report.not_measured or benchmark_report.missing_keys
    )
    for key in over_limit:
        assert any(key in reason for reason in benchmark_report.blocking_reasons())
