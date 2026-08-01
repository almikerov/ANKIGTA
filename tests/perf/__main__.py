"""Run the release benchmark and say whether the release may proceed.

    python -m tests.perf --report build/ankigta-performance.json

The same measurements the acceptance test holds against their thresholds, in
the form a release step can call: it prints the report, writes it as JSON where
it was told to, and exits non-zero when the report blocks the release — which
includes a threshold that was never measured, not only one that was missed.

The exit code is the gate. The JSON is the evidence, and is what a hand-timed
number from the manual checklist gets read next to.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .benchmark import run_benchmark


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tests.perf")
    parser.add_argument(
        "--report",
        type=Path,
        help="where to write the JSON report; printed to stdout either way",
    )
    parser.add_argument(
        "--mta-server-root",
        help=(
            "path to the MTA Server package this run had available, recorded "
            "with the machine so a report says what it could reach"
        ),
    )
    arguments = parser.parse_args(argv)

    report = run_benchmark(mta_server_root=arguments.mta_server_root)
    print(report.as_text())
    if arguments.report is not None:
        arguments.report.parent.mkdir(parents=True, exist_ok=True)
        arguments.report.write_text(report.as_json(), encoding="utf-8")
        print(f"\nreport written to {arguments.report}")
    for reason in report.blocking_reasons():
        print(f"blocking: {reason}", file=sys.stderr)
    return 1 if report.blocks_release else 0


if __name__ == "__main__":
    raise SystemExit(main())
