"""Write a generated scenario into the store (raw/ + truth/). OWNER: M2.
DRAFT by M3 for M2 review.

    python -m simulator.generator train_wildfire_0001      # or: make sim SCENARIO=...
"""

from __future__ import annotations

import json
import sys

from lantern_core import store
from lantern_core.config import settings
from lantern_core.ids import iso, report_key, sim_time
from simulator.world import World


def write_scenario(scenario_id: str, hours: int = 72) -> World:
    """Run the world with no transfers and write every file. Returns the finished world."""
    w = World(scenario_id, hours=hours)
    base = f"raw/scenarios/{scenario_id}"
    created = iso(sim_time(settings.sim_start_ts, 0))
    store.put_json(f"{base}/sites.json", w.site_rows(created))
    store.put_json(f"{base}/events.json", w.events())
    weather, truth = [], []
    for h in range(hours):
        weather.append(w.weather())
        store.put_object(report_key(scenario_id, h), "".join(json.dumps(r) + "\n" for r in w.reports()))
        truth.extend(w.advance())
    store.put_object(f"{base}/weather.jsonl", "".join(json.dumps(r) + "\n" for r in weather))
    store.put_object(f"truth/scenarios/{scenario_id}/stock.jsonl", "".join(json.dumps(r) + "\n" for r in truth))
    return w


if __name__ == "__main__":
    sid = sys.argv[1] if len(sys.argv) > 1 else "train_wildfire_0000"
    w = write_scenario(sid)
    print(f"{sid}: hazard {w.spec.hazard} from h{w.hazard_start} to h{w.hazard_end}, "
          f"dark {sorted(w.dark)}, shortage-hours {w.shortage_hours}")
