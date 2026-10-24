from baselines.equal_split import propose


def _row(site, supply, qty, people):
    return {
        "scenario_id": "x",
        "site_supply": f"{site}#{supply}",
        "site_id": site,
        "supply_id": supply,
        "sim_hour": 5,
        "last_reported_qty": qty,
        "last_report_hour": 5,
        "report_age_h": 0,
        "data_status": "live",
        "people_served": people,
    }


def test_shares_by_people_served():
    inv = [_row("S01", "water", 0, 100), _row("S02", "water", 400, 100)]
    sites = [
        {"site_id": "S01", "lat": 37.30, "lon": -121.90},
        {"site_id": "S02", "lat": 37.31, "lon": -121.88},
    ]
    ts = propose(inv, 5, "plan_x_equal_split_h005", sites=sites)
    assert [(t.source_site_id, t.dest_site_id, t.qty) for t in ts] == [("S02", "S01", 200)]
    assert ts[0].transfer_id == "plan_x_equal_split_h005_t01" and ts[0].distance_km > 0


def test_respects_cap_and_min():
    inv = [_row("S01", "insulin", 0, 100), _row("S02", "insulin", 30, 100), _row("S03", "insulin", 15.5, 100)]
    ts = propose(inv, 5, "plan_x_equal_split_h005")
    assert all(t.qty <= 6 and t.qty >= 2 for t in ts)
    assert sum(t.qty for t in ts if t.dest_site_id == "S01") <= 15.17 + 0.01
