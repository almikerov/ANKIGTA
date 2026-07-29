from __future__ import annotations

import sys
from pathlib import Path


COMPANION_ROOT = Path(__file__).resolve().parents[1] / "companion"
sys.path.insert(0, str(COMPANION_ROOT))
