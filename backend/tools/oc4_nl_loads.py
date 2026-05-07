"""
自然语言 → OC4 设计域载荷 JSON（经 Qwen），供 ``partition_oc4_mesh_inp(load_case=...)`` 使用。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from backend.qwen_client import QwenClient
from backend.tools.inp_oc4_design_nondesign import summarize_mesh_for_loads


def _parse_json_object(text: str) -> dict[str, Any] | None:
    t = (text or "").strip()
    for block in re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", t, flags=re.IGNORECASE):
        b = block.strip()
        if b.startswith("{"):
            try:
                o = json.loads(b)
                return o if isinstance(o, dict) else None
            except json.JSONDecodeError:
                continue
    dec = json.JSONDecoder()
    for i, ch in enumerate(t):
        if ch == "{":
            try:
                obj, _ = dec.raw_decode(t[i:])
                return obj if isinstance(obj, dict) else None
            except json.JSONDecodeError:
                break
    return None


def _clamp_load_case(lc: dict[str, Any], *, default_band: float, default_zfix: float, default_cload: float) -> dict[str, Any]:
    out = dict(lc)
    bs = out.get("band_scale")
    if bs is None or not isinstance(bs, (int, float)):
        out["band_scale"] = float(default_band)
    else:
        out["band_scale"] = max(1.0, min(float(bs), 3.0))
    zf = out.get("z_fix_band")
    if zf is None or not isinstance(zf, (int, float)):
        out["z_fix_band"] = float(default_zfix)
    else:
        out["z_fix_band"] = max(10.0, float(zf))
    mode = str(out.get("cload_mode") or "single_top").strip().lower()
    out["cload_mode"] = mode
    if out.get("cload_dof") is not None:
        try:
            d = int(out["cload_dof"])
            out["cload_dof"] = d if d in (1, 2, 3) else 3
        except (TypeError, ValueError):
            out["cload_dof"] = 3
    for key in ("cload_mag", "cload_each"):
        if out.get(key) is not None:
            try:
                out[key] = float(out[key])
            except (TypeError, ValueError):
                out.pop(key, None)
    if out.get("cload_mag") is None and out.get("cload_each") is None:
        out["cload_mag"] = float(default_cload)
    if mode in ("top_count", "count_top", "n_top"):
        try:
            n = int(out.get("top_node_count") or out.get("count") or 1)
            out["top_node_count"] = max(1, min(n, 500))
        except (TypeError, ValueError):
            out["top_node_count"] = 1
    if mode in ("top_fraction", "fraction_top"):
        try:
            f = float(out.get("top_fraction") or out.get("fraction") or 0.01)
            out["top_fraction"] = max(0.0001, min(f, 0.5))
        except (TypeError, ValueError):
            out["top_fraction"] = 0.01
    if mode == "explicit" and isinstance(out.get("explicit_cloads"), list):
        clean: list[dict[str, Any]] = []
        for it in out["explicit_cloads"]:
            if not isinstance(it, dict):
                continue
            try:
                nid = int(it.get("node") or it.get("nid") or 0)
                d = int(it.get("dof") or 3)
                m = float(it.get("magnitude") or it.get("mag") or it.get("value") or 0.0)
            except (TypeError, ValueError):
                continue
            if d not in (1, 2, 3):
                d = 3
            clean.append({"node": nid, "dof": d, "magnitude": m})
        out["explicit_cloads"] = clean[:500]
    return out


def parse_loads_natural_language(
    mesh_inp: Path,
    user_text: str,
    *,
    band_scale: float,
    z_fix_band: float,
    cload_mag: float,
    temperature: float = 0.15,
) -> tuple[str, dict[str, Any]]:
    """
    调用 Qwen，将用户自然语言转为 ``load_case`` dict（与 ``partition_oc4_mesh_inp`` 兼容）。

    Returns:
        (reply_zh, load_case_dict)
    """
    text = (user_text or "").strip()
    if not text:
        raise ValueError("loads_natural_language 为空")

    qwen = QwenClient()
    if not qwen.api_key:
        raise RuntimeError("未配置 QWEN_API_KEY，无法解析自然语言载荷。请在环境变量或前端设置中配置。")

    ctx = summarize_mesh_for_loads(mesh_inp)
    system = (
        "你是 CalculiX / 海洋导管架静力分析载荷助手。根据「网格摘要」与用户自然语言，"
        "推断边界带 z_fix_band、柱走廊 band_scale，以及 *CLOAD 施加方式。\n"
        "你必须只输出**一个** JSON 对象，不要 Markdown 围栏，不要其它文字。\n"
        "JSON 键：\n"
        '- "reply": string，中文简要说明你的理解；\n'
        '- "load_case": object，字段如下（未提及的数值可填 null 表示沿用请求默认）：\n'
        '  - "band_scale": number|null，1~3；\n'
        '  - "z_fix_band": number|null，底面固定带高度（与 z_min 距离，同 INP 逻辑）；\n'
        '  - "cload_mode": string，必须是之一：'
        '"single_top"（最高 z 单节点力）| "top_count"（沿 z 最高的若干节点各施力）| '
        '"top_fraction"（按节点数比例取最高区域）| "explicit"（显式节点列表）；\n'
        '  - "cload_dof": 1|2|3|null，默认 3 为整体 Z；\n'
        '  - "cload_mag": number|null，single_top 时单点力（N，向下为负）；\n'
        '  - "cload_each": number|null，top_count / top_fraction 时每节点力（N）；\n'
        '  - "top_node_count": int|null，cload_mode=top_count 时节点个数（<=500）；\n'
        '  - "top_fraction": number|null，cload_mode=top_fraction 时 0~0.5；\n'
        '  - "explicit_cloads": [{"node":int,"dof":int,"magnitude":number}]|null，'
        "节点号必须来自摘要中的 top_node_ids_sample 或 load_node_max_z。\n"
        "约定：用户说「向下」「受压」指 Z 负方向；总力若分配到多节点，用 top_count + cload_each 表达。\n"
    )
    user = (
        "网格摘要（单位与网格文件一致）:\n"
        f"{json.dumps(ctx, ensure_ascii=False)}\n\n"
        f"默认参数（用户未指定时可沿用）: band_scale={band_scale}, z_fix_band={z_fix_band}, cload_mag={cload_mag}\n\n"
        f"用户载荷描述:\n{text}"
    )
    resp = qwen.chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=temperature,
    )
    content = resp["choices"][0]["message"]["content"]
    data = _parse_json_object(content) or {}
    reply = str(data.get("reply") or "已根据描述生成载荷参数。")
    lc_raw = data.get("load_case")
    if not isinstance(lc_raw, dict):
        lc_raw = {}
    lc = _clamp_load_case(lc_raw, default_band=band_scale, default_zfix=z_fix_band, default_cload=cload_mag)
    return reply, lc
