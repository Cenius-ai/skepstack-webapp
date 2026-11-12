"""The shipped smoke script runs green and leaves the working tree untouched."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SMOKE = PROJECT_ROOT / "scripts" / "smoke.py"


def _generated(patterns=("*.jsonl", "*.csv")) -> set:
    found = set()
    for pattern in patterns:
        found.update(path.name for path in PROJECT_ROOT.glob(pattern))
    return found


def test_smoke_script_passes_and_cleans_up():
    before = _generated()
    result = subprocess.run(
        [sys.executable, str(SMOKE)],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=300,
        shell=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "SMOKE OK" in result.stdout
    assert _generated() == before


def test_smoke_script_reports_the_round_trip():
    result = subprocess.run(
        [sys.executable, str(SMOKE)],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=300,
        shell=False,
    )
    assert "field-for-field round trip" in result.stdout
    assert "10 inspections imported" in result.stdout
