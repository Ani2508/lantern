"""PRACTICE DATA ONLY: a small features.csv so M3 can build and test the
forecaster before M2's real training set exists. OWNER: M3.

Not used for any reported result. Columns and meaning match contract 2.9 and
the Dataset doc (v1.2: stock_qty is the ESTIMATED stock, target from truth).

    python -m models.make_dev_features            # -> clean/training/features.csv in the store
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from lantern_core import store
from lantern_core.config import settings
from lantern_core.schemas import SUPPLIES

COLUMNS = [
    "scenario_id", "hazard", "sim_hour", "site_id", "site_type", "supply_id", "people_served",
    "temp_c", "hazard_level", "stock_qty", "burn_rate_per_h", "report_age_h", "target_tts_h",
]
SITE_TYPES = ["shelter", "shelter", "clinic", "pharmacy", "food_bank"]
HAZARD_MULT = {"wildfire": 1.25, "flood": 1.15, "power_loss": 1.05}


def make(n_scenarios: int = 120, seed: int = 0, prefix: str = "train") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    hazards = list(HAZARD_MULT)
    for i in range(n_scenarios):
        hazard = hazards[i % 3]
        sid = f"{prefix}_{hazard}_{i:04d}"
        for s, stype in enumerate(SITE_TYPES):
            people = int(rng.integers(60, 600))
            for sup, spec in SUPPLIES.items():
                burn = people * spec.usage_per_person_per_day / 24
                for hour in range(0, 72, 6):
                    level = int(min(3, max(0, rng.normal(1.5, 1))))
                    true_mult = HAZARD_MULT[hazard] * (1 + 0.15 * level) * rng.lognormal(0, 0.15)
                    stock_true = burn * rng.uniform(0, 100)
                    age = float(rng.choice([0, 0, 0, 1, 2, 4, 7, 12]))
                    # what the engine would see: an aged, noisy estimate (no truth leak)
                    stock_est = max(0.0, stock_true * rng.lognormal(0, 0.05 + 0.03 * age))
                    tts = min(72.0, stock_true / (burn * true_mult)) if burn > 0 else 72.0
                    rows.append({
                        "scenario_id": sid, "hazard": hazard, "sim_hour": hour, "site_id": f"S{s + 1:02d}",
                        "site_type": stype, "supply_id": sup, "people_served": people,
                        "temp_c": round(rng.normal(28, 5), 1), "hazard_level": level,
                        "stock_qty": round(stock_est, 2), "burn_rate_per_h": round(burn, 4),
                        "report_age_h": age, "target_tts_h": round(tts, 2),
                    })
    return pd.DataFrame(rows, columns=COLUMNS)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", type=int, default=120)
    args = ap.parse_args()
    train = make(args.scenarios, seed=0, prefix="train")
    test = make(max(12, args.scenarios // 4), seed=1, prefix="test")
    df = pd.concat([train, test], ignore_index=True)
    store.put_object("clean/training/features.csv", df.to_csv(index=False))
    print(f"practice features: {len(df):,} rows -> clean/training/features.csv "
          f"({settings.lantern_mode} mode)")


if __name__ == "__main__":
    main()
