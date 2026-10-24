"""Lantern task runner (works on Windows, macOS and Linux; the Makefile wraps it).

Usage: python scripts/tasks.py <target> [args]
Targets: setup check sim train local-demo eval dashboard api fallback deploy destroy seed
         check-bedrock features regen-fixtures warm
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / ".venv"
VENV_PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
DASHBOARD = ROOT / "dashboard"


def _in_venv() -> bool:
    try:
        return Path(sys.prefix).resolve() == VENV.resolve()
    except OSError:
        return False


def _relaunch_in_venv() -> None:
    if VENV_PY.exists() and not _in_venv() and os.environ.get("LANTERN_NO_VENV") != "1":
        result = subprocess.run([str(VENV_PY), str(Path(__file__).resolve()), *sys.argv[1:]], cwd=ROOT)
        sys.exit(result.returncode)


def _run(cmd: list[str], cwd: Path = ROOT, env: dict | None = None, check: bool = True) -> int:
    print(f"$ {' '.join(cmd)}", flush=True)
    full_env = {**os.environ, **(env or {})}
    result = subprocess.run(cmd, cwd=cwd, env=full_env)
    if check and result.returncode != 0:
        print(f"Command failed with exit code {result.returncode}: {' '.join(cmd)}", file=sys.stderr)
        sys.exit(result.returncode)
    return result.returncode


def _py(*args: str, env: dict | None = None, check: bool = True) -> int:
    return _run([sys.executable, *args], env=env, check=check)


def _npm() -> str | None:
    return shutil.which("npm.cmd") if os.name == "nt" else shutil.which("npm")


def _kv_args(argv: list[str]) -> tuple[dict[str, str], list[str]]:
    """Split KEY=value args (make style) from the rest."""
    kv, rest = {}, []
    for a in argv:
        if "=" in a and not a.startswith("-") and a.split("=", 1)[0].isupper():
            k, v = a.split("=", 1)
            kv[k] = v
        else:
            rest.append(a)
    return kv, rest


def _opt(rest: list[str], name: str, default: str | None = None) -> str | None:
    if name in rest:
        i = rest.index(name)
        if i + 1 < len(rest):
            return rest[i + 1]
    for a in rest:
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return default


# --------------------------------------------------------------------------- targets


def t_setup(_kv, _rest) -> None:
    if not VENV_PY.exists():
        _run([sys.executable, "-m", "venv", str(VENV)])
    _run([str(VENV_PY), "-m", "pip", "install", "--upgrade", "pip"])
    _run([str(VENV_PY), "-m", "pip", "install", "-e", ".[dev]"])
    env_file = ROOT / ".env"
    if not env_file.exists():
        shutil.copyfile(ROOT / ".env.example", env_file)
        print("Created .env from .env.example")
    npm = _npm()
    if not npm:
        print("Node/npm not found, so the dashboard steps are skipped.")
        return
    if (DASHBOARD / "package.json").exists():
        cmd = [npm, "ci"] if (DASHBOARD / "package-lock.json").exists() else [npm, "install"]
        _run([*cmd, "--no-audit", "--no-fund"], cwd=DASHBOARD)


def t_check(_kv, _rest) -> None:
    _py("-m", "ruff", "check", ".")
    _py("-m", "pytest")
    if not (DASHBOARD / "package.json").exists():
        print("dashboard/package.json not found, so the dashboard checks are skipped.")
        return
    npm = _npm()
    if not npm:
        print("Node/npm not found, so the dashboard checks are skipped.")
        return
    if not (DASHBOARD / "node_modules").exists():
        print("dashboard/node_modules missing, so the dashboard checks are skipped (run setup).")
        return
    _run([npm, "run", "lint"], cwd=DASHBOARD)
    _run([npm, "run", "typecheck"], cwd=DASHBOARD)


def t_sim(kv, rest) -> None:
    scenario = kv.get("SCENARIO") or _opt(rest, "--scenario") or "wildfire_demo_01"
    _py("-m", "simulator.generator", "--scenario", scenario)


def t_features(_kv, rest) -> None:
    _py("-m", "eval.features", *rest)


def t_train(_kv, rest) -> None:
    from_existing = "--skip-features" in rest
    if not from_existing:
        t_features({}, [a for a in rest if a != "--skip-features"])
    _py("-m", "models.train")


def t_local_demo(_kv, _rest) -> None:
    _py(str(ROOT / "scripts" / "local_demo.py"))


def t_eval(_kv, rest) -> None:
    _py("-m", "eval.run_eval", *rest)


def t_api(_kv, _rest) -> None:
    env = {"LANTERN_MODE": os.environ.get("LANTERN_MODE", "local")}
    port = os.environ.get("API_PORT", "8000")  # 8000 is often taken by Docker/WSL; the dashboard proxies 8001
    _py("-m", "uvicorn", "api.app:app", "--reload", "--port", port, env=env)


def t_dashboard(_kv, _rest) -> None:
    npm = _npm()
    if not npm:
        print("Node/npm not found, so the dashboard cannot start.", file=sys.stderr)
        sys.exit(1)
    if not (DASHBOARD / "node_modules").exists():
        _run([npm, "install", "--no-audit", "--no-fund"], cwd=DASHBOARD)
    _run([npm, "run", "dev"], cwd=DASHBOARD)


def t_fallback(_kv, _rest) -> None:
    _py("-m", "alerts.fallback_publish")


def t_regen_fixtures(_kv, _rest) -> None:
    _py(str(ROOT / "scripts" / "regen_fixtures.py"))


def t_seed(_kv, _rest) -> None:
    _py(str(ROOT / "scripts" / "seed_demo.py"))


def t_check_bedrock(_kv, _rest) -> None:
    _py(str(ROOT / "scripts" / "check_bedrock.py"))


def t_warm(_kv, rest) -> None:
    _py(str(ROOT / "scripts" / "warm.py"), *rest)


def _sam() -> str:
    sam = shutil.which("sam.cmd") if os.name == "nt" else None
    sam = sam or shutil.which("sam")
    if not sam:
        print("SAM CLI not found. Install it before deploying (see extras/plans/05_aws_checklist.md).", file=sys.stderr)
        sys.exit(1)
    return sam


def t_deploy(_kv, _rest) -> None:
    sam = _sam()
    npm = _npm()
    if npm and (DASHBOARD / "package.json").exists():
        _run([npm, "run", "build"], cwd=DASHBOARD, env={"VITE_USE_MOCKS": "false", "VITE_API_BASE_URL": "/api"})
    _run([sam, "build", "--template-file", "infra/template.yaml"])
    _run([sam, "deploy", "--config-file", "infra/samconfig.toml", "--config-env", "dev", "--resolve-image-repos"])
    _py(str(ROOT / "scripts" / "publish_web.py"))


def t_destroy(_kv, _rest) -> None:
    sam = _sam()
    _run([sam, "delete", "--config-file", "infra/samconfig.toml", "--config-env", "dev"])


TARGETS = {
    "setup": t_setup,
    "check": t_check,
    "sim": t_sim,
    "features": t_features,
    "train": t_train,
    "local-demo": t_local_demo,
    "eval": t_eval,
    "api": t_api,
    "dashboard": t_dashboard,
    "fallback": t_fallback,
    "regen-fixtures": t_regen_fixtures,
    "seed": t_seed,
    "check-bedrock": t_check_bedrock,
    "warm": t_warm,
    "deploy": t_deploy,
    "destroy": t_destroy,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in TARGETS:
        print(__doc__)
        sys.exit(2)
    target = sys.argv[1]
    if target != "setup":
        _relaunch_in_venv()
    os.chdir(ROOT)
    kv, rest = _kv_args(sys.argv[2:])
    TARGETS[target](kv, rest)


if __name__ == "__main__":
    main()
