from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

from backend.qwen_client import QwenClient


@dataclass
class AgentDecision:
    inp_path: Optional[str] = None
    mass_goal_ratio: float = 0.25
    filter_radius: float = 2.0
    optimization_base: str = "failure_index"
    save_every: int = 1
    reasoning_summary: str | None = None


SYSTEM_PROMPT = """你是「AI Engineering」产品的参数解析模块；角色为资深 AI 工程助手，擅长将自然语言需求映射为可执行的仿真参数。把用户输入转换成一个 JSON 对象，用于运行 BESO 拓扑优化任务。
只输出 JSON，不要输出其它文本，也不要用 Markdown 代码围栏。

输出 JSON 字段（必须全部给出）：
- reasoning_summary: string  (一句话中文总结你是如何从用户话里抽取参数的)
- inp_path: string|null （inp 文件绝对路径；若系统上下文已给出当前 INP 且用户未要求换文件，填 null）
- mass_goal_ratio: number （0~1，优化域目标保留质量/体积比；**越小最终实体越少、镂空越明显**，常见 0.18~0.32；过小易应力超限或难收敛）
- filter_radius: number （mm；实体细网格可适当偏大以稳定灵敏度，服务端仍可能按网格尺度自动缩放）
- optimization_base: string （failure_index 或 stiffness）
- save_every: integer （每 N 次迭代保存一次 OBJ/INP 中间结果；**1** 表示每轮都存，结果查看器步进最密；大体网格或磁盘紧张时可取 2~5；仅看最终结果可用较大值）

常见输入含仓库示例 BESO2-FEMMeshGmsh.inp（Gmsh 体网格、规模大）：failure_index 与默认许用应力模板较常见；filter_radius 可取 2~10 mm 量级并结合用户“更平滑/更细结构”等描述调整。若用户希望「更多演化帧 / 更密结果曲线」，save_every 应取 **1** 或 **2**。
"""


def _parse_json_from_llm(content: str) -> Dict[str, Any]:
    """解析模型输出：支持纯 JSON 或 ```json ... ``` 围栏及前文后语中的首个对象。"""
    t = (content or "").strip()
    for block in re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", t, flags=re.IGNORECASE):
        b = block.strip()
        if b.startswith("{"):
            t = b
            break
    dec = json.JSONDecoder()
    for i, ch in enumerate(t):
        if ch == "{":
            obj, _ = dec.raw_decode(t[i:])
            if isinstance(obj, dict):
                return obj
            break
    return json.loads(t)


def decide_params(
    user_message: str,
    qwen: Optional[QwenClient] = None,
    *,
    effective_inp_path: Optional[str] = None,
    scan_dir: Optional[str] = None,
) -> AgentDecision:
    """
    MVP: 如果没有配置 QWEN_API_KEY，就用保守默认值；
    如果配置了，就让 Qwen 返回结构化 JSON。
    """
    if not qwen:
        qwen = QwenClient()

    # If API key not set, keep defaults (do not throw).
    if not qwen.api_key:
        return AgentDecision(reasoning_summary="未配置 QWEN_API_KEY，使用默认参数。")

    user_blocks = [user_message.strip() or "（空消息）请按合理默认给出 BESO 运行参数。"]
    if effective_inp_path:
        user_blocks.append(
            f"[系统上下文] 当前任务已解析的主 INP 绝对路径：\n{effective_inp_path}\n"
            "若用户未明确要求更换输入文件，请将 JSON 字段 inp_path 设为 null；"
            "并请结合该文件可能为大型体网格等特点，给出合适的 filter_radius、mass_goal_ratio 等。"
        )
    if scan_dir:
        user_blocks.append(f"[系统上下文] 扫描目录（多文件模式）：\n{scan_dir}")
    user_content = "\n\n".join(user_blocks)

    try:
        resp = qwen.chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ]
        )
        content = resp["choices"][0]["message"]["content"]
        data = _parse_json_from_llm(content)
        return AgentDecision(
            reasoning_summary=str(data.get("reasoning_summary", "")) or None,
            inp_path=data.get("inp_path"),
            mass_goal_ratio=float(data.get("mass_goal_ratio", 0.25)),
            filter_radius=float(data.get("filter_radius", 2.0)),
            optimization_base=str(data.get("optimization_base", "failure_index")),
            save_every=int(data.get("save_every", 1)),
        )
    except Exception:
        return AgentDecision(reasoning_summary="解析失败，使用默认参数。")

