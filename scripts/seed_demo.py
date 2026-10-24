"""Upload the demo fixture and write the sites table (local store or AWS)."""

from __future__ import annotations

from lantern_core.config import DEMO_SCENARIO_ID, settings
from simulator import run as sim


def main() -> None:
    hour = sim.reset(DEMO_SCENARIO_ID)
    print(f"seeded {DEMO_SCENARIO_ID} at hour {hour} (mode={settings.LANTERN_MODE})")


if __name__ == "__main__":
    main()
