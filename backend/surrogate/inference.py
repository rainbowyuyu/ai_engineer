"""Surrogate inference entry point."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from backend.surrogate.blend import choose_alpha, derive_economics_from_static
from backend.surrogate.config import load_surrogate_config, model_bundle_dir
from backend.surrogate.features import extract_feature_dict, feature_vector, normalize_features
from backend.surrogate.model import ModelBundle, load_bundle, predict_array
from backend.surrogate.physics_loss import combined_physics_residual, physics_penalties
from backend.surrogate.config import feature_keys, static_target_keys


@dataclass
class SurrogatePrediction:
    enabled: bool = False
    source: str = "heuristic"  # surrogate | heuristic | blend
    model_version: str | None = None
    physics_residual: float = 0.0
    blend_alpha: float = 0.0
    physics_penalties: dict[str, float] = field(default_factory=dict)
    static: dict[str, float] = field(default_factory=dict)
    unit_cost_cny_per_MW: float | None = None
    construction_years: float | None = None
    fatigue_life_years: float | None = None
    assumptions: list[str] = field(default_factory=list)

    def to_context(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "source": self.source,
            "model_version": self.model_version,
            "physics_residual": self.physics_residual,
            "blend_alpha": self.blend_alpha,
            "physics_penalties": dict(self.physics_penalties),
            "static_predictions": dict(self.static),
            "assumptions": list(self.assumptions),
            "derived": {
                "unit_cost_cny_per_MW": self.unit_cost_cny_per_MW,
                "construction_years": self.construction_years,
                "fatigue_life_years": self.fatigue_life_years,
            },
        }


def _bundle_available(cfg: dict[str, Any], *, force: bool = False) -> ModelBundle | None:
    if not force and not cfg.get("enabled"):
        return None
    bundle = load_bundle(model_bundle_dir(cfg))
    if bundle is None:
        return None
    n_train = int((bundle.metrics or {}).get("n_train") or 0)
    min_n = int(cfg.get("min_training_samples") or 30)
    if not force and n_train < min_n and min_n > 0:
        return None
    return bundle


def predict(
    geometry: dict[str, Any],
    *,
    use_surrogate: bool = False,
    cfg: dict[str, Any] | None = None,
) -> SurrogatePrediction:
    cfg = cfg or load_surrogate_config()
    if not use_surrogate:
        return SurrogatePrediction(enabled=False, source="heuristic")

    bundle = _bundle_available(cfg, force=True)
    if bundle is None:
        return SurrogatePrediction(
            enabled=False,
            source="heuristic",
            assumptions=["物理代理未启用或模型不可用，使用 heuristic proxy"],
        )

    try:
        fk = bundle.feat_keys
        tk = bundle.tgt_keys
        x_raw = feature_vector(geometry, keys=fk)
        x_norm = normalize_features(x_raw.reshape(1, -1), bundle.mean, bundle.std)
        y_pred = predict_array(bundle, x_norm)[0]
    except (ImportError, ModuleNotFoundError) as e:
        missing = getattr(e, "name", None) or str(e).split("'")[1] if "'" in str(e) else str(e)
        return SurrogatePrediction(
            enabled=False,
            source="heuristic",
            assumptions=[
                f"物理代理依赖未安装（{missing}），已回退 heuristic；"
                "可执行 pip install -r backend/requirements-surrogate.txt",
            ],
        )
    except Exception as e:
        return SurrogatePrediction(
            enabled=False,
            source="heuristic",
            assumptions=[f"物理代理推理失败（{e}），已回退 heuristic"],
        )

    static = {k: float(y_pred[i]) for i, k in enumerate(tk)}

    pen = physics_penalties(y_pred, x_raw, feat_keys=fk, tgt_keys=tk)
    phys_res = combined_physics_residual(pen, cfg)
    alpha = choose_alpha(phys_res, cfg)

    fd = extract_feature_dict(geometry)
    target_mw = float(fd.get("target_power_MW") or 20.0)
    steel_t = static.get("steel_mass_t") or 0.0
    intensity = steel_t / target_mw if target_mw > 0 else 0.0

    s_cost, s_const, s_fat = derive_economics_from_static(
        steel_mass_t=steel_t,
        steel_intensity_t_per_MW=intensity,
        max_uc_static=static.get("max_uc_static", 0.8),
        pitch_proxy_deg=static.get("pitch_proxy_deg", 3.0),
    )

    source = "surrogate" if alpha >= 0.99 else ("blend" if alpha > 0 else "heuristic")
    assumptions = [
        "物理信息神经代理（静力通道）参与造价/工期/疲劳估算；不替代 Zwind 时域或 CCS 审图",
        f"model={bundle.model_version}, physics_residual={phys_res:.3f}, α={alpha:.2f}",
    ]

    return SurrogatePrediction(
        enabled=True,
        source=source,
        model_version=bundle.model_version,
        physics_residual=phys_res,
        blend_alpha=alpha,
        physics_penalties=pen,
        static=static,
        unit_cost_cny_per_MW=s_cost,
        construction_years=s_const,
        fatigue_life_years=s_fat,
        assumptions=assumptions,
    )
