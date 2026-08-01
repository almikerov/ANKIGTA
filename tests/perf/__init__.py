"""Ticket 30 — the repeatable release benchmark.

`dataset` builds the reference world, `environment` records the machine it was
measured on, `thresholds` states what the ticket promises, and `report` turns
measurements into a verdict that can block a release. Nothing here drives a
GUI: every number comes from calling the real modules and timing them.
"""

from .dataset import ReferenceDataset, fill_store, reference_dataset
from .environment import MachineFacts, describe_machine
from .report import (
    Measurement,
    PerformanceReport,
    Threshold,
    THRESHOLDS,
    percentile,
)

__all__ = [
    "MachineFacts",
    "Measurement",
    "PerformanceReport",
    "ReferenceDataset",
    "Threshold",
    "THRESHOLDS",
    "describe_machine",
    "fill_store",
    "percentile",
    "reference_dataset",
]
