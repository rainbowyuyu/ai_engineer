/**
 * BESO7 演示悬浮面板：可拖动、最小化再开；右侧总览切换互斥显示；mini Three.js OBJ。
 */
import * as THREE from "three";
import { OBJLoader } from "three/examples/jsm/loaders/OBJLoader.js";

const _miniViewers = new Map();
/** @type {ReturnType<typeof createPanelOverview> | null} */
let _overview = null;

function absUrl(baseUrl, url) {
  const u = String(url || "");
  if (!u) return "";
  if (u.startsWith("http") || u.startsWith("blob:") || u.startsWith("#")) return u;
  return `${String(baseUrl || "").replace(/\/+$/, "")}${u.startsWith("/") ? u : `/${u}`}`;
}

/** FreeCAD `f v//vn` → 纯顶点索引，避免个别 loader 静默空网格 */
function sanitizeObjText(text) {
  return String(text || "")
    .split(/\r?\n/)
    .map((line) => {
      const t = line.trim();
      if (!t || t.startsWith("#")) return line;
      if (t.startsWith("vn ")) return "";
      if (t.startsWith("f ")) {
        const parts = t
          .slice(2)
          .trim()
          .split(/\s+/)
          .map((tok) => tok.split("/")[0])
          .filter(Boolean);
        return parts.length >= 3 ? `f ${parts.join(" ")}` : "";
      }
      return line;
    })
    .filter((l) => l !== "")
    .join("\n");
}

function countMeshes(root) {
  let n = 0;
  root?.traverse?.((c) => {
    if (c.isMesh && c.geometry) n += 1;
  });
  return n;
}

/** 串行挂载：避免多卡同时占满 WebGL 上下文导致后续全黑 */
const _mountQueue = [];
let _mountBusy = false;

function enqueueMount(task) {
  return new Promise((resolve, reject) => {
    _mountQueue.push({ task, resolve, reject });
    void drainMountQueue();
  });
}

async function drainMountQueue() {
  if (_mountBusy) return;
  _mountBusy = true;
  while (_mountQueue.length) {
    const { task, resolve, reject } = _mountQueue.shift();
    try {
      resolve(await task());
    } catch (e) {
      reject(e);
    }
  }
  _mountBusy = false;
}

function forceLoseWebgl(renderer) {
  try {
    const gl = renderer.getContext?.();
    gl?.getExtension?.("WEBGL_lose_context")?.loseContext?.();
  } catch {
    /* ignore */
  }
  try {
    renderer.dispose();
  } catch {
    /* ignore */
  }
  try {
    renderer.forceContextLoss?.();
  } catch {
    /* ignore */
  }
}

const MESH_PALETTE = [0x38bdf8, 0x34d399, 0xfbbf24, 0xf472b6, 0xa78bfa, 0x2dd4bf, 0xfb923c, 0x60a5fa];

/**
 * 加载 OBJ：默认渲染一帧为 PNG 缩略图并立即释放 WebGL（适合多卡画廊）。
 * 设 data-mini-live="1" 则保持轻量旋转预览（同时最多 1 个 live）。
 */
export async function mountMiniObj(container, url, { baseUrl = "", color, live } = {}) {
  if (!container || !url || url.startsWith("#")) return null;
  return enqueueMount(() =>
    mountMiniObjNow(container, url, {
      baseUrl,
      color,
      live: live ?? container.dataset.miniLive === "1",
    }),
  );
}

async function mountMiniObjNow(container, url, { baseUrl = "", color, live = false } = {}) {
  if (!container?.isConnected) return null;
  const full = absUrl(baseUrl, url);
  const key = container.dataset.miniKey || `m${Math.random().toString(36).slice(2, 9)}`;
  container.dataset.miniKey = key;
  container.dataset.miniObj = url;
  disposeMini(key);

  const tint =
    color != null
      ? color
      : MESH_PALETTE[Math.abs(hashStr(url)) % MESH_PALETTE.length];

  container.innerHTML = `<div class="beso7MiniFail beso7MiniLoading">加载 3D…</div>`;

  // 面板被总览隐藏时不建上下文；画廊内滚动遮挡仍可快照（用 CSS 尺寸）
  if (container.closest?.(".is-hidden-by-overview")) {
    container.innerHTML = `<div class="beso7MiniFail">展开窗口后显示</div>`;
    return null;
  }

  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  if (!container.isConnected) return null;

  const cssW = Math.max(container.clientWidth || 0, container.getBoundingClientRect().width || 0, 160);
  const cssH = Math.max(container.clientHeight || 0, container.getBoundingClientRect().height || 0, 140);
  const w = Math.round(cssW);
  const h = Math.round(cssH);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xf1f5f9);
  const camera = new THREE.PerspectiveCamera(42, w / h, 0.01, 5000);
  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: false,
    preserveDrawingBuffer: true,
    powerPreference: "low-power",
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  renderer.setSize(w, h, false);
  if ("outputColorSpace" in renderer) {
    renderer.outputColorSpace = THREE.SRGBColorSpace;
  }

  // 离屏但保持真实像素尺寸（1×1 宿主易导致全黑快照）
  const host = document.createElement("div");
  host.style.cssText = `position:fixed;left:0;top:0;width:${w}px;height:${h}px;opacity:0;pointer-events:none;z-index:-1;overflow:hidden;`;
  host.appendChild(renderer.domElement);
  document.body.appendChild(host);

  scene.add(new THREE.AmbientLight(0xffffff, 0.85));
  scene.add(new THREE.HemisphereLight(0xf1f5f9, 0x0f172a, 0.65));
  const dir = new THREE.DirectionalLight(0xffffff, 1.15);
  dir.position.set(3.2, 4.5, 2.4);
  scene.add(dir);
  const fill = new THREE.DirectionalLight(0x93c5fd, 0.4);
  fill.position.set(-2.5, 1.2, -1.8);
  scene.add(fill);

  let root = null;
  let raf = 0;
  let alive = true;
  let ro = null;

  const cleanupRenderer = () => {
    host.remove();
    forceLoseWebgl(renderer);
  };

  try {
    const res = await fetch(full, { cache: "no-store" });
    if (!alive || !container.isConnected) {
      cleanupRenderer();
      return null;
    }
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const raw = await res.text();
    if (!raw || raw.trim().startsWith("{") || raw.trim().startsWith("<")) {
      throw new Error("not obj");
    }
    const text = sanitizeObjText(raw);
    if (!/\bv\s/.test(text) || !/\bf\s/.test(text)) throw new Error("empty obj");

    const loader = new OBJLoader();
    root = loader.parse(text);
    if (countMeshes(root) < 1) throw new Error("no mesh");

    const mat = new THREE.MeshBasicMaterial({
      color: tint,
      side: THREE.DoubleSide,
    });
    root.traverse((c) => {
      if (c.isMesh) {
        c.material = mat;
      }
    });

    const box = new THREE.Box3().setFromObject(root);
    if (box.isEmpty()) throw new Error("empty bbox");
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    root.position.sub(center);
    const maxDim = Math.max(size.x, size.y, size.z, 1e-6);
    root.scale.setScalar(1.75 / maxDim);
    scene.add(root);

    const fitted = new THREE.Box3().setFromObject(root);
    const fSize = fitted.getSize(new THREE.Vector3());
    const fMax = Math.max(fSize.x, fSize.y, fSize.z, 1);
    const dist = fMax * 2.2;
    camera.position.set(dist * 0.95, dist * 0.58, dist * 1.1);
    camera.near = Math.max(0.001, dist / 250);
    camera.far = Math.max(80, dist * 50);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    camera.lookAt(0, 0, 0);
    root.rotation.y = 0.55;
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    renderer.render(scene, camera);
    renderer.render(scene, camera);

    if (!live) {
      let dataUrl = "";
      try {
        dataUrl = renderer.domElement.toDataURL("image/png");
      } catch {
        dataUrl = "";
      }
      cleanupRenderer();
      if (!dataUrl || dataUrl.length < 64) throw new Error("snapshot empty");
      const img = document.createElement("img");
      img.className = "beso7MiniThumb";
      img.alt = "3D preview";
      img.src = dataUrl;
      img.draggable = false;
      container.innerHTML = "";
      container.appendChild(img);
      const api = {
        dispose() {
          alive = false;
          container.innerHTML = "";
          _miniViewers.delete(key);
        },
      };
      _miniViewers.set(key, api);
      return api;
    }

    // live：仅保留一个旋转预览
    for (const [k, v] of [..._miniViewers.entries()]) {
      if (k !== key && v?._live) v.dispose();
    }
    container.innerHTML = "";
    container.appendChild(renderer.domElement);
    host.remove();
    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";

    const tick = () => {
      if (!alive) return;
      if (root) root.rotation.y += 0.012;
      renderer.render(scene, camera);
      raf = requestAnimationFrame(tick);
    };
    const onResize = () => {
      if (!alive || !container.isConnected) return;
      const nw = Math.max(48, container.clientWidth || w);
      const nh = Math.max(48, container.clientHeight || h);
      camera.aspect = nw / nh;
      camera.updateProjectionMatrix();
      renderer.setSize(nw, nh, false);
    };
    ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(onResize) : null;
    ro?.observe(container);
    tick();
    const api = {
      _live: true,
      dispose() {
        alive = false;
        cancelAnimationFrame(raf);
        ro?.disconnect();
        forceLoseWebgl(renderer);
        container.innerHTML = "";
        _miniViewers.delete(key);
      },
    };
    _miniViewers.set(key, api);
    return api;
  } catch (err) {
    cleanupRenderer();
    if (container.isConnected) {
      container.innerHTML = `<div class="beso7MiniFail" title="${String(err?.message || err).replace(/"/g, "")}">3D 加载失败</div>`;
    }
    return null;
  }
}

function hashStr(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return h;
}

export function disposeMini(key) {
  const prev = _miniViewers.get(key);
  if (prev) prev.dispose();
}

export function disposeAllMinis() {
  for (const k of [..._miniViewers.keys()]) disposeMini(k);
}

/**
 * 右侧窗口总览：互斥切换，避免主页多窗叠乱。
 */
export function createPanelOverview() {
  let rail = document.getElementById("beso7PanelOverview");
  if (!rail) {
    rail = document.createElement("aside");
    rail.id = "beso7PanelOverview";
    rail.className = "beso7PanelOverview";
    document.body.appendChild(rail);
  }
  if (
    !rail.querySelector(".beso7OverviewToggle") ||
    rail.querySelector(".beso7OverviewExpandTab") ||
    !rail.querySelector(".beso7OverviewScroll--prev")
  ) {
    rail.innerHTML = `
      <button type="button" class="beso7OverviewToggle" title="缩略/展开 (N)" aria-label="缩略或展开窗口导览">▾</button>
      <div class="beso7OverviewHd"><span class="beso7OverviewHdFull">窗口</span><span class="beso7OverviewHdShort" aria-hidden="true">窗</span></div>
      <button type="button" class="beso7OverviewScroll beso7OverviewScroll--prev" title="向左" aria-label="向左滚动窗口列表">‹</button>
      <div class="beso7OverviewList" role="list"></div>
      <button type="button" class="beso7OverviewScroll beso7OverviewScroll--next" title="向右" aria-label="向右滚动窗口列表">›</button>
      <button type="button" class="beso7OverviewClear" title="全部收起面板"><span class="beso7OverviewClearFull">收起</span><span class="beso7OverviewClearShort" aria-hidden="true">收</span></button>`;
  }
  const listEl = rail.querySelector(".beso7OverviewList");
  const clearBtn = rail.querySelector(".beso7OverviewClear");
  const toggleBtn = rail.querySelector(".beso7OverviewToggle");
  const scrollPrev = rail.querySelector(".beso7OverviewScroll--prev");
  const scrollNext = rail.querySelector(".beso7OverviewScroll--next");
  /** @type {Map<string, { id: string, title: string, short?: string, dock: any, badge?: string, order?: number }>} */
  const registry = new Map();
  let activeId = null;
  let collapsed = false;
  try {
    collapsed = sessionStorage.getItem("beso.ui.overview.collapsed") === "1";
  } catch {
    /* ignore */
  }

  const SHORT_LABEL = {
    guide: "引导",
    viz: "可视",
    candidates: "方案",
    tree: "版本",
    params: "参数",
    logs: "日志",
    validate: "验证",
    drawing: "图纸",
    deliverables: "交付",
  };

  const applyCollapsed = () => {
    rail.classList.add("is-toggling");
    rail.classList.toggle("is-collapsed", collapsed);
    rail.setAttribute("aria-expanded", collapsed ? "false" : "true");
    document.body.classList.add("beso7OverviewActive");
    document.body.classList.toggle("beso7OverviewCollapsed", collapsed);
    if (toggleBtn) {
      toggleBtn.textContent = collapsed ? "▴" : "▾";
      toggleBtn.title = collapsed ? "展开窗口导览 (N)" : "缩略窗口导览 (N)";
    }
    try {
      sessionStorage.setItem("beso.ui.overview.collapsed", collapsed ? "1" : "0");
    } catch {
      /* ignore */
    }
    window.setTimeout(() => rail.classList.remove("is-toggling"), 420);
  };
  applyCollapsed();

  const refresh = () => {
    if (!listEl) return;
    listEl.innerHTML = "";
    const entries = [...registry.values()].sort((a, b) => (a.order ?? 99) - (b.order ?? 99));
    for (const ent of entries) {
      const short = ent.short || SHORT_LABEL[ent.id] || String(ent.title || "").slice(0, 2);
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `beso7OverviewItem ${ent.id === activeId ? "is-active" : ""}`;
      btn.setAttribute("data-panel", ent.id);
      btn.title = `${ent.title}${ent.badge ? ` · ${ent.badge}` : ""}（点击打开）`;
      btn.innerHTML = `<span class="beso7OverviewDot" aria-hidden="true"></span>
        <span class="beso7OverviewLabel beso7OverviewLabel--full">${ent.title}</span>
        <span class="beso7OverviewLabel beso7OverviewLabel--short" aria-hidden="true">${short}</span>
        ${ent.badge ? `<em class="beso7OverviewBadge">${ent.badge}</em>` : ""}`;
      btn.addEventListener("click", () => {
        if (activeId === ent.id) api.hideAll();
        else api.focus(ent.id, { remount: true, keepCollapsed: true });
      });
      listEl.appendChild(btn);
    }
    rail.classList.toggle("is-empty", registry.size === 0);
    syncScrollButtons();
  };

  const syncScrollButtons = () => {
    if (!listEl) return;
    const max = Math.max(0, listEl.scrollWidth - listEl.clientWidth);
    const left = listEl.scrollLeft;
    if (scrollPrev) scrollPrev.disabled = left <= 2;
    if (scrollNext) scrollNext.disabled = left >= max - 2;
    const need = max > 4;
    if (scrollPrev) scrollPrev.hidden = !need;
    if (scrollNext) scrollNext.hidden = !need;
  };

  const scrollListBy = (dx) => {
    if (!listEl) return;
    listEl.scrollBy({ left: dx, behavior: "smooth" });
    window.setTimeout(syncScrollButtons, 280);
  };

  const api = {
    rail,
    register(id, { title, dock, badge, order, short } = {}) {
      if (!id || !dock) return;
      const prev = registry.get(id);
      registry.set(id, {
        id,
        title: title || prev?.title || id,
        short: short || prev?.short || SHORT_LABEL[id] || "",
        dock,
        badge: badge != null ? badge : prev?.badge || "",
        order: order != null ? order : prev?.order ?? 99,
      });
      dock.root?.classList.add("beso7FloatDock--managed");
      dock.setManaged?.(true);
      document.body.classList.add("beso7OverviewActive");
      refresh();
    },
    unregister(id) {
      registry.delete(id);
      if (activeId === id) activeId = null;
      refresh();
    },
    setBadge(id, badge) {
      const ent = registry.get(id);
      if (ent) {
        ent.badge = badge || "";
        refresh();
      }
    },
    setTitle(id, title) {
      const ent = registry.get(id);
      if (ent && title) {
        ent.title = title;
        ent.dock?.setTitle?.(title);
        refresh();
      }
    },
    listIds() {
      return [...registry.keys()];
    },
    setCollapsed(v) {
      collapsed = Boolean(v);
      applyCollapsed();
    },
    toggleCollapsed() {
      collapsed = !collapsed;
      applyCollapsed();
      return collapsed;
    },
    isCollapsed() {
      return collapsed;
    },
    focus(id, { remount = true, keepCollapsed = false } = {}) {
      if (!keepCollapsed && collapsed) {
        collapsed = false;
        applyCollapsed();
      }
      activeId = id;
      for (const [pid, ent] of registry) {
        const on = pid === id;
        const root = ent.dock.root;
        if (on) {
          /* 先定位再显示，避免从右侧旧坐标闪到中心 */
          if (root) {
            root.style.left = "";
            root.style.right = "";
            root.style.top = "";
            root.style.bottom = "";
            root.style.transform = "";
            root.classList.add("beso7FloatDock--centered");
            root.classList.add("is-focus");
          }
          ent.dock.setMinimized?.(false);
          ent.dock.setVisible?.(true);
          /* 滚到对应 tab */
          const tab = listEl?.querySelector(`[data-panel="${pid}"]`);
          tab?.scrollIntoView?.({ inline: "nearest", block: "nearest", behavior: "smooth" });
          ent.dock.onFocus?.();
        } else {
          if (root) {
            root.classList.remove("is-focus");
            root.classList.remove("beso7FloatDock--centered");
          }
          ent.dock.setVisible?.(false);
        }
      }
      refresh();
      syncScrollButtons();
      if (remount) {
        const ent = registry.get(id);
        if (ent?.dock?.body) {
          const base = ent.dock._baseUrl || "";
          setTimeout(() => {
            requestAnimationFrame(() => mountMeshCards(ent.dock.body, base));
          }, 120);
        }
      }
      return registry.get(id)?.dock || null;
    },
    hideAll() {
      activeId = null;
      for (const ent of registry.values()) {
        ent.dock.root?.classList.remove("is-focus", "beso7FloatDock--centered");
        ent.dock.setVisible?.(false);
      }
      refresh();
      syncScrollButtons();
    },
    getActive() {
      return activeId;
    },
    destroy() {
      registry.clear();
      window.removeEventListener("keydown", onKey);
      rail.remove();
      document.body.classList.remove("beso7OverviewCollapsed", "beso7OverviewActive");
      if (_overview === api) _overview = null;
    },
  };

  clearBtn?.addEventListener("click", () => api.hideAll());
  toggleBtn?.addEventListener("click", (e) => {
    e.stopPropagation();
    api.toggleCollapsed();
  });
  scrollPrev?.addEventListener("click", (e) => {
    e.stopPropagation();
    scrollListBy(-180);
  });
  scrollNext?.addEventListener("click", (e) => {
    e.stopPropagation();
    scrollListBy(180);
  });
  listEl?.addEventListener(
    "wheel",
    (e) => {
      if (!listEl) return;
      const mostlyVertical = Math.abs(e.deltaY) >= Math.abs(e.deltaX);
      if (mostlyVertical && listEl.scrollWidth > listEl.clientWidth + 4) {
        e.preventDefault();
        listEl.scrollLeft += e.deltaY;
        syncScrollButtons();
      } else {
        syncScrollButtons();
      }
    },
    { passive: false },
  );
  listEl?.addEventListener("scroll", () => syncScrollButtons(), { passive: true });
  window.addEventListener("resize", () => syncScrollButtons());
  window.setTimeout(syncScrollButtons, 60);

  const onKey = (e) => {
    if (e.key !== "n" && e.key !== "N") return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const t = e.target;
    const tag = String(t?.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select" || t?.isContentEditable) return;
    e.preventDefault();
    api.toggleCollapsed();
  };
  window.addEventListener("keydown", onKey);

  _overview = api;
  return api;
}

export function getPanelOverview() {
  return _overview;
}

/**
 * 创建可拖动悬浮窗；由总览管理时隐藏独立胶囊。
 */
export function createFloatDock({
  id,
  title,
  side = "right",
  storageKey,
  width = 380,
  defaultMinimized = true,
  managed = true,
}) {
  let root = document.getElementById(id);
  if (!root) {
    root = document.createElement("div");
    root.id = id;
    root.className = `beso7FloatDock beso7FloatDock--${side}`;
    document.body.appendChild(root);
  }
  root.classList.add("beso7FloatDock", `beso7FloatDock--${side}`);
  if (managed) root.classList.add("beso7FloatDock--managed");
  root.style.width = `min(${width}px, calc(100vw - 24px))`;

  const sk = storageKey || `beso.ui.${id}`;
  root.innerHTML = `
    <button type="button" class="beso7FloatPill" hidden></button>
    <div class="beso7FloatPanel">
      <header class="beso7FloatHd">
        <strong class="beso7FloatTitle">${title || ""}</strong>
        <div class="beso7FloatHdActions">
          <button type="button" class="beso7FloatMin" title="收起">–</button>
        </div>
      </header>
      <div class="beso7FloatBody"></div>
    </div>`;

  const pill = root.querySelector(".beso7FloatPill");
  const panel = root.querySelector(".beso7FloatPanel");
  const body = root.querySelector(".beso7FloatBody");
  const hd = root.querySelector(".beso7FloatHd");
  const titleEl = root.querySelector(".beso7FloatTitle");
  const minBtn = root.querySelector(".beso7FloatMin");
  let isManaged = managed;

  const setVisible = (v) => {
    root.classList.toggle("is-hidden-by-overview", !v);
    if (!v) root.classList.remove("is-focus");
  };

  const setMinimized = (v) => {
    root.classList.toggle("is-minimized", !!v);
    if (pill) {
      const showPill = !!v && !isManaged;
      pill.hidden = !showPill;
      pill.textContent = titleEl?.textContent || title || "面板";
    }
    try {
      sessionStorage.setItem(`${sk}.min`, v ? "1" : "0");
    } catch {
      /* ignore */
    }
  };

  const applyPos = () => {
    try {
      const raw = sessionStorage.getItem(`${sk}.pos`);
      if (raw) {
        const p = JSON.parse(raw);
        if (typeof p.left === "number") {
          root.style.left = `${p.left}px`;
          root.style.right = "auto";
        } else if (typeof p.right === "number") {
          root.style.right = `${p.right}px`;
          root.style.left = "auto";
        }
        if (typeof p.top === "number") {
          root.style.top = `${p.top}px`;
          root.style.bottom = "auto";
        }
        return;
      }
    } catch {
      /* ignore */
    }
    root.style.top = "72px";
    root.style.right = isManaged ? "88px" : side === "left" ? "auto" : "18px";
    root.style.left = side === "left" && !isManaged ? "18px" : "auto";
  };
  applyPos();
  setMinimized(defaultMinimized);
  if (isManaged) {
    setVisible(false);
    root.classList.remove("beso7FloatDock--centered", "is-focus");
  }

  pill?.addEventListener("click", () => {
    if (_overview) _overview.focus(id);
    else setMinimized(false);
  });
  minBtn?.addEventListener("click", (e) => {
    e.stopPropagation();
    if (_overview) _overview.hideAll();
    else setMinimized(true);
  });

  hd?.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    if (e.target.closest(".beso7FloatMin")) return;
    if (root.classList.contains("is-minimized")) return;
    if (root.classList.contains("is-hidden-by-overview")) return;
    e.preventDefault();
    const capId = e.pointerId;
    try {
      root.setPointerCapture(capId);
    } catch {
      /* ignore */
    }
    const rect = root.getBoundingClientRect();
    const startX = e.clientX;
    const startY = e.clientY;
    const startLeft = rect.left;
    const startTop = rect.top;
    root.classList.add("is-dragging");
    let finished = false;
    const onMove = (ev) => {
      const dx = ev.clientX - startX;
      const dy = ev.clientY - startY;
      const w = rect.width || 200;
      const h = rect.height || 80;
      const left = Math.max(8, Math.min(window.innerWidth - w - 8, startLeft + dx));
      const top = Math.max(8, Math.min(window.innerHeight - h - 8, startTop + dy));
      root.style.left = `${Math.round(left)}px`;
      root.style.top = `${Math.round(top)}px`;
      root.style.right = "auto";
      root.style.bottom = "auto";
    };
    const finish = () => {
      if (finished) return;
      finished = true;
      try {
        root.releasePointerCapture(capId);
      } catch {
        /* ignore */
      }
      root.classList.remove("is-dragging");
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", finish);
      window.removeEventListener("pointercancel", finish);
      const left = parseFloat(String(root.style.left || "").replace("px", "")) || 18;
      const top = parseFloat(String(root.style.top || "").replace("px", "")) || 72;
      try {
        sessionStorage.setItem(`${sk}.pos`, JSON.stringify({ left, top }));
      } catch {
        /* ignore */
      }
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    window.addEventListener("pointerup", finish);
    window.addEventListener("pointercancel", finish);
  });

  return {
    root,
    panel,
    body,
    _baseUrl: "",
    setMinimized,
    setVisible,
    setManaged(v) {
      isManaged = !!v;
      root.classList.toggle("beso7FloatDock--managed", isManaged);
      if (isManaged && pill) pill.hidden = true;
    },
    setTitle(t) {
      if (titleEl) titleEl.textContent = t;
    },
    destroy() {
      disposeAllMinis();
      _overview?.unregister?.(id);
      root.remove();
    },
  };
}

export function mountMeshCards(rootEl, baseUrl) {
  const cans = rootEl?.querySelectorAll?.("[data-mini-obj]") || [];
  cans.forEach((el) => {
    const url = el.getAttribute("data-mini-obj");
    if (url) void mountMiniObj(el, url, { baseUrl });
  });
}
