"""Warm the deployed Lambda (or the local API) so the first judged click is fast."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request


def _get(url: str) -> tuple[int, str, float]:
    t0 = time.perf_counter()
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, body, time.perf_counter() - t0
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace"), time.perf_counter() - t0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default=os.environ.get("LANTERN_API_URL", "http://localhost:8000"))
    args = ap.parse_args()
    base = args.url.rstrip("/")
    status, body, dt = _get(base + "/api/health")
    print(f"GET /api/health -> {status} in {dt:.2f}s: {body}")
    if status != 200:
        sys.exit(1)
    status, body, dt = _get(base + "/api/config/public")
    print(f"GET /api/config/public -> {status} in {dt:.2f}s")
    try:
        print(json.loads(body))
    except json.JSONDecodeError:
        print(body)
    sys.exit(0 if status == 200 else 1)


if __name__ == "__main__":
    main()
