from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    evidence = Path(sys.argv[1])
    setup = load(evidence / "setup.json")
    verification = load(evidence / "verification.json")

    assert setup["ankiVersion"] == "26.05"
    assert setup["snapshot"]["fsrsEnabled"] is True
    assert setup["snapshot"]["v3Scheduler"] is True
    assert verification["ankiVersion"] == "26.05"
    assert verification["beforeSnapshot"] == verification["afterSnapshot"]
    assert verification["open"]["status"] == 200
    assert verification["open"]["body"]["ok"] is True
    assert verification["open"]["body"]["payload"]["compatibility"]["status"] == (
        "supported"
    )
    assert verification["closing"]["status"] == 503
    assert (
        verification["closing"]["body"]["payload"]["collection"]["state"]
        == "closing"
    )
    assert verification["afterUnload"]["status"] == 503
    assert verification["reopened"]["status"] == 200
    assert verification["listenerReleased"] is True
    assert verification["ankigtaSessionAbsent"] is True
    print("Anki 26.05 integration evidence passed")


if __name__ == "__main__":
    main()
