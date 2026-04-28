from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from backend.qwen_client import QwenClient


@dataclass
class AgentDecision:
    inp_path: Optional[str] = None
    mass_goal_ratio: float = 0.4
    filter_radius: float = 2.0
    optimization_base: str = "failure_index"
    save_every: int = 10
    reasoning_summary: str | None = None


SYSTEM_PROMPT = """你是一个工程智能体，把用户的自然语言需求转换成一个 JSON 对象，用于运行 BESO 拓扑优化任务。
只输出 JSON，不要输出其它文本，也不要用 Markdown。

输出 JSON 字段（必须全部给出）：
- reasoning_summary: string  (一句话中文总结你是如何从用户话里抽取参数的)
- inp_path: string|null （inp 文件绝对路径；如果用户没给就保持 null）
- mass_goal_ratio: number （0~1）
- filter_radius: number （mm）
- optimization_base: string （failure_index 或 stiffness）
- save_every: integer （每 N 次迭代保存一次结果）
"""


def decide_params(user_message: str, qwen: Optional[QwenClient] = None) -> AgentDecision:
    """
    MVP: 如果没有配置 QWEN_API_KEY，就用保守默认值；
    如果配置了，就让 Qwen 返回结构化 JSON。
    """
    if not qwen:
        qwen = QwenClient()

    # If API key not set, keep defaults (do not throw).
    if not qwen.api_key:
        return AgentDecision(reasoning_summary="未配置 QWEN_API_KEY，使用默认参数。")

    try:
        resp = qwen.chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ]
        )
        content = resp["choices"][0]["message"]["content"]
        data: Dict[str, Any] = json.loads(content)
        return AgentDecision(
            reasoning_summary=str(data.get("reasoning_summary", "")) or None,
            inp_path=data.get("inp_path"),
            mass_goal_ratio=float(data.get("mass_goal_ratio", 0.4)),
            filter_radius=float(data.get("filter_radius", 2.0)),
            optimization_base=str(data.get("optimization_base", "failure_index")),
            save_every=int(data.get("save_every", 10)),
        )
    except Exception:
        return AgentDecision(reasoning_summary="解析失败，使用默认参数。")

