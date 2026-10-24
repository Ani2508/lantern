"""Local store behaves like the contract says. OWNER: M1."""

from __future__ import annotations

import pytest

from lantern_core import store
from lantern_core.config import settings


def test_object_roundtrip():
    store.put_object("raw/x/a.txt", "hi")
    assert store.get_object("raw/x/a.txt") == b"hi"
    assert store.list_keys("raw/x/") == ["raw/x/a.txt"]
    with pytest.raises(KeyError):
        store.get_object("raw/x/missing")


def test_items_drop_none_and_round():
    t = settings.table_inventory
    store.put_item(t, {"scenario_id": "s", "site_supply": "S01#water", "qty": 1.23456, "gone": None})
    item = store.get_item(t, {"scenario_id": "s", "site_supply": "S01#water"})
    assert item == {"scenario_id": "s", "site_supply": "S01#water", "qty": 1.23}
    assert len(store.query_pk(t, "s")) == 1
