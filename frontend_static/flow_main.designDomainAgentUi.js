/**
 * 设计域智能体：NDJSON 流 → Cursor 式单栏时间线（思考耗时、工具卡片、可点统计、Plan-Build 流等）。
 */
import { markdownLiteToHtml } from "./flow_markdownLite.js";

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function scrollAgentStreamToEnd(traceEl) {
  if (!traceEl) return;
  traceEl.scrollTop = traceEl.scrollHeight;
  const sc = traceEl.closest?.(".ddAgentUnifiedScroll");
  if (sc) sc.scrollTop = sc.scrollHeight;
}

/**
 * @param {object} opts
 * @param {HTMLElement | null | undefined} opts.traceEl
 * @param {HTMLTextAreaElement | null | undefined} opts.inputEl
 * @param {HTMLButtonElement | null | undefined} opts.sendBtn
 * @param {HTMLButtonElement | null | undefined} opts.stopBtn
 * @param {HTMLElement | null | undefined} [opts.statToolsEl]
 * @param {HTMLElement | null | undefined} [opts.statFilesEl]
 * @param {HTMLElement | null | undefined} [opts.statPathsEl]
 * @param {HTMLElement | null | undefined} [opts.statCharsEl]
 * @param {(chunk: string) => void} [opts.onPlanMdDelta]
 * @param {(path: string) => void} [opts.onPlanFileReady]
 * @param {(ok: boolean, detail?: { historyPath?: string; phase?: string }) => void} [opts.onStreamPhaseDone]
 * @param {(ev: { index: number; topic: string; label: string }) => void} [opts.onPlanRailStep]
 * @param {(ev: { index: number; phase: string; ok?: boolean; title?: string; tool?: string }) => void} [opts.onPlanBuildProgress]
 * @param {(rel: string) => void} [opts.onAgentProduce]
 * @param {HTMLElement | null | undefined} [opts.sessionStatsEl]
 * @param {HTMLElement | null | undefined} [opts.contextHintEl]
 * @param {HTMLElement | null | undefined} [opts.statDetailEl]
 * @param {HTMLElement | null | undefined} [opts.statDetailTitleEl]
 * @param {HTMLElement | null | undefined} [opts.statDetailBodyEl]
 * @param {(steps: object[], rationale?: string) => void} [opts.onDynamicPlan]
 * @param {() => { cut_center_column?: boolean; include_source_geometry?: boolean; mesh_preset?: string; mesh_user_note?: string | null; mesh_characteristic_length_max?: number }} [opts.getPlanBuildPayload]
 * @param {() => string} opts.getSessionId
 * @param {() => string} [opts.getTaskId]
 * @param {() => string} opts.normalizedBaseUrl
 * @param {(rel: string) => void} [opts.onOpenFile]
 * @param {() => void} [opts.onRefreshTree]
 * @param {(guided: object) => void} [opts.onReplanGuided]
 * @param {(role: string, text: string) => void} [opts.appendFlowLog]
 * @param {(role: string, text: string, oc4ChatIdx?: number) => void} [opts.renderDesignDomainChatRow]
 * @param {() => { ts?: number; role: string; text: string }[]} [opts.getChatActivityLog]
 * @param {HTMLSelectElement | null} [opts.modelQuickEl]
 */
export function mountDesignDomainAgentUi(opts) {
  const {
    traceEl,
    inputEl,
    sendBtn,
    stopBtn,
    statToolsEl,
    statFilesEl,
    statPathsEl,
    statCharsEl,
    sessionStatsEl,
    contextHintEl,
    statDetailEl,
    statDetailTitleEl,
    statDetailBodyEl,
    onPlanMdDelta,
    onPlanFileReady,
    onStreamPhaseDone,
    onPlanRailStep,
    onPlanBuildProgress,
    onAgentProduce,
    onDynamicPlan,
    getPlanBuildPayload,
    getSessionId,
    getTaskId,
    normalizedBaseUrl,
    onOpenFile,
    onRefreshTree,
    onReplanGuided,
    appendFlowLog,
    renderDesignDomainChatRow,
    getChatActivityLog,
    modelQuickEl,
  } = opts;

  /** @type {AbortController | null} */
  let abortCtrl = null;

  const LS_AGENT_UI = "beso.dd.agentUi.v1";
  let lastHydratedStorageKey = "";
  /** @type {ReturnType<typeof setTimeout> | null} */
  let persistTimer = null;

  /** 设计域智能体主时间线（与任务 oc4_activity 合并后重绘），按任务写入 localStorage */
  /** @type {object[]} */
  let timeline = [];
  let timelineOrd = 0;
  let suppressPersist = false;
  let replayingTrace = false;

  const TIMELINE_CAP = 220;
  const ASSISTANT_PERSIST_MAX = 48000;
  const SNIPPET_PERSIST_MAX = 12000;

  let toolCount = 0;
  const filePaths = new Set();
  let pathsListedTotal = 0;
  let readCharsTotal = 0;
  let runContextApproxChars = 0;
  /** 轮盘「满环」对应的粗估上下文字数，仅用于视觉比例 */
  const CONTEXT_RING_MAX_CHARS = 180000;
  /** @type {{ name: string; args: object; summary?: string; ok?: boolean }[]} */
  const toolCallLog = [];
  /** @type {{ path: string; action: string; ts: number; seq: number; detail: string }[]} */
  const fileEventLog = [];
  /** @type {{ path: string; chars: number }[]} */
  const readEventLog = [];
  let lastListingPreview = "";
  let fileEventSeq = 0;
  /** @type {"tools" | "files" | "paths" | "chars" | null} */
  let openDrawerKind = null;

  const statDrawerKickerEl = statDetailEl?.querySelector("#ddAgentStatDrawerKicker");

  const FILE_ACTION_ZH = {
    created: "新增文件",
    updated: "覆盖 / 更新已有文件",
    wrote: "写入文件",
    deleted: "删除文件",
    removed: "移除文件",
    touched: "触及文件",
  };

  function storageKeyTask(tid) {
    const t = String(tid || "").trim();
    return t ? `${LS_AGENT_UI}.t.${t}` : "";
  }

  function storageKeySession(sid) {
    const s = String(sid || "").trim();
    return s ? `${LS_AGENT_UI}.s.${s}` : "";
  }

  /** 旧版：会话 id 直接接在前缀后 */
  function storageKeyLegacySession(sid) {
    const s = String(sid || "").trim();
    return s ? `${LS_AGENT_UI}.${s}` : "";
  }

  function storageKey() {
    const tid = String(getTaskId?.() || "").trim();
    if (tid) return storageKeyTask(tid);
    const sid = String(getSessionId?.() || "").trim();
    return sid ? storageKeySession(sid) : "";
  }

  function persistPayload() {
    return {
      toolCount,
      filePaths: [...filePaths],
      pathsListedTotal,
      readCharsTotal,
      runContextApproxChars,
      toolCallLog,
      fileEventLog,
      readEventLog,
      lastListingPreview,
      fileEventSeq,
      timeline,
      composerDraft: String(inputEl?.value || ""),
      modelQuick: String(modelQuickEl?.value || "").trim(),
    };
  }

  function schedulePersist() {
    if (suppressPersist) return;
    const k = storageKey();
    if (!k) return;
    if (persistTimer) clearTimeout(persistTimer);
    persistTimer = setTimeout(() => {
      persistTimer = null;
      try {
        localStorage.setItem(k, JSON.stringify(persistPayload()));
      } catch {
        /* ignore */
      }
    }, 400);
  }

  function flushPersist() {
    if (persistTimer) {
      clearTimeout(persistTimer);
      persistTimer = null;
    }
    const k = storageKey();
    if (!k) return;
    try {
      localStorage.setItem(k, JSON.stringify(persistPayload()));
    } catch {
      /* ignore */
    }
  }

  function timelinePush(ev) {
    if (replayingTrace) return;
    timelineOrd += 1;
    timeline.push({ ts: Date.now(), ord: timelineOrd, ...ev });
    while (timeline.length > TIMELINE_CAP) timeline.shift();
    schedulePersist();
  }

  function deriveTimelineFromLegacy() {
    const out = [];
    let tick = 0;
    for (const t of toolCallLog) {
      tick += 1;
      out.push({ kind: "tool", ts: tick, ord: tick, name: String(t.name || ""), args: t.args && typeof t.args === "object" ? t.args : {} });
      tick += 1;
      if (t.ok !== undefined || (t.summary && String(t.summary).trim())) {
        out.push({
          kind: "tool_result",
          ts: tick,
          ord: tick,
          ok: t.ok !== false,
          name: String(t.name || ""),
          summary: String(t.summary || ""),
          paths_listed: undefined,
          read_chars: undefined,
          read_path: "",
          listing_preview: "",
          content_snippet: "",
        });
      }
    }
    for (const f of fileEventLog) {
      tick += 1;
      out.push({
        kind: "file",
        ts: tick,
        ord: tick,
        path: String(f.path || ""),
        action: String(f.action || ""),
      });
    }
    return out;
  }

  function renderToolDomOnly(name, args) {
    if (!traceEl) return;
    const row = document.createElement("div");
    row.className = "ddAgentLine ddAgentLine--tool";
    const card = document.createElement("div");
    card.className = "ddAgentToolCard";
    const head = document.createElement("div");
    head.className = "ddAgentToolCardHd";
    const ic = document.createElement("span");
    ic.className = "ddAgentToolCardIcon";
    ic.setAttribute("aria-hidden", "true");
    const tit = document.createElement("div");
    tit.className = "ddAgentToolCardTit";
    tit.innerHTML = `<span class="ddAgentToolCardK">调用工具</span><span class="ddAgentToolCardName mono">${esc(name)}</span>`;
    head.appendChild(ic);
    head.appendChild(tit);
    card.appendChild(head);
    if (args && Object.keys(args).length) {
      const pre = document.createElement("pre");
      pre.className = "ddAgentToolCardArgs mono";
      try {
        pre.textContent = JSON.stringify(args, null, 2).slice(0, 2400);
      } catch {
        pre.textContent = "";
      }
      card.appendChild(pre);
    }
    row.appendChild(card);
    traceEl.appendChild(row);
  }

  function renderToolResultDomOnly(ev) {
    if (!traceEl) return;
    const ok = Boolean(ev.ok);
    const row = document.createElement("div");
    row.className = `ddAgentLine ddAgentLine--toolres ddAgentToolResRow--${ok ? "ok" : "err"}`;
    const card = document.createElement("div");
    card.className = `ddAgentToolResCard ddAgentToolResCard--${ok ? "ok" : "err"}`;
    const main = document.createElement("div");
    main.className = "ddAgentToolResMain ddAgentToolResMain--md mdLiteRoot";
    main.innerHTML = markdownLiteToHtml(String(ev.summary || ""));
    card.appendChild(main);
    const metaBits = [];
    if (typeof ev.paths_listed === "number" && ev.paths_listed > 0) {
      metaBits.push(`列举 ${ev.paths_listed} 条路径`);
    }
    if (typeof ev.read_chars === "number" && ev.read_chars > 0) {
      const rp = String(ev.read_path || "").trim();
      metaBits.push(`已读 ${rp || "文件"} · ${ev.read_chars.toLocaleString()} 字`);
    }
    if (metaBits.length) {
      const sub = document.createElement("div");
      sub.className = "ddAgentToolResMeta";
      sub.textContent = metaBits.join(" · ");
      card.appendChild(sub);
    }
    row.appendChild(card);
    traceEl.appendChild(row);
  }

  function renderFileDomOnly(path, action) {
    if (!traceEl) return;
    const row = document.createElement("div");
    row.className = "ddAgentLine ddAgentLine--file";
    const card = document.createElement("div");
    card.className = "ddAgentFileCard";
    const badge = document.createElement("span");
    badge.className = "ddAgentFileBadge";
    badge.textContent = action === "updated" ? "+1" : "+";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ddAgentFileLink mono";
    btn.textContent = path;
    btn.dataset.relPath = path;
    const cap = document.createElement("span");
    cap.className = "ddAgentFileCap";
    cap.textContent = action === "updated" ? "已更新产物" : "文件";
    card.appendChild(badge);
    card.appendChild(btn);
    card.appendChild(cap);
    row.appendChild(card);
    traceEl.appendChild(row);
  }

  function renderAssistantDomOnly(text) {
    if (!traceEl) return;
    const s = String(text || "");
    const row = document.createElement("div");
    row.className = "ddAgentLine ddAgentLine--assistant";
    const inner = document.createElement("div");
    inner.className = "ddAgentReply mdBox ddAgentReply--md mdLiteRoot";
    row.appendChild(inner);
    traceEl.appendChild(row);
    inner.innerHTML = markdownLiteToHtml(s);
  }

  function renderSnippetDomOnly(path, snippet) {
    if (!traceEl || !String(snippet || "").trim()) return;
    const row = document.createElement("div");
    row.className = "ddAgentLine ddAgentLine--snippet";
    const card = document.createElement("div");
    card.className = "ddAgentSnippetCard";
    const hd = document.createElement("div");
    hd.className = "ddAgentSnippetHd";
    hd.textContent = `read_file 预览 · ${path}`;
    const pre = document.createElement("pre");
    pre.className = "ddAgentSnippetPre mono";
    const lines = String(snippet).split("\n");
    for (let i = 0; i < lines.length; i++) {
      const ln = document.createElement("div");
      ln.className = "ddAgentSnippetLine ddAgentSnippetLine--ctx";
      const n = document.createElement("span");
      n.className = "ddAgentSnippetNo";
      n.textContent = String(i + 1);
      const tx = document.createElement("span");
      tx.textContent = lines[i];
      ln.appendChild(n);
      ln.appendChild(tx);
      pre.appendChild(ln);
    }
    card.appendChild(hd);
    card.appendChild(pre);
    row.appendChild(card);
    traceEl.appendChild(row);
  }

  function renderThinkingDomOnly(text) {
    if (!traceEl) return;
    const row = document.createElement("div");
    row.className = "ddAgentLine ddAgentLine--thinking ddAgentLine--thinkingDone";
    const det = document.createElement("details");
    det.className = "ddAgentThinking ddAgentThinking--done";
    det.open = false;
    const sum = document.createElement("summary");
    sum.className = "ddAgentThinkingSum";
    sum.innerHTML =
      '<span class="ddAgentThoughtLabel">思考过程</span><span class="ddAgentThoughtChev" aria-hidden="true"></span>';
    const pre = document.createElement("pre");
    pre.className = "ddAgentThinkingPre mono";
    pre.textContent = String(text || "");
    det.appendChild(sum);
    det.appendChild(pre);
    row.appendChild(det);
    traceEl.appendChild(row);
  }

  function replayOneTimelineEvt(e) {
    const k = String(e?.kind || "");
    if (k === "activity") {
      const text = String(e.text || "");
      const kind = String(e.actKind || "misc");
      const row = document.createElement("div");
      row.className = `ddAgentLine ddAgentLine--activity ddAgentLine--activity-${kind || "misc"}`;
      const inner = document.createElement("div");
      inner.className = "ddAgentActivity";
      inner.textContent = text;
      row.appendChild(inner);
      traceEl?.appendChild(row);
      return;
    }
    if (k === "tool") {
      renderToolDomOnly(String(e.name || ""), e.args);
      return;
    }
    if (k === "tool_result") {
      renderToolResultDomOnly(e);
      return;
    }
    if (k === "file") {
      renderFileDomOnly(String(e.path || ""), String(e.action || ""));
      return;
    }
    if (k === "assistant") {
      renderAssistantDomOnly(String(e.text || ""));
      return;
    }
    if (k === "error") {
      const row = document.createElement("div");
      row.className = "ddAgentLine ddAgentLine--error";
      const inner = document.createElement("div");
      inner.className = "ddAgentErr";
      inner.textContent = String(e.msg || "");
      row.appendChild(inner);
      traceEl?.appendChild(row);
      return;
    }
    if (k === "snippet") {
      renderSnippetDomOnly(String(e.path || ""), String(e.snippet || ""));
      return;
    }
    if (k === "thinking") {
      renderThinkingDomOnly(String(e.text || ""));
    }
  }

  function rebuildMergedTrace() {
    if (!traceEl) return;
    replayingTrace = true;
    suppressPersist = true;
    try {
      traceEl.innerHTML = "";
      thinkingOpen = null;
      lastPlanActivitySig = "";
      const chatFn = typeof renderDesignDomainChatRow === "function" ? renderDesignDomainChatRow : null;
      const rawChat = typeof getChatActivityLog === "function" ? getChatActivityLog() : [];
      /** @type {{ kind: string; ts: number; ord: number; payload: object }[]} */
      const merged = [];
      let ix = 0;
      for (let cIdx = 0; cIdx < rawChat.length; cIdx++) {
        const c = rawChat[cIdx];
        if (!c || typeof c !== "object") continue;
        const role = c.role === "user" ? "user" : "agent";
        const text = String(c.text || "").trim();
        if (!text) continue;
        const ts = Number.isFinite(Number(c.ts)) ? Number(c.ts) : 0;
        merged.push({ kind: "chat", ts, ord: ix, payload: { role, text, chatIdx: cIdx } });
        ix += 1;
      }
      for (const ev of timeline) {
        if (!ev || typeof ev !== "object") continue;
        const kind = String(ev.kind || "");
        if (!kind) continue;
        const ts = Number.isFinite(Number(ev.ts)) ? Number(ev.ts) : 0;
        const ord = Number.isFinite(Number(ev.ord)) ? Number(ev.ord) : 0;
        merged.push({ kind, ts, ord: ord || ix, payload: ev });
        ix += 1;
      }
      merged.sort((a, b) => {
        if (a.ts !== b.ts) return a.ts - b.ts;
        return a.ord - b.ord;
      });
      for (const m of merged) {
        if (m.kind === "chat") {
          const { role, text, chatIdx } = m.payload;
          if (chatFn) chatFn(role, text, typeof chatIdx === "number" ? chatIdx : undefined);
          continue;
        }
        replayOneTimelineEvt(m.payload);
      }
      scrollAgentStreamToEnd(traceEl);
    } finally {
      replayingTrace = false;
      suppressPersist = false;
    }
    updateComposerContextHint();
  }

  function remergeAgentTrace() {
    rebuildMergedTrace();
  }

  function maybeHydrateSession() {
    const k = storageKey();
    if (!k || k === lastHydratedStorageKey) return;
    lastHydratedStorageKey = k;
    timeline = [];
    timelineOrd = 0;
    try {
      let raw = localStorage.getItem(k);
      if (!raw && k.startsWith(`${LS_AGENT_UI}.t.`)) {
        const sid = String(getSessionId?.() || "").trim();
        if (sid) {
          const altS = localStorage.getItem(storageKeySession(sid));
          const altL = localStorage.getItem(storageKeyLegacySession(sid));
          raw = altS || altL || null;
          if (raw) {
            try {
              localStorage.setItem(k, raw);
            } catch {
              /* ignore */
            }
            try {
              if (altS) localStorage.removeItem(storageKeySession(sid));
            } catch {
              /* ignore */
            }
            try {
              if (altL) localStorage.removeItem(storageKeyLegacySession(sid));
            } catch {
              /* ignore */
            }
          }
        }
      }
      if (!raw) {
        renderStats();
        rebuildMergedTrace();
        updateComposerContextHint();
        refreshDrawerBodyIfOpen();
        return;
      }
      const d = JSON.parse(raw);
      toolCount = Number(d.toolCount) || 0;
      filePaths.clear();
      for (const p of Array.isArray(d.filePaths) ? d.filePaths : []) {
        if (p) filePaths.add(String(p));
      }
      pathsListedTotal = Number(d.pathsListedTotal) || 0;
      readCharsTotal = Number(d.readCharsTotal) || 0;
      runContextApproxChars = Number(d.runContextApproxChars) || 0;
      toolCallLog.length = 0;
      for (const x of Array.isArray(d.toolCallLog) ? d.toolCallLog : []) {
        if (x && typeof x === "object") toolCallLog.push(x);
      }
      fileEventLog.length = 0;
      for (const x of Array.isArray(d.fileEventLog) ? d.fileEventLog : []) {
        if (x && typeof x === "object" && x.path) {
          fileEventLog.push({
            path: String(x.path),
            action: String(x.action || ""),
            ts: Number(x.ts) || Date.now(),
            seq: Number(x.seq) || 0,
            detail: String(x.detail || ""),
          });
        }
      }
      readEventLog.length = 0;
      for (const x of Array.isArray(d.readEventLog) ? d.readEventLog : []) {
        if (x && typeof x === "object") readEventLog.push(x);
      }
      lastListingPreview = String(d.lastListingPreview || "");
      fileEventSeq = Number(d.fileEventSeq) || fileEventLog.length;
      timeline = Array.isArray(d.timeline) ? d.timeline.filter((x) => x && typeof x === "object" && x.kind) : [];
      for (const ev of timeline) {
        if (!Number.isFinite(Number(ev.ord)) || Number(ev.ord) <= 0) {
          timelineOrd += 1;
          ev.ord = timelineOrd;
        } else {
          timelineOrd = Math.max(timelineOrd, Number(ev.ord));
        }
      }
      if (!timeline.length && (toolCallLog.length > 0 || fileEventLog.length > 0)) {
        timeline = deriveTimelineFromLegacy();
      }
      const draft = String(d.composerDraft || "");
      if (inputEl && draft) inputEl.value = draft;
      const mq = String(d.modelQuick || "").trim();
      if (modelQuickEl && mq) {
        let hasOpt = false;
        for (let i = 0; i < modelQuickEl.options.length; i++) {
          if (modelQuickEl.options[i].value === mq) {
            hasOpt = true;
            break;
          }
        }
        if (hasOpt) modelQuickEl.value = mq;
        else {
          const o = document.createElement("option");
          o.value = mq;
          o.textContent = `${mq}（已保存）`;
          modelQuickEl.appendChild(o);
          modelQuickEl.value = mq;
        }
      }
    } catch {
      /* ignore */
    }
    renderStats();
    rebuildMergedTrace();
    updateComposerContextHint();
    refreshDrawerBodyIfOpen();
  }

  function fileActionDetail(action, path) {
    const a = String(action || "").toLowerCase();
    if (a === "updated") return `已写入或覆盖「${path}」；若由工具生成，内容以服务端落盘为准。`;
    if (a === "created") return `新建「${path}」并写入会话工作区。`;
    if (a === "deleted" || a === "removed") return `已从工作区移除「${path}」。`;
    return `路径「${path}」发生变更（${a || "未知操作"}）。`;
  }

  function fileActionLabel(action) {
    const a = String(action || "").toLowerCase();
    return FILE_ACTION_ZH[a] || `操作：${action || "记录"}`;
  }

  function fmtShortTime(ts) {
    try {
      return new Date(ts).toLocaleString("zh-CN", { hour12: false, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
    } catch {
      return "";
    }
  }

  function emptyHintEl(text) {
    const d = document.createElement("div");
    d.className = "ddAgentStatEmpty";
    d.textContent = text;
    return d;
  }

  function drawerBodyExpanded() {
    return Boolean(statDetailEl && !statDetailEl.classList.contains("hidden"));
  }

  function refreshDrawerBodyIfOpen() {
    if (!statDetailBodyEl || !openDrawerKind || !drawerBodyExpanded()) return;
    if (openDrawerKind === "tools") renderToolDrawerBody(statDetailBodyEl);
    else if (openDrawerKind === "files") renderFileDrawerBody(statDetailBodyEl);
    else if (openDrawerKind === "paths") renderPathsDrawerBody(statDetailBodyEl);
    else if (openDrawerKind === "chars") renderCharsDrawerBody(statDetailBodyEl);
  }

  function renderToolDrawerBody(el) {
    el.innerHTML = "";
    if (!toolCallLog.length) {
      el.appendChild(emptyHintEl("暂无工具调用；发送消息或执行 Build 后，将在此按时间列出每次调用与参数摘要。"));
      return;
    }
    const wrap = document.createElement("div");
    wrap.className = "ddAgentStatToolList";
    for (let i = toolCallLog.length - 1; i >= 0; i--) {
      const t = toolCallLog[i];
      const card = document.createElement("div");
      card.className = `ddAgentStatToolCard${t.ok === false ? " ddAgentStatToolCard--err" : t.ok ? " ddAgentStatToolCard--ok" : ""}`;
      const top = document.createElement("div");
      top.className = "ddAgentStatToolCardTop";
      const name = document.createElement("span");
      name.className = "ddAgentStatToolName mono";
      name.textContent = t.name || "(未命名工具)";
      const st = document.createElement("span");
      st.className = "ddAgentStatToolState";
      if (t.ok === true) st.textContent = "成功";
      else if (t.ok === false) st.textContent = "失败";
      else st.textContent = "进行中";
      top.appendChild(name);
      top.appendChild(st);
      card.appendChild(top);
      if (t.summary) {
        const sm = document.createElement("div");
        sm.className = "ddAgentStatToolSummary mdLiteRoot";
        sm.innerHTML = markdownLiteToHtml(String(t.summary));
        card.appendChild(sm);
      }
      const pre = document.createElement("pre");
      pre.className = "ddAgentStatToolArgs mono";
      try {
        pre.textContent = JSON.stringify(t.args || {}, null, 2).slice(0, 2400);
      } catch {
        pre.textContent = "";
      }
      card.appendChild(pre);
      wrap.appendChild(card);
    }
    el.appendChild(wrap);
  }

  function renderFileDrawerBody(el) {
    el.innerHTML = "";
    if (!fileEventLog.length) {
      el.appendChild(emptyHintEl("暂无文件事件；智能体写入或更新产物后，将在此按时间列出并可点击在左侧预览。"));
      return;
    }
    const list = document.createElement("div");
    list.className = "ddAgentStatFileList";
    const rows = [...fileEventLog].sort((a, b) => b.seq - a.seq);
    for (const ev of rows) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "ddAgentStatFileRow";
      btn.setAttribute("data-stat-open", "file");
      btn.setAttribute("data-path", ev.path);
      const badge = document.createElement("span");
      const rawAct = String(ev.action || "").toLowerCase().replace(/[^a-z0-9_]/g, "") || "misc";
      const actKey = ["created", "updated", "wrote", "deleted", "removed", "touched"].includes(rawAct) ? rawAct : "misc";
      badge.className = `ddAgentStatFileBadge ddAgentStatFileBadge--${actKey}`;
      badge.textContent = fileActionLabel(ev.action);
      const main = document.createElement("span");
      main.className = "ddAgentStatFileMain";
      const p = document.createElement("span");
      p.className = "ddAgentStatFilePath mono";
      p.textContent = ev.path;
      const meta = document.createElement("span");
      meta.className = "ddAgentStatFileMeta";
      meta.textContent = `${fmtShortTime(ev.ts)} · 序号 #${ev.seq}`;
      const det = document.createElement("span");
      det.className = "ddAgentStatFileDetail";
      det.textContent = ev.detail || fileActionDetail(ev.action, ev.path);
      main.appendChild(p);
      main.appendChild(meta);
      main.appendChild(det);
      const chev = document.createElement("span");
      chev.className = "ddAgentStatFileChev";
      chev.setAttribute("aria-hidden", "true");
      chev.textContent = "›";
      btn.appendChild(badge);
      btn.appendChild(main);
      btn.appendChild(chev);
      list.appendChild(btn);
    }
    el.appendChild(list);
  }

  function renderPathsDrawerBody(el) {
    el.innerHTML = "";
    const t = document.createElement("div");
    t.className = "ddAgentStatPathsHead mono";
    t.textContent = `累计列举路径条目：${pathsListedTotal}`;
    el.appendChild(t);
    if (!lastListingPreview) {
      el.appendChild(emptyHintEl("暂无 list_files 原文摘要。"));
      return;
    }
    const pre = document.createElement("pre");
    pre.className = "ddAgentStatMonoBlock mono";
    pre.textContent = lastListingPreview.slice(0, 12000);
    el.appendChild(pre);
  }

  function renderCharsDrawerBody(el) {
    el.innerHTML = "";
    if (!readEventLog.length) {
      el.appendChild(emptyHintEl("暂无 read_file 记录。"));
      return;
    }
    const list = document.createElement("div");
    list.className = "ddAgentStatReadList";
    for (let i = readEventLog.length - 1; i >= 0; i--) {
      const r = readEventLog[i];
      const row = document.createElement("div");
      row.className = "ddAgentStatReadRow";
      row.innerHTML = `<span class="mono ddAgentStatReadPath">${esc(r.path)}</span><span class="ddAgentStatReadChars">${Number(r.chars).toLocaleString()} 字</span>`;
      list.appendChild(row);
    }
    el.appendChild(list);
  }
  /** @type {{ row: HTMLElement; det: HTMLDetailsElement; sum: HTMLElement; pre: HTMLElement; t0: number } | null} */
  let thinkingOpen = null;

  /** 与 applyDesignDomainStepUi 同频刷新时的 Plan 去重 */
  let lastPlanActivitySig = "";

  const PLAN_TOPIC_ZH = {
    design: "步骤 1 · 设计域",
    preview: "步骤 2 · OBJ",
    mesh: "步骤 3 · 体网格",
    loads: "步骤 4 · 载荷",
  };

  function abbrevApproxTokens(tok) {
    const t = Math.round(Number(tok) || 0);
    if (t <= 0) return "~0";
    if (t < 1000) return `~${t}`;
    if (t < 10000) {
      const k = t / 1000;
      const s = k.toFixed(1);
      return `~${s.endsWith(".0") ? String(Math.round(k)) : s}k`;
    }
    return `~${Math.round(t / 1000)}k`;
  }

  function updateComposerContextHint() {
    if (!contextHintEl) return;
    const draft = String(inputEl?.value || "").length;
    const tokEst = Math.round(runContextApproxChars / 3);
    const detail =
      runContextApproxChars <= 0
        ? `本句 ${draft} 字 · 本轮上下文约 0 字（估）`
        : `本句 ${draft} 字 · 本轮上下文约 ${runContextApproxChars.toLocaleString()} 字（估 · ~${Math.max(1, tokEst)} tokens）`;
    contextHintEl.title = detail;
    contextHintEl.setAttribute("aria-label", detail);

    const prog = contextHintEl.querySelector(".ddAgentContextRingProg");
    const tokEl = contextHintEl.querySelector(".ddAgentContextRingTok");
    if (prog instanceof SVGCircleElement) {
      const p = Math.min(1, runContextApproxChars / CONTEXT_RING_MAX_CHARS);
      prog.style.strokeDashoffset = String(100 * (1 - p));
      contextHintEl.classList.toggle("ddAgentContextRing--warm", p >= 0.52);
      contextHintEl.classList.toggle("ddAgentContextRing--hot", p >= 0.82);
    } else {
      contextHintEl.textContent = detail;
    }
    if (tokEl) tokEl.textContent = abbrevApproxTokens(tokEst);
  }

  function bumpContext(n) {
    const x = Number(n) || 0;
    if (x <= 0) return;
    runContextApproxChars += x;
    updateComposerContextHint();
    if (!suppressPersist) schedulePersist();
  }

  function renderStats() {
    if (statToolsEl) statToolsEl.textContent = String(toolCount);
    if (statFilesEl) statFilesEl.textContent = String(filePaths.size);
    if (statPathsEl) statPathsEl.textContent = String(pathsListedTotal);
    if (statCharsEl) statCharsEl.textContent = String(readCharsTotal);
    if (!suppressPersist) schedulePersist();
  }

  /** 与工具结果中的列举/读取统计同步（主栏统计已精简时仍用于明细） */
  function noteListReadFromToolResult(ev) {
    if (typeof ev.paths_listed === "number" && ev.paths_listed > 0) {
      pathsListedTotal += ev.paths_listed;
    }
    if (typeof ev.read_chars === "number" && ev.read_chars > 0) {
      readCharsTotal += ev.read_chars;
      const rp = String(ev.read_path || "").trim();
      readEventLog.push({ path: rp || "(路径未知)", chars: ev.read_chars });
    }
    if (typeof ev.listing_preview === "string" && ev.listing_preview.trim()) {
      lastListingPreview = ev.listing_preview;
    }
  }

  const DRAWER_TITLE = {
    tools: "工具调用明细",
    files: "文件事件明细",
    paths: "浏览路径 / list_files",
    chars: "read_file 字数明细",
  };

  function syncStatHitActiveUi() {
    if (!sessionStatsEl) return;
    sessionStatsEl.querySelectorAll("[data-dd-stat]").forEach((el) => {
      const k = el.getAttribute("data-dd-stat");
      const bodyOn = Boolean(openDrawerKind === k && statDetailEl && !statDetailEl.classList.contains("hidden"));
      el.classList.toggle("ddAgentStatHit--active", bodyOn);
      el.classList.remove("ddAgentStatHit--peek");
      el.setAttribute("aria-expanded", bodyOn ? "true" : "false");
    });
  }

  function hideDrawerCompletely() {
    openDrawerKind = null;
    statDetailEl?.classList.add("hidden");
    statDetailEl?.classList.remove("ddAgentStatDrawer--collapsed");
    if (statDetailBodyEl) statDetailBodyEl.innerHTML = "";
    syncStatHitActiveUi();
  }

  function openStatDrawer(kind) {
    if (!statDetailEl || !statDetailBodyEl) return;
    statDetailEl.classList.remove("hidden");
    statDetailEl.classList.remove("ddAgentStatDrawer--collapsed");
    openDrawerKind = kind;
    if (statDetailTitleEl) statDetailTitleEl.textContent = DRAWER_TITLE[kind] || "明细";
    if (statDrawerKickerEl) {
      statDrawerKickerEl.textContent =
        kind === "tools" ? "TOOLS" : kind === "files" ? "FILES" : kind === "paths" ? "PATHS" : "READ";
    }
    if (kind === "tools") renderToolDrawerBody(statDetailBodyEl);
    else if (kind === "files") renderFileDrawerBody(statDetailBodyEl);
    else if (kind === "paths") renderPathsDrawerBody(statDetailBodyEl);
    else if (kind === "chars") renderCharsDrawerBody(statDetailBodyEl);
    syncStatHitActiveUi();
  }

  /** 仅「工具 / 文件」统计条：互斥展开，再次点击同项则整抽屉收起 */
  function onStatHitClick(kind) {
    if (kind !== "tools" && kind !== "files") return;
    const visible = Boolean(statDetailEl && !statDetailEl.classList.contains("hidden"));
    if (visible && openDrawerKind === kind) {
      hideDrawerCompletely();
      return;
    }
    openStatDrawer(kind);
  }

  function resetStats() {
    const k = storageKey();
    lastHydratedStorageKey = k || "";
    toolCount = 0;
    filePaths.clear();
    pathsListedTotal = 0;
    readCharsTotal = 0;
    runContextApproxChars = 0;
    toolCallLog.length = 0;
    fileEventLog.length = 0;
    readEventLog.length = 0;
    lastListingPreview = "";
    fileEventSeq = 0;
    openDrawerKind = null;
    hideDrawerCompletely();
    renderStats();
    updateComposerContextHint();
  }

  function formatThoughtDuration(ms) {
    const s = Math.max(0, ms) / 1000;
    if (s < 10) return `${s.toFixed(1)}s`;
    return `${Math.round(s)}s`;
  }

  function finalizeThinkingRow() {
    if (!thinkingOpen || !traceEl) return;
    const { row, det, sum, pre, t0 } = thinkingOpen;
    const dt = Date.now() - t0;
    const label = `Thought for ${formatThoughtDuration(dt)}`;
    sum.innerHTML = `<span class="ddAgentThoughtLabel">${esc(label)}</span><span class="ddAgentThoughtChev" aria-hidden="true"></span>`;
    det.classList.add("ddAgentThinking--done");
    row.classList.add("ddAgentLine--thinkingDone");
    try {
      const thought = String(pre?.textContent || "").trim();
      if (thought) timelinePush({ kind: "thinking", text: thought.slice(0, 12000), ms: dt });
    } catch {
      /* ignore */
    }
    thinkingOpen = null;
    scrollAgentStreamToEnd(traceEl);
  }

  function openThinkingRow(text) {
    if (!traceEl) return;
    finalizeThinkingRow();
    const row = document.createElement("div");
    row.className = "ddAgentLine ddAgentLine--thinking";
    const det = document.createElement("details");
    det.className = "ddAgentThinking";
    det.open = false;
    const sum = document.createElement("summary");
    sum.className = "ddAgentThinkingSum";
    sum.innerHTML =
      '<span class="ddAgentThoughtLabel ddAgentThoughtLabel--pulse">思考中…</span><span class="ddAgentThoughtChev" aria-hidden="true"></span>';
    const pre = document.createElement("pre");
    pre.className = "ddAgentThinkingPre mono";
    pre.textContent = String(text || "");
    det.appendChild(sum);
    det.appendChild(pre);
    row.appendChild(det);
    traceEl.appendChild(row);
    thinkingOpen = { row, det, sum, pre, t0: Date.now() };
    scrollAgentStreamToEnd(traceEl);
  }

  function appendThinking(text) {
    if (!traceEl) return;
    const s = String(text || "");
    bumpContext(s.length);
    if (thinkingOpen) {
      thinkingOpen.pre.textContent = s;
      return;
    }
    openThinkingRow(s);
  }

  /**
   * @param {string} topic
   * @param {string} phase
   */
  function appendPlanActivity(topic, phase) {
    const sig = `${topic}:${phase}`;
    if (sig === lastPlanActivitySig) return;
    lastPlanActivitySig = sig;
    const ph = String(phase || "");
    if (ph === "reset") {
      appendActivityLine("执行计划已重置（无会话或回到起点）", "plan");
      return;
    }
    const zh = PLAN_TOPIC_ZH[topic] || topic;
    if (ph === "running") appendActivityLine(`Plan · ${zh} · 进行中`, "plan");
    else if (ph === "done") appendActivityLine(`Plan · ${zh} · 已完成`, "plan");
    else if (ph === "open") appendActivityLine(`Plan · ${zh} · 已展开`, "plan");
  }

  function appendActivityLine(text, kind = "") {
    if (!traceEl) return;
    finalizeThinkingRow();
    bumpContext(String(text || "").length);
    const row = document.createElement("div");
    row.className = `ddAgentLine ddAgentLine--activity ddAgentLine--activity-${kind || "misc"}`;
    const inner = document.createElement("div");
    inner.className = "ddAgentActivity";
    inner.textContent = text;
    row.appendChild(inner);
    traceEl.appendChild(row);
    timelinePush({ kind: "activity", text: String(text || ""), actKind: String(kind || "misc") });
    scrollAgentStreamToEnd(traceEl);
  }

  function appendReadSnippetCard(path, snippet) {
    if (!traceEl || !String(snippet || "").trim()) return;
    finalizeThinkingRow();
    bumpContext(String(snippet).length);
    const row = document.createElement("div");
    row.className = "ddAgentLine ddAgentLine--snippet";
    const card = document.createElement("div");
    card.className = "ddAgentSnippetCard";
    const hd = document.createElement("div");
    hd.className = "ddAgentSnippetHd";
    hd.textContent = `read_file 预览 · ${path}`;
    const pre = document.createElement("pre");
    pre.className = "ddAgentSnippetPre mono";
    const lines = String(snippet).split("\n");
    for (let i = 0; i < lines.length; i++) {
      const ln = document.createElement("div");
      ln.className = "ddAgentSnippetLine ddAgentSnippetLine--ctx";
      const n = document.createElement("span");
      n.className = "ddAgentSnippetNo";
      n.textContent = String(i + 1);
      const tx = document.createElement("span");
      tx.textContent = lines[i];
      ln.appendChild(n);
      ln.appendChild(tx);
      pre.appendChild(ln);
    }
    card.appendChild(hd);
    card.appendChild(pre);
    row.appendChild(card);
    traceEl.appendChild(row);
    timelinePush({
      kind: "snippet",
      path: String(path || ""),
      snippet: String(snippet || "").slice(0, SNIPPET_PERSIST_MAX),
    });
    scrollAgentStreamToEnd(traceEl);
  }

  function appendTool(name, args) {
    if (!traceEl) return;
    finalizeThinkingRow();
    bumpContext(String(name).length + (() => {
      try {
        return JSON.stringify(args || {}).length;
      } catch {
        return 0;
      }
    })());
    toolCallLog.push({ name: String(name || ""), args: args && typeof args === "object" ? args : {} });
    const row = document.createElement("div");
    row.className = "ddAgentLine ddAgentLine--tool";
    const card = document.createElement("div");
    card.className = "ddAgentToolCard ddAgentToolCard--enter";
    const head = document.createElement("div");
    head.className = "ddAgentToolCardHd";
    const ic = document.createElement("span");
    ic.className = "ddAgentToolCardIcon";
    ic.setAttribute("aria-hidden", "true");
    const tit = document.createElement("div");
    tit.className = "ddAgentToolCardTit";
    tit.innerHTML = `<span class="ddAgentToolCardK">调用工具</span><span class="ddAgentToolCardName mono">${esc(name)}</span>`;
    head.appendChild(ic);
    head.appendChild(tit);
    card.appendChild(head);
    if (args && Object.keys(args).length) {
      const pre = document.createElement("pre");
      pre.className = "ddAgentToolCardArgs mono";
      try {
        pre.textContent = JSON.stringify(args, null, 2).slice(0, 2400);
      } catch {
        pre.textContent = "";
      }
      card.appendChild(pre);
    }
    row.appendChild(card);
    traceEl.appendChild(row);
    timelinePush({
      kind: "tool",
      name: String(name || ""),
      args: args && typeof args === "object" ? args : {},
    });
    scrollAgentStreamToEnd(traceEl);
  }

  function appendToolResult(ev) {
    if (!traceEl) return;
    finalizeThinkingRow();
    const ok = Boolean(ev.ok);
    const name = String(ev.name || "");
    const last = toolCallLog[toolCallLog.length - 1];
    if (last && last.name === name) {
      last.ok = ok;
      last.summary = String(ev.summary || "");
    }
    bumpContext(String(ev.summary || "").length);
    const row = document.createElement("div");
    row.className = `ddAgentLine ddAgentLine--toolres ddAgentToolResRow--${ok ? "ok" : "err"} ddAgentToolResRow--pop`;
    const card = document.createElement("div");
    card.className = `ddAgentToolResCard ddAgentToolResCard--${ok ? "ok" : "err"} ddAgentToolResCard--pop`;
    const main = document.createElement("div");
    main.className = "ddAgentToolResMain ddAgentToolResMain--md mdLiteRoot";
    main.innerHTML = markdownLiteToHtml(String(ev.summary || ""));
    card.appendChild(main);
    const metaBits = [];
    noteListReadFromToolResult(ev);
    if (typeof ev.paths_listed === "number" && ev.paths_listed > 0) {
      metaBits.push(`列举 ${ev.paths_listed} 条路径`);
    }
    if (typeof ev.read_chars === "number" && ev.read_chars > 0) {
      const rp = String(ev.read_path || "").trim();
      metaBits.push(`已读 ${rp || "文件"} · ${ev.read_chars.toLocaleString()} 字`);
    }
    if (typeof ev.listing_preview === "string" && ev.listing_preview.trim()) {
      lastListingPreview = ev.listing_preview;
      bumpContext(ev.listing_preview.length);
    }
    if (metaBits.length) {
      const sub = document.createElement("div");
      sub.className = "ddAgentToolResMeta";
      sub.textContent = metaBits.join(" · ");
      card.appendChild(sub);
    }
    row.appendChild(card);
    traceEl.appendChild(row);
    const snip = String(ev.content_snippet || "").trim();
    const rpth = String(ev.read_path || "").trim();
    timelinePush({
      kind: "tool_result",
      ok: Boolean(ev.ok),
      name: String(ev.name || ""),
      summary: String(ev.summary || "").slice(0, 8000),
      paths_listed: typeof ev.paths_listed === "number" ? ev.paths_listed : undefined,
      read_chars: typeof ev.read_chars === "number" ? ev.read_chars : undefined,
      read_path: String(ev.read_path || ""),
      listing_preview:
        typeof ev.listing_preview === "string" ? ev.listing_preview.slice(0, 4000) : "",
      content_snippet: snip ? snip.slice(0, SNIPPET_PERSIST_MAX) : "",
    });
    renderStats();
    if (typeof ev.paths_listed === "number" && ev.paths_listed > 0) {
      appendActivityLine(`Explored ${ev.paths_listed} paths · list_files`, "explore");
    }
    if (typeof ev.read_chars === "number" && ev.read_chars > 0) {
      appendActivityLine(
        `Read ${String(ev.read_path || "").trim() || "file"} · ${ev.read_chars.toLocaleString()} chars`,
        "read",
      );
    }
    if (snip && rpth) appendReadSnippetCard(rpth, snip);
    scrollAgentStreamToEnd(traceEl);
    if (ev.replan_guided && typeof ev.replan_guided === "object") {
      try {
        onReplanGuided?.(ev.replan_guided);
      } catch {
        /* ignore */
      }
    }
    requestAnimationFrame(() => {
      card.classList.add("ddAgentToolResCard--popDone");
    });
  }

  function appendFile(path, action) {
    if (!traceEl) return;
    finalizeThinkingRow();
    const pStr = String(path || "");
    const aStr = String(action || "");
    fileEventSeq += 1;
    fileEventLog.push({
      path: pStr,
      action: aStr,
      ts: Date.now(),
      seq: fileEventSeq,
      detail: fileActionDetail(aStr, pStr),
    });
    bumpContext(pStr.length + 8);
    refreshDrawerBodyIfOpen();
    const row = document.createElement("div");
    row.className = "ddAgentLine ddAgentLine--file";
    const card = document.createElement("div");
    card.className = "ddAgentFileCard ddAgentFileCard--enter";
    const badge = document.createElement("span");
    badge.className = "ddAgentFileBadge";
    badge.textContent = action === "updated" ? "+1" : "+";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ddAgentFileLink mono";
    btn.textContent = path;
    btn.dataset.relPath = path;
    const cap = document.createElement("span");
    cap.className = "ddAgentFileCap";
    cap.textContent = action === "updated" ? "已更新产物" : "文件";
    card.appendChild(badge);
    card.appendChild(btn);
    card.appendChild(cap);
    row.appendChild(card);
    traceEl.appendChild(row);
    timelinePush({ kind: "file", path: pStr, action: aStr });
    if (!replayingTrace && String(action || "") === "updated" && path) {
      try {
        onAgentProduce?.(String(path).trim());
      } catch {
        /* ignore */
      }
    }
    scrollAgentStreamToEnd(traceEl);
  }

  function appendAssistant(text) {
    if (!traceEl) return;
    finalizeThinkingRow();
    const s = String(text || "");
    bumpContext(s.length);
    const row = document.createElement("div");
    row.className = "ddAgentLine ddAgentLine--assistant";
    const inner = document.createElement("div");
    inner.className = "ddAgentReply mdBox ddAgentReply--md mdLiteRoot";
    row.appendChild(inner);
    traceEl.appendChild(row);
    const approx = s.length;
    if (approx >= 120) appendActivityLine(`回复约 ${approx.toLocaleString()} 字`, "reply");
    scrollAgentStreamToEnd(traceEl);
    const n = s.length;
    if (!n) return;
    if (n < 200) {
      inner.innerHTML = markdownLiteToHtml(s);
      timelinePush({ kind: "assistant", text: s.slice(0, ASSISTANT_PERSIST_MAX) });
      return;
    }
    let pos = 0;
    const chunk = Math.max(2, Math.min(24, Math.ceil(n / 48) || 2));
    const tick = () => {
      pos = Math.min(n, pos + chunk);
      if (pos < n) {
        inner.innerHTML = esc(s.slice(0, pos)).replace(/\n/g, "<br/>");
        scrollAgentStreamToEnd(traceEl);
        requestAnimationFrame(tick);
      } else {
        inner.innerHTML = markdownLiteToHtml(s);
        timelinePush({ kind: "assistant", text: s.slice(0, ASSISTANT_PERSIST_MAX) });
        scrollAgentStreamToEnd(traceEl);
      }
    };
    requestAnimationFrame(tick);
  }

  function appendError(msg) {
    if (!traceEl) return;
    finalizeThinkingRow();
    bumpContext(String(msg || "").length);
    const row = document.createElement("div");
    row.className = "ddAgentLine ddAgentLine--error";
    const inner = document.createElement("div");
    inner.className = "ddAgentErr";
    inner.textContent = msg;
    row.appendChild(inner);
    traceEl.appendChild(row);
    timelinePush({ kind: "error", msg: String(msg || "") });
    scrollAgentStreamToEnd(traceEl);
  }

  function appendRunSummary() {
    if (!traceEl) return;
    const bits = [`工具 ${toolCount} 次`, `触及文件 ${filePaths.size} 个`];
    const row = document.createElement("div");
    row.className = "ddAgentLine ddAgentLine--summary";
    const inner = document.createElement("div");
    inner.className = "ddAgentRunSummary";
    inner.textContent = `本轮结束 · ${bits.join(" · ")}`;
    row.appendChild(inner);
    traceEl.appendChild(row);
    scrollAgentStreamToEnd(traceEl);
  }

  function handleEvent(ev) {
    const t = ev.type;
    if (t === "meta") {
      const m = String(ev.model || "").trim();
      const proto = String(ev.protocol || "").trim();
      if (m) {
        const extra = proto ? ` · ${proto}` : "";
        appendActivityLine(`使用模型 · ${m}${extra}`, "plan");
      }
    } else if (t === "activity") {
      appendActivityLine(String(ev.text || ""), String(ev.kind || "misc"));
    } else if (t === "thinking_delta") {
      const piece = String(ev.text || "");
      if (piece) appendThinking((thinkingOpen ? thinkingOpen.pre.textContent : "") + piece);
    } else if (t === "thinking") {
      appendThinking(String(ev.text || ""));
    } else if (t === "plan_md_delta") {
      const piece = String(ev.text || "");
      if (piece) {
        try {
          onPlanMdDelta?.(piece);
        } catch {
          /* ignore */
        }
      }
    } else if (t === "plan_rail_step") {
      try {
        onPlanRailStep?.({
          index: Number(ev.index) || 0,
          topic: String(ev.topic || "").trim(),
          label: String(ev.label || "").trim(),
        });
      } catch {
        /* ignore */
      }
    } else if (t === "plan_file") {
      const rel = String(ev.path || "").trim();
      if (rel) {
        try {
          onPlanFileReady?.(rel);
        } catch {
          /* ignore */
        }
      }
    } else if (t === "plan") {
      try {
        onDynamicPlan?.(Array.isArray(ev.steps) ? ev.steps : [], String(ev.rationale || ""));
      } catch {
        /* ignore */
      }
      const r = String(ev.rationale || "").trim();
      if (r) appendActivityLine(`Plan  rationale · ${r.slice(0, 400)}${r.length > 400 ? "…" : ""}`, "plan");
    } else if (t === "plan_step") {
      const ph = String(ev.phase || "");
      const ti = String(ev.title || ev.tool || "");
      const ix = ev.index != null ? `#${ev.index} ` : "";
      if (ph === "start") appendActivityLine(`执行步骤 ${ix}${ti}`, "plan");
      else if (ph === "done") appendActivityLine(`步骤完成 ${ix}${ti}${ev.ok === false ? " · 失败" : ""}`, "plan");
      try {
        onPlanBuildProgress?.({
          index: Number(ev.index) || 0,
          phase: ph,
          ok: ev.ok,
          title: String(ev.title || ""),
          tool: String(ev.tool || ""),
        });
      } catch {
        /* ignore */
      }
    } else if (t === "tool") {
      toolCount += 1;
      appendTool(String(ev.name || ""), ev.args);
      renderStats();
    } else if (t === "tool_result") {
      appendToolResult(ev);
      if (ev.ok) onRefreshTree?.();
    } else if (t === "file") {
      const p = String(ev.path || "").trim();
      if (p) filePaths.add(p);
      appendFile(p, String(ev.action || ""));
      renderStats();
    } else if (t === "assistant") appendAssistant(String(ev.text || ""));
    else if (t === "error") appendError(String(ev.message || ev.text || ""));
    else if (t === "refresh_tree") onRefreshTree?.();
    else if (t === "done") {
      finalizeThinkingRow();
      const ph = String(ev.phase || "");
      try {
        onStreamPhaseDone?.(Boolean(ev.ok), { historyPath: ev.history_path, phase: ph });
      } catch {
        /* ignore */
      }
    }
  }

  /** 计划草稿流：不写入主时间线（避免与 Plan 卡片重复） */
  async function consumeNdjsonPlanDraftStream(resp) {
    const reader = resp.body?.getReader();
    if (!reader) throw new Error("响应体不可读");
    const dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      for (;;) {
        const ix = buf.indexOf("\n");
        if (ix < 0) break;
        const line = buf.slice(0, ix).trim();
        buf = buf.slice(ix + 1);
        if (!line) continue;
        let ev;
        try {
          ev = JSON.parse(line);
        } catch {
          continue;
        }
        const t = ev.type;
        if (t === "plan_md_delta") {
          const piece = String(ev.text || "");
          if (piece) {
            try {
              onPlanMdDelta?.(piece);
            } catch {
              /* ignore */
            }
          }
        } else if (t === "plan_rail_step") {
          try {
            onPlanRailStep?.({
              index: Number(ev.index) || 0,
              topic: String(ev.topic || "").trim(),
              label: String(ev.label || "").trim(),
            });
          } catch {
            /* ignore */
          }
        } else if (t === "plan_file") {
          const rel = String(ev.path || "").trim();
          if (rel) {
            try {
              onPlanFileReady?.(rel);
            } catch {
              /* ignore */
            }
          }
        } else if (t === "error") {
          appendError(String(ev.message || ev.text || ""));
        } else if (t === "done") {
          const ph = String(ev.phase || "");
          try {
            onStreamPhaseDone?.(Boolean(ev.ok), { historyPath: ev.history_path, phase: ph });
          } catch {
            /* ignore */
          }
        }
      }
    }
  }

  /** @param {Response} resp */
  async function consumeNdjsonStream(resp) {
    const reader = resp.body?.getReader();
    if (!reader) throw new Error("响应体不可读");
    const dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      for (;;) {
        const ix = buf.indexOf("\n");
        if (ix < 0) break;
        const line = buf.slice(0, ix).trim();
        buf = buf.slice(ix + 1);
        if (!line) continue;
        let ev;
        try {
          ev = JSON.parse(line);
        } catch {
          continue;
        }
        handleEvent(ev);
      }
    }
  }

  traceEl?.addEventListener("click", (e) => {
    const b = e.target?.closest?.(".ddAgentFileLink");
    if (!b || !traceEl?.contains(b)) return;
    const p = b.getAttribute("data-rel-path");
    if (p) onOpenFile?.(p);
  });

  sessionStatsEl?.addEventListener("click", (e) => {
    const hit = e.target?.closest?.("[data-dd-stat]");
    if (!hit || !sessionStatsEl?.contains(hit)) return;
    const kind = hit.getAttribute("data-dd-stat");
    if (kind === "tools" || kind === "files") onStatHitClick(kind);
  });

  statDetailBodyEl?.addEventListener("click", (e) => {
    const b = e.target?.closest?.("[data-stat-open='file']");
    if (!b || !statDetailBodyEl?.contains(b)) return;
    const p = b.getAttribute("data-path");
    if (p) onOpenFile?.(p);
  });

  inputEl?.addEventListener("input", () => {
    updateComposerContextHint();
    schedulePersist();
  });
  modelQuickEl?.addEventListener("change", () => schedulePersist());

  async function send() {
    const sid = String(getSessionId?.() || "").trim();
    const msg = String(inputEl?.value || "").trim();
    if (!sid || !msg) return;
    if (inputEl) inputEl.value = "";
    abortCtrl = new AbortController();
    if (stopBtn) {
      stopBtn.classList.remove("hidden");
      stopBtn.disabled = false;
    }
    if (sendBtn) sendBtn.disabled = true;
    maybeHydrateSession();
    bumpContext(msg.length);
    appendFlowLog?.("user", msg);
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    let statusRow = null;
    if (traceEl) {
      finalizeThinkingRow();
      statusRow = document.createElement("div");
      statusRow.className = "ddAgentLine ddAgentLine--status";
      const inner = document.createElement("div");
      inner.className = "ddAgentStatusPill";
      inner.innerHTML =
        '<span class="ddAgentStatusDot" aria-hidden="true"></span><span class="ddAgentStatusTxt">正在运行智能体…</span>';
      statusRow.appendChild(inner);
      traceEl.appendChild(statusRow);
      scrollAgentStreamToEnd(traceEl);
    }
    const base = String(normalizedBaseUrl?.() || "").replace(/\/+$/, "");
    const url = `${base}/api/oc4/design-domain/session/${encodeURIComponent(sid)}/agent/stream`;
    try {
      const resp = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg }),
        signal: abortCtrl.signal,
      });
      if (!resp.ok) {
        const tx = await resp.text();
        throw new Error(tx.slice(0, 800) || `HTTP ${resp.status}`);
      }
      appendActivityLine("流已连接，等待模型首包…", "misc");
      await consumeNdjsonStream(resp);
    } catch (e) {
      if (e?.name !== "AbortError") appendError(String(e?.message || e));
    } finally {
      statusRow?.remove();
      finalizeThinkingRow();
      appendRunSummary();
      if (stopBtn) stopBtn.classList.add("hidden");
      if (sendBtn) sendBtn.disabled = false;
      abortCtrl = null;
      updateComposerContextHint();
    }
  }

  async function consumePlanBuildStream() {
    const sid = String(getSessionId?.() || "").trim();
    if (!sid) throw new Error("缺少会话");
    abortCtrl = new AbortController();
    if (stopBtn) {
      stopBtn.classList.remove("hidden");
      stopBtn.disabled = false;
    }
    if (sendBtn) sendBtn.disabled = true;
    maybeHydrateSession();
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    let statusRow = null;
    if (traceEl) {
      finalizeThinkingRow();
      statusRow = document.createElement("div");
      statusRow.className = "ddAgentLine ddAgentLine--status";
      const inner = document.createElement("div");
      inner.className = "ddAgentStatusPill";
      inner.innerHTML =
        '<span class="ddAgentStatusDot" aria-hidden="true"></span><span class="ddAgentStatusTxt">Build 管线执行中…</span>';
      statusRow.appendChild(inner);
      traceEl.appendChild(statusRow);
      scrollAgentStreamToEnd(traceEl);
    }
    const base = String(normalizedBaseUrl?.() || "").replace(/\/+$/, "");
    const url = `${base}/api/oc4/design-domain/session/${encodeURIComponent(sid)}/agent/plan-build/stream`;
    try {
      const resp = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          getPlanBuildPayload?.() || {
            cut_center_column: true,
            include_source_geometry: false,
          },
        ),
        signal: abortCtrl.signal,
      });
      if (!resp.ok) {
        const tx = await resp.text();
        throw new Error(tx.slice(0, 800) || `HTTP ${resp.status}`);
      }
      appendActivityLine("Plan-Build 流已连接…", "plan");
      await consumeNdjsonStream(resp);
    } catch (e) {
      if (e?.name !== "AbortError") appendError(String(e?.message || e));
    } finally {
      statusRow?.remove();
      finalizeThinkingRow();
      appendRunSummary();
      if (stopBtn) stopBtn.classList.add("hidden");
      if (sendBtn) sendBtn.disabled = false;
      abortCtrl = null;
      updateComposerContextHint();
    }
  }

  /** 仅流式生成 build_plan.md，不占用主对话统计与发送按钮 */
  async function consumePlanDraftStream() {
    const sid = String(getSessionId?.() || "").trim();
    if (!sid) throw new Error("缺少会话");
    const base = String(normalizedBaseUrl?.() || "").replace(/\/+$/, "");
    const url = `${base}/api/oc4/design-domain/session/${encodeURIComponent(sid)}/agent/plan-draft/stream`;
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    if (!resp.ok) {
      const tx = await resp.text();
      throw new Error(tx.slice(0, 800) || `HTTP ${resp.status}`);
    }
    await consumeNdjsonPlanDraftStream(resp);
  }

  function stop() {
    abortCtrl?.abort();
  }

  sendBtn?.addEventListener("click", () => void send());
  stopBtn?.addEventListener("click", () => stop());
  inputEl?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  });

  maybeHydrateSession();
  updateComposerContextHint();
  syncStatHitActiveUi();

  function switchTaskContext() {
    toolCount = 0;
    filePaths.clear();
    pathsListedTotal = 0;
    readCharsTotal = 0;
    runContextApproxChars = 0;
    toolCallLog.length = 0;
    fileEventLog.length = 0;
    readEventLog.length = 0;
    lastListingPreview = "";
    fileEventSeq = 0;
    openDrawerKind = null;
    hideDrawerCompletely();
    lastHydratedStorageKey = "";
    maybeHydrateSession();
  }

  function resetPersistedForNewDesignSession() {
    suppressPersist = true;
    try {
      timeline = [];
      timelineOrd = 0;
      lastPlanActivitySig = "";
      thinkingOpen = null;
      toolCount = 0;
      filePaths.clear();
      pathsListedTotal = 0;
      readCharsTotal = 0;
      runContextApproxChars = 0;
      toolCallLog.length = 0;
      fileEventLog.length = 0;
      readEventLog.length = 0;
      lastListingPreview = "";
      fileEventSeq = 0;
      openDrawerKind = null;
      hideDrawerCompletely();
      if (traceEl) traceEl.innerHTML = "";
      const k = storageKey();
      lastHydratedStorageKey = "";
      if (k) {
        try {
          localStorage.removeItem(k);
        } catch {
          /* ignore */
        }
      }
    } finally {
      suppressPersist = false;
    }
    renderStats();
    updateComposerContextHint();
  }

  return {
    clearTrace() {
      if (traceEl) traceEl.innerHTML = "";
      thinkingOpen = null;
      lastPlanActivitySig = "";
      timeline = [];
      timelineOrd = 0;
    },
    hydrateFromStorage(force) {
      if (force) lastHydratedStorageKey = "";
      maybeHydrateSession();
    },
    remergeAgentTrace,
    resetPersistedForNewDesignSession,
    flushPersist,
    switchTaskContext,
    resetStats,
    appendPlanActivity,
    consumePlanBuildStream,
    consumePlanDraftStream,
    dispose() {
      try {
        flushPersist();
      } catch {
        /* ignore */
      }
      stop();
    },
  };
}
