import csv
import io

from eval.features import FEATURE_COLUMNS, rows_for_scenario, write_features
from lantern_core import store
from lantern_core.schemas import InventoryState
from simulator.generator import test_ids, train_ids


def test_feature_columns_and_p50_not_truth():
    rows = rows_for_scenario("wildfire_demo_01")
    assert rows
    assert list(rows[0]) == FEATURE_COLUMNS or set(FEATURE_COLUMNS) <= set(rows[0])
    h9 = [r for r in rows if r["sim_hour"] == 9 and r["site_id"] == "S04" and r["supply_id"] == "insulin"]
    assert h9
    # estimated p50 (~39.56), not the true stock (~20.06)
    assert 35 < h9[0]["stock_qty"] < 45
    assert h9[0]["report_age_h"] == 7
    assert 0 <= h9[0]["target_tts_h"] <= 72


def test_write_features_column_order():
    n = write_features([train_ids()[0], test_ids()[0]], key="clean/training/features.csv")
    text = store.get_text("clean/training/features.csv")
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    assert header == FEATURE_COLUMNS
    assert n > 100
    row = next(reader)
    assert len(row) == 13


def test_inventory_schema_still_holds_on_demo_features():
    rows = [r for r in rows_for_scenario("wildfire_demo_01") if r["sim_hour"] == 0]
    assert {r["site_id"] for r in rows} == {"S01", "S02", "S03", "S04", "S05"}
    InventoryState.model_validate(
        {
            "scenario_id": "wildfire_demo_01",
            "site_supply": "S01#water",
            "site_id": "S01",
            "supply_id": "water",
            "sim_hour": 0,
            "last_reported_qty": 2000,
            "last_report_hour": 0,
            "report_age_h": 0,
            "data_status": "live",
            "people_served": 300,
        }
    )
