from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional


@dataclass
class QwenRuntimeConfig:
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None


_lock = threading.Lock()
_cfg = QwenRuntimeConfig()


def set_qwen_config(api_key: Optional[str], base_url: Optional[str], model: Optional[str]) -> None:
    with _lock:
        _cfg.api_key = api_key or None
        _cfg.base_url = base_url or None
        _cfg.model = model or None


def set_qwen_model_only(model: str) -> None:
    """仅更新进程内模型名，不改动 API Key / Base URL（供设计域侧栏快速切换）。"""
    m = (model or "").strip()
    with _lock:
        _cfg.model = m or None


def get_qwen_config() -> QwenRuntimeConfig:
    with _lock:
        return QwenRuntimeConfig(api_key=_cfg.api_key, base_url=_cfg.base_url, model=_cfg.model)

