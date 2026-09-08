function escapeHtml(s) {
  return String(s || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function formatTaskTime(v) {
  if (!v) return "-";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return String(v);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function taskIsGenericTitle(s) {
  const x = String(s || "").trim();
  if (!x || x === "未命名任务" || x === "未命名") return true;
  if (x === "新对话") return true;
  if (x.startsWith("新对话")) {
    return !/\s*[·•]\s*\S/u.test(x);
  }
  return false;
}

/** 与侧栏列表一致：用于主页顶栏会话标题等 */
export function taskListDisplayTitle(t) {
  const raw = String(t?.title || "").trim();
  // Full-flow demo: orchestration used to overwrite title with the internal prompt
  if (
    /^【全流程演示】/.test(raw) ||
    /BESO7\s*设计域已收尾/.test(raw) ||
    (String(t?.file_name || "").includes("BESO7") && /全流程演示/.test(raw) && raw.length > 40)
  ) {
    return "全流程演示 · BESO7";
  }
  if (raw === "全流程演示 · BESO7" || raw.startsWith("全流程演示 ·")) return raw;
  if (raw && !taskIsGenericTitle(raw)) return raw;
  const timeStr = formatTaskTime(t.updated_at || t.created_at);
  const fileHint = String(t.file_name || "")
    .replace(/^.*[/\\]/, "")
    .trim()
    .slice(0, 42);
  if (fileHint && /^BESO7/i.test(fileHint)) return "全流程演示 · BESO7";
  if (fileHint) return fileHint;
  const id = String(t.task_id || "").replace(/-/g, "");
  const shortId = id.length >= 6 ? id.slice(0, 6).toUpperCase() : (id.toUpperCase() || "—");
  return `对话 · ${shortId} · ${timeStr}`;
}

/** 构型优化编排（拓扑）总步数 1–4；尺寸时域 / AI Review 为独立子流程卡片 */
export const ORCH_TOTAL_STEPS = 4;

/** @param {string} status */
export function formatTaskStatus(status) {
  const st = String(status || "").toLowerCase();
  const map = {
    uploaded: { label: "已上传", tone: "info" },
    orchestrating: { label: "编排中", tone: "orch" },
    ready_to_execute: { label: "待执行", tone: "ready" },
    running: { label: "运行中", tone: "busy" },
    ready_for_analysis: { label: "待分析", tone: "ready" },
    analyzing: { label: "分析中", tone: "busy" },
    ready_for_review: { label: "待评审", tone: "ready" },
    reviewing: { label: "评审中", tone: "busy" },
    completed: { label: "已完成", tone: "ok" },
    done: { label: "已完成", tone: "ok" },
    failed: { label: "失败", tone: "bad" },
    cancelled: { label: "已取消", tone: "muted" },
    missing: { label: "无记录", tone: "muted" },
    pending: { label: "排队中", tone: "queue" },
    queued: { label: "排队中", tone: "queue" },
  };
  if (map[st]) return map[st];
  if (!st) return { label: "-", tone: "muted" };
  return { label: status || "-", tone: "muted" };
}

/** 侧栏步骤文案：编排用 N/4；后续阶段用独立标签 */
export function formatTaskStepLabel(task) {
  const st = String(task?.status || "").toLowerCase();
  const ui = String(task?.ui_stage || "").toLowerCase();
  const stepNum = Number(task?.step);
  if (
    ui === "validation" ||
    ["ready_for_review", "reviewing"].includes(st) ||
    Boolean(String(task?.validation_id || "").trim()) ||
    Boolean(task?.reached_review)
  ) {
    return "AI Review";
  }
  if (
    ui === "restruction" ||
    ["ready_for_analysis", "analyzing"].includes(st) ||
    Boolean(String(task?.restruction_session_id || "").trim()) ||
    Boolean(task?.reached_analysis)
  ) {
    return "尺寸时域";
  }
  if (Number.isFinite(stepNum) && stepNum >= 1) {
    return `步骤 ${Math.min(ORCH_TOTAL_STEPS, stepNum)}/${ORCH_TOTAL_STEPS}`;
  }
  return "";
}

/** 侧栏角标：设计域 / 编排 / 尺寸时域 / AI Review */
function taskSubprocessBadges(task) {
  const ui = String(task?.ui_stage || "").toLowerCase();
  const st = String(task?.status || "").toLowerCase();
  const sid = String(task?.oc4_design_domain_session_id || "").trim();
  const demoAsset = /BESO7/i.test(String(task?.file_name || "")) || /\.fcstd$/i.test(String(task?.file_name || ""));
  const designDomain = Boolean(sid) || ui === "design_domain" || (demoAsset && Boolean(sid));
  const orchestrate =
    ui === "orchestrate" ||
    ui === "flow" ||
    st === "orchestrating" ||
    st === "ready_to_execute" ||
    (st === "running" && (Boolean(task?.job_id) || Boolean(sid) || demoAsset)) ||
    (["completed", "done", "ready_for_analysis", "analyzing", "ready_for_review", "reviewing"].includes(st) &&
      (Boolean(task?.job_id) || demoAsset)) ||
    (demoAsset && (Boolean(task?.job_id) || Boolean(sid)));
  const hasJob = Boolean(String(task?.job_id || "").trim());
  const analysis =
    ui === "restruction" ||
    ["ready_for_analysis", "analyzing", "ready_for_review", "reviewing"].includes(st) ||
    Boolean(String(task?.restruction_session_id || "").trim()) ||
    Boolean(task?.reached_analysis) ||
    (hasJob && ["ready_for_analysis", "analyzing", "ready_for_review", "reviewing", "completed", "done"].includes(st));
  // 与尺寸时域同期露出，避免分析中面板缺第四枚 AI Review 图标
  const review =
    analysis ||
    ui === "validation" ||
    Boolean(String(task?.validation_id || "").trim()) ||
    Boolean(task?.reached_review) ||
    ["ready_for_review", "reviewing"].includes(st) ||
    (hasJob && ["ready_for_review", "reviewing", "completed", "done"].includes(st));
  return { designDomain, orchestrate, analysis, review };
}

/** 是否已进入子流程/工具链（设计域、编排、分步流或已有计算 Job）；否则视为仅主对话 */
export function taskEnteredToolSubflow(task) {
  if (String(task?.job_id || "").trim()) return true;
  const { designDomain, orchestrate, analysis, review } = taskSubprocessBadges(task);
  return Boolean(designDomain || orchestrate || analysis || review);
}

export function createTaskManager(deps) {
  const {
    refs,
    state,
    normalizedBaseUrl,
    onOpenTask,
    onTasksListUpdated,
    onBeforeSelectTask,
    onTaskBadgeClick,
    onOpenTaskWorkDir,
    onTaskRemoved,
  } = deps;

  function taskProgressByStep(step) {
    const n = Number(step);
    if (!Number.isFinite(n) || n <= 1) return 25;
    if (n === 2) return 50;
    if (n === 3) return 75;
    if (n >= 4) return 100;
    return 25;
  }

  async function upsertTask(patch = {}, opts = {}) {
    const taskIdOverride = String(opts.taskId || "").trim() || null;
    const tid = taskIdOverride || state.currentTaskId;
    if (!tid) return;
    const keys = [
      "title",
      "progress",
      "step",
      "status",
      "file_name",
      "file_id",
      "job_id",
      "scan_dir",
      "ui_stage",
      "oc4_design_domain_session_id",
      "oc4_activity",
      "restruction_session_id",
      "validation_id",
      "reached_analysis",
      "reached_review",
      "assistant_thread",
      "landing_session_digest",
    ];
    const body = { task_id: tid };
    for (const k of keys) {
      if (patch[k] !== undefined) body[k] = patch[k];
    }
    if (opts.allowSidebarReorder === true) {
      body.allow_sidebar_reorder = true;
    }
    const pk = Object.keys(patch);
    const onlyStagePersist =
      pk.length > 0 &&
      pk.every((k) =>
        [
          "ui_stage",
          "oc4_design_domain_session_id",
          "oc4_activity",
          "assistant_thread",
          "landing_session_digest",
        ].includes(k),
      );
    if (!onlyStagePersist) {
      if (body.title === undefined) {
        // Never auto-promote long orchestration prompts as task title during BESO7 demo
        if (!window.__beso7DemoActive) {
          const fromUi = String(refs.msgLanding?.value || refs.msgEl?.value || "").trim();
          if (fromUi && !/^【全流程演示】/.test(fromUi) && fromUi.length < 48) {
            body.title = fromUi.slice(0, 80);
          }
        }
      }
      if (body.file_name === undefined) body.file_name = patch.file_name ?? state.currentFileName ?? undefined;
      if (body.file_id === undefined) body.file_id = patch.file_id ?? state.currentFileId ?? undefined;
      if (body.job_id === undefined) body.job_id = patch.job_id ?? state.jobId ?? undefined;
      if (body.scan_dir === undefined) body.scan_dir = patch.scan_dir ?? state.uploadedSourceDir ?? undefined;
    }
    try {
      const resp = await fetch(`${normalizedBaseUrl()}/api/tasks/upsert`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        const t = await resp.text();
        let detail = t;
        try {
          const j = JSON.parse(t);
          if (j && j.detail != null) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
        } catch {
          /* keep t */
        }
        console.error("tasks/upsert failed", resp.status, detail);
      }
    } catch (e) {
      console.error("tasks/upsert fetch error", e);
    }
  }

  async function removeTask(taskId) {
    try {
      const r = await fetch(`${normalizedBaseUrl()}/api/tasks/${encodeURIComponent(taskId)}`, { method: "DELETE" });
      if (r.ok) {
        try {
          onTaskRemoved?.(taskId);
        } catch {
          /* ignore */
        }
      }
    } catch {
      /* ignore */
    }
    if (state.currentTaskId === taskId) {
      state.currentTaskId = null;
      state.jobId = null;
      if (refs.jobIdEl) refs.jobIdEl.textContent = "(未启动)";
      if (refs.statusEl) refs.statusEl.textContent = "-";
    }
    await loadTasks();
  }

  async function renameTask(taskId, title) {
    const clean = String(title || "").trim();
    if (!clean) return;
    try {
      const resp = await fetch(`${normalizedBaseUrl()}/api/tasks/upsert`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task_id: taskId, title: clean }),
      });
      if (!resp.ok) {
        const t = await resp.text();
        console.error("tasks/upsert (rename) failed", resp.status, t.slice(0, 500));
      }
    } catch (e) {
      console.error("tasks/upsert (rename) fetch error", e);
    }
  }

  let renameDialogWired = false;
  let renameTargetId = "";

  function wireRenameDialogOnce() {
    if (renameDialogWired) return;
    const dlg = refs.taskRenameDialog;
    const input = refs.taskRenameInput;
    const save = refs.taskRenameSave;
    const cancel = refs.taskRenameCancel;
    if (!dlg || !input || !save || !cancel) return;
    renameDialogWired = true;
    cancel.addEventListener("click", () => {
      dlg.close();
    });
    save.addEventListener("click", async () => {
      const next = String(input.value || "").trim();
      if (!next || !renameTargetId) {
        dlg.close();
        return;
      }
      await renameTask(renameTargetId, next);
      dlg.close();
      await loadTasks();
    });
    dlg.addEventListener("close", () => {
      renameTargetId = "";
    });
  }

  function openRenameDialog(taskId, currentTitle) {
    wireRenameDialogOnce();
    const dlg = refs.taskRenameDialog;
    const input = refs.taskRenameInput;
    if (!dlg || !input) {
      const next = window.prompt("请输入新的任务名称", String(currentTitle || "对话任务"));
      if (next == null || !String(next).trim()) return;
      renameTask(taskId, next).then(() => loadTasks());
      return;
    }
    renameTargetId = taskId;
    input.value = String(currentTitle || "");
    dlg.showModal();
    queueMicrotask(() => {
      try {
        input.focus();
        input.select();
      } catch {
        input.focus();
      }
    });
  }

  function lastOc4ActivitySnippet(raw) {
    const arr = Array.isArray(raw) ? raw : [];
    for (let i = arr.length - 1; i >= 0; i -= 1) {
      const x = arr[i];
      if (x && String(x.text || "").trim()) {
        return String(x.text).replace(/\s+/g, " ").trim().slice(0, 100);
      }
    }
    return "";
  }

  /** 与「展示/顺序」相关的字段（不含 updated_at），用于避免仅时间戳变化时整表重绘闪烁 */
  let _lastTaskListShapeSig = "";

  function taskRowShape(t) {
    const oc4Snip = lastOc4ActivitySnippet(t.oc4_activity);
    return [
      String(t.task_id || ""),
      String(t.title || ""),
      String(t.status || ""),
      String(t.step ?? ""),
      String(t.progress ?? ""),
      String(t.job_id || ""),
      String(t.ui_stage || ""),
      String(t.oc4_design_domain_session_id || ""),
      String(t.file_name || ""),
      oc4Snip,
    ].join("\x1e");
  }

  function orderShapeSig(items) {
    return (items || []).map(taskRowShape).join("\x1f");
  }

  let _cachedTaskItems = [];

  function taskSearchHaystack(t) {
    const display = taskListDisplayTitle(t);
    const stLabel = formatTaskStatus(t.status).label;
    const oc4 = lastOc4ActivitySnippet(t.oc4_activity);
    const pieces = [
      display,
      t?.title,
      t?.file_name,
      t?.task_id,
      t?.status,
      t?.scan_dir,
      t?.job_id,
      t?.ui_stage,
      oc4,
      stLabel,
    ];
    return pieces.map((x) => String(x || "").toLowerCase()).join("\n");
  }

  function taskMatchesQuery(t, q) {
    if (!q) return true;
    return taskSearchHaystack(t).includes(q);
  }

  function applySearchFilter(items, qRaw) {
    const q = String(qRaw || "").trim().toLowerCase();
    if (!q) return (items || []).slice();
    let filtered = (items || []).filter((t) => taskMatchesQuery(t, q));
    const cur = String(state.currentTaskId || "").trim();
    if (cur && q) {
      const has = filtered.some((t) => String(t.task_id || "").trim() === cur);
      if (!has) {
        const pinned = (items || []).find((x) => String(x.task_id || "").trim() === cur);
        if (pinned) filtered = [pinned, ...filtered];
      }
    }
    return filtered;
  }

  function patchTaskListActiveAndTimes(listEl, items, activeTaskId) {
    const byId = new Map(
      (items || []).map((t) => [String(t.task_id || "").trim(), t]).filter((e) => e[0]),
    );
    const aid = String(activeTaskId || "").trim();
    listEl.querySelectorAll(".taskItem[data-task-id]").forEach((row) => {
      const id = String(row.dataset.taskId || "").trim();
      const t = byId.get(id);
      if (!t) return;
      row.classList.toggle("active", Boolean(aid && id === aid));
      const timeStr = formatTaskTime(t.updated_at || t.created_at);
      row.querySelectorAll(".taskItemTime").forEach((el) => {
        el.textContent = timeStr;
      });
    });
  }

  function renderTaskList(items) {
    if (!refs.taskListEl) return;
    const rawItems = Array.isArray(items) ? items : [];
    _cachedTaskItems = rawItems.slice();

    if (!rawItems.length) {
      _lastTaskListShapeSig = "";
      refs.taskListEl.innerHTML = "";
      const wrap = document.createElement("div");
      wrap.className = "taskListEmpty";
      wrap.innerHTML = `
        <div class="taskListEmptyTitle">暂无任务记录</div>
        <p class="taskListEmptyDesc">上传文件并运行流程后，任务会出现在此侧栏。</p>
        <button type="button" class="btn taskListEmptyRefresh" id="taskListEmptyRefresh">刷新列表</button>
      `;
      refs.taskListEl.appendChild(wrap);
      wrap.querySelector("#taskListEmptyRefresh")?.addEventListener("click", () => loadTasks().catch(() => {}));
      return;
    }

    const q = String(refs.taskSearchInput?.value || "").trim().toLowerCase();
    const filtered = applySearchFilter(rawItems, q);

    if (q && !filtered.length) {
      _lastTaskListShapeSig = "";
      refs.taskListEl.innerHTML = "";
      const wrap = document.createElement("div");
      wrap.className = "taskListEmpty taskListEmpty--search";
      const qDisp = String(refs.taskSearchInput?.value || "").trim();
      wrap.innerHTML = `
        <div class="taskListEmptyTitle">未找到匹配任务</div>
        <p class="taskListEmptyDesc">没有任务与「<span class="taskListEmptyQuery">${escapeHtml(qDisp)}</span>」相符。可换个关键词，或清除搜索后查看全部任务。</p>
        <button type="button" class="btn taskListEmptyRefresh" id="taskSearchEmptyClear">清除搜索</button>
      `;
      refs.taskListEl.appendChild(wrap);
      wrap.querySelector("#taskSearchEmptyClear")?.addEventListener("click", () => {
        if (refs.taskSearchInput) refs.taskSearchInput.value = "";
        if (refs.taskSearchClear) refs.taskSearchClear.hidden = true;
        renderTaskList(_cachedTaskItems);
      });
      return;
    }

    const nextSig = `${orderShapeSig(rawItems)}|q:${q}`;
    const rowCount = refs.taskListEl.querySelectorAll(".taskItem[data-task-id]").length;
    if (
      nextSig === _lastTaskListShapeSig &&
      _lastTaskListShapeSig &&
      rowCount === filtered.length &&
      rowCount > 0
    ) {
      patchTaskListActiveAndTimes(refs.taskListEl, filtered, String(state.currentTaskId || "").trim());
      return;
    }
    _lastTaskListShapeSig = nextSig;
    refs.taskListEl.innerHTML = "";
    filtered.forEach((t) => {
      const stRaw = String(t.status || "").toLowerCase();
      const isTerminal = ["completed", "done", "failed", "cancelled", "missing"].includes(stRaw);
      const enteredTool = taskEnteredToolSubflow(t);
      const st =
        !enteredTool && !isTerminal ? { label: "对话中", tone: "live" } : formatTaskStatus(t.status);
      const stepNum = Number(t.step);
      const showStepBadge =
        enteredTool ||
        (isTerminal &&
          (Boolean(String(t.job_id || "").trim()) ||
            (Number.isFinite(stepNum) && stepNum >= 2)));
      const stepLabel = showStepBadge ? formatTaskStepLabel(t) || "步骤 —" : "";
      const oc4Note = lastOc4ActivitySnippet(t.oc4_activity);
      const timeStr = formatTaskTime(t.updated_at || t.created_at);
      const rawTitle = String(t.title || "").trim();
      const displayTitle = taskListDisplayTitle(t);
      const titleDerived = taskIsGenericTitle(rawTitle);
      const { designDomain: hasDd, orchestrate: hasOrb, analysis: hasAna, review: hasRev } =
        taskSubprocessBadges(t);
      const svgDd =
        '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3z"/><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5"/></svg>';
      const svgOrb =
        '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="6" r="2"/><circle cx="6" cy="16" r="2"/><circle cx="18" cy="16" r="2"/><path d="M12 8v4M10.2 14.2l-2.5 1.4m6.1-1.4l2.5 1.4"/></svg>';
      const svgAna =
        '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 19V5"/><path d="M4 19h16"/><path d="M8 15l3-4 3 2 4-6"/></svg>';
      const svgRev =
        '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="1"/><path d="M9 13l2.2 2.2L16 10.4"/></svg>';
      const svgRename =
        '<svg class="taskIconSvg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>';
      const svgDelete =
        '<svg class="taskIconSvg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18"/><path d="M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6"/><path d="M10 11v6M14 11v6"/></svg>';
      const svgFolder =
        '<svg class="taskIconSvg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>';
      const badgeHtml =
        hasDd || hasOrb || hasAna || hasRev
          ? `<div class="taskItemBadgeRow" role="group" aria-label="子流程快捷入口">
          ${
            hasDd
              ? `<button type="button" class="taskBadgeBtn taskBadgeBtn--dd" data-task-badge="design_domain" title="进入设计域">${svgDd}</button>`
              : ""
          }
          ${
            hasOrb
              ? `<button type="button" class="taskBadgeBtn taskBadgeBtn--orc" data-task-badge="orchestrate" title="进入构型优化编排 / 拓扑流程">${svgOrb}</button>`
              : ""
          }
          ${
            hasAna
              ? `<button type="button" class="taskBadgeBtn taskBadgeBtn--ana" data-task-badge="restruction" title="进入尺寸时域分析">${svgAna}</button>`
              : ""
          }
          ${
            hasRev
              ? `<button type="button" class="taskBadgeBtn taskBadgeBtn--rev" data-task-badge="validation" title="进入 AI Review">${svgRev}</button>`
              : ""
          }
        </div>`
          : "";
      const row = document.createElement("div");
      row.className = `taskItem${t.task_id === state.currentTaskId ? " active" : ""}`;
      row.dataset.taskId = String(t.task_id || "");
      row.setAttribute("role", "listitem");
      row.setAttribute("tabindex", "0");
      row.setAttribute("aria-label", `打开任务：${displayTitle}`);
      const chatOnlyLayout = !enteredTool && !isTerminal;
      const showProgressBar = showStepBadge;
      const titleClass = `taskItemTitle${titleDerived ? " taskItemTitle--derived" : ""}`;
      const scanDirTrim = String(t.scan_dir || "").trim();
      const folderBtn = scanDirTrim
        ? `<button type="button" class="taskIconBtn taskOpenFolder" title="在资源管理器中打开该任务工作目录" aria-label="打开工作目录">${svgFolder}</button>`
        : "";
      const stepRowHtml = stepLabel
        ? `<div class="taskItemStepRow"><span class="taskItemStepBadge">${escapeHtml(stepLabel)}</span></div>`
        : "";
      const oc4Html = oc4Note
        ? `<div class="taskItemOc4" title="${escapeHtml(oc4Note)}"><span class="taskItemOc4Prefix">OC4</span><span class="taskItemOc4Text">${escapeHtml(oc4Note)}</span></div>`
        : "";
      const extraBlock = chatOnlyLayout
        ? ""
        : `<div class="taskItemExtra">
        ${stepRowHtml}
        ${oc4Html}
        ${badgeHtml}
        <div class="taskProgress${showProgressBar ? "" : " taskProgress--hidden"}" aria-hidden="true"><span style="width:${Math.max(0, Math.min(100, Number(t.progress || 0)))}%"></span></div>
      </div>`;
      if (!chatOnlyLayout) row.classList.add("taskItem--hasExtra");
      row.innerHTML = `
        <div class="taskItemTop">
          <div class="${titleClass}">${escapeHtml(displayTitle)}</div>
          <span class="taskStatusPill taskStatus--${st.tone}">${escapeHtml(st.label)}</span>
        </div>
        ${extraBlock}
        <div class="taskItemFoot">
          <span class="taskItemTime">${escapeHtml(timeStr)}</span>
          <div class="taskItemFootActions" role="toolbar" aria-label="任务操作">
            ${folderBtn}
            <button type="button" class="taskIconBtn taskRename" title="重命名任务" aria-label="重命名任务">${svgRename}</button>
            <button type="button" class="taskIconBtn taskDelete" title="删除任务" aria-label="删除任务">${svgDelete}</button>
          </div>
        </div>
      `;
      row.querySelector(".taskDelete")?.addEventListener("click", async (e) => {
        e.stopPropagation();
        if (!window.confirm("确定删除该任务？此操作无法撤销。")) return;
        await removeTask(t.task_id);
      });
      row.querySelector(".taskRename")?.addEventListener("click", async (e) => {
        e.stopPropagation();
        openRenameDialog(t.task_id, rawTitle || displayTitle);
      });
      row.querySelector(".taskOpenFolder")?.addEventListener("click", async (e) => {
        e.stopPropagation();
        if (!onOpenTaskWorkDir) return;
        try {
          await onOpenTaskWorkDir(t);
        } catch {
          /* ignore */
        }
      });
      row.querySelectorAll("[data-task-badge]").forEach((btn) => {
        btn.addEventListener("click", async (e) => {
          e.stopPropagation();
          e.preventDefault();
          const kind = btn.getAttribute("data-task-badge");
          if (!kind || !onTaskBadgeClick) return;
          try {
            await onTaskBadgeClick(t, kind);
          } catch {
            /* ignore */
          }
        });
      });
      row.addEventListener("click", async (ev) => {
        if (ev.target?.closest?.("button")) return;
        const tid = String(t.task_id || "").trim();
        const list = refs.taskListEl;
        if (list) {
          list.querySelectorAll(".taskItem").forEach((n) => n.classList.remove("active"));
          row.classList.add("active");
        }
        try {
          await onBeforeSelectTask?.(tid);
        } catch {
          /* ignore */
        }
        state.currentTaskId = tid;
        state.jobId = t.job_id || null;
        state.uploadedSourceDir = t.scan_dir || "";
        state.currentFileName = t.file_name || "";
        state.currentFileId = t.file_id || null;
        await onOpenTask?.(t);
      });
      row.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          row.click();
        }
      });
      refs.taskListEl.appendChild(row);
    });
  }

  async function loadTasks() {
    if (!refs.taskListEl) return;
    refs.taskListEl.setAttribute("aria-busy", "true");
    let items = [];
    try {
      const resp = await fetch(`${normalizedBaseUrl()}/api/tasks`);
      const data = await resp.json();
      items = data.items || [];
      renderTaskList(items);
    } catch {
      renderTaskList([]);
      items = [];
    } finally {
      refs.taskListEl.removeAttribute("aria-busy");
      try {
        onTasksListUpdated?.(items);
      } catch {
        /* ignore */
      }
    }
  }

  return {
    upsertTask,
    loadTasks,
    taskProgressByStep,
    reapplyTaskSearchFilter: () => renderTaskList(_cachedTaskItems),
    getCachedTaskItems: () => _cachedTaskItems.slice(),
  };
}
