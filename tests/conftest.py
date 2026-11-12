"""Shared fixtures: every test drives the real CLI as a subprocess."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Callable, List, Optional

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOOL = PROJECT_ROOT / "skepstack.py"
LEDGER_NAME = "skepstack-ledger.jsonl"


@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    """An empty directory the CLI runs inside, so ./skepstack-ledger.jsonl is local."""
    return tmp_path


@pytest.fixture
def run(workdir: Path) -> Callable[..., subprocess.CompletedProcess]:
    def _run(*args: str, stdin: Optional[str] = None) -> subprocess.CompletedProcess:
        # argv list, shell=False: no shell string is ever built or interpolated.
        return subprocess.run(
            [sys.executable, str(TOOL), *args],
            cwd=str(workdir),
            input=stdin,
            capture_output=True,
            text=True,
            timeout=120,
            shell=False,
        )

    return _run


@pytest.fixture
def ledger(workdir: Path) -> Path:
    return workdir / LEDGER_NAME


@pytest.fixture
def log(run: Callable[..., subprocess.CompletedProcess]) -> Callable[..., subprocess.CompletedProcess]:
    """Log one inspection through the CLI with sensible defaults."""

    def _log(
        hive: str = "H1",
        date: str = "2024-05-01",
        mites: str = "3",
        queen: str = "queenright",
        treatment: Optional[str] = None,
        notes: Optional[str] = None,
        ledger: str = LEDGER_NAME,
    ) -> subprocess.CompletedProcess:
        args = ["--ledger", ledger, "log", "--hive", hive, "--date", date, "--mites", mites, "--queen", queen]
        if treatment is not None:
            args += ["--treatment-date", treatment]
        if notes is not None:
            args += ["--notes", notes]
        return run(*args)

    return _log


@pytest.fixture
def records() -> Callable[[Path], List[dict]]:
    def _records(path: Path) -> List[dict]:
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    return _records
