#!/usr/bin/env python3
"""Task-local grade entry — delegates to shared scripts/common/grade."""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.argv = [
    sys.argv[0],
    "--world",
    "unistore-mail",
    "--task",
    "fraud-hold",
    *sys.argv[1:],
]
runpy.run_path(
    str(ROOT / "scripts" / "common" / "grade" / "run_grade.py"),
    run_name="__main__",
)
