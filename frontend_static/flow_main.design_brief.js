/**
 * Phase I — design checklist via landing chat (NL-triggered + clarification)
 */
const LS_CHECKLIST_ID = "beso.design_checklist_id";
const LS_CHECKLIST_PENDING = "beso.design_checklist_pending";

export function getActiveDesignChecklistId() {
  try {
    return String(localStorage.getItem(LS_CHECKLIST_ID) || "").trim();
  } catch {
    return "";
  }
}

export function setActiveDesignChecklistId(id) {
  const v = String(id || "").trim();
  try {
    if (v) localStorage.setItem(LS_CHECKLIST_ID, v);
    else localStorage.removeItem(LS_CHECKLIST_ID);
  } catch {
    /* ignore */
  }
}

export function getChecklistPendingState() {
  try {
    const raw = localStorage.getItem(LS_CHECKLIST_PENDING);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function setChecklistPendingState(state) {
  try {
    if (state && state.checklistId) {
      localStorage.setItem(LS_CHECKLIST_PENDING, JSON.stringify(state));
    } else {
      localStorage.removeItem(LS_CHECKLIST_PENDING);
    }
  } catch {
    /* ignore */
  }
}

export function clearChecklistPendingState() {
  setChecklistPendingState(null);
}

export function detectDesignChecklistIntent(text) {
  const raw = String(text || "").trim();
  if (!raw) return false;
  if (/设计清单|生成.{0,6}清单|形式化.{0,8}需求|整理.{0,6}(设计)?需求|输出.{0,4}清单|Phase\s*I/i.test(raw)) {
    return true;
  }
  if (/^(开始|运行|进入|打开).{0,16}(编排|优化|设计域|BESO)/i.test(raw) && raw.length < 48) {
    return false;
  }
  const hasCapacity = /\d+\s*(?:MW|兆瓦)/i.test(raw);
  const hasSiteOrTarget = /Hs|Tp|场址|钢耗|t\s*\/\s*MW|入级|AIP|CCS|稳性|水密|半潜|漂浮/i.test(raw);
  return hasCapacity && hasSiteOrTarget && raw.length >= 18;
}

export function isChecklistClarificationReply(text, pendingState) {
  if (!pendingState?.checklistId || pendingState.finalized) return false;
  const raw = String(text || "").trim();
  if (!raw) return false;
  if (detectDesignChecklistIntent(raw) && /设计清单|形式化|Phase\s*I/i.test(raw)) return false;
  if (/^(开始|运行|进入|打开).{0,16}(编排|优化|设计域|BESO|构型)/i.test(raw) && raw.length < 48) {
    return false;
  }
  // 澄清作答：默认/跳过/数值/场址相关关键词，或短回复
  if (/默认|不知道|不详|跳过|暂未|水深|风速|静倾|疲劳|造价|吃水|寿命|Hs|Tp|\d/i.test(raw)) {
    return true;
  }
  return raw.length <= 160;
}

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fmt(v, unit = "") {
  if (v == null || v === "") return "—";
  return unit ? `${v} ${unit}` : String(v);
}

function chip(label, tone = "") {
  return `<span class="dcChip dcChip--${tone || "muted"}">${esc(label)}</span>`;
}

export function buildChecklistCardPayload(data, baseUrl) {
  const cl = data.checklist || {};
  const proj = cl.project || {};
  const site = cl.site || {};
  const reg = cl.regulatory || {};
  const perf = cl.performance_targets || {};
  const struct = cl.structural_assumptions || {};
  const job = cl.job_descriptor || {};
  const theta = job.theta || {};
  const beso = theta.beso || {};
  const oc4 = theta.oc4_loads || {};
  const retry = job.retry_policy || {};
  const exc = perf.excitation_bands_hz || {};
  const oneP = exc.one_p || {};
  const threeP = exc.three_p || {};
  const env = site.sea_state_envelope || {};
  const id = data.checklist_id || cl.meta?.checklist_id || "";
  const parserLabel = data.parser === "qwen" ? "Qwen 解析" : "规则回退";
  const base = String(baseUrl || "").replace(/\/+$/, "");
  const mdUrl = id ? `${base}/api/design-requirements/${encodeURIComponent(id)}/export/markdown` : "";
  const pending = data.pending_clarifications || [];
  const complete = data.clarification_complete !== false && pending.length === 0;

  const sections = [
    {
      title: "项目目标",
      rows: [
        ["容量", fmt(proj.target_capacity_mw, "MW")],
        ["型式", proj.platform_type || "—"],
        ["业主意图", (proj.owner_intent_zh || "—").slice(0, 120)],
      ],
    },
    {
      title: "场址海况",
      rows: [
        ["场址", site.location_name || "—"],
        ["Hs / Tp", `${site.Hs_m ?? "—"} m / ${site.Tp_s ?? "—"} s`],
        ["水深", fmt(site.water_depth_m, "m")],
        ["参考风速", fmt(site.wind_ref_m_s, "m/s")],
        ["海况包络", env.reference || "—"],
      ],
    },
    {
      title: "入级规范",
      rows: [
        ["认证路径", reg.certification_path || "—"],
        ["适用规范", (reg.standards || []).join(" · ") || "—"],
        ["关联条款", (reg.clause_ids || []).slice(0, 5).join(", ") || "—"],
        ["Reviewer", reg.reviewer_threshold ? `S≥${reg.reviewer_threshold.S_min}` : "—"],
      ],
    },
    {
      title: "性能指标",
      rows: [
        ["钢耗目标", fmt(perf.steel_intensity_t_per_MW, "t/MW")],
        ["单位造价", perf.unit_cost_cny_per_MW != null ? `${perf.unit_cost_cny_per_MW} 万元/MW` : "—"],
        ["静倾限值", fmt(perf.pitch_limit_deg, "°")],
        ["疲劳寿命", fmt(perf.fatigue_design_life_years, "年")],
        ["1P / 3P", `${oneP.hz_min ?? "—"}–${oneP.hz_max ?? "—"} / ${threeP.hz_min ?? "—"}–${threeP.hz_max ?? "—"} Hz`],
      ],
    },
    {
      title: "结构假设",
      rows: [
        ["吃水", fmt(struct.draft_m, "m")],
        ["壁厚", fmt(struct.wall_thickness_m, "m")],
        ["缩放因子", struct.scale_factor ?? "—"],
      ],
    },
    {
      title: "任务参数 J",
      rows: [
        ["相位", job.phase || "I"],
        ["BESO", `mg=${beso.mass_goal_ratio ?? "—"}, r=${beso.filter_radius ?? "—"}, base=${beso.optimization_base ?? "—"}`],
        ["OC4 载荷", `band=${oc4.band_scale ?? "—"}, z=${oc4.z_fix_band ?? "—"}`],
        ["尺寸优化", theta.sizing?.optimizer || "—"],
        ["重试策略", `×${retry.max_retries ?? "—"} · mesh=${retry.on_mesh_fail ?? "—"}`],
      ],
    },
  ];

  let html = `<div class="dcCard" data-checklist-id="${esc(id)}">`;
  html += `<div class="dcCardHd"><div class="dcCardTitle">Phase I 设计清单</div>`;
  html += `<div class="dcCardChips">${chip(parserLabel, data.parser === "qwen" ? "ok" : "warn")}${chip(`ID ${id.slice(0, 8)}…`, "id")}</div></div>`;

  if (data.parser === "rule_fallback") {
    html += `<div class="dcBanner dcBanner--warn">未配置 Qwen 时使用规则回退；已从描述抽取关键数值，其余字段请补充或确认默认。</div>`;
  }

  html += `<div class="dcGrid">`;
  for (const sec of sections) {
    html += `<div class="dcSec"><div class="dcSecTitle">${esc(sec.title)}</div><dl class="dcKv">`;
    for (const [k, v] of sec.rows) {
      html += `<div class="dcKvRow"><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`;
    }
    html += `</dl></div>`;
  }
  html += `</div>`;

  if (pending.length) {
    html += `<div class="dcClarify"><div class="dcClarifyTitle">待您确认的参数</div>`;
    html += `<p class="dcClarifyHint">以下参数未在您的描述中出现。请直接回复数值；若暂不确定，可回复「用默认」或「水深不知道，其余默认」。</p><ol class="dcClarifyList">`;
    for (const p of pending.slice(0, 8)) {
      html += `<li><strong>${esc(p.question)}</strong><span class="dcClarifyDef">建议默认：${esc(p.default_display || p.default_value)}</span></li>`;
    }
    html += `</ol></div>`;
  } else if ((cl.assumptions || []).length) {
    html += `<div class="dcAssumptions"><div class="dcSecTitle">已采用的默认项</div><ul>`;
    for (const a of (cl.assumptions || []).slice(0, 6)) {
      html += `<li>${esc(a)}</li>`;
    }
    html += `</ul></div>`;
  }

  html += `<div class="dcCardFt">`;
  if (complete && id) {
    html += `<span class="dcStatus dcStatus--ok">已锁定并带入当前任务 · 后续 BESO / 设计域 / 验证将引用此清单</span>`;
  } else if (id) {
    html += `<span class="dcStatus dcStatus--pending">清单草稿已保存 · 请回复上方待确认项后自动锁定</span>`;
  }
  if (mdUrl) {
    html += `<a class="dcDlBtn" href="${esc(mdUrl)}" download target="_blank" rel="noopener noreferrer">`;
    html += `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 3v12M7 11l5 5 5-5M5 21h14"/></svg>`;
    html += `下载完整 Markdown 报告</a>`;
  }
  html += `</div></div>`;

  return {
    html,
    plainSummary: `Phase I 设计清单（${parserLabel}）· ${proj.target_capacity_mw ?? "—"} MW · Hs=${site.Hs_m ?? "—"} m`,
    checklistId: id,
    pending,
    complete,
    mdUrl,
  };
}

export async function parseDesignChecklistFromChat(text, baseUrl) {
  const base = String(baseUrl || "").replace(/\/+$/, "");
  const r = await fetch(`${base}/api/design-requirements/parse`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: String(text || "").trim(), persist: true }),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : r.statusText || "设计清单解析失败");
  }
  return data;
}

export async function clarifyDesignChecklist(checklistId, reply, baseUrl) {
  const base = String(baseUrl || "").replace(/\/+$/, "");
  const r = await fetch(`${base}/api/design-requirements/${encodeURIComponent(checklistId)}/clarify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reply: String(reply || "").trim() }),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : r.statusText || "澄清失败");
  }
  return data;
}

/** Detect "演示重规划 Case1/2/3" style intents */
export function detectReplanDemoIntent(text) {
  const raw = String(text || "").trim();
  if (!raw) return null;
  if (!/重规划|replan|Table\s*S\.?1|失败驱动|自治恢复/i.test(raw)) return null;
  if (/case\s*1|案例\s*1|网格|gmsh|mesh/i.test(raw)) return "case1";
  if (/case\s*2|案例\s*2|残差|calculix|收敛|solver/i.test(raw)) return "case2";
  if (/case\s*3|案例\s*3|zwind|pitch|倾角|海况/i.test(raw)) return "case3";
  if (/三案例|全部案例|所有案例|case\s*1\s*[\/、,]\s*2/i.test(raw)) return "all";
  return "case1";
}

export async function runReplanCaseDemo(caseId, baseUrl) {
  const base = String(baseUrl || "").replace(/\/+$/, "");
  const r = await fetch(`${base}/api/replan/cases/${encodeURIComponent(caseId)}/demo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : r.statusText || "重规划演示失败");
  }
  return data;
}

export function buildReplanCardPayload(data, baseUrl) {
  const base = String(baseUrl || "").replace(/\/+$/, "");
  const title = data.title || data.case_id || "重规划";
  const before = data.feedback_before || {};
  const after = data.feedback_after || {};
  const result = data.result || {};
  const actions = result.actions || [];
  const thetaB = result.theta_before || {};
  const thetaA = result.theta_after || {};
  const outcome = data.outcome || {};
  const eid = result.event?.event_id || "";
  const eventUrl = eid ? `${base}/api/replan/events/${encodeURIComponent(eid)}` : "";

  const sig = before.signals || {};
  const sigLines = [];
  if (sig.mesh_quality_min != null) sigLines.push(`mesh_quality_min=${sig.mesh_quality_min}`);
  if (sig.mesh_error_code != null) sigLines.push(`mesh_error_code=${sig.mesh_error_code}`);
  if (sig.residual_norm != null) sigLines.push(`residual_norm=${sig.residual_norm}`);
  if (sig.convergence_flag != null) sigLines.push(`convergence_flag=${sig.convergence_flag}`);
  if (sig.pitch_max_deg != null) sigLines.push(`pitch_max=${sig.pitch_max_deg}°`);
  if (sig.simulation_abort != null) sigLines.push(`simulation_abort=${sig.simulation_abort}`);

  const keys = Array.from(new Set([...Object.keys(thetaB), ...Object.keys(thetaA)])).filter(
    (k) => !["dt_s_extreme_window"].includes(k),
  );

  let html = `<div class="dcCard dcCard--replan" data-case-id="${esc(data.case_id || "")}">`;
  html += `<div class="dcCardHd"><div class="dcCardTitle">${esc(title)}</div>`;
  html += `<div class="dcCardChips">${chip(data.ok ? "演示成功" : "未通过", data.ok ? "ok" : "warn")}`;
  html += `${chip(`ρ ${before.rho_p ?? "—"}→${after.rho_p ?? "—"}`, "id")}</div></div>`;

  html += `<div class="dcGrid">`;
  html += `<div class="dcSec"><div class="dcSecTitle">诊断信号 Fₚ</div><dl class="dcKv">`;
  html += `<div class="dcKvRow"><dt>失败类型</dt><dd>${esc(before.failure_kind || "—")}</dd></div>`;
  html += `<div class="dcKvRow"><dt>信号</dt><dd>${esc(sigLines.join(" · ") || "—")}</dd></div>`;
  html += `</dl></div>`;

  html += `<div class="dcSec"><div class="dcSecTitle">重规划策略</div><ul class="dcAssumptions" style="margin:0;padding-left:1.1em;border:none;background:transparent">`;
  for (const a of actions) {
    html += `<li><strong>${esc(a.policy)}</strong> — ${esc(a.description || "")}</li>`;
  }
  if (!actions.length) html += `<li>（无策略）</li>`;
  html += `</ul></div>`;

  html += `<div class="dcSec"><div class="dcSecTitle">θ 前后对比</div><dl class="dcKv">`;
  for (const k of keys.slice(0, 8)) {
    const vb = thetaB[k];
    const va = thetaA[k];
    if (JSON.stringify(vb) === JSON.stringify(va)) continue;
    html += `<div class="dcKvRow"><dt>${esc(k)}</dt><dd>${esc(vb)} → <strong>${esc(va)}</strong></dd></div>`;
  }
  html += `</dl></div>`;

  html += `<div class="dcSec"><div class="dcSecTitle">结果</div><p style="margin:0;font-size:12.5px">${esc(outcome.note || "")}</p></div>`;
  html += `</div>`;

  html += `<div class="dcCardFt">`;
  html += `<span class="dcStatus ${data.ok ? "dcStatus--ok" : "dcStatus--pending"}">${
    data.ok ? "失败驱动重规划闭环完成（Table S.1）" : "演示未通过验收断言"
  }</span>`;
  if (eventUrl) {
    html += `<a class="dcDlBtn" href="${esc(eventUrl)}" target="_blank" rel="noopener noreferrer">查看审计 JSON</a>`;
  }
  html += `</div></div>`;

  return {
    html,
    plainSummary: `${title} · ${data.ok ? "OK" : "FAIL"} · ${before.failure_kind || ""}`,
    caseId: data.case_id,
  };
}
