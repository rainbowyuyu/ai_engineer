#!/usr/bin/env python3
"""兼容入口：转调 examples/three/main.py。"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

_MAIN = Path(__file__).resolve().parents[1] / "examples" / "tri" / "three" / "main.py"
sys.argv[0] = str(_MAIN)
raise SystemExit(runpy.run_path(str(_MAIN), run_name="__main__") or 0)
