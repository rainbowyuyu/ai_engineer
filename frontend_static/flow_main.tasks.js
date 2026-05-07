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

export function createTaskManager(deps) {
  const { refs, state, normalizedBaseUrl, onOpenTask } = deps;

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

  async function upsertTask(patch = {}) {
    if (!state.currentTaskId) return;
    const keys = ["title", "progress", "step", "status", "file_name", "job_id", "scan_dir", "ui_stage", "oc4_design_domain_session_id"];
    const body = { task_id: state.currentTaskId };
    for (const k of keys) {
      if (patch[k] !== undefined) body[k] = patch[k];
    }
    const pk = Object.keys(patch);
    const onlyStagePersist =
      pk.length > 0 && pk.every((k) => k === "ui_stage" || k === "oc4_design_domain_session_id");
    if (!onlyStagePersist) {
      if (body.title === undefined) {
        body.title = String(refs.msgLanding?.value || refs.msgEl?.value || "未命名任务").slice(0, 80);
      }
      if (body.file_name === undefined) body.file_name = patch.file_name ?? state.currentFileName ?? undefined;
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
    await fetch(`${normalizedBaseUrl()}/api/tasks/${encodeURIComponent(taskId)}`, { method: "DELETE" });
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
        <div class="taskProgress" aria-hidden="true"><span style="width:${Math.max(0, Math.min(100, Number(t.progress || 0)))}%"></span></div>
        <div class="taskActions">
          <button type="button" class="taskIconBtn taskRename" title="重命名">✎</button>
          <button type="button" class="taskIconBtn taskDelete" title="删除">🗑</button>
        </div>
      `;
      row.querySelector(".taskDelete")?.addEventListener("click", async (e) => {
        e.stopPropagation();
        await removeTask(t.task_id);
      });
      row.querySelector(".taskRename")?.addEventListener("click", async (e) => {
        e.stopPropagation();
        openRenameDialog(t.task_id, t.title);
      });
      row.addEventListener("click", async (ev) => {
        if (ev.target?.closest?.("button")) return;
        state.currentTaskId = t.task_id;
        state.jobId = t.job_id || null;
        state.uploadedSourceDir = t.scan_dir || "";
        state.currentFileName = t.file_name || "";
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
    try {
      const resp = await fetch(`${normalizedBaseUrl()}/api/tasks`);
      const data = await resp.json();
      renderTaskList(data.items || []);
    } catch {
      renderTaskList([]);
    } finally {
      refs.taskListEl.removeAttribute("aria-busy");
    }
  }

  return {
    upsertTask,
    loadTasks,
    taskProgressByStep,
  };
}
