"""Forecaster training and prediction on practice data. OWNER: M3."""

from __future__ import annotations

import pytest

from engine import forecaster
from lantern_core.config import settings

ROW = dict(hazard="wildfire", site_type="shelter", supply_id="water", sim_hour=9, people_served=500,
           temp_c=30, hazard_level=2, stock_qty=700, burn_rate_per_h=20.8, report_age_h=0)


def test_fallback_without_model():
    (lo, mid, hi), = forecaster.predict([ROW])
    assert lo == mid == hi == pytest.approx(700 / 20.8, rel=1e-3)


def test_train_and_predict():
    pytest.importorskip("xgboost")
    import pandas as pd

    from models.make_dev_features import make
    from models.train import train

    df = pd.concat([make(24, seed=0, prefix="train"), make(9, seed=1, prefix="test")], ignore_index=True)
    m = train(df, n_estimators=40)
    assert 0 <= m["interval_coverage_90"] <= 1
    preds = forecaster.predict([ROW, {**ROW, "stock_qty": 50}])
    for lo, mid, hi in preds:
        assert 0 <= lo <= mid <= hi <= settings.plan_horizon_h
    assert preds[0][1] > preds[1][1]  # more stock -> longer time to shortage
