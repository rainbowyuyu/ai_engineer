from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests

from backend.qwen_runtime_config import get_qwen_config


class QwenClient:
    """
    Minimal Qwen client (OpenAI-compatible endpoint).
    Default base_url matches DashScope compatible mode. Override via env.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout_s: float = 60.0,
    ):
        runtime = get_qwen_config()
        self.api_key = api_key or runtime.api_key or os.environ.get("QWEN_API_KEY")
        self.base_url = (
            base_url
            or runtime.base_url
            or os.environ.get("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        )
        self.model = model or runtime.model or os.environ.get("QWEN_MODEL", "qwen-plus")
        self.timeout_s = timeout_s

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.2) -> Dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("QWEN_API_KEY is not set (use environment variable)")
        url = f"{self.base_url}/chat/completions"
        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "messages": messages, "temperature": temperature},
            timeout=self.timeout_s,
        )
        r.raise_for_status()
        return r.json()

