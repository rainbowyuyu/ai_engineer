/**
 * Validation page — report UI with markdown + figure lightbox
 */
(function () {
  "use strict";

  const FIG_LABELS = {
    fig_benchmark_position: "钢耗强度 · 行业基准位置",
    fig_score_radar: "四维得分雷达",
    fig_rule_heatmap: "规则得分分解",
    fig_capacity_intensity: "容量–钢耗强度散点",
  };

  const GRADE_COLORS = { A: "#10b981", B: "#2563eb", C: "#f59e0b", D: "#ef4444" };

  const $ = (sel) => document.querySelector(sel);
  const apiBase = () => {
    const o = window.location.origin;
    if (o && o !== "null" && o.startsWith("http")) return o.replace(/\/$/, "");
    return "http://127.0.0.1:8000";
  };

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

  function renderCategoryCards(scores) {
    const grid = $("#valCatGrid");
    if (!grid) return;
    grid.innerHTML = "";
    const labels = {
      benchmark: "基准对标",
      stability_watertight: "稳性 / 水密",
      structural_layout: "结构布局",
      detailing_fatigue_proxy: "疲劳 / 细节",
    };
    Object.entries(scores || {}).forEach(([key, val], i) => {
      const card = document.createElement("div");
      card.className = "valCatCard";
      card.style.animationDelay = `${i * 60}ms`;
      card.innerHTML = `
        <div class="valCatLabel">${labels[key] || key}</div>
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
      ["相对 AI", bc.delta_vs_ai_pct != null ? `${bc.delta_vs_ai_pct > 0 ? "+" : ""}${bc.delta_vs_ai_pct}%` : "—"],
      ["目标线", "300 t/MW"],
      ["钢重可信度", conf],
    ];
    strip.innerHTML = items
      .map(
        ([k, v]) =>
          `<div class="valBenchChip"><span>${k}</span> · <strong>${v}</strong></div>`
      )
      .join("");
  }

  function buildFigCard(name, pngUrl) {
    const card = document.createElement("article");
    card.className = "valFigCard";
    card.innerHTML = `
      <img src="${assetUrl(pngUrl)}" alt="${FIG_LABELS[name] || name}" loading="lazy" />
      <div class="valFigCap">
        <span>${FIG_LABELS[name] || name}</span>
        <code>${name}.png</code>
      </div>`;
    card.querySelector("img")?.addEventListener("click", () =>
      openLightbox(assetUrl(pngUrl), FIG_LABELS[name] || name)
    );
    return card;
  }

  function renderFigures(figs) {
    figureUrls = figs || {};
    const grid = $("#valFigGrid");
    const preview = $("#valFigGridPreview");
    const strip = $("#valReportFigStrip");
    if (grid) grid.innerHTML = "";
    if (preview) preview.innerHTML = "";
    if (strip) strip.innerHTML = "";

    for (const [name, paths] of Object.entries(figureUrls)) {
      const png = (paths || []).find((p) => p.endsWith(".png"));
      if (!png) continue;
      grid?.appendChild(buildFigCard(name, png));
      if (name === "fig_benchmark_position" && preview) {
        preview.appendChild(buildFigCard(name, png));
      }
      if (strip) {
        const thumb = document.createElement("img");
        thumb.src = assetUrl(png);
        thumb.alt = FIG_LABELS[name] || name;
        thumb.loading = "lazy";
        thumb.title = FIG_LABELS[name] || name;
        thumb.addEventListener("click", () => openLightbox(assetUrl(png), FIG_LABELS[name] || name));
        strip.appendChild(thumb);
      }
    }
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
      sub.textContent = `共 ${data.rule_count || data.rules?.length || 0} 条规则 · 四维加权综合分`;
    }

    const weightsEl = $("#valRulesModalWeights");
    if (weightsEl) {
      const labels = data.category_labels || {};
      const weights = data.category_weights || {};
      weightsEl.innerHTML = Object.entries(weights)
        .map(
          ([k, w]) =>
            `<span class="valRulesWeightChip"><strong>${labels[k] || k}</strong> ${(Number(w) * 100).toFixed(0)}%</span>`
        )
        .join("");
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
    const r = await fetch(`${apiBase()}/api/validation/rules/summary`);
    if (!r.ok) throw new Error("无法加载规则库");
    rulesCatalog = await r.json();
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
      setStatus(`规则加载失败：${e.message}`, "err");
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

  async function runValidation() {
    const btn = $("#valRunBtn");
    const path = $("#geomPath")?.value?.trim() || "rules/optimized_geometry.json";
    btn?.classList.add("is-loading");
    btn?.setAttribute("disabled", "true");
    setStatus("正在解析几何、运行规则引擎并生成报告…", "busy");

    try {
      const r = await fetch(`${apiBase()}/api/validation/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          geometry_path: path,
          options: {
            use_llm_rationale: $("#useLlm")?.checked || false,
            candidate_label: "本方案",
          },
        }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : r.statusText);

      lastData = data;
      const urls = data.artifact_urls || {};

      $("#valScoreNum").textContent = Number(data.overall_score).toFixed(1);
      animateScoreRing(data.overall_score, data.grade);
      renderCategoryCards(data.category_scores);
      renderBenchStrip(data.benchmark_context);

      if (urls.report_md) $("#valReportLink").href = assetUrl(urls.report_md);
      if (urls.score_json) $("#valJsonLink").href = assetUrl(urls.score_json);

      renderFigures(urls.figures);

      const [fullRes, repRes] = await Promise.all([
        fetch(`${apiBase()}/api/validation/${data.validation_id}`),
        fetch(`${apiBase()}/api/validation/${data.validation_id}/report`),
      ]);
      lastFull = await fullRes.json();
      const rep = await repRes.json();
      renderRules(lastFull.rules);
      renderCalibrationNote(lastFull.calibration_notes || data.calibration_notes);
      renderReportMarkdown(rep.markdown);

      showResults();
      switchTab("Overview");
      setStatus(`验证完成 · ID ${data.validation_id.slice(0, 8)}…`, "ok");
    } catch (e) {
      setStatus(`失败：${e.message}`, "err");
    } finally {
      btn?.classList.remove("is-loading");
      btn?.removeAttribute("disabled");
    }
  }

  function init() {
    configureMarked();
    bindTabs();
    bindLightbox();
    bindRulesModal();
    $("#valRunBtn")?.addEventListener("click", runValidation);
    $("#geomPath")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") runValidation();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
