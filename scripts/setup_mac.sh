#!/usr/bin/env bash
# One-time Mac setup for Lantern (contract 2.4). Run from the repo root:
#     bash scripts/setup_mac.sh
# Safe to run again. Installs tools with Homebrew, creates .venv, runs the tests.
set -euo pipefail

say() { printf "\n\033[1;33m==> %s\033[0m\n" "$*"; }

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew not found. Install it from https://brew.sh first, then re-run this script."
  exit 1
fi

say "Installing tools (python 3.12, node 20, AWS CLI, SAM CLI, libomp for XGBoost)"
brew install python@3.12 node@20 awscli libomp git || true
brew tap aws/tap >/dev/null 2>&1 || true
brew install aws-sam-cli || true

PY312="$(brew --prefix python@3.12)/bin/python3.12"

say "Creating .venv with Python 3.12"
[ -d .venv ] || "$PY312" -m venv .venv
.venv/bin/pip install -q -U pip
.venv/bin/pip install -q -e ".[dev]"

if [ ! -f .env ]; then
  cp .env.example .env
  say "Created .env - open it and set ACCOUNT_ID when M1 gives you AWS access"
fi

say "Running tests"
.venv/bin/python -m pytest

say "Running the local demo"
LANTERN_MODE=local .venv/bin/python scripts/local_demo.py

cat <<'EOF'

Done. Next steps:
  1. AWS (when M1 sends credentials - never paste keys in chat):
       aws configure --profile lantern      # region us-east-1, output json
       aws sts get-caller-identity --profile lantern
  2. In VS Code: open this folder, pick the .venv interpreter when asked.
  3. Before every push:  make check
EOF
