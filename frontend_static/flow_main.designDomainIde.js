/**
 * 设计域三栏：文件树、多文件标签、源码/预览切换、可编辑保存、Plan 状态。
 */
import { createDdIdePreview3d } from "./flow_main.ddIdePreview3d.js";
import { markdownLiteToHtml } from "./flow_markdownLite.js";
import {
  extToHljsLang,
  extWantsPlainPreview,
  highlightCodeToHtml,
  pathWantsRichPreview,
  plainCodeBlockHtml,
  wrapCodePreviewChrome,
} from "./flow_codePreviewHl.js";

function extOf(name) {
  const i = String(name || "").lastIndexOf(".");
  return i >= 0 ? String(name).slice(i).toLowerCase() : "";
}

function runsSessionFileUrl(normalizedBaseUrl, sessionId, relPath) {
  const base = String(normalizedBaseUrl?.() || "").replace(/\/+$/, "");
  const sid = encodeURIComponent(String(sessionId || "").trim());
  const parts = String(relPath || "")
    .replace(/\\/g, "/")
    .replace(/^\/+/, "")
    .split("/")
    .filter(Boolean)
    .map((p) => encodeURIComponent(p));
  return `${base}/runs/_design_domain/${sid}/${parts.join("/")}`;
}

function tabTitle(rel) {
  const p = String(rel || "").split("/").filter(Boolean);
  return p.length ? p[p.length - 1] : rel;
}

/**
 * @param {object} opts
 * @param {() => string} opts.getSessionId
 * @param {() => string} [opts.getTaskId]
 * @param {() => string} opts.normalizedBaseUrl
 * @param {HTMLElement | null | undefined} opts.fileTreeEl
 * @param {HTMLElement | null | undefined} opts.fileHintEl
 * @param {HTMLElement | null | undefined} opts.refreshBtn
 * @param {HTMLElement | null | undefined} opts.newFileBtn
 * @param {HTMLElement | null | undefined} opts.fileTabsEl
 * @param {HTMLElement | null | undefined} opts.viewSegEl
 * @param {HTMLElement | null | undefined} opts.panePreview
 * @param {HTMLElement | null | undefined} opts.paneSource
 * @param {HTMLElement | null | undefined} opts.previewCanvasWrap
 * @param {HTMLTextAreaElement | null | undefined} opts.codeEditor
 * @param {HTMLElement | null | undefined} opts.codePathEl
 * @param {HTMLElement | null | undefined} opts.codeMetaEl
 * @param {HTMLElement | null | undefined} opts.planListEl
 * @param {HTMLElement | null | undefined} [opts.planDynListEl] 模型生成步骤列表容器
 * @param {HTMLIFrameElement | null | undefined} [opts.vscodeFrameEl]
 * @param {HTMLElement | null | undefined} [opts.nativeCodeWrapEl]
 * @param {HTMLElement | null | undefined} [opts.previewLabelEl]
 * @param {HTMLElement | null | undefined} [opts.mdPreviewWrapEl]
 * @param {HTMLElement | null | undefined} [opts.mdPreviewEl]
 * @param {HTMLDetailsElement | null | undefined} [opts.tabsMoreDetailsEl]
 * @param {HTMLElement | null | undefined} [opts.tabsMoreDropdownEl]
 * @param {() => void} [opts.onShowPreview]
 * @param {(rel?: string) => void | Promise<void>} [opts.openSessionExplorer] 打开 runs/_design_domain/&lt;id&gt;[ /rel ]
 * @param {(msg: string) => void} [opts.onWorkspaceToast]
 * @param {(p: { topic: string; phase: string }) => void} [opts.onPlanStateChange] Plan 高亮变化时回调（写入智能体时间线等）
 * @param {() => void} [opts.onClearDynamicPlan] 关闭模型动态步骤列表、恢复静态四步条时回调（可补全空步骤）
 */
export function mountDesignDomainIde(opts) {
  const {
    getSessionId,
    getTaskId,
    normalizedBaseUrl,
    onShowPreview,
    openSessionExplorer,
    onWorkspaceToast,
    onPlanStateChange,
    onClearDynamicPlan,
    fileTreeEl,
    fileHintEl,
    refreshBtn,
    newFileBtn,
    fileTabsEl,
    viewSegEl,
    panePreview,
    paneSource,
    previewCanvasWrap,
    codeEditor,
    codePathEl,
    codeMetaEl,
    planListEl,
    planDynListEl,
    vscodeFrameEl,
    nativeCodeWrapEl,
    previewLabelEl,
    mdPreviewWrapEl,
    mdPreviewEl,
    tabsMoreDetailsEl,
    tabsMoreDropdownEl,
  } = opts;

  const workspaceRailEl = fileTreeEl?.closest?.(".ddIdeFileRail") ?? null;

  function toast(msg) {
    try {
      onWorkspaceToast?.(String(msg || ""));
    } catch {
      /* ignore */
    }
  }

  /** @type {string | null} */
  let selectedRel = null;
  /** @type {HTMLButtonElement | null} */
  let selectedTreeBtn = null;
  /** @type {AbortController | null} */
  let fetchAborter = null;

  /** @type {"source" | "preview"} */
  let viewMode = "source";

  /**
   * @typedef {{ rel: string; buffer: string; saved: string; loaded: boolean; isNew?: boolean }} DdOpenTab
   */
  /** @type {DdOpenTab[]} */
  let openTabs = [];
  let activeTabIndex = -1;

  const LS_IDE_TABS = "beso.dd.ideTabs.v1.t";
  /** @type {ReturnType<typeof setTimeout> | null} */
  let _ideTabsPersistTimer = null;
  /** @type {string} */
  let _ideScopedTaskId = "";

  function tabsKey(tid) {
    const t = String(tid || "").trim();
    return t ? `${LS_IDE_TABS}.${t}` : "";
  }

  function flushTabsToStorageForTask(tid) {
    const k = tabsKey(tid);
    if (!k) return;
    try {
      localStorage.setItem(
        k,
        JSON.stringify({
          v: 1,
          rels: openTabs.map((x) => x.rel),
          active: activeTabIndex,
          viewMode,
        }),
      );
    } catch {
      /* ignore */
    }
  }

  function schedulePersistTabs() {
    const tid = String(getTaskId?.() || "").trim();
    if (!tid) return;
    if (_ideTabsPersistTimer) clearTimeout(_ideTabsPersistTimer);
    _ideTabsPersistTimer = setTimeout(() => {
      _ideTabsPersistTimer = null;
      flushTabsToStorageForTask(tid);
    }, 320);
  }

  function persistOpenTabsForTaskId(tid) {
    if (_ideTabsPersistTimer) {
      clearTimeout(_ideTabsPersistTimer);
      _ideTabsPersistTimer = null;
    }
    flushTabsToStorageForTask(String(tid || "").trim());
  }

  const preview3d = createDdIdePreview3d({
    mountEl: previewCanvasWrap || null,
    normalizedBaseUrl,
  });

  const dirtyTopics = new Set();

  function base() {
    return String(normalizedBaseUrl?.() || "").replace(/\/+$/, "");
  }

  async function apiGet(path) {
    const url = `${base()}/api/oc4/design-domain${path}`;
    const resp = await fetch(url, { method: "GET", cache: "no-store" });
    const raw = await resp.text();
    let data = {};
    try {
      data = raw ? JSON.parse(raw) : {};
    } catch {
      data = { detail: raw.slice(0, 500) };
    }
    if (!resp.ok) {
      const d = data.detail;
      const msg = typeof d === "string" ? d : JSON.stringify(data);
      throw new Error(msg || `HTTP ${resp.status}`);
    }
    return data;
  }

  async function apiPostJson(path, body) {
    const url = `${base()}/api/oc4/design-domain${path}`;
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    const raw = await resp.text();
    let data = {};
    try {
      data = raw ? JSON.parse(raw) : {};
    } catch {
      data = { detail: raw.slice(0, 500) };
    }
    if (!resp.ok) {
      const d = data.detail;
      const msg = typeof d === "string" ? d : JSON.stringify(data);
      throw new Error(msg || `HTTP ${resp.status}`);
    }
    return data;
  }

  async function apiDeleteFile(rel) {
    const sid = String(getSessionId?.() || "").trim();
    if (!sid) throw new Error("无会话");
    const q = encodeURIComponent(rel);
    const url = `${base()}/api/oc4/design-domain/session/${encodeURIComponent(sid)}/file?path=${q}`;
    const resp = await fetch(url, { method: "DELETE", cache: "no-store" });
    const raw = await resp.text();
    let data = {};
    try {
      data = raw ? JSON.parse(raw) : {};
    } catch {
      data = { detail: raw.slice(0, 500) };
    }
    if (!resp.ok) {
      const d = data.detail;
      const msg = typeof d === "string" ? d : JSON.stringify(data);
      throw new Error(msg || `HTTP ${resp.status}`);
    }
    return data;
  }

  async function apiPutFile(rel, content) {
    const sid = String(getSessionId?.() || "").trim();
    if (!sid) throw new Error("无会话");
    const url = `${base()}/api/oc4/design-domain/session/${encodeURIComponent(sid)}/file`;
    const resp = await fetch(url, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: rel, content: String(content ?? "") }),
    });
    const raw = await resp.text();
    let data = {};
    try {
      data = raw ? JSON.parse(raw) : {};
    } catch {
      data = { detail: raw.slice(0, 500) };
    }
    if (!resp.ok) {
      const d = data.detail;
      const msg = typeof d === "string" ? d : JSON.stringify(data);
      throw new Error(msg || `HTTP ${resp.status}`);
    }
    return data;
  }

  /** @param {{ path: string, kind: string, size?: number | null }[]} rows */
  function buildTreeNodes(rows) {
    const root = { name: "", children: /** @type {Map<string, any>} */ (new Map()), kind: "dir" };
    for (const row of rows || []) {
      const p = String(row.path || "").replace(/\\/g, "/").replace(/^\/+/, "");
      if (!p) continue;
      const parts = p.split("/").filter(Boolean);
      let cur = root;
      for (let i = 0; i < parts.length; i += 1) {
        const seg = parts[i];
        const isLast = i === parts.length - 1;
        const kind = isLast ? row.kind || "file" : "dir";
        if (!cur.children.has(seg)) {
          cur.children.set(seg, { name: seg, children: new Map(), kind });
        }
        const node = cur.children.get(seg);
        if (isLast && kind === "file") node.kind = "file";
        if (isLast && row.size != null) node.size = row.size;
        cur = node;
      }
    }
    return root;
  }

  function sortEntries(map) {
    return [...map.entries()].sort((a, b) => {
      const [na, ca] = a;
      const [nb, cb] = b;
      const da = ca.kind === "dir";
      const db = cb.kind === "dir";
      if (da !== db) return da ? -1 : 1;
      return na.localeCompare(nb, undefined, { sensitivity: "base" });
    });
  }

  /**
   * @param {any} node
   * @param {string} prefix
   * @param {HTMLElement} ul
   */
  function renderLevel(node, prefix, ul) {
    for (const [name, child] of sortEntries(node.children)) {
      const rel = prefix ? `${prefix}/${name}` : name;
      const li = document.createElement("li");
      li.className = "ddIdeTreeLi";
      li.setAttribute("role", "none");
      if (child.kind === "dir") {
        const details = document.createElement("details");
        details.className = "ddIdeTreeDetails";
        details.open = false;
        const sum = document.createElement("summary");
        sum.className = "ddIdeTreeSummary";
        sum.textContent = name;
        sum.dataset.dirRel = rel;
        sum.setAttribute("role", "treeitem");
        sum.setAttribute("aria-expanded", details.open ? "true" : "false");
        details.addEventListener("toggle", () => {
          sum.setAttribute("aria-expanded", details.open ? "true" : "false");
        });
        const sub = document.createElement("ul");
        sub.className = "ddIdeTreeUl";
        sub.setAttribute("role", "group");
        renderLevel(child, rel, sub);
        details.appendChild(sum);
        details.appendChild(sub);
        li.appendChild(details);
      } else {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "ddIdeTreeFile";
        btn.setAttribute("role", "treeitem");
        btn.dataset.relPath = rel;
        const sz = child.size != null ? ` · ${formatSize(child.size)}` : "";
        btn.textContent = `${name}${sz}`;
        li.appendChild(btn);
      }
      ul.appendChild(li);
    }
  }

  function formatSize(n) {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / (1024 * 1024)).toFixed(2)} MB`;
  }

  function findTreeFileBtn(rel) {
    if (!fileTreeEl) return null;
    for (const b of fileTreeEl.querySelectorAll(".ddIdeTreeFile")) {
      if (b.getAttribute("data-rel-path") === rel) return /** @type {HTMLButtonElement} */ (b);
    }
    return null;
  }

  function setTreeSelection(btn) {
    if (selectedTreeBtn) selectedTreeBtn.classList.remove("ddIdeTreeFile--active");
    selectedTreeBtn = btn;
    if (btn) btn.classList.add("ddIdeTreeFile--active");
  }

  function renderTree(rows) {
    if (!fileTreeEl) return;
    fileTreeEl.innerHTML = "";
    const root = buildTreeNodes(rows);
    const ul = document.createElement("ul");
    ul.className = "ddIdeTreeUl ddIdeTreeUl--root";
    ul.setAttribute("role", "tree");
    renderLevel(root, "", ul);
    fileTreeEl.appendChild(ul);
    if (selectedRel) {
      const b = findTreeFileBtn(selectedRel);
      if (b) {
        setTreeSelection(b);
        try {
          b.scrollIntoView({ block: "nearest" });
        } catch {
          /* ignore */
        }
      }
    }
  }

  async function refreshFileTree() {
    const sid = String(getSessionId?.() || "").trim();
    if (!fileTreeEl) return;
    if (!sid) {
      fileTreeEl.innerHTML = "";
      if (fileHintEl) fileHintEl.textContent = "请先进入设计域会话（上传 IGES 并进入本页）。";
      void refreshVscodeEmbed();
      return;
    }
    if (fileHintEl) {
      fileHintEl.textContent = `会话 ${sid.slice(0, 10)}… 工作区文件；.step / .obj 可在「预览」中 3D 查看。`;
    }
    fetchAborter?.abort();
    fetchAborter = new AbortController();
    try {
      const data = await fetch(`${base()}/api/oc4/design-domain/session/${encodeURIComponent(sid)}/files?max_depth=12`, {
        method: "GET",
        cache: "no-store",
        signal: fetchAborter.signal,
      }).then(async (resp) => {
        const raw = await resp.text();
        let j = {};
        try {
          j = raw ? JSON.parse(raw) : {};
        } catch {
          j = {};
        }
        if (!resp.ok) throw new Error(typeof j.detail === "string" ? j.detail : `HTTP ${resp.status}`);
        return j;
      });
      renderTree(data.files || []);
      if (data.truncated && fileHintEl) {
        fileHintEl.textContent += " 列表已截断（文件过多）。";
      }
      void refreshVscodeEmbed();
    } catch (e) {
      if (e?.name === "AbortError") return;
      fileTreeEl.innerHTML = "";
      const err = document.createElement("p");
      err.className = "ddIdeFileErr";
      err.textContent = String(e?.message || e);
      fileTreeEl.appendChild(err);
      void refreshVscodeEmbed();
    }
  }

  function flushEditorToActiveTab() {
    const tab = activeTabIndex >= 0 ? openTabs[activeTabIndex] : null;
    if (!tab || !codeEditor) return;
    tab.buffer = codeEditor.value;
  }

  function isTabDirty(tab) {
    return tab.buffer !== tab.saved;
  }

  function updateViewSegButtons() {
    if (!viewSegEl) return;
    viewSegEl.dataset.ddView = viewMode;
    for (const b of viewSegEl.querySelectorAll("[data-dd-view-btn]")) {
      const el = /** @type {HTMLButtonElement} */ (b);
      const m = el.getAttribute("data-dd-view-btn");
      const on = (m === "preview" && viewMode === "preview") || (m === "source" && viewMode === "source");
      el.classList.toggle("ddIdeViewSegBtn--active", on);
      el.setAttribute("aria-pressed", on ? "true" : "false");
    }
  }

  /**
   * @param {"preview" | "source"} which
   */
  function setActiveTab(which) {
    viewMode = which === "preview" ? "preview" : "source";
    updateViewSegButtons();
    schedulePersistTabs();
    const preview = viewMode === "preview";
    if (panePreview) {
      panePreview.classList.toggle("hidden", !preview);
      if (preview) {
        panePreview.removeAttribute("hidden");
        queueMicrotask(() => {
          preview3d.resize?.();
          onShowPreview?.();
        });
      } else panePreview.setAttribute("hidden", "true");
    }
    if (paneSource) {
      paneSource.classList.toggle("hidden", preview);
      if (!preview) paneSource.removeAttribute("hidden");
      else paneSource.setAttribute("hidden", "true");
    }
  }

  async function loadFilePreview3d(rel) {
    const sid = String(getSessionId?.() || "").trim();
    if (!sid || !rel) return;
    const ex = extOf(rel);
    const url = runsSessionFileUrl(normalizedBaseUrl, sid, rel);
    if (previewLabelEl) previewLabelEl.textContent = rel;
    if (ex === ".obj") {
      await preview3d.loadObjFromUrl(url);
    } else if (ex === ".step" || ex === ".stp") {
      await preview3d.loadStepFromUrl(url);
    } else {
      throw new Error("不支持的 3D 扩展名");
    }
    preview3d.resize?.();
  }

  /**
   * 选中文件后视图跟随：可预览则切预览并加载；否则源码。无粘滞。
   * @param {{ forceSource?: boolean }} [viewOpt]
   */
  async function applyAutoViewForRel(rel, viewOpt = {}) {
    const r = String(rel || "").trim();
    if (!r) return;
    const vp = previewCanvasWrap?.closest?.(".designDomainViewport");
    const ex = extOf(r);
    const isMd = ex === ".md" || ex === ".markdown";
    const codeLang = extToHljsLang(ex);
    const plainPrev = extWantsPlainPreview(ex);

    if (viewOpt.forceSource) {
      mdPreviewWrapEl?.classList.add("hidden");
      vp?.classList.remove("hidden");
      setActiveTab("source");
      return;
    }

    if (isMd || codeLang || plainPrev) {
      const tab = openTabs.find((t) => t.rel === r);
      if (tab && !tab.loaded && !tab.isNew) await fetchIntoTab(tab);
      if (mdPreviewEl) {
        if (isMd) {
          mdPreviewEl.className = "ddIdeMdPreview mdLiteRoot aeMdSurface";
          mdPreviewEl.innerHTML = markdownLiteToHtml(tab?.buffer || "");
        } else if (codeLang) {
          mdPreviewEl.className = "ddIdeMdPreview ddIdeCodePreviewRoot";
          const inner = await highlightCodeToHtml(tab?.buffer || "", codeLang);
          mdPreviewEl.innerHTML = wrapCodePreviewChrome(r, codeLang, inner);
        } else {
          mdPreviewEl.className = "ddIdeMdPreview ddIdeCodePreviewRoot";
          mdPreviewEl.innerHTML = wrapCodePreviewChrome(r, "plain", plainCodeBlockHtml(tab?.buffer || ""));
        }
      }
      mdPreviewWrapEl?.classList.remove("hidden");
      vp?.classList.add("hidden");
      if (previewLabelEl) previewLabelEl.textContent = isMd ? r : `代码预览 · ${r}`;
      setActiveTab("preview");
      if (codeMetaEl) codeMetaEl.textContent = "";
      return;
    }

    mdPreviewWrapEl?.classList.add("hidden");
    vp?.classList.remove("hidden");

    const is3d = ex === ".obj" || ex === ".step" || ex === ".stp";
    if (!is3d) {
      setActiveTab("source");
      return;
    }
    try {
      await loadFilePreview3d(r);
      setActiveTab("preview");
      if (codeMetaEl) codeMetaEl.textContent = "";
    } catch (e) {
      setActiveTab("source");
      if (codeMetaEl) codeMetaEl.textContent = String(e?.message || e);
    }
  }

  async function fetchIntoTab(tab) {
    const sid = String(getSessionId?.() || "").trim();
    if (!sid || !tab.rel) return;
    if (codeMetaEl) codeMetaEl.textContent = "加载中…";
    try {
      const q = encodeURIComponent(tab.rel);
      const data = await apiGet(`/session/${encodeURIComponent(sid)}/file?path=${q}`);
      tab.buffer = String(data.content ?? "");
      tab.saved = tab.buffer;
      tab.loaded = true;
      if (codeMetaEl) codeMetaEl.textContent = data.size != null ? formatSize(data.size) : "";
    } catch (e) {
      tab.buffer = String(e?.message || e);
      tab.saved = tab.buffer;
      tab.loaded = true;
      if (codeMetaEl) codeMetaEl.textContent = "";
    }
  }

  const MAIN_TAB_MAX = 5;
  let _mdLivePreviewTimer = null;

  function pickVisibleTabIndices() {
    const n = openTabs.length;
    if (n <= MAIN_TAB_MAX) return [...Array(n).keys()];
    const s = new Set();
    if (activeTabIndex >= 0 && activeTabIndex < n) s.add(activeTabIndex);
    for (let i = 0; i < n && s.size < MAIN_TAB_MAX; i++) s.add(i);
    return [...s].sort((a, b) => a - b);
  }

  function buildTabWrap(i) {
    const tab = openTabs[i];
    const wrap = document.createElement("div");
    wrap.className = "ddIdeFileTab" + (i === activeTabIndex ? " ddIdeFileTab--active" : "");
    wrap.setAttribute("role", "presentation");
    wrap.dataset.tabIndex = String(i);

    const main = document.createElement("button");
    main.type = "button";
    main.className = "ddIdeFileTabMain";
    main.setAttribute("role", "tab");
    main.setAttribute("aria-selected", i === activeTabIndex ? "true" : "false");
    const lab = document.createElement("span");
    lab.className = "ddIdeFileTabLabel";
    lab.textContent = tabTitle(tab.rel);
    if (isTabDirty(tab)) lab.classList.add("ddIdeFileTabLabel--dirty");
    main.appendChild(lab);
    main.addEventListener("click", () => {
      void activateTabIndex(i);
    });

    const close = document.createElement("button");
    close.type = "button";
    close.className = "ddIdeFileTabClose";
    close.setAttribute("aria-label", `关闭 ${tabTitle(tab.rel)}`);
    close.textContent = "×";
    close.addEventListener("click", (ev) => {
      ev.stopPropagation();
      void closeTabAt(i);
    });

    wrap.appendChild(main);
    wrap.appendChild(close);
    return wrap;
  }

  function renderFileTabs() {
    if (!fileTabsEl) return;
    fileTabsEl.innerHTML = "";
    if (tabsMoreDropdownEl) tabsMoreDropdownEl.innerHTML = "";
    const n = openTabs.length;
    if (!n) {
      tabsMoreDetailsEl?.classList.add("hidden");
      schedulePersistTabs();
      return;
    }
    const vis = pickVisibleTabIndices();
    const visSet = new Set(vis);
    for (const i of vis) {
      fileTabsEl.appendChild(buildTabWrap(i));
    }
    if (tabsMoreDropdownEl && tabsMoreDetailsEl) {
      for (let i = 0; i < n; i++) {
        if (visSet.has(i)) continue;
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "ddIdeMoreTabBtn";
        btn.textContent = tabTitle(openTabs[i].rel);
        if (isTabDirty(openTabs[i])) btn.classList.add("ddIdeMoreTabBtn--dirty");
        btn.addEventListener("click", () => {
          try {
            tabsMoreDetailsEl.open = false;
          } catch {
            /* ignore */
          }
          void activateTabIndex(i);
        });
        tabsMoreDropdownEl.appendChild(btn);
      }
      tabsMoreDetailsEl.classList.toggle("hidden", n <= MAIN_TAB_MAX);
    }
    schedulePersistTabs();
  }

  async function activateTabIndex(ix, viewOpt = {}) {
    if (ix < 0 || ix >= openTabs.length) return;
    flushEditorToActiveTab();
    activeTabIndex = ix;
    const tab = openTabs[ix];
    selectedRel = tab.rel;
    if (codePathEl) codePathEl.textContent = tab.rel;

    if (!tab.loaded && !tab.isNew) {
      await fetchIntoTab(tab);
    }
    if (codeEditor) {
      codeEditor.value = tab.buffer;
      codeEditor.readOnly = false;
    }
    renderFileTabs();
    const b = findTreeFileBtn(tab.rel);
    if (b) setTreeSelection(b);
    else if (selectedTreeBtn) {
      selectedTreeBtn.classList.remove("ddIdeTreeFile--active");
      selectedTreeBtn = null;
    }
    await applyAutoViewForRel(tab.rel, viewOpt);
  }

  async function closeTabAt(ix) {
    if (ix < 0 || ix >= openTabs.length) return;
    flushEditorToActiveTab();
    const tab = openTabs[ix];
    if (isTabDirty(tab)) {
      try {
        if (String(getSessionId?.() || "").trim()) await apiPutFile(tab.rel, tab.buffer);
        tab.saved = tab.buffer;
      } catch {
        /* keep tab if save fails — user may retry */
        if (codeMetaEl) codeMetaEl.textContent = "关闭前保存失败，请手动保存";
        return;
      }
    }
    openTabs.splice(ix, 1);
    if (!openTabs.length) {
      activeTabIndex = -1;
      selectedRel = null;
      if (codeEditor) {
        codeEditor.value = "";
        codeEditor.placeholder = "在左侧选择或新建文件；支持 Ctrl+S 保存。";
      }
      if (codePathEl) codePathEl.textContent = "未选择文件";
      if (codeMetaEl) codeMetaEl.textContent = "";
      renderFileTabs();
      return;
    }
    const ni = Math.min(ix, openTabs.length - 1);
    activeTabIndex = -1;
    await activateTabIndex(ni);
  }

  /**
   * @param {string} rel
   * @param {{ preferPreview?: boolean }} [opt]
   */
  async function openOrAddTab(rel, opt = {}) {
    const r = String(rel || "").trim().replace(/\\/g, "/");
    if (!r) return;
    let ix = openTabs.findIndex((t) => t.rel === r);
    if (ix < 0) {
      openTabs.push({ rel: r, buffer: "", saved: "", loaded: false, isNew: false });
      ix = openTabs.length - 1;
    }
    await activateTabIndex(ix, { forceSource: opt.preferPreview === false });
  }

  async function saveActiveTab() {
    const tab = activeTabIndex >= 0 ? openTabs[activeTabIndex] : null;
    if (!tab || !String(getSessionId?.() || "").trim()) return;
    flushEditorToActiveTab();
    if (!isTabDirty(tab)) {
      if (codeMetaEl) codeMetaEl.textContent = "已保存";
      return;
    }
    if (codeMetaEl) codeMetaEl.textContent = "保存中…";
    try {
      await apiPutFile(tab.rel, tab.buffer);
      tab.saved = tab.buffer;
      tab.isNew = false;
      if (codeMetaEl) codeMetaEl.textContent = "已保存";
      const at = openTabs[activeTabIndex];
      if (at && mdPreviewEl && viewMode === "preview") {
        const ex0 = extOf(at.rel);
        if (ex0 === ".md" || ex0 === ".markdown") {
          mdPreviewEl.className = "ddIdeMdPreview mdLiteRoot aeMdSurface";
          mdPreviewEl.innerHTML = markdownLiteToHtml(at.buffer);
        } else {
          const lang = extToHljsLang(ex0);
          if (lang) {
            mdPreviewEl.className = "ddIdeMdPreview ddIdeCodePreviewRoot";
            void highlightCodeToHtml(at.buffer || "", lang).then((inner) => {
              mdPreviewEl.innerHTML = wrapCodePreviewChrome(at.rel, lang, inner);
            });
          } else if (extWantsPlainPreview(ex0)) {
            mdPreviewEl.className = "ddIdeMdPreview ddIdeCodePreviewRoot";
            mdPreviewEl.innerHTML = wrapCodePreviewChrome(at.rel, "plain", plainCodeBlockHtml(at.buffer || ""));
          }
        }
      }
      renderFileTabs();
      void refreshFileTree();
    } catch (e) {
      if (codeMetaEl) codeMetaEl.textContent = String(e?.message || e);
    }
  }

  /**
   * @param {string} rel
   * @param {{ preferPreview?: boolean }} [opt]
   */
  async function openRelPath(rel, opt = {}) {
    await openOrAddTab(rel, opt);
  }

  /** @deprecated 兼容旧名 */
  async function loadFileSource(rel) {
    await openOrAddTab(rel, { preferPreview: false });
  }

  async function hydrateTabsForTask(tid) {
    const k = tabsKey(tid);
    if (!k) return;
    let d = null;
    try {
      const raw = localStorage.getItem(k);
      if (raw) d = JSON.parse(raw);
    } catch {
      return;
    }
    if (!d || Number(d.v) !== 1) return;
    const rels = Array.isArray(d.rels) ? d.rels.map((x) => String(x || "").trim()).filter(Boolean) : [];
    if (!rels.length) return;
    for (const rel of rels) {
      await openOrAddTab(rel, { preferPreview: false });
    }
    const ix = Math.min(Math.max(0, Number(d.active) || 0), openTabs.length - 1);
    await activateTabIndex(ix, { forceSource: true });
    const vm = d.viewMode === "preview" || d.viewMode === "source" ? d.viewMode : "source";
    setActiveTab(vm);
  }

  async function switchTaskContext(nextTid) {
    const tid = String(nextTid || "").trim();
    if (!tid) return;
    if (tid === _ideScopedTaskId && openTabs.length) return;
    if (_ideScopedTaskId && _ideScopedTaskId !== tid) persistOpenTabsForTaskId(_ideScopedTaskId);
    _ideScopedTaskId = tid;
    flushEditorToActiveTab();
    openTabs = [];
    activeTabIndex = -1;
    selectedRel = null;
    if (selectedTreeBtn) {
      selectedTreeBtn.classList.remove("ddIdeTreeFile--active");
      selectedTreeBtn = null;
    }
    if (codeEditor) {
      codeEditor.value = "";
      codeEditor.placeholder = "在左侧选择或新建文件；支持 Ctrl+S 保存。";
    }
    if (codePathEl) codePathEl.textContent = "未选择文件";
    if (codeMetaEl) codeMetaEl.textContent = "";
    renderFileTabs();
    await hydrateTabsForTask(tid);
  }

  function setDynamicPlanSteps(steps, rationale) {
    if (!planListEl || !planDynListEl) return;
    planListEl.classList.add("hidden");
    planDynListEl.classList.remove("hidden");
    planDynListEl.innerHTML = "";
    const rat = String(rationale || "").trim();
    if (rat) {
      const li0 = document.createElement("li");
      li0.className = "ddIdePlanItem ddIdePlanItem--rationale";
      const t0 = document.createElement("span");
      t0.className = "ddIdePlanTxt";
      t0.textContent = rat.length > 420 ? `${rat.slice(0, 420)}…` : rat;
      li0.appendChild(t0);
      planDynListEl.appendChild(li0);
    }
    let n = 1;
    for (const st of Array.isArray(steps) ? steps : []) {
      if (!st || typeof st !== "object") continue;
      const li = document.createElement("li");
      const ix = Number(st.id) || n;
      li.className = "ddIdePlanItem ddIdePlanItem--dyn ddIdePlanItem--buildWait";
      li.dataset.ddBuildIx = String(ix);
      const dot = document.createElement("span");
      dot.className = "ddIdePlanDot";
      dot.setAttribute("aria-hidden", "true");
      const tx = document.createElement("span");
      tx.className = "ddIdePlanTxt";
      const title = String(st.title || st.tool || "").trim() || "步骤";
      const tool = String(st.tool || "").trim();
      tx.textContent = `${n}. ${title}`;
      if (tool) {
        const m = document.createElement("span");
        m.className = "mono";
        m.textContent = ` ${tool}`;
        tx.appendChild(m);
      }
      li.appendChild(dot);
      li.appendChild(tx);
      planDynListEl.appendChild(li);
      n += 1;
    }
  }

  function setDynamicPlanStepState(ev) {
    if (!planDynListEl) return;
    const ix = Number(ev.index) || 0;
    const li = planDynListEl.querySelector(`[data-dd-build-ix="${ix}"]`);
    if (!li) return;
    const ph = String(ev.phase || "");
    li.classList.remove("ddIdePlanItem--buildWait", "ddIdePlanItem--buildRun", "ddIdePlanItem--buildDone", "ddIdePlanItem--buildErr");
    if (ph === "start") {
      li.classList.add("ddIdePlanItem--buildRun");
      const ti = String(ev.title || "").trim();
      const tool = String(ev.tool || "").trim();
      if (ti || tool) {
        const tx = li.querySelector(".ddIdePlanTxt");
        if (tx) {
          tx.textContent = "";
          tx.appendChild(document.createTextNode(`${ix}. ${ti || tool}`));
          if (tool && ti) {
            const m = document.createElement("span");
            m.className = "mono";
            m.textContent = ` ${tool}`;
            tx.appendChild(m);
          }
        }
      }
    } else if (ph === "done") {
      li.classList.add(ev.ok === false ? "ddIdePlanItem--buildErr" : "ddIdePlanItem--buildDone");
    }
  }

  function clearDynamicPlan() {
    if (planDynListEl) {
      planDynListEl.classList.add("hidden");
      planDynListEl.innerHTML = "";
    }
    planListEl?.classList.remove("hidden");
    try {
      onClearDynamicPlan?.();
    } catch {
      /* ignore */
    }
  }

  async function refreshVscodeEmbed() {
    if (!vscodeFrameEl || !nativeCodeWrapEl) return;
    const sid = String(getSessionId?.() || "").trim();
    if (!sid) {
      vscodeFrameEl.classList.add("hidden");
      nativeCodeWrapEl.classList.remove("hidden");
      try {
        vscodeFrameEl.removeAttribute("src");
      } catch {
        /* ignore */
      }
      return;
    }
    const base = String(normalizedBaseUrl?.() || "").replace(/\/+$/, "");
    try {
      const r = await fetch(
        `${base}/api/config/editor/session-open?session_id=${encodeURIComponent(sid)}`,
        { cache: "no-store" },
      );
      const d = await r.json().catch(() => ({}));
      if (d?.ok && d.url) {
        vscodeFrameEl.src = String(d.url);
        vscodeFrameEl.classList.remove("hidden");
        nativeCodeWrapEl.classList.add("hidden");
        return;
      }
    } catch {
      /* ignore */
    }
    vscodeFrameEl.classList.add("hidden");
    nativeCodeWrapEl.classList.remove("hidden");
    try {
      vscodeFrameEl.removeAttribute("src");
    } catch {
      /* ignore */
    }
  }

  function syncPlanState({ topic, phase }) {
    if (!planListEl) return;
    const order = ["design", "preview", "mesh", "loads"];
    const items = planListEl.querySelectorAll(".ddIdePlanItem");
    const reapplyDirty = () => {
      items.forEach((li) => {
        const t = li.getAttribute("data-dd-plan");
        if (t && dirtyTopics.has(t)) li.classList.add("ddIdePlanItem--dirty");
        else li.classList.remove("ddIdePlanItem--dirty");
      });
    };
    const notify = () => {
      try {
        onPlanStateChange?.({ topic: String(topic || ""), phase: String(phase || "") });
      } catch {
        /* ignore */
      }
    };
    if (phase === "reset") {
      items.forEach((li) => {
        li.classList.remove("ddIdePlanItem--active", "ddIdePlanItem--done", "ddIdePlanItem--wait");
      });
      reapplyDirty();
      notify();
      return;
    }
    items.forEach((li) => {
      li.classList.remove("ddIdePlanItem--active", "ddIdePlanItem--done", "ddIdePlanItem--wait");
    });
    reapplyDirty();
    const ix = order.indexOf(String(topic || ""));
    if (ix < 0) return;
    if (phase === "open") {
      order.forEach((t, i) => {
        const el = planListEl.querySelector(`[data-dd-plan="${t}"]`);
        if (!el) return;
        if (i < ix) el.classList.add("ddIdePlanItem--done");
        if (i === ix) el.classList.add("ddIdePlanItem--active");
        if (i > ix) el.classList.add("ddIdePlanItem--wait");
      });
      notify();
      return;
    }
    if (phase === "running") {
      order.forEach((t, i) => {
        const el = planListEl.querySelector(`[data-dd-plan="${t}"]`);
        if (!el) return;
        if (i < ix) el.classList.add("ddIdePlanItem--done");
        if (i === ix) el.classList.add("ddIdePlanItem--active");
        if (i > ix) el.classList.add("ddIdePlanItem--wait");
      });
      notify();
      return;
    }
    if (phase === "done") {
      items.forEach((li) => li.classList.remove("ddIdePlanItem--active", "ddIdePlanItem--wait"));
      order.forEach((t, i) => {
        const el = planListEl.querySelector(`[data-dd-plan="${t}"]`);
        if (!el) return;
        if (i <= ix) el.classList.add("ddIdePlanItem--done");
      });
      reapplyDirty();
      notify();
    }
  }

  function markTopicDirty(topic) {
    if (!topic) return;
    dirtyTopics.add(topic);
    const el = planListEl?.querySelector(`[data-dd-plan="${topic}"]`);
    el?.classList.add("ddIdePlanItem--dirty");
  }

  function clearDirtyTopic(topic) {
    dirtyTopics.delete(topic);
    const el = planListEl?.querySelector(`[data-dd-plan="${topic}"]`);
    el?.classList.remove("ddIdePlanItem--dirty");
  }

  fileTreeEl?.addEventListener("click", (e) => {
    const btn = e.target?.closest?.(".ddIdeTreeFile");
    if (!btn || !fileTreeEl?.contains(btn)) return;
    const rel = btn.getAttribute("data-rel-path");
    if (!rel) return;
    setTreeSelection(btn);
    const ex = extOf(rel);
    const is3d = ex === ".obj" || ex === ".step" || ex === ".stp";
    const isMd = ex === ".md" || ex === ".markdown";
    void openOrAddTab(rel, { preferPreview: Boolean(is3d || isMd || pathWantsRichPreview(rel)) });
  });

  viewSegEl?.addEventListener("click", (e) => {
    const b = e.target?.closest?.("[data-dd-view-btn]");
    if (!b || !viewSegEl?.contains(b)) return;
    const m = b.getAttribute("data-dd-view-btn");
    if (m === "preview") {
      if (selectedRel) {
        void applyAutoViewForRel(selectedRel, {}).catch((err) => {
          if (codeMetaEl) codeMetaEl.textContent = String(err?.message || err);
        });
      } else {
        setActiveTab("preview");
      }
    } else {
      setActiveTab("source");
    }
  });

  codeEditor?.addEventListener("input", () => {
    flushEditorToActiveTab();
    renderFileTabs();
    const tab = openTabs[activeTabIndex];
    if (!tab || !mdPreviewEl || viewMode !== "preview") return;
    const ex = extOf(tab.rel);
    const isMd = ex === ".md" || ex === ".markdown";
    const lang = extToHljsLang(ex);
    const plain = extWantsPlainPreview(ex);
    if (!isMd && !lang && !plain) return;
    if (_mdLivePreviewTimer) clearTimeout(_mdLivePreviewTimer);
    _mdLivePreviewTimer = setTimeout(() => {
      _mdLivePreviewTimer = null;
      if (isMd) {
        mdPreviewEl.className = "ddIdeMdPreview mdLiteRoot aeMdSurface";
        mdPreviewEl.innerHTML = markdownLiteToHtml(tab.buffer);
      } else if (lang) {
        void highlightCodeToHtml(tab.buffer || "", lang).then((inner) => {
          mdPreviewEl.className = "ddIdeMdPreview ddIdeCodePreviewRoot";
          mdPreviewEl.innerHTML = wrapCodePreviewChrome(tab.rel, lang, inner);
        });
      } else {
        mdPreviewEl.className = "ddIdeMdPreview ddIdeCodePreviewRoot";
        mdPreviewEl.innerHTML = wrapCodePreviewChrome(tab.rel, "plain", plainCodeBlockHtml(tab.buffer || ""));
      }
    }, 220);
  });

  codeEditor?.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "s") {
      e.preventDefault();
      void saveActiveTab();
    }
  });

  function suggestNewRel() {
    let n = 1;
    let rel = "scratch.txt";
    while (openTabs.some((t) => t.rel === rel)) {
      n += 1;
      rel = `scratch_${n}.txt`;
    }
    return rel;
  }

  newFileBtn?.addEventListener("click", () => {
    const sid = String(getSessionId?.() || "").trim();
    if (!sid) return;
    const def = suggestNewRel();
    const raw = window.prompt("新建文件相对路径（例如 notes.txt 或 sub/dir.txt）", def);
    if (raw == null) return;
    let rel = String(raw).trim().replace(/\\/g, "/").replace(/^\/+/, "");
    if (!rel || rel.includes("..")) return;
    if (openTabs.some((t) => t.rel === rel)) {
      void activateTabIndex(openTabs.findIndex((t) => t.rel === rel));
      return;
    }
    openTabs.push({ rel, buffer: "", saved: "", loaded: true, isNew: true });
    void activateTabIndex(openTabs.length - 1, { forceSource: true });
    if (codeMetaEl) codeMetaEl.textContent = "未保存";
  });

  refreshBtn?.addEventListener("click", () => {
    void refreshFileTree();
  });

  function downloadDataUrl(filename, dataUrl) {
    const a = document.createElement("a");
    a.href = dataUrl;
    a.download = filename;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  async function copyTextToClipboard(s) {
    const t = String(s || "");
    try {
      await navigator.clipboard.writeText(t);
      toast("已复制到剪贴板");
    } catch {
      toast("复制失败（请检查浏览器剪贴板权限）");
    }
  }

  function ctxRelFromTarget(tgt) {
    const f = tgt?.closest?.(".ddIdeTreeFile");
    if (f) return String(f.getAttribute("data-rel-path") || "").trim();
    const sm = tgt?.closest?.(".ddIdeTreeSummary");
    if (sm && sm.dataset.dirRel != null) return String(sm.dataset.dirRel || "").trim();
    return "";
  }

  function ctxKindForRel(rel) {
    if (!rel) return "empty";
    if (findTreeFileBtn(rel)) return "file";
    return "dir";
  }

  /** @type {(() => void) | null} */
  let unmountWorkspaceMenu = null;
  if (workspaceRailEl && fileTreeEl) {
    const menu = document.createElement("div");
    menu.className = "ddWsMenu hidden";
    menu.setAttribute("role", "menu");
    document.body.appendChild(menu);

    let lastCtxRel = "";
    let lastCtxKind = /** @type {"empty" | "file" | "dir"} */ ("empty");

    function hideMenu() {
      menu.classList.add("hidden");
    }

    function addItem(label, shortcut, act, disabled) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "ddWsMenuItem" + (disabled ? " ddWsMenuItem--disabled" : "");
      b.setAttribute("role", "menuitem");
      b.dataset.act = act;
      const row = document.createElement("span");
      row.className = "ddWsMenuRow";
      const lab = document.createElement("span");
      lab.className = "ddWsMenuLabel";
      lab.textContent = label;
      row.appendChild(lab);
      if (shortcut) {
        const sc = document.createElement("span");
        sc.className = "ddWsMenuKey";
        sc.textContent = shortcut;
        row.appendChild(sc);
      }
      b.appendChild(row);
      b.disabled = Boolean(disabled);
      menu.appendChild(b);
    }

    function addSep() {
      const d = document.createElement("div");
      d.className = "ddWsMenuSep";
      menu.appendChild(d);
    }

    function rebuildMenu() {
      menu.innerHTML = "";
      const sid = String(getSessionId?.() || "").trim();
      const hasSess = Boolean(sid);
      const rel = lastCtxRel;
      const kind = lastCtxKind;
      const fileOnly = kind === "file";

      addItem("新建文件…", "", "new-file", !hasSess);
      addItem("新建文件夹…", "", "new-dir", !hasSess);
      addSep();
      addItem("在资源管理器中显示", "Shift+Alt+R", "explorer", !hasSess);
      addSep();
      addItem("截图 · 3D 视口", "", "cap-3d", false);
      addItem("截图 · 工作区", "", "cap-ws", false);
      addSep();
      addItem("剪切", "Ctrl+X", "cut", true);
      addItem("复制", "Ctrl+C", "copy", !rel);
      addItem("粘贴", "Ctrl+V", "paste", true);
      addSep();
      addItem("复制路径", "Shift+Alt+C", "copy-path", !hasSess);
      addItem("复制相对路径", "", "copy-rel", !rel);
      addSep();
      addItem("重命名…", "F2", "rename", !hasSess || !fileOnly);
      addItem("删除", "Del", "delete", !hasSess || !fileOnly);
    }

    function placeMenu(clientX, clientY) {
      rebuildMenu();
      menu.classList.remove("hidden");
      const pad = 8;
      const w = menu.offsetWidth || 220;
      const h = menu.offsetHeight || 200;
      let x = clientX + pad;
      let y = clientY + pad;
      if (x + w > window.innerWidth - 6) x = window.innerWidth - w - 6;
      if (y + h > window.innerHeight - 6) y = window.innerHeight - h - 6;
      menu.style.left = `${Math.max(6, x)}px`;
      menu.style.top = `${Math.max(6, y)}px`;
    }

    async function runMenuAct(act) {
      const sid = String(getSessionId?.() || "").trim();
      const rel = lastCtxRel;
      hideMenu();
      if (act === "new-file") {
        newFileBtn?.click();
        return;
      }
      if (act === "new-dir") {
        const raw = window.prompt("新建文件夹相对路径（例如 sub 或 sub/nested）", "new_folder");
        if (raw == null || !sid) return;
        const p = String(raw).trim().replace(/\\/g, "/").replace(/^\/+/, "");
        if (!p || p.includes("..")) return;
        try {
          await apiPostJson(`/session/${encodeURIComponent(sid)}/mkdir`, { path: p });
          toast(`已创建文件夹：${p}`);
          void refreshFileTree();
        } catch (e) {
          toast(String(e?.message || e));
        }
        return;
      }
      if (act === "explorer") {
        try {
          await openSessionExplorer?.(rel || "");
        } catch (e) {
          toast(String(e?.message || e));
        }
        return;
      }
      if (act === "cap-3d") {
        const url = preview3d?.capturePngDataUrl?.();
        if (url && url.startsWith("data:image")) {
          downloadDataUrl(`preview_${(selectedRel || "view").replace(/[^\w.-]+/g, "_")}.png`, url);
          toast("已下载 3D 视口截图");
        } else {
          toast("当前无法截取 3D（请先打开可预览的 OBJ/STEP 并切到预览）");
        }
        return;
      }
      if (act === "cap-ws") {
        try {
          const mod = await import("https://esm.sh/html2canvas@1.4.1");
          const html2canvas = mod.default;
          const el = workspaceRailEl;
          const c = await html2canvas(el, {
            backgroundColor: "#f8fafc",
            scale: Math.min(2, window.devicePixelRatio || 1),
            useCORS: true,
          });
          downloadDataUrl("workspace.png", c.toDataURL("image/png"));
          toast("已下载工作区截图");
        } catch (e) {
          toast(`工作区截图失败：${e?.message || e}`);
        }
        return;
      }
      if (act === "copy") {
        if (!rel) return;
        const base = tabTitle(rel);
        await copyTextToClipboard(base);
        return;
      }
      if (act === "copy-path") {
        if (!sid) return;
        const full = `runs/_design_domain/${sid}/${rel ? `${rel}`.replace(/^\/+/, "") : ""}`.replace(/\/$/, "");
        await copyTextToClipboard(full);
        return;
      }
      if (act === "copy-rel") {
        if (!rel) return;
        await copyTextToClipboard(rel);
        return;
      }
      if (act === "rename") {
        if (!sid || !rel || !findTreeFileBtn(rel)) return;
        const nn = window.prompt("新相对路径（含子目录）", rel);
        if (nn == null) return;
        const dst = String(nn).trim().replace(/\\/g, "/").replace(/^\/+/, "");
        if (!dst || dst.includes("..") || dst === rel) return;
        try {
          await apiPostJson(`/session/${encodeURIComponent(sid)}/rename`, { src: rel, dst });
          toast("已重命名");
          void refreshFileTree();
          const ix = openTabs.findIndex((t) => t.rel === rel);
          if (ix >= 0) {
            openTabs[ix].rel = dst;
            openTabs[ix].loaded = false;
            selectedRel = dst;
            if (activeTabIndex === ix) await activateTabIndex(ix, {});
          }
        } catch (e) {
          toast(String(e?.message || e));
        }
        return;
      }
      if (act === "delete") {
        if (!sid || !rel || !findTreeFileBtn(rel)) return;
        if (!window.confirm(`确定删除「${rel}」？`)) return;
        try {
          await apiDeleteFile(rel);
          toast("已删除");
          void refreshFileTree();
          const ix = openTabs.findIndex((t) => t.rel === rel);
          if (ix >= 0) void closeTabAt(ix);
        } catch (e) {
          toast(String(e?.message || e));
        }
      }
    }

    const onCtx = (e) => {
      if (!workspaceRailEl.contains(e.target)) return;
      if (e.target.closest?.(".ddIdeIconToolbar")) return;
      e.preventDefault();
      lastCtxRel = ctxRelFromTarget(e.target);
      lastCtxKind = ctxKindForRel(lastCtxRel);
      placeMenu(e.clientX, e.clientY);
    };

    const onDocClick = (e) => {
      if (!menu.classList.contains("hidden") && !menu.contains(e.target)) hideMenu();
    };

    const onKey = (e) => {
      if (e.key === "Escape") hideMenu();
    };

    menu.addEventListener("click", (e) => {
      const b = e.target?.closest?.(".ddWsMenuItem");
      if (!b || b.disabled || !menu.contains(b)) return;
      const act = b.getAttribute("data-act");
      if (act) void runMenuAct(act);
    });

    workspaceRailEl.addEventListener("contextmenu", onCtx);
    document.addEventListener("click", onDocClick, true);
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", hideMenu, true);

    unmountWorkspaceMenu = () => {
      workspaceRailEl.removeEventListener("contextmenu", onCtx);
      document.removeEventListener("click", onDocClick, true);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", hideMenu, true);
      menu.remove();
    };
  }

  updateViewSegButtons();
  setActiveTab("source");
  _ideScopedTaskId = String(getTaskId?.() || "").trim();
  if (_ideScopedTaskId) void hydrateTabsForTask(_ideScopedTaskId);

  void refreshVscodeEmbed();

  return {
    refreshFileTree,
    loadFilePreview: loadFileSource,
    openRelPath,
    setActiveTab,
    syncPlanState,
    markTopicDirty,
    clearDirtyTopic,
    setDynamicPlanSteps,
    setDynamicPlanStepState,
    clearDynamicPlan,
    refreshVscodeEmbed,
    preview3d,
    saveActiveEditor: saveActiveTab,
    dispose() {
      try {
        const tid = String(getTaskId?.() || "").trim();
        if (tid) persistOpenTabsForTaskId(tid);
      } catch {
        /* ignore */
      }
      unmountWorkspaceMenu?.();
      unmountWorkspaceMenu = null;
      fetchAborter?.abort();
      fetchAborter = null;
      dirtyTopics.clear();
      openTabs = [];
      activeTabIndex = -1;
      clearDynamicPlan();
      try {
        vscodeFrameEl?.removeAttribute("src");
      } catch {
        /* ignore */
      }
      preview3d.dispose();
    },
    persistOpenTabsForTaskId,
    switchTaskContext,
  };
}
