/**
 * Validation page — report UI with markdown + figure lightbox
 */
(function () {
  "use strict";

  const FIG_LABELS = {
    fig_benchmark_position: "钢耗强度 · 行业基准位置",
    fig_benchmark_capacity: "单机容量 · 行业基准位置",
    fig_benchmark_unit_cost: "单位造价 · 行业基准位置",
    fig_benchmark_construction: "施工年限 · 行业基准位置",
    fig_benchmark_fatigue: "疲劳寿命 · 行业基准位置",
    fig_score_radar: "AI Review 五维对比雷达",
    fig_fleet_metrics_bars: "AI Review 有效性 · 原始指标 vs 得分",
    fig_rule_heatmap: "规则得分分解（补充）",
    fig_capacity_intensity: "容量–钢耗强度散点",
    fig_ai_review_validity: "AI/法规 同一五维得分对照",
    fig_surrogate_pinn: "物理信息神经代理 PINN · 静力/物理残差/混合",
  };

  /** Display order — keep in sync with backend.validation.paths.FIGURE_STEMS */
  const FIG_STEMS = Object.keys(FIG_LABELS);

  const GRADE_COLORS = { A: "#10b981", B: "#2563eb", C: "#f59e0b", D: "#ef4444" };
  const BASE_URL_KEY = "beso.settings.baseUrl";

  const LOADING_STEPS = [
    { id: "parse", label: "解析几何 JSON 与优化参数" },
    { id: "steel", label: "restruction4 混合平台用钢量计算" },
    { id: "rules", label: "DNV 规则引擎 · 26+ 条合规检查" },
    { id: "ai", label: "AI Review 五维加权打分" },
    { id: "pinn", label: "物理信息神经代理（PINN）静力通道与混合" },
    { id: "charts", label: "生成 Nature 风格图表与报告" },
  ];

  const $ = (sel) => document.querySelector(sel);

  function normalizeBaseUrl(raw) {
    let s = String(raw || "").trim().replace(/\/+$/, "");
    if (!s) return "";
    if (!/^https?:\/\//i.test(s)) s = `http://${s}`;
    /** UI is mounted at /ui — API root must not include /ui or img/API URLs 404 */
    return s.replace(/\/ui$/i, "").replace(/\/$/, "");
  }

  function apiBase() {
    const custom = normalizeBaseUrl($("#valApiBase")?.value || localStorage.getItem(BASE_URL_KEY) || "");
    if (custom) return custom;
    const o = window.location.origin;
    if (o && o !== "null" && /^https?:\/\//i.test(o) && !o.startsWith("file:")) {
      return o.replace(/\/$/, "");
    }
    return "http://127.0.0.1:8000";
  }

  function persistApiBase(url) {
    const n = normalizeBaseUrl(url);
    if (!n) return;
    try {
      localStorage.setItem(BASE_URL_KEY, n);
    } catch (_) {
      /* ignore */
    }
    const inp = $("#valApiBase");
    if (inp && inp.value !== n) inp.value = n;
  }

  function friendlyFetchError(err) {
    const msg = String(err?.message || err || "未知错误");
    if (/failed to fetch|networkerror|load failed|connection refused|net::err_connection_refused/i.test(msg)) {
      return `无法连接后端 ${apiBase()}。请确认已启动 uvicorn，并通过 ${apiBase()}/ui/validation.html 打开本页。`;
    }
    return msg;
  }

  async function fetchJson(url, options) {
    let r;
    try {
      r = await fetch(url, options);
    } catch (e) {
      throw new Error(friendlyFetchError(e));
    }
    let data = {};
    try {
      data = await r.json();
    } catch (_) {
      /* non-json body */
    }
    if (!r.ok) {
      throw new Error(typeof data.detail === "string" ? data.detail : r.statusText || "请求失败");
    }
    return data;
  }

  let backendOnline = null;
  let loadingTimer = null;
  let loadingStepIdx = 0;

  async function checkBackendHealth() {
    const base = apiBase();
    persistApiBase(base);
    const banner = $("#valConnBanner");
    const btn = $("#valRunBtn");
    try {
      const r = await fetch(`${base}/health`, { method: "GET", cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      backendOnline = true;
      banner?.setAttribute("hidden", "");
      btn?.removeAttribute("disabled");
      setStatus(`后端已连接 · ${base.replace(/^https?:\/\//, "")}`, "ok");
      return true;
    } catch (_) {
      backendOnline = false;
      banner?.removeAttribute("hidden");
      btn?.setAttribute("disabled", "true");
      const text = $("#valConnBannerText");
      if (text) {
        text.innerHTML =
          `无法访问 <code>${base}/health</code>。请在项目根目录启动：<br>` +
          `<code>python -m uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000</code><br>` +
          `然后通过 <a href="${base}/ui/validation.html" target="_blank" rel="noopener">${base}/ui/validation.html</a> 打开（不要直接双击 HTML 文件）。`;
      }
      setStatus("后端未连接 — 请先启动 API 服务", "err");
      return false;
    }
  }

  function initLoadingSteps() {
    const list = $("#valLoadingSteps");
    if (!list) return;
    list.innerHTML = LOADING_STEPS.map(
      (s, i) =>
        `<li data-step="${s.id}" class="${i === 0 ? "is-active" : ""}">` +
        `<span class="valStepIcon">${i + 1}</span><span>${s.label}</span></li>`,
    ).join("");
  }

  function setLoadingProgress(stepIdx, pct, label) {
    const bar = $("#valLoadingBar");
    const stepEl = $("#valLoadingStep");
    if (bar) bar.style.width = `${Math.min(100, Math.max(0, pct))}%`;
    if (stepEl && label) stepEl.textContent = label;
    const items = $("#valLoadingSteps")?.querySelectorAll("li") || [];
    items.forEach((li, i) => {
      li.classList.remove("is-active", "is-done");
      if (i < stepIdx) li.classList.add("is-done");
      else if (i === stepIdx) li.classList.add("is-active");
      const icon = li.querySelector(".valStepIcon");
      if (icon) icon.textContent = i < stepIdx ? "✓" : String(i + 1);
    });
  }

  function showLoadingOverlay() {
    const overlay = $("#valLoadingOverlay");
    if (!overlay) return;
    loadingStepIdx = 0;
    initLoadingSteps();
    setLoadingProgress(0, 4, LOADING_STEPS[0].label);
    overlay.classList.add("is-open");
    overlay.setAttribute("aria-hidden", "false");
    overlay.setAttribute("aria-busy", "true");
    document.body.style.overflow = "hidden";

    clearInterval(loadingTimer);
    loadingTimer = setInterval(() => {
      if (loadingStepIdx >= LOADING_STEPS.length - 1) return;
      loadingStepIdx += 1;
      const pct = Math.min(92, 8 + loadingStepIdx * 18);
      setLoadingProgress(loadingStepIdx, pct, LOADING_STEPS[loadingStepIdx].label);
    }, 2200);
  }

  function hideLoadingOverlay(success) {
    clearInterval(loadingTimer);
    loadingTimer = null;
    if (success) {
      setLoadingProgress(LOADING_STEPS.length, 100, "验证完成，正在呈现结果…");
    }
    const overlay = $("#valLoadingOverlay");
    window.setTimeout(() => {
      overlay?.classList.remove("is-open");
      overlay?.setAttribute("aria-hidden", "true");
      overlay?.setAttribute("aria-busy", "false");
      if (!$("#valLightbox")?.classList.contains("is-open") && !$("#valRulesModal")?.classList.contains("is-open")) {
        document.body.style.overflow = "";
      }
    }, success ? 420 : 0);
  }

  /** Resolve artifact path to absolute URL (API or /runs static). */
  function assetUrl(path) {
    if (!path) return "";
    const p = String(path).trim();
    if (/^https?:\/\//i.test(p)) return p;
    const base = apiBase();
    if (p.startsWith("/")) return `${base}${p}`;
    return `${base}/${p.replace(/^\/+/, "")}`;
  }

  let lastData = null;
  let lastFull = null;
  let figureUrls = {};
  let figureStaticBase = "";
  let lastValidationId = "";

  function setStatus(text, kind) {
    const el = $("#valStatus");
    if (!el) return;
    el.textContent = text || "";
    el.classList.remove("valStatus--ok", "valStatus--err", "valStatus--busy");
    if (kind) el.classList.add(`valStatus--${kind}`);
  }

  function configureMarked() {
    if (typeof marked === "undefined") return;
    marked.setOptions({ gfm: true, breaks: false });
  }

  function renderMarkdown(md) {
    if (typeof marked === "undefined") return md;
    const raw = marked.parse(md || "");
    if (typeof DOMPurify !== "undefined") {
      return DOMPurify.sanitize(raw, {
        ADD_ATTR: ["target", "rel"],
        ALLOWED_TAGS: [
          "h1", "h2", "h3", "h4", "p", "ul", "ol", "li", "strong", "em", "code", "pre",
          "blockquote", "hr", "table", "thead", "tbody", "tr", "th", "td", "a", "br", "span",
        ],
      });
    }
    return raw;
  }

  function openLightbox(src, alt) {
    const lb = $("#valLightbox");
    const img = $("#valLightboxImg");
    if (!lb || !img) return;
    img.src = src;
    img.alt = alt || "";
    lb.classList.add("is-open");
    lb.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
  }

  function closeLightbox() {
    const lb = $("#valLightbox");
    if (!lb) return;
    lb.classList.remove("is-open");
    lb.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
  }

  function bindLightbox() {
    $("#valLightbox")?.addEventListener("click", (e) => {
      if (e.target.id === "valLightbox" || e.target.closest(".valLightboxClose")) closeLightbox();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeLightbox();
    });
  }

  function switchTab(tabId) {
    document.querySelectorAll(".valTab").forEach((btn) => {
      const active = btn.dataset.tab === tabId;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });
    document.querySelectorAll(".valTabPanel").forEach((panel) => {
      panel.classList.toggle("is-active", panel.id === `valPanel${tabId}`);
    });
    if (tabId === "Charts" || tabId === "Report" || tabId === "Pinn") {
      requestAnimationFrame(() => kickFigureLoads());
    }
  }

  function bindTabs() {
    document.querySelectorAll(".valTab").forEach((btn) => {
      btn.addEventListener("click", () => switchTab(btn.dataset.tab));
    });
  }

  function animateScoreRing(score, grade) {
    const ring = $("#valGradeRing");
    const letter = $("#valGradeLetter");
    if (!ring || !letter) return;
    const color = GRADE_COLORS[grade] || "#64748b";
    ring.style.setProperty("--ring-color", color);
    letter.textContent = grade || "—";
    letter.style.color = color;
    requestAnimationFrame(() => {
      ring.style.setProperty("--pct", String(Math.min(100, Math.max(0, score))));
    });
  }

  function renderCategoryCards(scores, labels, metrics) {
    const grid = $("#valCatGrid");
    if (!grid) return;
    grid.innerHTML = "";
    const defaultLabels = {
      capacity_mw: "单机兆瓦数",
      steel_per_mw: "单位兆瓦用钢量",
      unit_cost: "单位造价",
      construction_years: "施工年限",
      fatigue_life: "疲劳寿命",
    };
    const unitMap = {
      capacity_mw: "MW",
      steel_per_mw: "t/MW",
      unit_cost: "万元/MW",
      construction_years: "年",
      fatigue_life: "年",
    };
    Object.entries(scores || {}).forEach(([key, val], i) => {
      const card = document.createElement("div");
      card.className = "valCatCard";
      card.style.animationDelay = `${i * 60}ms`;
      const lab = (labels && labels[key]) || defaultLabels[key] || key;
      const mv = metrics && metrics[key];
      const unit = unitMap[key] || "";
      const meta = mv != null && Number.isFinite(Number(mv)) ? `${Number(mv).toFixed(2)} ${unit}` : "—";
      card.innerHTML = `
        <div class="valCatLabel">${lab}</div>
        <div class="valCatMeta mono">${meta}</div>
        <div class="valCatScore">${Number(val).toFixed(1)}</div>
        <div class="valCatBar"><div class="valCatBarFill" data-pct="${val}"></div></div>`;
      grid.appendChild(card);
    });
    requestAnimationFrame(() => {
      grid.querySelectorAll(".valCatBarFill").forEach((bar) => {
        bar.style.width = `${Math.min(100, Number(bar.dataset.pct) || 0)}%`;
      });
    });
  }

  function renderBenchStrip(bc) {
    const strip = $("#valBenchStrip");
    if (!strip || !bc) return;
    const conf =
      bc.estimation_confidence_score != null
        ? `${Math.round(Number(bc.estimation_confidence_score) * 100)}%`
        : "—";
    const items = [
      ["20 MW 分位", bc.percentile_vs_fleet_20mw != null ? `${bc.percentile_vs_fleet_20mw}%` : "—"],
      ["机队中位", bc.fleet_median_intensity_20mw != null ? `${bc.fleet_median_intensity_20mw} t/MW` : "—"],
      ["相对图强", bc.delta_vs_tuqiang_pct != null ? `${bc.delta_vs_tuqiang_pct > 0 ? "+" : ""}${bc.delta_vs_tuqiang_pct}%` : "—"],
      ["目标线", "300 t/MW"],
      ["钢重可信度", conf],
    ];
    if (lastData?.regulatory_overall != null) {
      items.push(["法规五维综合（对照）", `${Number(lastData.regulatory_overall).toFixed(1)} / 100`]);
    }
    strip.innerHTML = items
      .map(
        ([k, v]) =>
          `<div class="valBenchChip"><span>${k}</span> · <strong>${v}</strong></div>`
      )
      .join("");
  }

  function renderValidityTable(validity) {
    const host = $("#valValidityBlock");
    if (!host) return;
    if (!validity || !validity.ai_columns) {
      host.innerHTML = "";
      return;
    }
    const aiCols = validity.ai_columns || [];
    const regCols = validity.regulatory_columns || [];
    let html = `<p class="fieldLabel" style="margin:16px 0 8px">表1 · 同一五维指标：AI Review vs 法规标准</p>`;
    html += `<p class="valValidityNote">${validity.note || ""}</p>`;
    const vs = validity.validity_summary;
    if (vs && vs.overall_spearman != null) {
      html += `<p class="valValidityNote valValidityStats">有效性：已建成 n=${vs.n}，综合分 Spearman=${vs.overall_spearman}，平均 |AI−法规|=${vs.overall_mean_abs_diff} 分，一致占比 ${vs.high_agreement_pct}%。</p>`;
    }

    const rawHdr = ["MW", "t/MW", "kCNY/MW", "yr", "yr"];
    function renderSection(title, rows) {
      if (!rows || !rows.length) return "";
      let block = `<h4 class="valValiditySub">${title}</h4>`;
      block += `<div class="valRulesWrap valValidityScroll"><table class="valRulesTable valValidityTable"><thead><tr>`;
      block += `<th class="valStickyCol" rowspan="2">项目</th>`;
      block += `<th colspan="${aiCols.length}" class="valThGroup valThGroup--raw">原始指标</th>`;
      block += `<th colspan="${aiCols.length}" class="valThGroup valThGroup--ai">AI Review</th>`;
      block += `<th colspan="${regCols.length}" class="valThGroup valThGroup--reg">法规</th>`;
      block += `</tr><tr>`;
      rawHdr.forEach((h) => {
        block += `<th class="valThRaw">${h}</th>`;
      });
      aiCols.forEach((c) => {
        block += `<th class="valThAi">${c.label}</th>`;
      });
      regCols.forEach((c) => {
        block += `<th class="valThReg">${c.label}</th>`;
      });
      block += `</tr></thead><tbody>`;
      for (const row of rows) {
        const ai = row.ai_scores || {};
        const reg = row.regulatory_scores || {};
        const raw = row.raw_metrics || {};
        const hi = row.is_candidate ? " valRowCandidate" : "";
        block += `<tr class="${hi}"><td class="valStickyCol">${row.name}</td>`;
        aiCols.forEach((c) => {
          const v = raw[c.key];
          block += `<td class="valTdRaw">${v != null ? v : "-"}</td>`;
        });
        aiCols.forEach((c) => {
          const v = ai[c.key];
          block += `<td class="valTdAi">${v != null ? Number(v).toFixed(1) : "-"}</td>`;
        });
        regCols.forEach((c) => {
          const v = reg[c.key];
          block += `<td class="valTdReg">${v != null ? Number(v).toFixed(1) : "-"}</td>`;
        });
        block += `</tr>`;
      }
      block += `</tbody></table></div>`;
      return block;
    }

    html += renderSection("已建成机队", validity.commissioned_cohort);
    html += renderSection("规划/前瞻项目", validity.planned_cohort);
    if (validity.candidate) {
      html += renderSection("本方案（候选）", [validity.candidate]);
    }
    host.innerHTML = html;
  }

  const STATIC_LABELS_ZH = {
    steel_mass_t: "结构用钢量",
    max_uc_static: "静力最大 UC",
    compliance_static: "柔度代理",
    pitch_proxy_deg: "静倾角",
  };

  const PENALTY_LABELS_ZH = {
    mass: "质量锚定 L_mass",
    pitch: "静倾约束 L_pitch",
    mono: "单调性 L_mono",
    bound: "物理边界 L_bound",
  };

  function renderSurrogatePanel(ctx) {
    const host = $("#valSurrogateBlock");
    if (!host) return;
    ctx = ctx || {};
    const requested = !!ctx.requested;
    const enabled = !!ctx.enabled;
    const source = ctx.source || "heuristic";
    const alpha = Number(ctx.blend_alpha || 0);
    const phys = Number(ctx.physics_residual || 0);
    const staticPred = ctx.static_predictions || {};
    const penalties = ctx.physics_penalties || {};
    const assumptions = ctx.assumptions || [];

    let badgeCls = "valSurBadge--off";
    let badgeText = "未启用";
    if (requested && enabled) {
      badgeCls = source === "blend" ? "valSurBadge--blend" : "valSurBadge--on";
      badgeText = source === "blend" ? `混合 α=${alpha.toFixed(2)}` : "PINN 主导";
    } else if (requested && !enabled) {
      badgeCls = "valSurBadge--warn";
      badgeText = "已请求 · 回退 heuristic";
    }

    const flowSteps = [
      { n: "1", t: "几何 JSON", d: "设计变量与尺度" },
      { n: "2", t: "特征提取", d: "柱径/壁厚/D/t 等" },
      { n: "3", t: "MLP 推理", d: ctx.model_version || "static_v1" },
      { n: "4", t: "物理校验", d: `残差 ${phys.toFixed(3)}` },
      { n: "5", t: "混合评分", d: `α·PINN + (1−α)·H` },
    ];

    let html = `<div class="valSurHead">
      <div>
        <h3 class="valSurTitle">物理信息神经代理（PINN）</h3>
        <p class="valSurSub">Phase 1 静力通道 · 辅助造价/工期/疲劳估算 · 不替代 Zwind / CCS</p>
      </div>
      <span class="valSurBadge ${badgeCls}">${badgeText}</span>
    </div>`;

    html += `<div class="valSurFlow">${flowSteps
      .map(
        (s) =>
          `<div class="valSurFlowStep${enabled && requested ? " is-active" : ""}">
            <span class="valSurFlowNum">${s.n}</span>
            <strong>${s.t}</strong>
            <span>${s.d}</span>
          </div>`,
      )
      .join("")}</div>`;

    if (Object.keys(staticPred).length) {
      html += `<div class="valSurGrid">`;
      for (const [k, v] of Object.entries(staticPred)) {
        html += `<div class="valSurMetric">
          <span class="valSurMetricLabel">${STATIC_LABELS_ZH[k] || k}</span>
          <span class="valSurMetricVal mono">${Number(v).toFixed(3)}</span>
        </div>`;
      }
      html += `</div>`;
    } else if (requested) {
      html += `<p class="valSurNote">静力预测未生成 — 请确认已训练模型并安装 <code>requirements-surrogate.txt</code> 依赖。</p>`;
    } else {
      html += `<p class="valSurNote">勾选「启用物理代理估算」并运行验证，即可在此查看 PINN 静力预测与物理残差。</p>`;
    }

    if (Object.keys(penalties).length) {
      html += `<p class="fieldLabel" style="margin:14px 0 8px">物理损失分项（越低越好 · 阈值 0.35）</p>`;
      html += `<div class="valSurPenalties">`;
      const maxP = Math.max(0.35, ...Object.values(penalties).map(Number));
      for (const [k, v] of Object.entries(penalties)) {
        const pct = Math.min(100, (Number(v) / maxP) * 100);
        html += `<div class="valSurPenRow">
          <span>${PENALTY_LABELS_ZH[k] || k}</span>
          <div class="valSurPenBar"><div class="valSurPenFill" style="width:${pct}%"></div></div>
          <span class="mono">${Number(v).toFixed(3)}</span>
        </div>`;
      }
      html += `</div>`;
    }

    const h = ctx.heuristic_derived || {};
    const s = ctx.derived || {};
    const b = ctx.blended_derived || {};
    if (enabled && h.unit_cost_cny_per_MW != null) {
      html += `<p class="fieldLabel" style="margin:14px 0 8px">经济性混合（万元/MW · 年）</p>`;
      html += `<div class="valSurBlendTable"><table class="valRulesTable">
        <thead><tr><th>指标</th><th>Heuristic</th><th>PINN</th><th>混合结果</th></tr></thead><tbody>`;
      const rows = [
        ["单位造价", h.unit_cost_cny_per_MW, s.unit_cost_cny_per_MW, b.unit_cost_cny_per_MW],
        ["施工年限", h.construction_years, s.construction_years, b.construction_years],
        ["疲劳寿命", h.fatigue_life_years, s.fatigue_life_years, b.fatigue_life_years],
      ];
      for (const [lab, hv, sv, bv] of rows) {
        html += `<tr><td>${lab}</td><td class="mono">${hv != null ? Number(hv).toFixed(2) : "—"}</td>
          <td class="mono">${sv != null ? Number(sv).toFixed(2) : "—"}</td>
          <td class="mono"><strong>${bv != null ? Number(bv).toFixed(2) : "—"}</strong></td></tr>`;
      }
      html += `</tbody></table></div>`;
    }

    if (assumptions.length) {
      html += `<ul class="valSurAssump">${assumptions.map((a) => `<li>${a}</li>`).join("")}</ul>`;
    }

    host.innerHTML = html;
  }

  function resolveFigurePng(name, paths) {
    const list = paths || figureUrls[name] || [];
    const fromApi = list.find((p) => typeof p === "string" && p.endsWith(".png") && p.startsWith("/"));
    if (fromApi) return fromApi;
    if (figureStaticBase) return `${figureStaticBase}/${name}.png`;
    if (lastValidationId) return `/api/validation/${lastValidationId}/files/${name}.png`;
    return "";
  }

  function bindFigureImg(img, name, pngPath) {
    if (!img || !pngPath) return;
    const primary = assetUrl(pngPath);
    const fallback =
      figureStaticBase && !String(pngPath).startsWith(figureStaticBase)
        ? assetUrl(`${figureStaticBase}/${name}.png`)
        : "";
    if (img.dataset.valBound === name && img.dataset.valPrimary === primary) {
      return;
    }
    img.dataset.valBound = name;
    img.dataset.valPrimary = primary;
    img.loading = "eager";
    img.decoding = "async";
    img.onerror = () => {
      if (fallback && img.dataset.valFallback !== "1") {
        img.dataset.valFallback = "1";
        img.src = fallback;
      }
    };
    img.onclick = () => openLightbox(img.src || primary, FIG_LABELS[name] || name);
    img.src = primary;
  }

  function kickFigureLoads() {
    document.querySelectorAll(".valFigCard img, .valReportFigStrip img").forEach((img) => {
      const stem = img.closest(".valFigCard")?.dataset?.figStem || img.dataset.figStem;
      if (!stem) return;
      const pngPath = resolveFigurePng(stem, figureUrls[stem]);
      if (!pngPath) return;
      if (!img.complete || img.naturalWidth === 0) {
        bindFigureImg(img, stem, pngPath);
      }
    });
  }

  function buildFigCard(name, pngPath) {
    const card = document.createElement("article");
    card.className = "valFigCard";
    card.dataset.figStem = name;
    card.innerHTML = `
      <img alt="${FIG_LABELS[name] || name}" />
      <div class="valFigCap">
        <span>${FIG_LABELS[name] || name}</span>
        <code>${name}.png</code>
      </div>`;
    bindFigureImg(card.querySelector("img"), name, pngPath);
    return card;
  }

  function renderFigures(figs, artifactUrls, validationId) {
    figureUrls = figs || {};
    figureStaticBase = String(artifactUrls?.static_base || "").replace(/\/$/, "");
    lastValidationId = validationId || lastData?.validation_id || "";
    const grid = $("#valFigGrid");
    const preview = $("#valFigGridPreview");
    const pinnGrid = $("#valFigGridPinn");
    const strip = $("#valReportFigStrip");
    if (grid) grid.innerHTML = "";
    if (preview) preview.innerHTML = "";
    if (pinnGrid) pinnGrid.innerHTML = "";
    if (strip) strip.innerHTML = "";

    for (const name of FIG_STEMS) {
      const pngPath = resolveFigurePng(name, figureUrls[name]);
      if (!pngPath) continue;
      if (name === "fig_surrogate_pinn") {
        pinnGrid?.appendChild(buildFigCard(name, pngPath));
        continue;
      }
      grid?.appendChild(buildFigCard(name, pngPath));
      if (name === "fig_benchmark_position" && preview) {
        preview.appendChild(buildFigCard(name, pngPath));
      }
      if (name === "fig_score_radar" && preview) {
        preview.appendChild(buildFigCard(name, pngPath));
      }
      if (strip) {
        const thumb = document.createElement("img");
        thumb.dataset.figStem = name;
        thumb.alt = FIG_LABELS[name] || name;
        thumb.title = FIG_LABELS[name] || name;
        bindFigureImg(thumb, name, pngPath);
        strip.appendChild(thumb);
      }
    }
    requestAnimationFrame(() => kickFigureLoads());
  }

  function renderCalibrationNote(notes) {
    let el = $("#valCalibrationNote");
    if (!notes?.length) {
      el?.remove();
      return;
    }
    const head = $(".valReportHead");
    if (!head) return;
    if (!el) {
      el = document.createElement("p");
      el.id = "valCalibrationNote";
      el.className = "valCalibrationNote";
      head.appendChild(el);
    }
    el.textContent = notes.join(" ");
  }

  const OPERATOR_LABELS = {
    range: "区间",
    max: "上限",
    min: "下限",
    percentile_rank: "分位排名",
    delta_vs_reference: "相对基准偏差",
    target_band: "目标带",
    margin_below: "上限裕度",
    slenderness_tier: "长细比分档",
    design_stage_ratio: "设计阶段比值",
    design_stage_mass_band: "设计阶段钢量带",
  };

  function formatLimits(rule) {
    const lim = rule.limits || {};
    const ref = rule.reference || {};
    const parts = [];
    if (lim.min != null) parts.push(`min ${lim.min}`);
    if (lim.max != null) parts.push(`max ${lim.max}`);
    if (lim.target != null) parts.push(`target ${lim.target}±${lim.tolerance ?? 0}`);
    if (lim.cap != null) parts.push(`cap ${lim.cap}`);
    if (lim.reference_value != null) parts.push(`ref ${lim.reference_value}`);
    if (lim.reference_ratio != null) parts.push(`ref ratio ${lim.reference_ratio}`);
    if (lim.cap_unverified != null) parts.push(`设计阶段上限 ${lim.cap_unverified}`);
    if (ref.name) parts.push(`基准 ${ref.name}`);
    if (ref.peer_set) parts.push(`样本 ${ref.peer_set}`);
    return parts.length ? parts.join(" · ") : "—";
  }

  function formatScoring(scoring) {
    if (!scoring) return "—";
    return `优 ${scoring.excellent ?? "—"} / 良 ${scoring.good ?? "—"} / 及格 ${scoring.pass ?? "—"}`;
  }

  function renderRulesModal(data, runRules) {
    const byId = {};
    for (const r of runRules || []) byId[r.id] = r;

    const sub = $("#valRulesModalSub");
    if (sub) {
      sub.textContent = `共 ${data.rule_count || data.rules?.length || 0} 条 DNV 规则 · 综合分由 AI Review 五维加权`;
    }

    const weightsEl = $("#valRulesModalWeights");
    if (weightsEl) {
      const aiLabels = data.ai_review_labels || {};
      const aiWeights = data.ai_review_weights || {};
      const aiChips = Object.entries(aiWeights)
        .map(
          ([k, w]) =>
            `<span class="valRulesWeightChip valRulesWeightChip--ai"><strong>${aiLabels[k] || k}</strong> ${(Number(w) * 100).toFixed(0)}%</span>`
        )
        .join("");
      const labels = data.category_labels || {};
      const weights = data.category_weights || {};
      const dnvChips = Object.entries(weights)
        .map(
          ([k, w]) =>
            `<span class="valRulesWeightChip valRulesWeightChip--dnv"><strong>${labels[k] || k}</strong> ${(Number(w) * 100).toFixed(0)}% <em>明细</em></span>`
        )
        .join("");
      weightsEl.innerHTML = `<div class="valRulesWeightRow"><span class="valRulesWeightLead">AI Review</span>${aiChips || "—"}</div><div class="valRulesWeightRow"><span class="valRulesWeightLead">DNV 合规</span>${dnvChips || "—"}</div>`;
    }

    const body = $("#valRulesModalBody");
    if (!body) return;
    body.innerHTML = "";

    const grouped = {};
    for (const rule of data.rules || []) {
      const cat = rule.category_label || rule.category;
      grouped[cat] = grouped[cat] || [];
      grouped[cat].push(rule);
    }

    for (const [cat, rules] of Object.entries(grouped)) {
      const section = document.createElement("section");
      section.className = "valRulesModalSection";
      section.innerHTML = `<h3 class="valRulesModalCat">${cat}</h3>`;
      for (const rule of rules) {
        const run = byId[rule.id];
        const scoreHtml =
          run != null
            ? `<span class="valRulesRunScore">本次 ${run.score_0_100} · ${run.status}</span>`
            : "";
        const card = document.createElement("article");
        card.className = "valRulesModalCard";
        card.innerHTML = `
          <header class="valRulesModalCardHead">
            <code>${rule.id}</code>
            <span class="valRulesModalWeight">权重 ${rule.weight}</span>
            ${scoreHtml}
          </header>
          <p class="valRulesModalDesc">${rule.description_zh || "—"}</p>
          <dl class="valRulesModalMeta">
            <div><dt>指标</dt><dd>${rule.metric}${rule.unit ? ` (${rule.unit})` : ""}</dd></div>
            <div><dt>算子</dt><dd>${OPERATOR_LABELS[rule.operator] || rule.operator}</dd></div>
            <div><dt>阈值</dt><dd>${formatLimits(rule)}</dd></div>
            <div><dt>分档</dt><dd>${formatScoring(rule.scoring)}</dd></div>
            <div><dt>法规</dt><dd>${rule.regulation_ref || "—"}</dd></div>
            <div><dt>来源</dt><dd>${rule.source || "—"}</dd></div>
          </dl>`;
        section.appendChild(card);
      }
      body.appendChild(section);
    }

    if (data.scoring_config?.shell_estimate_note_zh) {
      const note = document.createElement("p");
      note.className = "valRulesModalFootnote";
      note.textContent = data.scoring_config.shell_estimate_note_zh;
      body.appendChild(note);
    }
  }

  let rulesCatalog = null;

  async function loadRulesCatalog() {
    if (rulesCatalog) return rulesCatalog;
    rulesCatalog = await fetchJson(`${apiBase()}/api/validation/rules/summary`);
    return rulesCatalog;
  }

  async function openRulesModal() {
    const modal = $("#valRulesModal");
    if (!modal) return;
    try {
      setStatus("正在加载打分规则…", "busy");
      const data = await loadRulesCatalog();
      renderRulesModal(data, lastFull?.rules);
      modal.classList.add("is-open");
      modal.setAttribute("aria-hidden", "false");
      document.body.style.overflow = "hidden";
      setStatus("", null);
    } catch (e) {
      setStatus(`规则加载失败：${friendlyFetchError(e)}`, "err");
    }
  }

  function closeRulesModal() {
    const modal = $("#valRulesModal");
    if (!modal) return;
    modal.classList.remove("is-open");
    modal.setAttribute("aria-hidden", "true");
    if (!$("#valLightbox")?.classList.contains("is-open")) {
      document.body.style.overflow = "";
    }
  }

  function bindRulesModal() {
    $("#valRulesBtn")?.addEventListener("click", openRulesModal);
    $("#valRulesBtnHead")?.addEventListener("click", openRulesModal);
    $("#valRulesModalClose")?.addEventListener("click", closeRulesModal);
    $("#valRulesModal")?.addEventListener("click", (e) => {
      if (e.target.id === "valRulesModal") closeRulesModal();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && $("#valRulesModal")?.classList.contains("is-open")) closeRulesModal();
    });
  }

  function renderRules(rules) {
    const tbody = $("#valRulesBody");
    if (!tbody) return;
    tbody.innerHTML = "";
    for (const rule of rules || []) {
      const tr = document.createElement("tr");
      const badgeCls =
        rule.status === "pass" ? "valBadge--pass" : rule.status === "fail" ? "valBadge--fail" : "valBadge--warn";
      const measured =
        rule.measured != null ? (Number(rule.measured) < 100 ? Number(rule.measured).toFixed(3) : Number(rule.measured).toFixed(1)) : "—";
      tr.innerHTML = `
        <td><code style="font-size:11px">${rule.id}</code></td>
        <td><span class="valBadge ${badgeCls}">${rule.status}</span></td>
        <td><strong>${rule.score_0_100}</strong></td>
        <td>${measured}</td>
        <td style="color:var(--muted);font-size:12px">${rule.threshold || "—"}</td>`;
      tbody.appendChild(tr);
    }
  }

  function renderReportMarkdown(md) {
    const el = $("#valReportProse");
    if (!el) return;
    el.innerHTML = renderMarkdown(md);
  }

  function showResults() {
    const shell = $("#valResults");
    shell?.classList.add("is-visible");
    shell?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function parseDownloadFilename(contentDisposition, fallback) {
    if (!contentDisposition) return fallback;
    const m = /filename\*?=(?:UTF-8''|")?([^";]+)/i.exec(contentDisposition);
    if (m && m[1]) return decodeURIComponent(m[1].replace(/"/g, "").trim());
    return fallback;
  }

  async function downloadWordReport() {
    const btn = $("#valDocxBtn");
    const vid = lastData?.validation_id;
    if (!vid) {
      setStatus("请先运行验证后再导出 Word", "err");
      return;
    }
    const urls = lastData?.artifact_urls || {};
    const exportPath = urls.export_word || `/api/validation/${vid}/export/word`;
    const url = assetUrl(exportPath);
    btn?.setAttribute("disabled", "true");
    setStatus("正在生成 Word 报告…", "busy");
    try {
      const r = await fetch(url);
      if (!r.ok) {
        let detail = r.statusText;
        try {
          const err = await r.json();
          if (typeof err.detail === "string") detail = err.detail;
        } catch (_) {
          /* non-JSON error body */
        }
        throw new Error(detail);
      }
      const blob = await r.blob();
      const fallback = `validation_report_${String(vid).slice(0, 8)}.docx`;
      const filename = parseDownloadFilename(r.headers.get("Content-Disposition"), fallback);
      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objectUrl;
      a.download = filename;
      a.rel = "noopener";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(objectUrl);
      setStatus("Word 报告已下载", "ok");
    } catch (e) {
      setStatus(`Word 导出失败：${friendlyFetchError(e)}`, "err");
    } finally {
      btn?.removeAttribute("disabled");
    }
  }

  async function downloadWordReportDetailed() {
    const btn = $("#valDocxDetailedBtn");
    const vid = lastData?.validation_id;
    if (!vid) {
      setStatus("请先运行验证后再导出详细 Word", "err");
      return;
    }
    const urls = lastData?.artifact_urls || {};
    const exportPath = urls.export_word_detailed || `/api/validation/${vid}/export/word/detailed`;
    const url = assetUrl(exportPath);
    btn?.setAttribute("disabled", "true");
    setStatus("正在生成详细 Word 报告…", "busy");
    try {
      const r = await fetch(url);
      if (!r.ok) {
        let detail = r.statusText;
        try {
          const err = await r.json();
          if (typeof err.detail === "string") detail = err.detail;
        } catch (_) {
          /* non-JSON error body */
        }
        throw new Error(detail);
      }
      const blob = await r.blob();
      const fallback = `validation_report_detailed_${String(vid).slice(0, 8)}.docx`;
      const filename = parseDownloadFilename(r.headers.get("Content-Disposition"), fallback);
      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objectUrl;
      a.download = filename;
      a.rel = "noopener";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(objectUrl);
      setStatus("详细 Word 报告已下载", "ok");
    } catch (e) {
      setStatus(`详细 Word 导出失败：${friendlyFetchError(e)}`, "err");
    } finally {
      btn?.removeAttribute("disabled");
    }
  }

  function updateDownloadLinks(urls, validationId) {
    if (urls.report_md) $("#valReportLink").href = assetUrl(urls.report_md);
    if (urls.score_json) $("#valJsonLink").href = assetUrl(urls.score_json);
    const docxBtn = $("#valDocxBtn");
    const docxDetailedBtn = $("#valDocxDetailedBtn");
    if (docxBtn && validationId) docxBtn.removeAttribute("disabled");
    if (docxDetailedBtn && validationId) docxDetailedBtn.removeAttribute("disabled");
  }

  async function runValidation() {
    const btn = $("#valRunBtn");
    const path = $("#geomPath")?.value?.trim() || "rules/optimized_geometry.json";

    if (backendOnline === false) {
      const ok = await checkBackendHealth();
      if (!ok) return;
    }

    btn?.classList.add("is-loading");
    btn?.setAttribute("disabled", "true");
    setStatus("正在提交验证任务…", "busy");
    showLoadingOverlay();

    try {
      const data = await fetchJson(`${apiBase()}/api/validation/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          geometry_path: path,
          options: {
            use_llm_rationale: $("#useLlm")?.checked || false,
            use_surrogate: $("#useSurrogate")?.checked || false,
            candidate_label: "本方案",
            design_checklist_id: (() => {
              try {
                return localStorage.getItem("beso.design_checklist_id") || null;
              } catch (_) {
                return null;
              }
            })(),
          },
        }),
      });

      setLoadingProgress(LOADING_STEPS.length - 1, 88, "加载报告与规则明细…");

      lastData = data;
      const urls = data.artifact_urls || {};

      $("#valScoreNum").textContent = Number(data.overall_score).toFixed(1);
      animateScoreRing(data.overall_score, data.grade);
      renderCategoryCards(
        data.ai_review_scores || data.category_scores,
        data.ai_review_labels,
        data.ai_review_metrics || data.metrics,
      );
      renderBenchStrip(data.benchmark_context);
      renderValidityTable(data.validity_table);
      renderSurrogatePanel(data.surrogate_context);

      updateDownloadLinks(urls, data.validation_id);
      const wordErrors = [data.word_export_error, data.word_detailed_export_error].filter(Boolean);
      if (wordErrors.length) {
        setStatus(`验证完成，Word 预生成部分失败：${wordErrors.join("；")}`, "err");
      }

      renderFigures(urls.figures, urls, data.validation_id);

      const [fullRes, rep] = await Promise.all([
        fetchJson(`${apiBase()}/api/validation/${data.validation_id}`),
        fetchJson(`${apiBase()}/api/validation/${data.validation_id}/report`),
      ]);
      lastFull = fullRes;
      renderRules(lastFull.rules);
      renderCalibrationNote(lastFull.calibration_notes || data.calibration_notes);
      renderReportMarkdown(rep.markdown);

      hideLoadingOverlay(true);
      showResults();
      const wantSur = $("#useSurrogate")?.checked;
      switchTab(wantSur ? "Pinn" : "Overview");
      if (!wordErrors.length) {
        const ctx = data.surrogate_context || {};
        const wantSur = $("#useSurrogate")?.checked;
        if (wantSur && !ctx.enabled && ctx.assumptions?.length) {
          setStatus(`验证完成（代理回退 heuristic：${ctx.assumptions[0]}）`, "err");
        } else {
          setStatus(`验证完成 · ID ${data.validation_id.slice(0, 8)}…`, "ok");
        }
      }
    } catch (e) {
      hideLoadingOverlay(false);
      setStatus(`失败：${friendlyFetchError(e)}`, "err");
      await checkBackendHealth();
    } finally {
      btn?.classList.remove("is-loading");
      if (backendOnline) btn?.removeAttribute("disabled");
    }
  }

  function init() {
    configureMarked();
    bindTabs();
    bindLightbox();
    bindRulesModal();
    const apiInp = $("#valApiBase");
    if (apiInp) {
      const stored = localStorage.getItem(BASE_URL_KEY) || "";
      apiInp.value = stored || (window.location.origin?.startsWith("http") ? window.location.origin : "http://127.0.0.1:8000");
      apiInp.addEventListener("change", () => {
        persistApiBase(apiInp.value);
        void checkBackendHealth();
      });
    }
    $("#valConnRetry")?.addEventListener("click", () => void checkBackendHealth());
    $("#valDocxBtn")?.addEventListener("click", downloadWordReport);
    $("#valDocxDetailedBtn")?.addEventListener("click", downloadWordReportDetailed);
    $("#valRunBtn")?.addEventListener("click", runValidation);
    $("#geomPath")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") runValidation();
    });
    void checkBackendHealth();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
