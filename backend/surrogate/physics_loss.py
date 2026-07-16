"""Physics-informed penalty terms for surrogate training and confidence."""
from __future__ import annotations

from typing import Any

import numpy as np

from backend.surrogate.config import load_surrogate_config


def analytical_steel_mass_kg(
    leg_mean_diameter_m: float,
    leg_mean_length_m: float,
    wall_thickness_m: float,
    n_legs: int = 3,
    steel_density: float = 7850.0,
) -> float:
    """Cylindrical shell mass estimate (physics anchor)."""
    if leg_mean_diameter_m <= 0 or leg_mean_length_m <= 0 or wall_thickness_m <= 0:
        return 0.0
    r_o = leg_mean_diameter_m / 2.0
    r_i = max(r_o - wall_thickness_m, 0.0)
    area = np.pi * (r_o**2 - r_i**2)
    vol_one = area * leg_mean_length_m
    return float(n_legs * vol_one * steel_density / 1000.0)  # tonnes


def physics_penalties(
    y_pred: np.ndarray,
    x_raw: np.ndarray,
    *,
    feat_keys: list[str],
    tgt_keys: list[str],
) -> dict[str, float]:
    """Compute scalar physics residual terms (lower is better)."""
    pred = {k: float(y_pred[i]) for i, k in enumerate(tgt_keys)}
    feat = {k: float(x_raw[i]) if i < len(x_raw) else 0.0 for i, k in enumerate(feat_keys)}

    idx = {k: i for i, k in enumerate(feat_keys)}
    d_m = feat.get("leg_mean_diameter_m", feat.get(idx.get("leg_mean_diameter_m", 0), 0))
    if "leg_mean_diameter_m" in idx:
        d_m = float(x_raw[idx["leg_mean_diameter_m"]])
    len_m = float(x_raw[idx["leg_mean_length_m"]]) if "leg_mean_length_m" in idx else 50.0
    wt = float(x_raw[idx["wall_thickness_m"]]) if "wall_thickness_m" in idx else 0.06

    steel_anchor = analytical_steel_mass_kg(d_m, len_m, wt)
    steel_pred = pred.get("steel_mass_t", 0.0)
    l_mass = abs(steel_pred - steel_anchor) / max(steel_anchor, 1.0)

    pitch_pred = pred.get("pitch_proxy_deg", 0.0)
    l_pitch = max(0.0, pitch_pred - 5.0) ** 2 / 25.0  # SLS 5 deg soft cap

    uc = pred.get("max_uc_static", 0.0)
    l_bound = max(0.0, -uc) ** 2 + max(0.0, -pitch_pred) ** 2

    # monotonicity: larger diameter should not reduce steel (soft)
    l_mono = 0.0
    if d_m > 0 and steel_pred > 0:
        l_mono = max(0.0, (steel_anchor - steel_pred) / max(steel_anchor, 1.0))

    return {
        "mass": float(l_mass),
        "pitch": float(l_pitch),
        "mono": float(l_mono),
        "bound": float(l_bound),
    }


def combined_physics_residual(penalties: dict[str, float], cfg: dict[str, Any] | None = None) -> float:
    cfg = cfg or load_surrogate_config()
    w = cfg.get("physics_loss_weights") or {}
    total = 0.0
    for key in ("mass", "pitch", "mono", "bound"):
        total += float(w.get(key, 0.1)) * float(penalties.get(key, 0.0))
    return float(total)


def torch_physics_loss(
    y_pred,
    x_batch,
    feat_keys: list[str],
    tgt_keys: list[str],
    weights: dict[str, float],
):
    """Optional torch batch physics loss (import torch lazily)."""
    import torch

    loss = torch.tensor(0.0, device=y_pred.device, dtype=y_pred.dtype)
    steel_idx = tgt_keys.index("steel_mass_t") if "steel_mass_t" in tgt_keys else None
    pitch_idx = tgt_keys.index("pitch_proxy_deg") if "pitch_proxy_deg" in tgt_keys else None
    uc_idx = tgt_keys.index("max_uc_static") if "max_uc_static" in tgt_keys else None

    d_idx = feat_keys.index("leg_mean_diameter_m") if "leg_mean_diameter_m" in feat_keys else None
    l_idx = feat_keys.index("leg_mean_length_m") if "leg_mean_length_m" in feat_keys else None
    w_idx = feat_keys.index("wall_thickness_m") if "wall_thickness_m" in feat_keys else None

    if steel_idx is not None and d_idx is not None and l_idx is not None and w_idx is not None:
        d_m = x_batch[:, d_idx]
        len_m = x_batch[:, l_idx]
        wt = x_batch[:, w_idx]
        r_o = d_m / 2.0
        r_i = torch.clamp(r_o - wt, min=0.0)
        area = torch.pi * (r_o**2 - r_i**2)
        anchor = 3.0 * area * len_m * 7850.0 / 1000.0
        steel_pred = y_pred[:, steel_idx]
        l_mass = torch.mean(((steel_pred - anchor) / torch.clamp(anchor, min=1.0)) ** 2)
        loss = loss + float(weights.get("mass", 0.15)) * l_mass
        l_mono = torch.mean(torch.relu((anchor - steel_pred) / torch.clamp(anchor, min=1.0)) ** 2)
        loss = loss + float(weights.get("mono", 0.05)) * l_mono

    if pitch_idx is not None:
        pitch = y_pred[:, pitch_idx]
        l_pitch = torch.mean(torch.relu(pitch - 5.0) ** 2) / 25.0
        loss = loss + float(weights.get("pitch", 0.10)) * l_pitch
        loss = loss + float(weights.get("bound", 0.05)) * torch.mean(torch.relu(-pitch) ** 2)

    if uc_idx is not None:
        uc = y_pred[:, uc_idx]
        loss = loss + float(weights.get("bound", 0.05)) * torch.mean(torch.relu(-uc) ** 2)

    return loss
