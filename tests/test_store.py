import pytest

from lantern_core import store
from lantern_core.config import settings


def _exercise(mode_label: str):
    store.put_object("raw/a/b.json", '{"x": 1}')
    store.put_object("raw/a/c.json", b"{}")
    store.put_object("fallback/plan.json", "{}", bucket=settings.WEB_BUCKET)
    assert store.get_object("raw/a/b.json") == b'{"x": 1}'
    assert store.get_object("missing/key") is None
    assert store.list_keys("raw/a/") == ["raw/a/b.json", "raw/a/c.json"]
    assert store.list_keys("fallback/", bucket=settings.WEB_BUCKET) == ["fallback/plan.json"]
    assert "fallback/plan.json" not in store.list_keys("")

    t = settings.TABLE_INVENTORY
    store.put_item(t, {"scenario_id": "s1", "site_supply": "S02#water", "qty": 1.23456, "gone": None})
    store.batch_put(
        t,
        [
            {"scenario_id": "s1", "site_supply": "S01#water", "qty": 2},
            {"scenario_id": "s2", "site_supply": "S01#water", "qty": 3.0},
        ],
    )
    item = store.get_item(t, "s1", "S02#water")
    assert item == {"scenario_id": "s1", "site_supply": "S02#water", "qty": 1.23}, mode_label
    assert [i["site_supply"] for i in store.query_pk(t, "s1")] == ["S01#water", "S02#water"]
    assert store.query_pk(t, "nope") == []
    assert store.get_item(t, "s1", "nope") is None

    # overwrite by key
    store.put_item(t, {"scenario_id": "s1", "site_supply": "S02#water", "qty": 9})
    assert store.get_item(t, "s1", "S02#water")["qty"] == 9

    with pytest.raises(ValueError):
        store.put_item(t, {"scenario_id": "s1"})


def test_memory_backend():
    _exercise("memory")
    store.reset_memory()
    assert store.get_object("raw/a/b.json") is None


def test_local_backend(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "LANTERN_MODE", "local")
    monkeypatch.setattr(settings, "LOCAL_STORE_DIR", str(tmp_path / "ls"))
    _exercise("local")
    assert (tmp_path / "ls" / "s3" / "raw" / "a" / "b.json").exists()
    assert (tmp_path / "ls" / "s3web" / "fallback" / "plan.json").exists()
    assert (tmp_path / "ls" / "ddb" / f"{settings.TABLE_INVENTORY}.json").exists()
    leftovers = [p for p in (tmp_path / "ls").rglob(".tmp_*")]
    assert not leftovers


def test_normalize():
    assert store.normalize({"a": 1.006, "b": None, "c": [1.111, None], "d": True}) == {
        "a": 1.01,
        "c": [1.11],
        "d": True,
    }
    assert store.normalize({"lat": 37.305, "lon": -121.89, "qty": 1.234}) == {
        "lat": 37.305,
        "lon": -121.89,
        "qty": 1.23,
    }


def test_aws_backend_with_moto(monkeypatch):
    moto = pytest.importorskip("moto")
    import boto3

    for k, v in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": "us-east-1",
    }.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(settings, "LANTERN_MODE", "aws")
    monkeypatch.setattr(settings, "AWS_PROFILE", "")
    with moto.mock_aws():
        store.clear_cache()
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=settings.DATA_BUCKET)
        s3.create_bucket(Bucket=settings.WEB_BUCKET)
        ddb = boto3.client("dynamodb", region_name="us-east-1")
        for table in (settings.TABLE_SITES, settings.TABLE_INVENTORY, settings.TABLE_PLANS, settings.TABLE_GATE_LOG):
            pk, sk = store.table_keys(table)
            ddb.create_table(
                TableName=table,
                KeySchema=[{"AttributeName": pk, "KeyType": "HASH"}, {"AttributeName": sk, "KeyType": "RANGE"}],
                AttributeDefinitions=[
                    {"AttributeName": pk, "AttributeType": "S"},
                    {"AttributeName": sk, "AttributeType": "S"},
                ],
                BillingMode="PAY_PER_REQUEST",
            )
        _exercise("aws")
        store.clear_cache()
