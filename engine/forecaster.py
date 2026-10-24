"""Time-to-shortage forecaster: XGBoost quantile model with a heuristic fallback.

The model artefact (FORECASTER_MODEL_KEY in the store) is a JSON wrapper:
{"format": "lantern-xgb-v1", "feature_columns": [...], "booster": <xgboost json>, "conformal": {"lo": x, "hi": y}}
"""

from __future__ import annotations

import json
import logging

from engine.estimator import heuristic_tts
from lantern_core import store
from lantern_core.config import SUPPLY_ORDER, settings
from lantern_core.schemas import HAZARDS, SITE_TYPES

log = logging.getLogger(__name__)

NUMERIC_COLUMNS = ["sim_hour", "people_served", "temp_c", "hazard_level", "stock_qty", "burn_rate_per_h", "report_age_h"]
FEATURE_COLUMNS = (
    NUMERIC_COLUMNS
    + [f"hazard_{h}" for h in HAZARDS]
    + [f"site_type_{t}" for t in SITE_TYPES]
    + [f"supply_id_{s}" for s in SUPPLY_ORDER]
    + ["stock_hours"]
)

_cache: dict[str, object] = {}
_warned: set[str] = set()


def feature_vector(row: dict) -> list[float]:
    burn = float(row.get("burn_rate_per_h") or 0.0)
    stock = float(row.get("stock_qty") or 0.0)
    v = [float(row.get(c) or 0.0) for c in NUMERIC_COLUMNS]
    v += [1.0 if row.get("hazard") == h else 0.0 for h in HAZARDS]
    v += [1.0 if row.get("site_type") == t else 0.0 for t in SITE_TYPES]
    v += [1.0 if row.get("supply_id") == s else 0.0 for s in SUPPLY_ORDER]
    v.append(min(settings.PLAN_HORIZON_H * 4.0, stock / burn) if burn > 0 else settings.PLAN_HORIZON_H * 4.0)
    return v


def _warn_once(msg: str) -> None:
    if msg not in _warned:
        _warned.add(msg)
        log.warning(msg)


def reset_cache() -> None:
    _cache.clear()


def load_model():
    """Return (booster, wrapper) or None. Loaded once per process and cached."""
    key = settings.FORECASTER_MODEL_KEY
    if key in _cache:
        return _cache[key]
    model = None
    try:
        raw = store.get_object(key)
        if raw is None:
            _warn_once(f"forecaster model {key} not found; using heuristic tts")
        else:
            import xgboost as xgb

            wrapper = json.loads(raw.decode("utf-8"))
            booster = xgb.Booster()
            booster.load_model(bytearray(json.dumps(wrapper["booster"]).encode("utf-8")))
            model = (booster, wrapper)
    except Exception as e:  # xgboost missing or bad artefact
        _warn_once(f"forecaster unavailable ({e}); using heuristic tts")
        model = None
    _cache[key] = model
    return model


def _heuristic(rows: list[dict]) -> list[tuple[float, float, float]]:
    h = settings.PLAN_HORIZON_H
    out = []
    for r in rows:
        burn = float(r["burn_rate_per_h"])
        out.append(tuple(heuristic_tts(float(r[k]), burn, h) for k in ("est_qty_p05", "est_qty_p50", "est_qty_p95")))
    return out


def predict(rows: list[dict]) -> list[tuple[float, float, float]]:
    """(tts_p05_h, tts_p50_h, tts_p95_h) per estimated row, sorted and capped at the horizon."""
    if not rows:
        return []
    if settings.FORECASTER_MODE == "heuristic":
        return _heuristic(rows)
    model = load_model()
    if model is None:
        return _heuristic(rows)
    try:
        import numpy as np
        import xgboost as xgb

        booster, wrapper = model
        conf = wrapper.get("conformal", {"lo": 0.0, "hi": 0.0})
        preds = []
        for k, qcol in enumerate(("est_qty_p05", "est_qty_p50", "est_qty_p95")):
            X = np.array([feature_vector({**r, "stock_qty": r[qcol]}) for r in rows], dtype=float)
            p = booster.predict(xgb.DMatrix(X, feature_names=wrapper["feature_columns"]))
            p = p.reshape(len(rows), -1)
            preds.append(p[:, min(k, p.shape[1] - 1)])
        cap = float(settings.PLAN_HORIZON_H)
        out = []
        for i in range(len(rows)):
            lo, mid, hi = sorted([float(preds[0][i]) - conf["lo"], float(preds[1][i]), float(preds[2][i]) + conf["hi"]])
            out.append(tuple(min(cap, max(0.0, v)) for v in (lo, mid, hi)))
        return out
    except Exception as e:
        _warn_once(f"forecaster predict failed ({e}); using heuristic tts")
        return _heuristic(rows)
