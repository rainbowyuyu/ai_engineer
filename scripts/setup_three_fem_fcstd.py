#!/usr/bin/env python3
"""兼容入口：转调 examples/three/setup_fem_fcstd.py。"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

_TARGET = Path(__file__).resolve().parents[1] / "examples" / "three" / "setup_fem_fcstd.py"
sys.argv[0] = str(_TARGET)
raise SystemExit(runpy.run_path(str(_TARGET), run_name="__main__") or 0)
