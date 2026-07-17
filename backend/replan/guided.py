"""Guided step narrative for smooth replan UX: detect → think → adjust → resume."""
from __future__ import annotations

from typing import Any


def build_guided_steps(
    *,
    case_id: str | None,
    failure_kind: str | None,
    feedback_before: dict[str, Any],
    result: dict[str, Any],
    outcome: dict[str, Any],
    feedback_after: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return ordered UI steps with soft copy for progressive reveal."""
    sig = (feedback_before or {}).get("signals") or {}
    actions = (result or {}).get("actions") or []
    theta_b = (result or {}).get("theta_before") or {}
    theta_a = (result or {}).get("theta_after") or {}
    kind = failure_kind or (feedback_before or {}).get("failure_kind") or "unknown"

    detect_detail = _detect_detail(kind, sig)
    think_detail = _think_detail(kind, sig)
    adjust_lines = [f"· **{a.get('policy', '')}**：{a.get('description', '')}" for a in actions]
    theta_lines = []
    for k in sorted(set(list(theta_b.keys()) + list(theta_a.keys()))):
        if k in ("dt_s_extreme_window",):
            continue
        if theta_b.get(k) != theta_a.get(k):
            theta_lines.append(f"· `{k}`：{theta_b.get(k)} → **{theta_a.get(k)}**")

    resume = _resume_meta(kind, case_id)

    steps: list[dict[str, Any]] = [
        {
            "id": "detect",
            "title": "检测到异常",
            "subtitle": "监控求解器 / 网格诊断",
            "tone": "warn",
            "delay_ms": 1400,
            "body": detect_detail,
            "metrics": {k: sig[k] for k in sig if k != "raw_excerpt" and sig.get(k) not in (None, False, "")},
        },
        {
            "id": "diagnose",
            "title": "对照阈值 τ",
            "subtitle": f"构造反馈元组 Fₚ · ρₚ={(feedback_before or {}).get('rho_p', 1)}",
            "tone": "info",
            "delay_ms": 1300,
            "body": f"失败类型判定为 **{kind}**。将结构化日志 Lₚ 与指标 Mₚ 对照规则增强阈值，确认需要自治恢复。",
        },
        {
            "id": "think",
            "title": "思考调整策略",
            "subtitle": "从策略库选取可执行动作",
            "tone": "think",
            "delay_ms": 1600,
            "body": think_detail,
        },
        {
            "id": "replan",
            "title": "执行重规划 replan(θ, Fₚ)",
            "subtitle": f"更新任务参数 · {len(actions)} 项策略",
            "tone": "accent",
            "delay_ms": 1500,
            "body": "\n".join(adjust_lines) if adjust_lines else "应用默认恢复策略。",
            "theta_diff": theta_lines,
        },
        {
            "id": "resume",
            "title": "重新进入流程",
            "subtitle": resume["label"],
            "tone": "ok",
            "delay_ms": 1200,
            "body": outcome.get("note") or "异常已解除，流程可继续。",
            "resume": resume,
            "rho_after": (feedback_after or {}).get("rho_p", 0),
        },
    ]
    return steps


def _detect_detail(kind: str, sig: dict[str, Any]) -> str:
    if kind == "mesh":
        return (
            f"网格生成出现翻转单元或质量过低："
            f"mesh_quality_min={sig.get('mesh_quality_min', '—')}，"
            f"error_code={sig.get('mesh_error_code', '—')}。"
        )
    if kind == "solver":
        return (
            f"静力求解残差平台、未能收敛："
            f"residual_norm={sig.get('residual_norm', '—')}，"
            f"convergence_flag={sig.get('convergence_flag', '—')}。"
        )
    if kind == "zwind":
        return (
            f"时域仿真中止、纵摇超限："
            f"pitch_max={sig.get('pitch_max_deg', '—')}°，"
            f"simulation_abort={sig.get('simulation_abort', '—')}。"
        )
    return "检测到求解链路异常，正在提取诊断信号。"


def _think_detail(kind: str, sig: dict[str, Any]) -> str:
    if kind == "mesh":
        return "优先缩小特征尺寸并在柱—撑交汇区局部加密，同时适度放宽质量接受阈值，避免直接放弃拓扑结果。"
    if kind == "solver":
        return "残差平台通常与步长过大或畸变单元有关：增加最大迭代、减小载荷增量，并从较早收敛增量重启初值。"
    if kind == "zwind":
        return "极端波群段减小时间步，并小幅提高纵荡方向系泊刚度，以抑制纵摇发散并满足 CFL 稳定。"
    return "根据失败类型匹配策略库中的恢复动作。"


def _resume_meta(kind: str, case_id: str | None) -> dict[str, Any]:
    if kind == "mesh" or case_id == "case1":
        return {
            "target": "mesh",
            "label": "返回设计域 · 重新体网格",
            "cta": "继续划分网格",
            "hint": "将使用更新后的 characteristic_length_max 重新进入体网格步骤。",
        }
    if kind == "solver" or case_id == "case2":
        return {
            "target": "beso",
            "label": "返回构型优化 · 按建议参数重跑",
            "cta": "用建议参数重跑 BESO",
            "hint": "将写入的 load_increment / max_iterations / restart_increment 建议用于下一轮作业。",
        }
    if kind == "zwind" or case_id == "case3":
        return {
            "target": "zwind",
            "label": "继续尺寸 / 时域校核阶段",
            "cta": "标记已恢复并继续",
            "hint": "时域步长与系泊刚度已更新；真实 Zwind 子进程就绪后可直接重跑。",
        }
    return {
        "target": "home",
        "label": "返回主流程",
        "cta": "继续",
        "hint": "异常已处理。",
    }


def attach_guided(demo: dict[str, Any]) -> dict[str, Any]:
    out = dict(demo)
    result = out.get("result") or {}
    out["guided_steps"] = build_guided_steps(
        case_id=out.get("case_id"),
        failure_kind=(out.get("feedback_before") or {}).get("failure_kind"),
        feedback_before=out.get("feedback_before") or {},
        result=result,
        outcome=out.get("outcome") or {},
        feedback_after=out.get("feedback_after"),
    )
    out["resume"] = (out["guided_steps"][-1].get("resume") if out["guided_steps"] else None)
    return out
