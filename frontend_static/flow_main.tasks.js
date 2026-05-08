function escapeHtml(s) {
  return String(s || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

/** @param {string} status */
export function formatTaskStatus(status) {
  const st = String(status || "").toLowerCase();
  const map = {
    uploaded: { label: "已上传", tone: "info" },
    orchestrating: { label: "编排中", tone: "progress" },
    ready_to_execute: { label: "待执行", tone: "ready" },
    running: { label: "运行中", tone: "progress" },
    completed: { label: "已完成", tone: "ok" },
    done: { label: "已完成", tone: "ok" },
    failed: { label: "失败", tone: "bad" },
    cancelled: { label: "已取消", tone: "muted" },
    missing: { label: "无记录", tone: "muted" },
    pending: { label: "排队中", tone: "progress" },
    queued: { label: "排队中", tone: "progress" },
  };
  if (map[st]) return map[st];
  if (!st) return { label: "-", tone: "muted" };
  return { label: status || "-", tone: "muted" };
}

/** 侧栏角标：是否曾进入设计域 / 编排或拓扑分步流 */
function taskSubprocessBadges(task) {
  const ui = String(task?.ui_stage || "").toLowerCase();
  const st = String(task?.status || "").toLowerCase();
  const sid = String(task?.oc4_design_domain_session_id || "").trim();
  const designDomain = Boolean(sid) || ui === "design_domain";
  const orchestrate =
    ui === "orchestrate" ||
    ui === "flow" ||
    st === "orchestrating" ||
    st === "ready_to_execute" ||
    (st === "running" && Boolean(task?.job_id));
  return { designDomain, orchestrate };
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
    onTaskRemoved,
  } = deps;

  function formatTaskTime(v) {
    if (!v) return "-";
    const d = new Date(v);
    if (Number.isNaN(d.getTime())) return String(v);
    return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  }

  function taskProgressByStep(step) {
    if (step <= 1) return 25;
    if (step === 2) return 55;
    if (step === 3) return 80;
    return 100;
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
      "assistant_thread",
      "landing_session_digest",
    ];
    const body = { task_id: tid };
    for (const k of keys) {
      if (patch[k] !== undefined) body[k] = patch[k];
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
        const fromUi = String(refs.msgLanding?.value || refs.msgEl?.value || "").trim();
        if (fromUi) body.title = fromUi.slice(0, 80);
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
      const next = window.prompt("请输入新的任务名称", String(currentTitle || "未命名任务"));
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

  function renderTaskList(items) {
    if (!refs.taskListEl) return;
    refs.taskListEl.innerHTML = "";
    if (!items.length) {
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
    items.forEach((t) => {
      const st = formatTaskStatus(t.status);
      const stepNum = Number(t.step);
      const stepLabel = Number.isFinite(stepNum) && stepNum >= 1 && stepNum <= 4 ? `步骤 ${stepNum}/4` : "步骤 —";
      const oc4Note = lastOc4ActivitySnippet(t.oc4_activity);
      const { designDomain: hasDd, orchestrate: hasOrb } = taskSubprocessBadges(t);
      const svgDd =
        '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3z"/><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5"/></svg>';
      const svgOrb =
        '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="6" r="2"/><circle cx="6" cy="16" r="2"/><circle cx="18" cy="16" r="2"/><path d="M12 8v4M8 15l-2 1m10-1l2 1"/></svg>';
      const svgRename =
        '<svg class="taskIconSvg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>';
      const svgDelete =
        '<svg class="taskIconSvg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18"/><path d="M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6"/><path d="M10 11v6M14 11v6"/></svg>';
      const badgeHtml =
        hasDd || hasOrb
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
        </div>`
          : "";
      const row = document.createElement("div");
      row.className = `taskItem${t.task_id === state.currentTaskId ? " active" : ""}`;
      row.setAttribute("role", "listitem");
      row.setAttribute("tabindex", "0");
      row.setAttribute("aria-label", `打开任务：${t.title || "未命名任务"}`);
      row.innerHTML = `
        <div class="taskItemTop">
          <div class="taskItemTitle">${escapeHtml(t.title || "未命名任务")}</div>
          <span class="taskStatusPill taskStatus--${st.tone}">${escapeHtml(st.label)}</span>
        </div>
        <div class="taskItemMetaRow">
          <span class="taskItemStepBadge">${escapeHtml(stepLabel)}</span>
          <span class="taskItemTime">${escapeHtml(formatTaskTime(t.updated_at || t.created_at))}</span>
        </div>
        ${oc4Note ? `<div class="taskItemOc4" title="${escapeHtml(oc4Note)}">OC4：${escapeHtml(oc4Note)}</div>` : ""}
        ${badgeHtml}
        <div class="taskProgress" aria-hidden="true"><span style="width:${Math.max(0, Math.min(100, Number(t.progress || 0)))}%"></span></div>
        <div class="taskActions" role="toolbar" aria-label="任务操作">
          <button type="button" class="taskIconBtn taskRename" title="重命名任务" aria-label="重命名任务">${svgRename}</button>
          <span class="taskActionsSpacer" aria-hidden="true"></span>
          <button type="button" class="taskIconBtn taskDelete" title="删除任务" aria-label="删除任务">${svgDelete}</button>
        </div>
      `;
      row.querySelector(".taskDelete")?.addEventListener("click", async (e) => {
        e.stopPropagation();
        if (!window.confirm("确定删除该任务？此操作无法撤销。")) return;
        await removeTask(t.task_id);
      });
      row.querySelector(".taskRename")?.addEventListener("click", async (e) => {
        e.stopPropagation();
        openRenameDialog(t.task_id, t.title);
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
        try {
          await onBeforeSelectTask?.(t.task_id);
        } catch {
          /* ignore */
        }
        state.currentTaskId = t.task_id;
        state.jobId = t.job_id || null;
        state.uploadedSourceDir = t.scan_dir || "";
        state.currentFileName = t.file_name || "";
        state.currentFileId = t.file_id || null;
        await onOpenTask?.(t);
        await loadTasks();
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
  };
}
