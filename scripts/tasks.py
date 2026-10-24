"""Fallback for people without `make` (e.g. Windows):  python scripts/tasks.py <target>

Covers the targets you need day to day. Deploy stays in the Makefile (M1 only, Mac/Linux).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV_PY = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
PY = str(VENV_PY if VENV_PY.exists() else sys.executable)

TASKS: dict[str, tuple[list[list[str]], dict[str, str]]] = {
    "setup": ([[sys.executable, "-m", "venv", ".venv"], ["{py}", "-m", "pip", "install", "-e", ".[dev]"]], {}),
    "check": ([["{py}", "-m", "ruff", "check", "."], ["{py}", "-m", "pytest"]], {}),
    "test": ([["{py}", "-m", "pytest"]], {}),
    "lint": ([["{py}", "-m", "ruff", "check", "."]], {}),
    "local-demo": ([["{py}", "scripts/local_demo.py"]], {"LANTERN_MODE": "local"}),
    "fixture": ([["{py}", "-m", "simulator.demo_fixture"]], {}),
    "features": ([["{py}", "-m", "simulator.features"]], {}),
    "dev-features": ([["{py}", "-m", "models.make_dev_features"]], {}),
    "train": ([["{py}", "-m", "models.train"]], {}),
    "eval": ([["{py}", "-m", "eval.run_eval"]], {"NOTIFY_ENABLED": "false", "BEDROCK_ENABLED": "false"}),
    "api": ([["{py}", "-m", "uvicorn", "api.app:app", "--reload", "--port", "8000"]], {"LANTERN_MODE": "local"}),
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in TASKS:
        print("usage: python scripts/tasks.py <" + "|".join(TASKS) + "> [extra args]")
        return 1
    cmds, env = TASKS[sys.argv[1]]
    for i, cmd in enumerate(cmds):
        py = PY if sys.argv[1] != "setup" or i > 0 else sys.executable
        if sys.argv[1] == "setup" and i > 0:
            py = str(VENV_PY)
        cmd = [py if c == "{py}" else c for c in cmd]
        if i == len(cmds) - 1:
            cmd += sys.argv[2:]
        print("$", " ".join(cmd))
        rc = subprocess.call(cmd, cwd=ROOT, env={**os.environ, **env})
        if rc:
            return rc
    return 0


if __name__ == "__main__":
    sys.exit(main())
