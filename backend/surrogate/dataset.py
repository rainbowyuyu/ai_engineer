"""Dataset manifest I/O and train/val split."""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import numpy as np

from backend.surrogate.config import feature_keys, static_target_keys
from backend.surrogate.targets import DatasetRow


def write_manifest(rows: list[DatasetRow], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row.to_manifest_entry(), ensure_ascii=False) + "\n")
    return path


def read_manifest(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def manifest_to_arrays(
    rows: list[dict[str, Any]],
    *,
    feat_keys: list[str] | None = None,
    tgt_keys: list[str] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    feat_keys = feat_keys or feature_keys()
    tgt_keys = tgt_keys or static_target_keys()
    xs: list[list[float]] = []
    ys: list[list[float]] = []
    for row in rows:
        feats = row.get("features") or {}
        labels = row.get("labels") or {}
        xs.append([float(feats.get(k) or 0.0) for k in feat_keys])
        ys.append([float(labels.get(k) or 0.0) for k in tgt_keys])
    return np.array(xs, dtype=np.float64), np.array(ys, dtype=np.float64)


def train_val_split(
    rows: list[dict[str, Any]],
    *,
    val_fraction: float = 0.2,
    seed: int = 42,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if len(rows) < 2:
        return rows, []
    rng = random.Random(seed)
    shuffled = list(rows)
    rng.shuffle(shuffled)
    n_val = max(1, int(len(shuffled) * val_fraction))
    return shuffled[n_val:], shuffled[:n_val]
