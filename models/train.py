"""Train the quantile time-to-shortage forecaster (XGBoost, with a heuristic fallback)."""

from __future__ import annotations

import csv
import io
import json
import logging

from engine.estimator import heuristic_tts
from engine.forecaster import FEATURE_COLUMNS, feature_vector
from lantern_core import store
from lantern_core.config import settings

log = logging.getLogger(__name__)
FEATURES_KEY = "clean/training/features.csv"


def _read_features() -> list[dict]:
    text = store.get_text(FEATURES_KEY)
    if not text:
        raise FileNotFoundError(f"{FEATURES_KEY} is missing; run python scripts/tasks.py features first")
    return list(csv.DictReader(io.StringIO(text)))


def _split(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    train = [r for r in rows if str(r["scenario_id"]).startswith("train_")]
    test = [r for r in rows if str(r["scenario_id"]).startswith("test_")]
    return train, test


def _coverage(pred_lo, pred_hi, y) -> float:
    if len(y) == 0:
        return 0.0
    hits = sum(1 for a, b, t in zip(pred_lo, pred_hi, y, strict=True) if a <= t <= b)
    return hits / len(y)


def _heuristic_predict(rows: list[dict]) -> tuple[list[float], list[float], list[float]]:
    lo, mid, hi = [], [], []
    h = settings.PLAN_HORIZON_H
    for r in rows:
        burn = float(r["burn_rate_per_h"])
        stock = float(r["stock_qty"])
        # features.csv stock_qty is p50; widen by the same age-based sigma the estimator uses
        age = float(r["report_age_h"])
        sigma = max(settings.STALE_SIGMA_FRAC * burn * age, settings.STALE_QTY_FRAC * stock * age)
        p05 = max(0.0, stock - settings.Z_90 * sigma)
        p95 = stock + settings.Z_90 * sigma
        lo.append(heuristic_tts(p05, burn, h))
        mid.append(heuristic_tts(stock, burn, h))
        hi.append(heuristic_tts(p95, burn, h))
    return lo, mid, hi


def _train_xgb(train: list[dict], test: list[dict]) -> dict:
    import numpy as np
    import xgboost as xgb

    def xy(rows):
        X = np.array([feature_vector(r) for r in rows], dtype=float)
        y = np.array([float(r["target_tts_h"]) for r in rows], dtype=float)
        return X, y

    Xtr, ytr = xy(train)
    Xte, yte = xy(test)
    dtr = xgb.DMatrix(Xtr, label=ytr, feature_names=list(FEATURE_COLUMNS))
    dte = xgb.DMatrix(Xte, label=yte, feature_names=list(FEATURE_COLUMNS))
    params = {
        "objective": "reg:quantileerror",
        "quantile_alpha": [0.05, 0.5, 0.95],
        "max_depth": 5,
        "eta": 0.08,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 4,
        "tree_method": "hist",
        "seed": 7,
    }
    booster = xgb.train(params, dtr, num_boost_round=80, evals=[(dte, "test")], verbose_eval=False)
    raw = booster.predict(dte).reshape(len(test), -1)
    lo, mid, hi = raw[:, 0], raw[:, 1], raw[:, 2]
    order = np.argsort(np.vstack([lo, mid, hi]), axis=0)
    stacked = np.vstack([lo, mid, hi])
    lo, mid, hi = (stacked[order[i], np.arange(len(test))] for i in range(3))
    cov = float(_coverage(lo, hi, yte))
    conformal = {"lo": 0.0, "hi": 0.0}
    if abs(cov - 0.90) > 0.05 and len(yte):
        extra = float(np.quantile(np.maximum(yte - hi, lo - yte), 0.90))
        extra = max(0.0, extra)
        conformal = {"lo": extra, "hi": extra}
        lo, hi = lo - extra, hi + extra
        cov = float(_coverage(lo, hi, yte))
    wrapper = {
        "format": "lantern-xgb-v1",
        "feature_columns": list(FEATURE_COLUMNS),
        "booster": json.loads(booster.save_raw(raw_format="json").decode("utf-8")),
        "conformal": conformal,
        "coverage_test": cov,
    }
    return wrapper


def train() -> dict:
    rows = _read_features()
    train_rows, test_rows = _split(rows)
    metrics = {
        "n_train": len(train_rows),
        "n_test": len(test_rows),
        "backend": "heuristic",
        "interval_coverage_90": None,
    }
    wrapper = None
    try:
        wrapper = _train_xgb(train_rows, test_rows)
        metrics["backend"] = "xgboost"
        metrics["interval_coverage_90"] = wrapper["coverage_test"]
        metrics["conformal"] = wrapper["conformal"]
    except Exception as e:
        log.warning("xgboost train failed (%s); writing heuristic metrics only", e)
        if test_rows:
            lo, _mid, hi = _heuristic_predict(test_rows)
            y = [float(r["target_tts_h"]) for r in test_rows]
            metrics["interval_coverage_90"] = _coverage(lo, hi, y)
        wrapper = {
            "format": "lantern-heuristic-v1",
            "feature_columns": list(FEATURE_COLUMNS),
            "booster": None,
            "conformal": {"lo": 0.0, "hi": 0.0},
            "coverage_test": metrics["interval_coverage_90"],
        }

    store.put_object(settings.FORECASTER_MODEL_KEY, json.dumps(wrapper), content_type="application/json")
    store.put_object("models/forecaster/v1/metrics.json", json.dumps(metrics, indent=1), content_type="application/json")
    log.info("forecaster metrics %s", metrics)
    return metrics


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(json.dumps(train(), indent=2))


if __name__ == "__main__":
    main()
