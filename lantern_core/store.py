"""Storage facade: the same seven functions in local, memory and aws modes (contract 2.4).

local:  objects under LOCAL_STORE_DIR/s3/<key> (web bucket: LOCAL_STORE_DIR/s3web/<key>),
        tables as LOCAL_STORE_DIR/ddb/<table>.json
memory: process-local dicts (evaluation and tests)
aws:    boto3 with the default credential chain (plus AWS_PROFILE outside Lambda)
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from decimal import Decimal
from pathlib import Path
from typing import Any

from lantern_core.config import settings

log = logging.getLogger(__name__)

_lock = threading.RLock()
_MEM: dict[str, dict] = {"s3": {}, "ddb": {}}
_TABLE_CACHE: dict[Path, tuple[int, dict]] = {}
_AWS: dict[str, Any] = {}


# --------------------------------------------------------------------------- helpers


def table_keys(table: str) -> tuple[str, str]:
    """Table key registry: (partition key, sort key) for each configured table."""
    registry = {
        settings.TABLE_SITES: ("scenario_id", "site_id"),
        settings.TABLE_INVENTORY: ("scenario_id", "site_supply"),
        settings.TABLE_PLANS: ("scenario_id", "plan_id"),
        settings.TABLE_GATE_LOG: ("session_id", "transfer_id"),
    }
    if table not in registry:
        raise KeyError(f"unknown table {table!r}")
    return registry[table]


_COORD_KEYS = {"lat", "lon"}


def normalize(value: Any, key: str | None = None) -> Any:
    """Round quantities to 2 decimals (lat/lon to 4) and drop None values, recursively."""
    if isinstance(value, dict):
        return {k: normalize(v, k) for k, v in value.items() if v is not None}
    if isinstance(value, list | tuple):
        return [normalize(v, key) for v in value if v is not None]
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return round(value, 4 if key in _COORD_KEYS else 2)
    if isinstance(value, Decimal):
        return _from_decimal(value)
    return value


def _to_decimal(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _to_decimal(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_decimal(v) for v in value]
    if isinstance(value, bool):
        return value
    if isinstance(value, float | int):
        return Decimal(str(value))
    return value


def _from_decimal(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _from_decimal(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_from_decimal(v) for v in value]
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() and "." not in str(value) else float(value)
    return value


def _mode() -> str:
    return settings.LANTERN_MODE


def _is_web(bucket: str | None) -> bool:
    return bucket is not None and bucket in (settings.WEB_BUCKET, "web")


def _bucket_name(bucket: str | None) -> str:
    if bucket is None:
        return settings.DATA_BUCKET
    if bucket == "web":
        return settings.WEB_BUCKET
    return bucket


def _to_bytes(data: bytes | str) -> bytes:
    return data.encode("utf-8") if isinstance(data, str) else bytes(data)


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=path.suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def reset_memory() -> None:
    with _lock:
        _MEM["s3"].clear()
        _MEM["ddb"].clear()


def clear_cache() -> None:
    with _lock:
        _TABLE_CACHE.clear()
        _AWS.clear()


# --------------------------------------------------------------------------- local backend


def _local_obj_path(key: str, bucket: str | None) -> Path:
    base = settings.local_store_path / ("s3web" if _is_web(bucket) else "s3")
    return base.joinpath(*key.split("/"))


def _local_table_path(table: str) -> Path:
    return settings.local_store_path / "ddb" / f"{table}.json"


def _local_load_table(table: str) -> dict:
    path = _local_table_path(table)
    if not path.exists():
        return {}
    mtime = path.stat().st_mtime_ns
    cached = _TABLE_CACHE.get(path)
    if cached and cached[0] == mtime:
        return cached[1]
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    _TABLE_CACHE[path] = (mtime, data)
    return data


def _local_save_table(table: str, data: dict) -> None:
    path = _local_table_path(table)
    _atomic_write(path, json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    _TABLE_CACHE[path] = (path.stat().st_mtime_ns, data)


# --------------------------------------------------------------------------- aws backend


def _aws_session():
    if "session" not in _AWS:
        import boto3

        if os.environ.get("AWS_LAMBDA_FUNCTION_NAME") or not settings.AWS_PROFILE:
            _AWS["session"] = boto3.Session(region_name=settings.AWS_REGION)
        else:
            try:
                _AWS["session"] = boto3.Session(profile_name=settings.AWS_PROFILE, region_name=settings.AWS_REGION)
            except Exception:  # profile missing: fall back to the default chain
                _AWS["session"] = boto3.Session(region_name=settings.AWS_REGION)
    return _AWS["session"]


def aws_client(service: str):
    key = f"client:{service}"
    if key not in _AWS:
        _AWS[key] = _aws_session().client(service, region_name=settings.AWS_REGION)
    return _AWS[key]


def _aws_table(table: str):
    key = f"table:{table}"
    if key not in _AWS:
        _AWS[key] = _aws_session().resource("dynamodb", region_name=settings.AWS_REGION).Table(table)
    return _AWS[key]


# --------------------------------------------------------------------------- the seven functions


def put_object(key: str, data: bytes | str, bucket: str | None = None, content_type: str | None = None) -> None:
    body = _to_bytes(data)
    mode = _mode()
    if mode == "memory":
        with _lock:
            _MEM["s3"].setdefault(_bucket_name(bucket), {})[key] = body
    elif mode == "local":
        with _lock:
            _atomic_write(_local_obj_path(key, bucket), body)
    else:
        extra = {"ContentType": content_type} if content_type else {}
        aws_client("s3").put_object(Bucket=_bucket_name(bucket), Key=key, Body=body, **extra)


def get_object(key: str, bucket: str | None = None) -> bytes | None:
    """Return the object bytes, or None if it does not exist."""
    mode = _mode()
    if mode == "memory":
        return _MEM["s3"].get(_bucket_name(bucket), {}).get(key)
    if mode == "local":
        path = _local_obj_path(key, bucket)
        return path.read_bytes() if path.exists() else None
    from botocore.exceptions import ClientError

    try:
        return aws_client("s3").get_object(Bucket=_bucket_name(bucket), Key=key)["Body"].read()
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404", "NotFound"):
            return None
        raise


def list_keys(prefix: str = "", bucket: str | None = None) -> list[str]:
    mode = _mode()
    if mode == "memory":
        return sorted(k for k in _MEM["s3"].get(_bucket_name(bucket), {}) if k.startswith(prefix))
    if mode == "local":
        base = settings.local_store_path / ("s3web" if _is_web(bucket) else "s3")
        if not base.exists():
            return []
        keys = []
        for p in base.rglob("*"):
            if p.is_file() and not p.name.startswith(".tmp_"):
                k = p.relative_to(base).as_posix()
                if k.startswith(prefix):
                    keys.append(k)
        return sorted(keys)
    keys = []
    paginator = aws_client("s3").get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=_bucket_name(bucket), Prefix=prefix):
        keys.extend(o["Key"] for o in page.get("Contents", []))
    return sorted(keys)


def put_item(table: str, item: dict) -> None:
    batch_put(table, [item])


def get_item(table: str, pk: str, sk: str) -> dict | None:
    mode = _mode()
    pk_name, sk_name = table_keys(table)
    if mode == "memory":
        item = _MEM["ddb"].get(table, {}).get(pk, {}).get(sk)
        return json.loads(json.dumps(item)) if item is not None else None
    if mode == "local":
        with _lock:
            item = _local_load_table(table).get(pk, {}).get(sk)
        return json.loads(json.dumps(item)) if item is not None else None
    resp = _aws_table(table).get_item(Key={pk_name: pk, sk_name: sk})
    item = resp.get("Item")
    return _from_decimal(item) if item else None


def query_pk(table: str, pk: str) -> list[dict]:
    """All items with partition key `pk`, sorted by sort key."""
    mode = _mode()
    pk_name, sk_name = table_keys(table)
    if mode in ("memory", "local"):
        with _lock:
            data = _MEM["ddb"].get(table, {}) if mode == "memory" else _local_load_table(table)
            items = [data[pk][sk] for sk in sorted(data.get(pk, {}))]
        return json.loads(json.dumps(items))
    from boto3.dynamodb.conditions import Key

    items, kwargs = [], {"KeyConditionExpression": Key(pk_name).eq(pk)}
    while True:
        resp = _aws_table(table).query(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    items = [_from_decimal(i) for i in items]
    return sorted(items, key=lambda i: str(i[sk_name]))


def batch_put(table: str, items: list[dict]) -> None:
    if not items:
        return
    pk_name, sk_name = table_keys(table)
    clean = [normalize(i) for i in items]
    for i in clean:
        if pk_name not in i or sk_name not in i:
            raise ValueError(f"item for {table} must have {pk_name} and {sk_name}")
    mode = _mode()
    if mode == "memory":
        with _lock:
            t = _MEM["ddb"].setdefault(table, {})
            for i in clean:
                t.setdefault(str(i[pk_name]), {})[str(i[sk_name])] = i
        return
    if mode == "local":
        with _lock:
            data = _local_load_table(table)
            for i in clean:
                data.setdefault(str(i[pk_name]), {})[str(i[sk_name])] = i
            _local_save_table(table, data)
        return
    with _aws_table(table).batch_writer(overwrite_by_pkeys=[pk_name, sk_name]) as w:
        for i in clean:
            w.put_item(Item=_to_decimal(i))


# --------------------------------------------------------------------------- convenience


def put_json(key: str, obj: Any, bucket: str | None = None) -> None:
    put_object(key, json.dumps(obj, ensure_ascii=False, indent=1), bucket=bucket, content_type="application/json")


def get_json(key: str, bucket: str | None = None, default: Any = None) -> Any:
    raw = get_object(key, bucket=bucket)
    return json.loads(raw.decode("utf-8")) if raw is not None else default


def put_jsonl(key: str, rows: list[dict], bucket: str | None = None) -> None:
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    put_object(key, text, bucket=bucket, content_type="application/x-ndjson")


def get_jsonl(key: str, bucket: str | None = None) -> list[dict]:
    raw = get_object(key, bucket=bucket)
    if raw is None:
        return []
    return [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]


def get_text(key: str, bucket: str | None = None) -> str | None:
    raw = get_object(key, bucket=bucket)
    return raw.decode("utf-8") if raw is not None else None
