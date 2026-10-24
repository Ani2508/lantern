"""Storage layer with the same seven functions in local and aws mode (contract 2.4).

OWNER: M1.

Local mode keeps S3 objects as files under ./.localstore/s3/<key> and each
DynamoDB table as ./.localstore/ddb/<table>.json. Memory mode keeps the same
data in process memory (fast; used by evaluation). AWS mode uses boto3.
All writes drop None values and round floats to 2 decimals (contract 2.6).
"""

from __future__ import annotations

import json
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

from lantern_core.config import settings


# (partition key, sort key) per table, by table name from settings
def _keys() -> dict[str, tuple[str, str]]:
    return {
        settings.table_sites: ("scenario_id", "site_id"),
        settings.table_inventory: ("scenario_id", "site_supply"),
        settings.table_plans: ("scenario_id", "plan_id"),
        settings.table_gate_log: ("session_id", "transfer_id"),
    }


def _clean(value: Any) -> Any:
    """Drop None, round floats to 2 decimals, recurse into lists and dicts."""
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_clean(v) for v in value if v is not None]
    if isinstance(value, float):
        return round(value, 2)
    return value


def _to_dynamo(value: Any) -> Any:
    return json.loads(json.dumps(value), parse_float=Decimal)


def _from_dynamo(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _from_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_from_dynamo(v) for v in value]
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


def _local() -> bool:
    """True for both file-backed local mode and in-process memory mode."""
    return settings.lantern_mode in ("local", "memory")


def _memory() -> bool:
    return settings.lantern_mode == "memory"


_MEM_OBJECTS: dict[str, bytes] = {}
_MEM_TABLES: dict[str, dict[str, dict]] = {}


def reset_memory() -> None:
    """Clear memory mode (tests and eval runs)."""
    _MEM_OBJECTS.clear()
    _MEM_TABLES.clear()


# --- AWS clients ----------------------------------------------------------
@lru_cache(maxsize=1)
def _session():
    import boto3

    profile = settings.aws_profile if not _running_in_lambda() else None
    return boto3.Session(profile_name=profile or None, region_name=settings.aws_region)


def _running_in_lambda() -> bool:
    import os

    return "AWS_LAMBDA_FUNCTION_NAME" in os.environ


def _s3():
    return _session().client("s3")


def _table(name: str):
    return _session().resource("dynamodb").Table(name)


# --- local helpers --------------------------------------------------------
def _s3_path(key: str) -> Path:
    return settings.store_path / "s3" / key


def _table_path(table: str) -> Path:
    return settings.store_path / "ddb" / f"{table}.json"


def _load_table(table: str) -> dict[str, dict]:
    if _memory():
        return _MEM_TABLES.setdefault(table, {})
    p = _table_path(table)
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def _save_table(table: str, rows: dict[str, dict]) -> None:
    if _memory():
        _MEM_TABLES[table] = rows
        return
    p = _table_path(table)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, indent=1, sort_keys=True))
    tmp.replace(p)


def _row_key(table: str, item: dict) -> str:
    pk, sk = _keys()[table]
    return f"{item[pk]}|{item[sk]}"


# --- the seven contract functions -----------------------------------------
def put_object(key: str, body: bytes | str, bucket: str | None = None) -> None:
    data = body.encode() if isinstance(body, str) else body
    if _memory():
        _MEM_OBJECTS[key] = data
        return
    if _local():
        p = _s3_path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return
    _s3().put_object(Bucket=bucket or settings.data_bucket, Key=key, Body=data)


def get_object(key: str, bucket: str | None = None) -> bytes:
    """Raises KeyError when the object does not exist."""
    if _memory():
        if key not in _MEM_OBJECTS:
            raise KeyError(key)
        return _MEM_OBJECTS[key]
    if _local():
        p = _s3_path(key)
        if not p.exists():
            raise KeyError(key)
        return p.read_bytes()
    s3 = _s3()
    try:
        return s3.get_object(Bucket=bucket or settings.data_bucket, Key=key)["Body"].read()
    except s3.exceptions.NoSuchKey as e:
        raise KeyError(key) from e


def list_keys(prefix: str, bucket: str | None = None) -> list[str]:
    if _memory():
        return sorted(k for k in _MEM_OBJECTS if k.startswith(prefix))
    if _local():
        root = settings.store_path / "s3"
        base = root / prefix
        search = base if base.is_dir() else base.parent
        if not search.exists():
            return []
        return sorted(
            str(p.relative_to(root))
            for p in search.rglob("*")
            if p.is_file() and str(p.relative_to(root)).startswith(prefix)
        )
    keys: list[str] = []
    paginator = _s3().get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket or settings.data_bucket, Prefix=prefix):
        keys.extend(o["Key"] for o in page.get("Contents", []))
    return sorted(keys)


def put_item(table: str, item: dict) -> None:
    item = _clean(item)
    if _local():
        rows = _load_table(table)
        rows[_row_key(table, item)] = item
        _save_table(table, rows)
        return
    _table(table).put_item(Item=_to_dynamo(item))


def get_item(table: str, key: dict) -> dict | None:
    if _local():
        return _load_table(table).get(_row_key(table, key))
    resp = _table(table).get_item(Key=key)
    item = resp.get("Item")
    return _from_dynamo(item) if item else None


def query_pk(table: str, pk_value: str) -> list[dict]:
    """All rows with this partition key, sorted by sort key."""
    pk, sk = _keys()[table]
    if _local():
        rows = [r for r in _load_table(table).values() if r.get(pk) == pk_value]
        return sorted(rows, key=lambda r: str(r[sk]))
    from boto3.dynamodb.conditions import Key

    t = _table(table)
    items: list[dict] = []
    kwargs: dict[str, Any] = {"KeyConditionExpression": Key(pk).eq(pk_value)}
    while True:
        resp = t.query(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return [_from_dynamo(i) for i in items]


def batch_put(table: str, items: list[dict]) -> None:
    if _local():
        rows = _load_table(table)
        for item in items:
            item = _clean(item)
            rows[_row_key(table, item)] = item
        _save_table(table, rows)
        return
    with _table(table).batch_writer() as w:
        for item in items:
            w.put_item(Item=_to_dynamo(_clean(item)))


# --- small JSON helpers built on the seven functions -----------------------
def put_json(key: str, obj: Any, bucket: str | None = None) -> None:
    put_object(key, json.dumps(obj, indent=1), bucket)


def get_json(key: str, bucket: str | None = None) -> Any:
    return json.loads(get_object(key, bucket))


def get_jsonl(key: str, bucket: str | None = None) -> list[dict]:
    try:
        raw = get_object(key, bucket).decode()
    except KeyError:
        return []
    return [json.loads(line) for line in raw.splitlines() if line.strip()]
