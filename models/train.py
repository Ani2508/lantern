"""Train the time-to-shortage quantile forecaster. OWNER: M3.  (make train)

Reads clean/training/features.csv (contract 2.9), trains ONE XGBoost model
with objective reg:quantileerror at alphas 0.05 / 0.5 / 0.95 on train_* rows,
reports on test_* rows, applies a conformal widening if test coverage of
[p05, p95] misses 90% by more than 5 points, then saves:
    models/forecaster/v1/model.json
    models/forecaster/v1/metrics.json   (pinball loss, coverage, feature_columns)
"""

from __future__ import annotations

import argparse
import io
import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from engine import forecaster
from lantern_core import store
from lantern_core.config import settings
from lantern_core.ids import iso

ALPHAS = np.array(settings.quantiles)


def pinball(y: np.ndarray, q: np.ndarray, alpha: float) -> float:
    d = y - q
    return float(np.mean(np.maximum(alpha * d, (alpha - 1) * d)))


def coverage(y: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> float:
    return float(np.mean((y >= lo) & (y <= hi)))


def train(df: pd.DataFrame, n_estimators: int = 300, seed: int = 0) -> dict:
    import xgboost as xgb

    is_train = df["scenario_id"].str.startswith("train_")
    is_test = df["scenario_id"].str.startswith("test_")
    if not is_train.any() or not is_test.any():
        raise ValueError("features.csv needs both train_* and test_* scenarios")

    # hold out 20% of training scenarios for calibration
    train_ids = df.loc[is_train, "scenario_id"].unique()
    rng = np.random.default_rng(seed)
    calib_ids = set(rng.choice(train_ids, size=max(1, len(train_ids) // 5), replace=False))
    is_calib = df["scenario_id"].isin(calib_ids)
    fit = is_train & ~is_calib

    X_all, cols = forecaster.encode(df.to_dict("records"))
    y = df["target_tts_h"].to_numpy(dtype=float)

    model = xgb.XGBRegressor(
        objective="reg:quantileerror", quantile_alpha=ALPHAS, tree_method="hist",
        n_estimators=n_estimators, learning_rate=0.05, max_depth=6, random_state=seed,
    )
    model.fit(X_all[fit.values], y[fit.values])

    def pred(mask):
        p = model.predict(X_all[mask.values])
        return np.sort(np.clip(p, 0, settings.plan_horizon_h), axis=1)

    # conformal widening (CQR) on the calibration split
    pc, yc = pred(is_calib), y[is_calib.values]
    scores = np.maximum(pc[:, 0] - yc, yc - pc[:, 2])
    target = 0.90
    pt, yt = pred(is_test), y[is_test.values]
    raw_cov = coverage(yt, pt[:, 0], pt[:, 2])
    widen = 0.0
    if abs(raw_cov - target) > 0.05:
        n = len(scores)
        widen = float(np.quantile(scores, min(1.0, np.ceil((n + 1) * target) / n)))
    lo, hi = np.clip(pt[:, 0] - widen, 0, None), pt[:, 2] + widen

    metrics = {
        "trained_at": iso(),
        "rows_fit": int(fit.sum()), "rows_calib": int(is_calib.sum()), "rows_test": int(is_test.sum()),
        "pinball_test": {str(a): pinball(yt, pt[:, i], a) for i, a in enumerate(ALPHAS)},
        "coverage_90_raw": raw_cov,
        "conformal_widen_h": widen,
        "interval_coverage_90": coverage(yt, lo, hi),
        "feature_columns": cols,
    }

    # the widening is applied at predict time (engine.forecaster reads it from metrics)
    booster = model.get_booster()
    path = Path(tempfile.gettempdir()) / "lantern_model_out.json"
    booster.save_model(str(path))
    store.put_object(settings.forecaster_model_key, path.read_bytes())
    store.put_json(forecaster.metrics_key(), metrics)
    forecaster.reload_model()
    return metrics


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-estimators", type=int, default=300)
    args = ap.parse_args()
    df = pd.read_csv(io.BytesIO(store.get_object("clean/training/features.csv")))
    m = train(df, n_estimators=args.n_estimators)
    print(json.dumps({k: v for k, v in m.items() if k != "feature_columns"}, indent=2))


if __name__ == "__main__":
    main()
