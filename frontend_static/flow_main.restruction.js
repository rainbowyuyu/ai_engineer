/**
 * 尺寸时域分析 — 上传拓扑参数汇总 → 静力尺寸 / Zwind，回传指标与图。
 * 支持从同一 Job 工作区继承 parameters_summary.json，分析完成后回调进入 AI Review。
 */
export function mountRestructionAgent(ctx) {
  const { refs, layout, state, apiBase } = ctx;
  const $ = (id) => document.getElementById(id);

  const root = $("restructionMain");
  if (!root) return { open: () => {}, close: () => {} };

  const LABEL = "尺寸时域分析";
  const els = {
    back: $("restructionBackBtn"),
    toDesign: $("restructionToDesignBtn"),
    toTopo: $("restructionToTopoBtn"),
    toReview: $("restructionToReviewBtn"),
    mw: $("restructionMwInput"),
    pitch: $("restructionPitchInput"),
    platform: $("restructionPlatformSelect"),
    runStatic: $("restructionRunStaticBtn"),
    runZwind: $("restructionRunZwindBtn"),
    runBoth: $("restructionRunBothBtn"),
    status: $("restructionStatus"),
    results: $("restructionResults"),
    chat: $("restructionChat"),
    fileInput: $("restructionFileInput"),
    fileName: $("restructionFileName"),
    fileMeta: $("restructionFileMeta"),
    upload: root.querySelector(".restructionUpload"),
  };

  let sessionId = "";
  let paramsSummary = null;
  /** @type {null | ((result: any) => void | Promise<void>)} */
  let onAnalyzeDoneCb = null;
  /** @type {null | (() => void | Promise<void>)} */
  let onNavigateDesign = null;
  /** @type {null | (() => void | Promise<void>)} */
  let onNavigateTopo = null;
  /** @type {null | (() => void | Promise<void>)} */
  let onNavigateReview = null;

  function base() {
    return String(apiBase?.() || state?.apiBase || "").replace(/\/$/, "") || "";
  }

  function setStatus(text, tone = "") {
    if (!els.status) return;
    els.status.textContent = text || "";
    els.status.dataset.tone = tone || "";
  }

  function syncNavAvailability() {
    const hasJob = Boolean(String(state?.jobId || "").trim());
    const hasDd = Boolean(String(state?.oc4DesignDomainSessionId || state?.oc4DesignDomainSessionIdForResume || "").trim());
    if (els.toDesign) {
      els.toDesign.disabled = !hasDd;
      els.toDesign.title = hasDd ? "返回设计域（同一工作区）" : "当前任务尚无设计域会话";
    }
    if (els.toTopo) {
      els.toTopo.disabled = !hasJob && !hasDd;
      els.toTopo.title = hasJob || hasDd ? "返回拓扑优化 / 构型编排" : "尚无拓扑 Job，可先回主页编排";
    }
    if (els.toReview) {
      els.toReview.disabled = false;
      els.toReview.title = "进入 AI Review";
    }
  }

  function appendChat(role, text) {
    if (!els.chat) return;
    const row = document.createElement("div");
    row.className = `restructionMsg restructionMsg--${role}`;
    row.innerHTML = `<div class="restructionMsgBubble">${escapeHtml(text)}</div>`;
    els.chat.appendChild(row);
    els.chat.scrollTop = els.chat.scrollHeight;
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmt(v) {
    const n = Number(v);
    if (!Number.isFinite(n)) return "—";
    return Math.abs(n) >= 100 ? n.toFixed(1) : n.toFixed(3).replace(/\.?0+$/, "");
  }

  function renderFigures(figures) {
    const list = Array.isArray(figures) ? figures : [];
    if (!list.length) return "";
    const imgs = list
      .filter((f) => f.kind === "img" || /\.(png|jpe?g|webp)$/i.test(String(f.url || "")))
      .map(
        (p) =>
          `<a class="restructionPanelThumb" href="${escapeHtml(base() + p.url)}" target="_blank" rel="noopener">
            <img src="${escapeHtml(base() + p.url)}" alt="${escapeHtml(p.label || "")}" loading="lazy" />
            <span>${escapeHtml(p.label || "")}</span>
          </a>`,
      )
      .join("");
    const jsons = list
      .filter((f) => f.kind === "json" || String(f.url || "").endsWith(".json"))
      .map(
        (p) =>
          `<a class="restructionJsonLink" href="${escapeHtml(base() + p.url)}" target="_blank" rel="noopener">${escapeHtml(
            p.label || "JSON",
          )}</a>`,
      )
      .join("");
    return `
      ${imgs ? `<div class="restructionPanelRow">${imgs}</div>` : ""}
      ${jsons ? `<div class="restructionJsonRow">${jsons}</div>` : ""}
    `;
  }

  function renderStaticCard(data) {
    const g = data.geometry || {};
    const baseP = data.base_platform || {};
    return `
      <article class="restructionCard restructionCard--static">
        <header class="restructionCardHd">
          <span class="restructionCardKicker">静力尺寸</span>
          <h3>平台库优化 · ${escapeHtml(baseP.name || "—")}</h3>
        </header>
        <div class="restructionMetricGrid">
          <div><span>目标功率</span><strong>${escapeHtml(data.target_power_MW ?? "—")} MW</strong></div>
          <div><span>优化因子 x</span><strong>${fmt(data.extra_scale_x)}</strong></div>
          <div><span>库估钢耗</span><strong>${fmt(data.steel_intensity_t_per_MW)} t/MW</strong></div>
          <div><span>纵摇</span><strong>${fmt(data.pitch_angle_deg)}°</strong></div>
          <div><span>边柱径</span><strong>${fmt(g.offset_col_dia_m)} m</strong></div>
          <div><span>柱间距</span><strong>${fmt(g.spacing_m)} m</strong></div>
          ${
            data.shell_steel_intensity_t_per_MW != null
              ? `<div><span>壳用钢</span><strong>${fmt(data.shell_steel_intensity_t_per_MW)} t/MW</strong></div>`
              : ""
          }
        </div>
        <p class="restructionCardNote">${escapeHtml(data.process?.detail || "")}</p>
        ${renderFigures(data.figures)}
      </article>`;
  }

  function renderZwindCard(data) {
    const hl = data.highlights || {};
    const chk = data.pass_checks || {};
    return `
      <article class="restructionCard restructionCard--zwind">
        <header class="restructionCardHd">
          <span class="restructionCardKicker">时域</span>
          <h3>Zwind 包络 · ${escapeHtml(data.zwind_mode || data.mode || "paper_fig2")}</h3>
        </header>
        <div class="restructionMetricGrid">
          <div><span>塔架 1st FA</span><strong>${fmt(hl.tower_1st_fa_hz)} Hz</strong></div>
          <div><span>DLC6.1 pitch</span><strong>${fmt(hl.extreme_pitch_deg)}°</strong></div>
          <div><span>系泊峰值</span><strong>${fmt(hl.max_mooring_tension_kn)} kN</strong></div>
          <div><span>门控</span><strong>${chk.extreme_pitch_within_limit && chk.mooring_within_limit ? "通过" : "复核"}</strong></div>
        </div>
        <p class="restructionCardNote">${escapeHtml(data.process?.detail || "")}</p>
        ${renderFigures(data.figures || data.panel_urls?.map((p) => ({ ...p, kind: "img" })))}
      </article>`;
  }

  function renderAnalyzeBundle(j) {
    const parts = [];
    const st = j?.results?.static;
    const zw = j?.results?.zwind;
    if (st) parts.push(renderStaticCard(st));
    if (zw) parts.push(renderZwindCard(zw));
    if (!parts.length && Array.isArray(j?.figures) && j.figures.length) {
      parts.push(`
        <article class="restructionCard">
          <header class="restructionCardHd"><span class="restructionCardKicker">${LABEL}</span><h3>分析产物</h3></header>
          ${renderFigures(j.figures)}
        </article>`);
    }
    return parts.join("");
  }

  async function uploadFile(file) {
    if (!file) return;
    setStatus(`正在上传 ${file.name}…`, "busy");
    let localJson = null;
    try {
      localJson = JSON.parse(await file.text());
    } catch {
      localJson = null;
    }
    const fd = new FormData();
    // 重新包装，避免部分浏览器对已读 File 的二次提交问题
    const blob = new Blob([JSON.stringify(localJson || {})], { type: "application/json" });
    fd.append("file", blob, file.name || "params.json");
    if (sessionId) fd.append("session_id", sessionId);
    const resp = await fetch(`${base()}/api/restruction/upload`, { method: "POST", body: fd });
    const j = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(typeof j.detail === "string" ? j.detail : resp.statusText);
    sessionId = String(j.session_id || sessionId || "");
    state.restructionSessionId = sessionId;
    paramsSummary = localJson && typeof localJson === "object" ? localJson : null;
    if (Number.isFinite(Number(j.inferred_target_power_MW)) && els.mw) {
      els.mw.value = String(j.inferred_target_power_MW);
    }
    if (els.fileName) els.fileName.textContent = file.name;
    if (els.fileMeta) {
      els.fileMeta.textContent = [
        j.title || "参数汇总已就绪",
        j.has_geometry ? "含几何" : "无完整几何（将走平台库）",
        j.inferred_target_power_MW != null ? `${j.inferred_target_power_MW} MW` : "",
      ]
        .filter(Boolean)
        .join(" · ");
    }
    appendChat(
      "agent",
      `已载入参数汇总「${file.name}」${j.inferred_target_power_MW != null ? `，推断功率 ${j.inferred_target_power_MW} MW` : ""}。`,
    );
    setStatus("参数汇总已上传", "ok");
    return j;
  }

  /** 从同一工作区 URL 继承 parameters_summary（无需用户重新选择文件） */
  async function loadParamsFromUrl(url, displayName = "parameters_summary.json") {
    const u = String(url || "").trim();
    if (!u) return null;
    const abs = u.startsWith("http") ? u : `${base()}${u.startsWith("/") ? "" : "/"}${u}`;
    setStatus(`正在从工作区载入 ${displayName}…`, "busy");
    const resp = await fetch(abs);
    if (!resp.ok) throw new Error(`无法读取 ${displayName}（HTTP ${resp.status}）`);
    const text = await resp.text();
    const file = new File([text], displayName, { type: "application/json" });
    return uploadFile(file);
  }

  async function runAnalyze(modes) {
    const mw = Number(els.mw?.value || 20);
    const pitch = Number(els.pitch?.value || 5);
    const platform = String(els.platform?.value || "ai");
    const label = modes.includes("static") && modes.includes("zwind") ? "全套分析" : modes.includes("zwind") ? "Zwind 时域" : "静力尺寸";
    setStatus(`正在运行${label}…`, "busy");
    [els.runStatic, els.runZwind, els.runBoth].forEach((b) => b && (b.disabled = true));
    try {
      const resp = await fetch(`${base()}/api/restruction/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          modes,
          target_power_mw: mw,
          pitch_limit_deg: pitch,
          platform,
          session_id: sessionId || null,
          params_summary: paramsSummary,
        }),
      });
      const j = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail || resp.statusText));
      sessionId = String(j.session_id || sessionId || "");
      state.restructionSessionId = sessionId;
      if (els.results) els.results.insertAdjacentHTML("afterbegin", renderAnalyzeBundle(j));
      const nFig = (j.figures || []).length;
      appendChat("agent", `${LABEL}完成（${label}）：功率 ${j.target_power_MW ?? mw} MW，回传 ${nFig} 个产物。可点右上角「AI Review →」继续评审。`);
      setStatus(`${label}完成 · 可继续 AI Review`, "ok");
      state.restructionLastAnalyze = j;
      if (j.results?.static) state.restructionLastStatic = j.results.static;
      if (j.results?.zwind) state.restructionLastZwind = j.results.zwind;
      if (els.toReview) {
        els.toReview.classList.add("btnPrimary");
        els.toReview.disabled = false;
      }
      if (typeof onAnalyzeDoneCb === "function") {
        try {
          await onAnalyzeDoneCb(j);
        } catch (cbErr) {
          appendChat("agent", `后续衔接：${cbErr?.message || cbErr}`);
        }
      }
      return j;
    } catch (e) {
      setStatus(`${label}失败：${e?.message || e}`, "err");
      appendChat("agent", `${label}失败：${e?.message || e}`);
      throw e;
    } finally {
      [els.runStatic, els.runZwind, els.runBoth].forEach((b) => b && (b.disabled = false));
    }
  }

  async function open(opts = {}) {
    layout?.showStage?.("restruction");
    if (opts.mw != null && els.mw) els.mw.value = String(opts.mw);
    if (opts.pitch != null && els.pitch) els.pitch.value = String(opts.pitch);
    if (typeof opts.onAnalyzeDone === "function") onAnalyzeDoneCb = opts.onAnalyzeDone;
    else if (opts.onAnalyzeDone === null) onAnalyzeDoneCb = null;
    if (typeof opts.onNavigateDesign === "function") onNavigateDesign = opts.onNavigateDesign;
    if (typeof opts.onNavigateTopo === "function") onNavigateTopo = opts.onNavigateTopo;
    if (typeof opts.onNavigateReview === "function") onNavigateReview = opts.onNavigateReview;
    syncNavAvailability();
    if (opts.toast) appendChat("agent", String(opts.toast));
    else if (!els.chat?.childElementCount) {
      appendChat("agent", `欢迎使用${LABEL}。请上传拓扑优化参数汇总 JSON，或直接按功率运行静力 / Zwind。`);
    }
    if (opts.paramsUrl) {
      try {
        await loadParamsFromUrl(opts.paramsUrl, opts.paramsName || "parameters_summary.json");
      } catch (e) {
        appendChat("agent", `工作区继承失败：${e?.message || e}。仍可手动上传 JSON。`);
        setStatus(`继承失败：${e?.message || e}`, "err");
      }
    }
    if (opts.auto === "static") await runAnalyze(["static"]).catch(() => {});
    if (opts.auto === "zwind") await runAnalyze(["zwind"]).catch(() => {});
    if (opts.auto === "both" || opts.auto === "all") await runAnalyze(["static", "zwind"]).catch(() => {});
  }

  function close() {
    layout?.showStage?.("landing");
  }

  els.back?.addEventListener("click", () => close());
  els.toDesign?.addEventListener("click", () => {
    void (async () => {
      if (typeof onNavigateDesign === "function") await onNavigateDesign();
      else appendChat("agent", "尚未绑定设计域回跳；请先从主页进入过设计域。");
    })();
  });
  els.toTopo?.addEventListener("click", () => {
    void (async () => {
      if (typeof onNavigateTopo === "function") await onNavigateTopo();
      else appendChat("agent", "尚未绑定拓扑回跳；请从主页打开构型优化编排。");
    })();
  });
  els.toReview?.addEventListener("click", () => {
    void (async () => {
      if (typeof onNavigateReview === "function") await onNavigateReview();
      else appendChat("agent", "尚未绑定 AI Review；请返回主页后继续。");
    })();
  });
  els.runStatic?.addEventListener("click", () => void runAnalyze(["static"]));
  els.runZwind?.addEventListener("click", () => void runAnalyze(["zwind"]));
  els.runBoth?.addEventListener("click", () => void runAnalyze(["static", "zwind"]));
  els.fileInput?.addEventListener("change", () => {
    const f = els.fileInput.files?.[0];
    if (f) void uploadFile(f).catch((e) => {
      setStatus(`上传失败：${e?.message || e}`, "err");
      appendChat("agent", `上传失败：${e?.message || e}`);
    });
  });

  if (els.upload) {
    ["dragenter", "dragover"].forEach((ev) => {
      els.upload.addEventListener(ev, (e) => {
        e.preventDefault();
        els.upload.classList.add("is-drag");
      });
    });
    ["dragleave", "drop"].forEach((ev) => {
      els.upload.addEventListener(ev, (e) => {
        e.preventDefault();
        els.upload.classList.remove("is-drag");
      });
    });
    els.upload.addEventListener("drop", (e) => {
      const f = e.dataTransfer?.files?.[0];
      if (f) void uploadFile(f).catch((err) => {
        setStatus(`上传失败：${err?.message || err}`, "err");
        appendChat("agent", `上传失败：${err?.message || err}`);
      });
    });
  }

  return {
    open,
    close,
    loadParamsFromUrl,
    runStatic: () => runAnalyze(["static"]),
    runZwind: () => runAnalyze(["zwind"]),
    runBoth: () => runAnalyze(["static", "zwind"]),
    getSessionId: () => sessionId,
    syncNavAvailability,
  };
}
