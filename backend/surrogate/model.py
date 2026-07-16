"""MLP surrogate model: train (torch) and persist bundle."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from backend.surrogate.config import feature_keys, load_surrogate_config, static_target_keys
from backend.surrogate.dataset import manifest_to_arrays, train_val_split
from backend.surrogate.features import normalize_features
from backend.surrogate.physics_loss import combined_physics_residual, physics_penalties


@dataclass
class ModelBundle:
    mean: np.ndarray
    std: np.ndarray
    feat_keys: list[str]
    tgt_keys: list[str]
    model_version: str
    backend: str  # "torch" | "sklearn"
    state_path: Path
    metrics: dict[str, Any]

    def meta_path(self) -> Path:
        return self.state_path.parent / "meta.json"

    def save_meta(self) -> None:
        meta = {
            "mean": self.mean.tolist(),
            "std": self.std.tolist(),
            "feat_keys": self.feat_keys,
            "tgt_keys": self.tgt_keys,
            "model_version": self.model_version,
            "backend": self.backend,
            "state_file": self.state_path.name,
            "metrics": self.metrics,
        }
        self.meta_path().write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def load_bundle(bundle_dir: Path) -> ModelBundle | None:
    meta_file = bundle_dir / "meta.json"
    if not meta_file.is_file():
        return None
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    state_name = meta.get("state_file") or "model.pt"
    state_path = bundle_dir / state_name
    if not state_path.is_file():
        sk = bundle_dir / "model.joblib"
        if sk.is_file():
            state_path = sk
        else:
            return None
    return ModelBundle(
        mean=np.array(meta["mean"], dtype=np.float64),
        std=np.array(meta["std"], dtype=np.float64),
        feat_keys=list(meta["feat_keys"]),
        tgt_keys=list(meta["tgt_keys"]),
        model_version=str(meta.get("model_version") or "unknown"),
        backend=str(meta.get("backend") or "torch"),
        state_path=state_path,
        metrics=dict(meta.get("metrics") or {}),
    )


def train_from_manifest(
    manifest_path: Path,
    out_dir: Path,
    *,
    cfg: dict[str, Any] | None = None,
) -> ModelBundle:
    cfg = cfg or load_surrogate_config()
    rows = []
    from backend.surrogate.dataset import read_manifest

    rows = read_manifest(manifest_path)
    if len(rows) < 3:
        raise ValueError(f"Need at least 3 samples, got {len(rows)}")

    feat_keys = feature_keys(cfg)
    tgt_keys = static_target_keys(cfg)
    train_rows, val_rows = train_val_split(
        rows,
        val_fraction=float((cfg.get("training") or {}).get("val_fraction") or 0.2),
        seed=int((cfg.get("training") or {}).get("seed") or 42),
    )
    x_train, y_train = manifest_to_arrays(train_rows, feat_keys=feat_keys, tgt_keys=tgt_keys)
    x_val, y_val = manifest_to_arrays(val_rows, feat_keys=feat_keys, tgt_keys=tgt_keys) if val_rows else (None, None)

    mean = x_train.mean(axis=0)
    std = x_train.std(axis=0)
    x_train_n = normalize_features(x_train, mean, std)
    x_val_n = normalize_features(x_val, mean, std) if x_val is not None else None

    tcfg = cfg.get("training") or {}
    out_dir.mkdir(parents=True, exist_ok=True)
    version = str(cfg.get("model_version") or "static_v1")

    try:
        bundle = _train_torch(
            x_train_n,
            y_train,
            x_val_n,
            y_val,
            x_train_raw=x_train,
            out_dir=out_dir,
            cfg=cfg,
            mean=mean,
            std=std,
            feat_keys=feat_keys,
            tgt_keys=tgt_keys,
            version=version,
        )
    except ImportError:
        bundle = _train_sklearn(
            x_train_n,
            y_train,
            x_val_n,
            y_val,
            x_train_raw=x_train,
            out_dir=out_dir,
            cfg=cfg,
            mean=mean,
            std=std,
            feat_keys=feat_keys,
            tgt_keys=tgt_keys,
            version=version,
        )

    bundle.save_meta()
    return bundle


def _eval_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    x_raw: np.ndarray,
    feat_keys: list[str],
    tgt_keys: list[str],
) -> dict[str, Any]:
    mae = float(np.mean(np.abs(y_true - y_pred)))
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - np.mean(y_true, axis=0)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else 0.0
    phys = [combined_physics_residual(physics_penalties(y_pred[i], x_raw[i], feat_keys=feat_keys, tgt_keys=tgt_keys)) for i in range(len(y_pred))]
    return {
        "mae": mae,
        "r2": float(r2),
        "mean_physics_residual": float(np.mean(phys)) if phys else 0.0,
        "n_train": int(len(y_true)),
    }


def _train_torch(
    x_train_n,
    y_train,
    x_val_n,
    y_val,
    *,
    x_train_raw,
    out_dir,
    cfg,
    mean,
    std,
    feat_keys,
    tgt_keys,
    version,
) -> ModelBundle:
    import torch
    import torch.nn as nn

    tcfg = cfg.get("training") or {}
    hidden = list(tcfg.get("hidden_dims") or [64, 32])
    epochs = int(tcfg.get("epochs") or 200)
    lr = float(tcfg.get("learning_rate") or 1e-3)
    batch_size = int(tcfg.get("batch_size") or 16)
    pw = cfg.get("physics_loss_weights") or {}

    layers: list[nn.Module] = []
    in_d = x_train_n.shape[1]
    for h in hidden:
        layers.extend([nn.Linear(in_d, h), nn.ReLU()])
        in_d = h
    layers.append(nn.Linear(in_d, y_train.shape[1]))
    net = nn.Sequential(*layers)

    opt = torch.optim.Adam(net.parameters(), lr=lr)
    mse = nn.MSELoss()
    xt = torch.tensor(x_train_n, dtype=torch.float32)
    yt = torch.tensor(y_train, dtype=torch.float32)

    from backend.surrogate.physics_loss import torch_physics_loss

    n = len(x_train_n)
    for _ in range(epochs):
        perm = torch.randperm(n)
        for start in range(0, n, batch_size):
            idx = perm[start : start + batch_size]
            xb = xt[idx]
            yb = yt[idx]
            xb_raw = torch.tensor(x_train_raw[idx.numpy()], dtype=torch.float32)
            pred = net(xb)
            loss = mse(pred, yb)
            loss = loss + torch_physics_loss(pred, xb_raw, feat_keys, tgt_keys, pw)
            opt.zero_grad()
            loss.backward()
            opt.step()

    net.eval()
    with torch.no_grad():
        y_pred_train = net(torch.tensor(x_train_n, dtype=torch.float32)).numpy()
    metrics = _eval_metrics(y_train, y_pred_train, x_train_raw, feat_keys, tgt_keys)
    if x_val_n is not None and y_val is not None:
        with torch.no_grad():
            y_pred_val = net(torch.tensor(x_val_n, dtype=torch.float32)).numpy()
        # approximate val raw with val normalized * std + mean for physics
        x_val_raw = x_val_n * std + mean
        metrics["val_mae"] = float(np.mean(np.abs(y_val - y_pred_val)))
        metrics["val_physics_residual"] = float(
            np.mean([
                combined_physics_residual(
                    physics_penalties(y_pred_val[i], x_val_raw[i], feat_keys=feat_keys, tgt_keys=tgt_keys)
                )
                for i in range(len(y_pred_val))
            ])
        )

    state_path = out_dir / "model.pt"
    torch.save(net.state_dict(), state_path)
    return ModelBundle(
        mean=mean,
        std=std,
        feat_keys=feat_keys,
        tgt_keys=tgt_keys,
        model_version=version,
        backend="torch",
        state_path=state_path,
        metrics=metrics,
    )


def _train_sklearn(
    x_train_n,
    y_train,
    x_val_n,
    y_val,
    *,
    x_train_raw,
    out_dir,
    cfg,
    mean,
    std,
    feat_keys,
    tgt_keys,
    version,
) -> ModelBundle:
    import joblib
    from sklearn.neural_network import MLPRegressor

    tcfg = cfg.get("training") or {}
    hidden = tuple(tcfg.get("hidden_dims") or [64, 32])
    reg = MLPRegressor(
        hidden_layer_sizes=hidden,
        max_iter=int(tcfg.get("epochs") or 500),
        learning_rate_init=float(tcfg.get("learning_rate") or 1e-3),
        random_state=int(tcfg.get("seed") or 42),
    )
    reg.fit(x_train_n, y_train)
    y_pred_train = reg.predict(x_train_n)
    metrics = _eval_metrics(y_train, y_pred_train, x_train_raw, feat_keys, tgt_keys)
    if x_val_n is not None and y_val is not None:
        y_pred_val = reg.predict(x_val_n)
        x_val_raw = x_val_n * std + mean
        metrics["val_mae"] = float(np.mean(np.abs(y_val - y_pred_val)))
        metrics["val_physics_residual"] = float(
            np.mean([
                combined_physics_residual(
                    physics_penalties(y_pred_val[i], x_val_raw[i], feat_keys=feat_keys, tgt_keys=tgt_keys)
                )
                for i in range(len(y_pred_val))
            ])
        )

    state_path = out_dir / "model.joblib"
    joblib.dump(reg, state_path)
    return ModelBundle(
        mean=mean,
        std=std,
        feat_keys=feat_keys,
        tgt_keys=tgt_keys,
        model_version=version,
        backend="sklearn",
        state_path=state_path,
        metrics=metrics,
    )


def predict_array(bundle: ModelBundle, x_norm: np.ndarray) -> np.ndarray:
    if bundle.backend == "sklearn":
        try:
            import joblib
        except ImportError as e:
            raise ImportError(
                "surrogate sklearn backend requires joblib (pip install -r backend/requirements-surrogate.txt)"
            ) from e
        reg = joblib.load(bundle.state_path)
        return reg.predict(x_norm)
    try:
        import torch
        import torch.nn as nn
    except ImportError as e:
        raise ImportError(
            "surrogate torch backend requires torch (pip install -r backend/requirements-surrogate.txt)"
        ) from e

    meta = json.loads(bundle.meta_path().read_text(encoding="utf-8"))
    tcfg = load_surrogate_config().get("training") or {}
    hidden = list(tcfg.get("hidden_dims") or [64, 32])
    in_d = len(bundle.feat_keys)
    out_d = len(bundle.tgt_keys)
    layers: list[nn.Module] = []
    for h in hidden:
        layers.extend([nn.Linear(in_d, h), nn.ReLU()])
        in_d = h
    layers.append(nn.Linear(in_d, out_d))
    net = nn.Sequential(*layers)
    try:
        state = torch.load(bundle.state_path, map_location="cpu", weights_only=True)
    except TypeError:
        state = torch.load(bundle.state_path, map_location="cpu")
    net.load_state_dict(state)
    net.eval()
    with torch.no_grad():
        return net(torch.tensor(x_norm, dtype=torch.float32)).numpy()
