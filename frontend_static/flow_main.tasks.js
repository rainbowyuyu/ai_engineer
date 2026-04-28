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
    const body = {
      task_id: state.currentTaskId,
      title: patch.title || (refs.msgLanding?.value || refs.msgEl?.value || "未命名任务").slice(0, 80),
      progress: patch.progress,
      step: patch.step,
      status: patch.status,
      file_name: patch.file_name ?? (state.currentFileName || undefined),
      job_id: patch.job_id ?? (state.jobId || undefined),
      scan_dir: patch.scan_dir ?? (state.uploadedSourceDir || undefined),
    };
    await fetch(`${normalizedBaseUrl()}/api/tasks/upsert`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
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
    await fetch(`${normalizedBaseUrl()}/api/tasks/upsert`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_id: taskId, title: clean }),
    });
  }

  function renderTaskList(items) {
    if (!refs.taskListEl) return;
    refs.taskListEl.innerHTML = "";
    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "fieldLabel";
      empty.textContent = "暂无任务记录";
      refs.taskListEl.appendChild(empty);
      return;
    }
    items.forEach((t) => {
      const row = document.createElement("div");
      row.className = `taskItem${t.task_id === state.currentTaskId ? " active" : ""}`;
      row.innerHTML = `
        <div class="taskItemTitle">${t.title || "未命名任务"}</div>
        <div class="taskItemMeta"><span>${t.status || "-"}</span><span>${formatTaskTime(t.updated_at || t.created_at)}</span></div>
        <div class="taskProgress"><span style="width:${Math.max(0, Math.min(100, Number(t.progress || 0)))}%"></span></div>
        <div class="taskActions">
          <button class="taskRename" data-rename="${t.task_id}">重命名</button>
          <button class="taskDelete" data-del="${t.task_id}">删除</button>
        </div>
      `;
      row.addEventListener("click", async () => {
        state.currentTaskId = t.task_id;
        state.jobId = t.job_id || null;
        state.uploadedSourceDir = t.scan_dir || "";
        state.currentFileName = t.file_name || "";
        await onOpenTask?.(t);
        await loadTasks();
      });
      row.querySelector("[data-del]")?.addEventListener("click", async (e) => {
        e.stopPropagation();
        await removeTask(t.task_id);
      });
      row.querySelector("[data-rename]")?.addEventListener("click", async (e) => {
        e.stopPropagation();
        const next = window.prompt("请输入新的任务名称", String(t.title || "未命名任务"));
        if (next == null) return;
        if (!String(next).trim()) return;
        await renameTask(t.task_id, next);
        await loadTasks();
      });
      refs.taskListEl.appendChild(row);
    });
  }

  async function loadTasks() {
    const resp = await fetch(`${normalizedBaseUrl()}/api/tasks`);
    const data = await resp.json();
    renderTaskList(data.items || []);
  }

  return {
    upsertTask,
    loadTasks,
    taskProgressByStep,
  };
}
