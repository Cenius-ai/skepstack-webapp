#!/usr/bin/env bash
# SkepStack setup: install dependencies, seed the demo ledger, then EXIT.
# Safe to re-run. Never starts a server (SkepStack is a command-line tool) and
# never installs system packages.
set -euo pipefail
cd "$(dirname "$0")"

install_requirements() {
  python3 -m pip install -r requirements.txt && return 0
  echo "note: retrying the dependency install for the current user" >&2
  python3 -m pip install --user -r requirements.txt && return 0
  python3 -c 'import pytest' 2>/dev/null
}

echo "==> refreshing pip, setuptools and wheel"
if ! python3 -m pip install --upgrade pip setuptools wheel; then
  echo "note: could not refresh the Python tooling; continuing with what is installed" >&2
fi

echo "==> installing project dependencies"
if ! install_requirements; then
  echo "error: could not install requirements.txt and pytest is not importable" >&2
  exit 1
fi

echo "==> installing the 'skepstack' console script"
if ! python3 -m pip install --no-build-isolation -e .; then
  if ! python3 -m pip install --no-build-isolation --user -e .; then
    echo "note: the console script could not be installed; 'python3 skepstack.py <command>' works without it" >&2
  fi
fi

echo "==> verifying the tool imports and runs"
python3 -c 'import skepstack'
python3 skepstack.py --version

echo "==> seeding the demo ledger"
bash scripts/seed_demo.sh

echo
echo "Setup complete. Nothing is running in the background."
echo "Try:"
echo "  python3 skepstack.py list"
echo "  python3 skepstack.py list --hive H1"
echo "  bash demo.sh"
echo "  python3 -m pytest"
