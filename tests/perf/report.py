"""Thresholds, measurements and the verdict that blocks a release.

The one rule this module exists to enforce: a measurement that was never taken
is not a measurement that passed. A release gate whose evidence file is missing
half its entries has to say so at the top, in the same field a reader checks for
a pass, or it becomes a gate that opens whenever the harness is broken.

That is not hypothetical here. The reference volume for the launched-server
measurements comes from a disposable copy of an MTA server, and the package it
is copied from is not in the repository — `.scratch/` is ignored. On a machine
without one, those measurements cannot be taken at all, and the report must name
what it lacked rather than either crashing inside an assertion or quietly
reporting on the parts it could reach.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence


PASSED = "passed"
FAILED = "failed"
NOT_MEASURED = "not_measured"


@dataclass(frozen=True)
class Threshold:
    """One promise from the ticket, in the units it is promised in."""

    key: str
    statement: str
    limit: float
    unit: str
    #: Which acceptance-criteria line this threshold answers, so a failing
    #: number points at the checkbox it leaves open.
    criterion: str
    #: `p95` where the ticket says "for 95% of requests", `max` otherwise.
    aggregate: str = "max"


THRESHOLDS: tuple[Threshold, ...] = (
    Threshold(
        key="f7_available",
        statement="F7 snapshot is available",
        limit=2000.0,
        unit="ms",
        criterion="F7 available <=2 s; search/filter <=150 ms.",
    ),
    Threshold(
        key="search_filter",
        statement="Card Picker deck filter returns its first page",
        limit=150.0,
        unit="ms",
        criterion="F7 available <=2 s; search/filter <=150 ms.",
    ),
    Threshold(
        key="spatial_frame",
        statement="Activation Zone, Pick Entity and HUD, per frame",
        limit=2.0,
        unit="ms",
        criterion=(
            "Pick Entity, Activation Zone and HUD add <=2 ms average frame time."
        ),
        aggregate="mean",
    ),
    Threshold(
        key="card_picker_first_page",
        statement="Card Picker first page",
        limit=1000.0,
        unit="ms",
        criterion=(
            "Card Picker first page, card open and rating confirmation <=1 s "
            "for 95% local requests."
        ),
        aggregate="p95",
    ),
    Threshold(
        key="card_open",
        statement="Card open",
        limit=1000.0,
        unit="ms",
        criterion=(
            "Card Picker first page, card open and rating confirmation <=1 s "
            "for 95% local requests."
        ),
        aggregate="p95",
    ),
    Threshold(
        key="rating_confirmation",
        statement="Rating confirmation",
        limit=1000.0,
        unit="ms",
        criterion=(
            "Card Picker first page, card open and rating confirmation <=1 s "
            "for 95% local requests."
        ),
        aggregate="p95",
    ),
    Threshold(
        key="session_rebuild",
        statement="Full 5,000-link session rebuild",
        limit=5000.0,
        unit="ms",
        criterion=(
            "Full 5,000-link session rebuild <=5 s while UI remains "
            "responsive/progress visible."
        ),
    ),
)

THRESHOLDS_BY_KEY = {threshold.key: threshold for threshold in THRESHOLDS}


def percentile(samples: Sequence[float], fraction: float) -> float:
    """The nearest-rank percentile.

    Nearest-rank rather than interpolated: with the sample counts a local
    benchmark takes, interpolation invents a value between two real ones, and
    "95% of requests were under this" is a claim about real requests.
    """
    if not samples:
        raise ValueError("percentile of no samples")
    ordered = sorted(samples)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def aggregate(samples: Sequence[float], how: str) -> float:
    if how == "max":
        return max(samples)
    if how == "mean":
        return sum(samples) / len(samples)
    if how == "p95":
        return percentile(samples, 0.95)
    raise ValueError(f"unknown aggregate: {how}")


@dataclass(frozen=True)
class Measurement:
    """What one threshold was measured as, or why it was not measured."""

    key: str
    samples: tuple[float, ...] = ()
    #: Set when the measurement could not be taken. A reason is mandatory: the
    #: point of the state is that it names what was missing.
    unavailable_reason: str | None = None
    #: Free-form facts about the run — sizes, counts, what was warmed.
    context: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.key not in THRESHOLDS_BY_KEY:
            raise ValueError(f"no threshold named {self.key}")
        if self.unavailable_reason is None and not self.samples:
            raise ValueError(
                f"{self.key}: a measurement with no samples must say why"
            )
        if self.unavailable_reason is not None and self.samples:
            raise ValueError(
                f"{self.key}: an unavailable measurement cannot carry samples"
            )

    @property
    def threshold(self) -> Threshold:
        return THRESHOLDS_BY_KEY[self.key]

    @property
    def value(self) -> float | None:
        if not self.samples:
            return None
        return aggregate(self.samples, self.threshold.aggregate)

    @property
    def spread(self) -> dict[str, float] | None:
        """The lowest, middle and highest sample.

        Reported next to the aggregate because these numbers move with whatever
        else the machine is doing: a threshold whose maximum is close to its
        limit can pass on a quiet run and fail on a busy one, and a report
        showing one number would hide that the answer was marginal.
        """
        if not self.samples:
            return None
        ordered = sorted(self.samples)
        return {
            "min": ordered[0],
            "median": ordered[len(ordered) // 2],
            "max": ordered[-1],
        }

    @property
    def status(self) -> str:
        if self.unavailable_reason is not None:
            return NOT_MEASURED
        value = self.value
        assert value is not None
        return PASSED if value <= self.threshold.limit else FAILED

    def payload(self) -> dict[str, object]:
        threshold = self.threshold
        return {
            "key": self.key,
            "statement": threshold.statement,
            "criterion": threshold.criterion,
            "status": self.status,
            "aggregate": threshold.aggregate,
            "value": self.value,
            "limit": threshold.limit,
            "unit": threshold.unit,
            "sampleCount": len(self.samples),
            "spread": self.spread,
            "samples": [round(sample, 3) for sample in self.samples],
            "unavailableReason": self.unavailable_reason,
            "context": dict(self.context),
        }


@dataclass(frozen=True)
class PerformanceReport:
    """Every threshold's outcome, and whether the release may proceed."""

    measurements: tuple[Measurement, ...]
    machine: object
    dataset: dict[str, object]
    #: Which run this is — a cold start, a warm repeat, a restart.
    runs: tuple[str, ...] = ()

    @property
    def missing_keys(self) -> tuple[str, ...]:
        measured = {measurement.key for measurement in self.measurements}
        return tuple(
            threshold.key
            for threshold in THRESHOLDS
            if threshold.key not in measured
        )

    @property
    def not_measured(self) -> tuple[Measurement, ...]:
        return tuple(
            measurement
            for measurement in self.measurements
            if measurement.status == NOT_MEASURED
        )

    @property
    def failed(self) -> tuple[Measurement, ...]:
        return tuple(
            measurement
            for measurement in self.measurements
            if measurement.status == FAILED
        )

    @property
    def blocks_release(self) -> bool:
        """A release is blocked by a failure *and* by an absence.

        Not measured is not passed. A gate that treats a missing number as
        satisfied opens exactly when the harness is broken, which is the moment
        it is least entitled to.
        """
        return bool(self.failed or self.not_measured or self.missing_keys)

    def blocking_reasons(self) -> tuple[str, ...]:
        reasons = [
            f"{measurement.key}: {measurement.value:.1f} {measurement.threshold.unit}"
            f" over the {measurement.threshold.limit:.0f}"
            f" {measurement.threshold.unit} limit"
            for measurement in self.failed
            if measurement.value is not None
        ]
        reasons.extend(
            f"{measurement.key}: not measured ({measurement.unavailable_reason})"
            for measurement in self.not_measured
        )
        reasons.extend(f"{key}: absent from the report" for key in self.missing_keys)
        return tuple(reasons)

    def payload(self) -> dict[str, object]:
        machine = self.machine
        return {
            "report": "ankigta-performance",
            "reportVersion": 1,
            "ticket": 30,
            "blocksRelease": self.blocks_release,
            "blockingReasons": list(self.blocking_reasons()),
            "runs": list(self.runs),
            "dataset": dict(self.dataset),
            "machine": machine.payload() if hasattr(machine, "payload") else machine,
            "measurements": [
                measurement.payload() for measurement in self.measurements
            ],
        }

    def as_json(self) -> str:
        return json.dumps(self.payload(), indent=2, ensure_ascii=False)

    def as_text(self) -> str:
        """The report a human reads, one line per threshold."""
        lines = [
            f"ANKIGTA performance report — "
            f"{'BLOCKS RELEASE' if self.blocks_release else 'clear'}"
        ]
        for measurement in self.measurements:
            threshold = measurement.threshold
            if measurement.status == NOT_MEASURED:
                lines.append(
                    f"  {measurement.status:<12} {measurement.key:<24}"
                    f" — {measurement.unavailable_reason}"
                )
                continue
            value = measurement.value
            spread = measurement.spread
            assert value is not None and spread is not None
            lines.append(
                f"  {measurement.status:<12} {measurement.key:<24}"
                f" {threshold.aggregate}={value:8.1f} {threshold.unit}"
                f" limit={threshold.limit:.0f} {threshold.unit}"
                f" n={len(measurement.samples)}"
                f" [min {spread['min']:.1f}"
                f" median {spread['median']:.1f}"
                f" max {spread['max']:.1f}]"
            )
        for key in self.missing_keys:
            lines.append(f"  {NOT_MEASURED:<12} {key:<24} — absent from the report")
        return "\n".join(lines)


def build_report(
    measurements: Iterable[Measurement],
    *,
    machine: object,
    dataset: dict[str, object],
    runs: Iterable[str] = (),
) -> PerformanceReport:
    return PerformanceReport(
        measurements=tuple(measurements),
        machine=machine,
        dataset=dict(dataset),
        runs=tuple(runs),
    )
