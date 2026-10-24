"""Quantile forecaster for time-to-shortage. OWNER: M3.

`predict(rows)` returns (p05, p50, p95) hours per feature row. If a trained
XGBoost model exists at settings.forecaster_model_key it is used; otherwise
the stock / burn fallback is returned so the pipeline always works.

Feature rows use the features.csv columns (contract 2.9) minus the target.
At prediction time stock_qty is the ESTIMATED stock (v1.2: no truth leak):
  tts_p05_h <- low quantile of the row with stock_qty = est_qty_p05
  tts_p50_h <- median        of the row with stock_qty = est_qty_p50
  tts_p95_h <- high quantile of the row with stock_qty = est_qty_p95
"""

from __future__ import annotations

import json
import tempfile
from functools import lru_cache
from pathlib import Path

from engine.estimator import tts_hours
from lantern_core import store
from lantern_core.config import settings
from lantern_core.schemas import InventoryState

CATEGORICAL = ["hazard", "site_type", "supply_id"]
NUMERIC = ["sim_hour", "people_served", "temp_c", "hazard_level", "stock_qty", "burn_rate_per_h", "report_age_h"]


def metrics_key() -> str:
    return settings.forecaster_model_key.rsplit("/", 1)[0] + "/metrics.json"


@lru_cache(maxsize=1)
def _load_model():
    """(booster, feature_columns, widen_h) or None when no model has been trained yet."""
    try:
        raw = store.get_object(settings.forecaster_model_key)
        meta = json.loads(store.get_object(metrics_key()))
    except KeyError:
        return None
    import xgboost as xgb

    path = Path(tempfile.gettempdir()) / "lantern_forecaster_model.json"
    path.write_bytes(raw)
    booster = xgb.Booster()
    booster.load_model(str(path))
    return booster, meta["feature_columns"], float(meta.get("conformal_widen_h", 0.0))


def reload_model() -> None:
    _load_model.cache_clear()


def encode(rows: list[dict], columns: list[str] | None = None):
    """One-hot encode feature rows. Returns (DataFrame, columns)."""
    import pandas as pd

    df = pd.DataFrame(rows)
    for c in NUMERIC:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    df = pd.get_dummies(df[CATEGORICAL + NUMERIC], columns=CATEGORICAL, dtype=float)
    if columns is not None:
        df = df.reindex(columns=columns, fill_value=0.0)
    return df, list(df.columns)


def predict(rows: list[dict]) -> list[tuple[float, float, float]]:
    if not rows:
        return []
    model = _load_model()
    if model is None:
        out = []
        for r in rows:
            t = tts_hours(float(r["stock_qty"]), float(r["burn_rate_per_h"]))
            out.append((t, t, t))
        return out
    import numpy as np
    import xgboost as xgb

    booster, columns, widen = model
    X, _ = encode(rows, columns)
    pred = booster.predict(xgb.DMatrix(X.values, feature_names=columns))
    pred = np.sort(pred, axis=1)  # quantiles never cross
    pred[:, 0] -= widen  # conformal calibration from training
    pred[:, 2] += widen
    pred = np.clip(pred, 0, settings.plan_horizon_h)
    return [(float(a), float(b), float(c)) for a, b, c in pred]


def feature_row(row: InventoryState, site_type: str, hazard: str, weather: dict, stock_qty: float) -> dict:
    return {
        "hazard": hazard, "site_type": site_type, "supply_id": row.supply_id,
        "sim_hour": row.sim_hour, "people_served": row.people_served,
        "temp_c": weather.get("temp_c", 20.0), "hazard_level": weather.get("hazard_level", 0),
        "stock_qty": stock_qty, "burn_rate_per_h": row.burn_rate_per_h or 0.0,
        "report_age_h": row.report_age_h,
    }


def apply_forecast(
    inventory: list[InventoryState], site_types: dict[str, str], hazard: str, weather: dict
) -> list[InventoryState]:
    """Fill tts_p05_h / tts_p50_h / tts_p95_h on estimated rows."""
    if _load_model() is None:
        return inventory  # estimator's stock / burn values already filled
    feats = []
    for r in inventory:
        st = site_types.get(r.site_id, "shelter")
        for q in (r.est_qty_p05, r.est_qty_p50, r.est_qty_p95):
            feats.append(feature_row(r, st, hazard, weather, q or 0.0))
    preds = predict(feats)
    out = []
    for i, r in enumerate(inventory):
        lo, mid, hi = preds[3 * i][0], preds[3 * i + 1][1], preds[3 * i + 2][2]
        lo, mid, hi = sorted((lo, mid, hi))
        out.append(r.model_copy(update={"tts_p05_h": lo, "tts_p50_h": mid, "tts_p95_h": hi}))
    return out
