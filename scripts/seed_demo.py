"""Upload wildfire_demo_01 and write the sites table (run with LANTERN_MODE=aws).  OWNER: M1."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lantern_core.config import settings  # noqa: E402
from simulator.run import reset  # noqa: E402

reset("wildfire_demo_01")
print(f"seeded wildfire_demo_01 ({settings.lantern_mode} mode)")
