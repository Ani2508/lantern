"""Warm every Lambda 5 minutes before judging.  OWNER: M1.   python scripts/warm.py https://<cloudfront>"""

from __future__ import annotations

import json
import sys
import time
import urllib.request

base = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/") + "/api"


def call(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(base + path, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.loads(r.read())
    print(f"{method} {path}: {time.time() - t0:.2f}s")
    return out


call("GET", "/health")
call("POST", "/scenarios/wildfire_demo_01/reset")
call("POST", "/scenarios/wildfire_demo_01/step", {"to_hour": 9})
call("GET", "/scenarios/wildfire_demo_01/state")
call("POST", "/scenarios/wildfire_demo_01/plan", {"planner": "lantern"})
call("POST", "/scenarios/wildfire_demo_01/reset")  # leave it at hour 0 for the demo
print("warm")
