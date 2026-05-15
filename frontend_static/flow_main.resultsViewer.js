/**
 * 本地结果查看器：导入文件夹，按类型筛选，预览 STEP / OBJ / INP / VTK 与四张指标 PNG；
 * 支持 BESO 多轨迭代序列：`fileNNN.vtk`、`fileNNN_state0.inp`、`fileNNN_state1.inp`、`fileNNN.inp` 分开，可在工具条选择要播放的序列。
 */
import * as THREE from "three";
import { OBJLoader } from "three/examples/jsm/loaders/OBJLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { parseInpC3D4ToBufferGeometry } from "./flow_main.inpCcxAscii.js";
import { parseLegacyAsciiUnstructuredGridTets } from "./flow_main.vtkLegacyAscii.js";

const OCCT_IMPORT_JS_URL = "https://unpkg.com/occt-import-js@0.0.23/dist/occt-import-js.js";

/** @type {Promise<any> | null} */
let occtModulePromise = null;

function loadOcctImportJs() {
  if (occtModulePromise) return occtModulePromise;
  occtModulePromise = new Promise((resolve, reject) => {
    const start = () => {
      const fn = globalThis.occtimportjs;
      if (typeof fn !== "function") {
        reject(new Error("occt-import-js 未正确加载"));
        return;
      }
      fn()
        .then(resolve)
        .catch(reject);
    };
    if (typeof globalThis.occtimportjs === "function") {
      start();
      return;
    }
    const s = document.createElement("script");
    s.src = OCCT_IMPORT_JS_URL;
    s.async = true;
    s.onload = () => start();
    s.onerror = () => reject(new Error("无法加载 occt-import-js（检查网络或 CSP）"));
    document.head.appendChild(s);
  });
  return occtModulePromise;
}

function flattenNumberArray(arr) {
  if (!arr || !arr.length) return [];
  if (typeof arr[0] === "number") return arr;
  return arr.flat(Infinity);
}

const METRIC_NAMES = ["Mass.png", "FI_mean.png", "FI_max.png", "FI_violated.png"];

function extOf(name) {
  const i = name.lastIndexOf(".");
  return i >= 0 ? name.slice(i).toLowerCase() : "";
}

function parseFileNumber(name, ext) {
  const m = new RegExp(`^file(\\d+)\\${ext}$`, "i").exec(name);
  return m ? parseInt(m[1], 10) : -1;
}

/**
 * @typedef {{ kind: 'vtk' | 'inp', file: File, n: number }} MeshFrame
 * @typedef {{ id: string, label: string, frames: MeshFrame[] }} MeshTrack
 */

function _mapIterFilesToFrames(/** @type {Map<number, File>} */ byN, /** @type {'vtk'|'inp'} */ kind) {
  const ns = [...byN.keys()].sort((a, b) => a - b);
  return ns.map((n) => ({ kind, file: /** @type {File} */ (byN.get(n)), n }));
}

/** 按 BESO 命名拆成多条独立序列（不按迭代合并 VTK/INP）。 */
function discoverMeshTracks(files) {
  const arr = Array.from(files || []);
  /** @type {Map<number, File>} */
  const vtkByN = new Map();
  /** @type {Map<number, File>} */
  const plainInpByN = new Map();
  /** @type {Map<string, Map<number, File>>} */
  const stateInpByKey = new Map();

  for (const f of arr) {
    let m = /^file(\d+)\.vtk$/i.exec(f.name);
    if (m) {
      vtkByN.set(parseInt(m[1], 10), f);
      continue;
    }
    m = /^file(\d+)_state(\d+)\.inp$/i.exec(f.name);
    if (m) {
      const n = parseInt(m[1], 10);
      const si = parseInt(m[2], 10);
      const key = `state${si}`;
      if (!stateInpByKey.has(key)) stateInpByKey.set(key, new Map());
      stateInpByKey.get(key).set(n, f);
      continue;
    }
    m = /^file(\d+)\.inp$/i.exec(f.name);
    if (m) {
      plainInpByN.set(parseInt(m[1], 10), f);
    }
  }

  /** @type {MeshTrack[]} */
  const tracks = [];
  if (vtkByN.size) {
    tracks.push({ id: "vtk", label: "VTK", frames: _mapIterFilesToFrames(vtkByN, "vtk") });
  }
  const stateKeys = [...stateInpByKey.keys()].sort((a, b) => {
    const na = parseInt(a.replace(/[^\d]/g, "") || "0", 10);
    const nb = parseInt(b.replace(/[^\d]/g, "") || "0", 10);
    return na - nb || a.localeCompare(b);
  });
  for (const key of stateKeys) {
    const mp = stateInpByKey.get(key);
    if (!mp?.size) continue;
    tracks.push({
      id: `inp_${key}`,
      label: key,
      frames: _mapIterFilesToFrames(mp, "inp"),
    });
  }
  if (plainInpByN.size) {
    tracks.push({ id: "inp_plain", label: "INP", frames: _mapIterFilesToFrames(plainInpByN, "inp") });
  }
  return tracks.filter((t) => t.frames.length);
}

function pickDefaultMeshTrackId(/** @type {MeshTrack[]} */ tracks) {
  if (!tracks.length) return "";
  const vtk = tracks.find((t) => t.id === "vtk");
  if (vtk) return "vtk";
  return tracks[0].id;
}

function pickDefaultMeshFile(files) {
  const arr = Array.from(files || []);
  const tracks = discoverMeshTracks(arr);
  if (tracks.length) {
    const tid = pickDefaultMeshTrackId(tracks);
    const tr = tracks.find((t) => t.id === tid) || tracks[0];
    if (tr.frames.length) return tr.frames[0].file;
  }
  const objs = arr.filter((f) => extOf(f.name) === ".obj");
  if (objs.length) {
    const latest = objs.find((f) => f.name.toLowerCase() === "latest.obj");
    if (latest) return latest;
    let best = objs[0];
    let bestN = parseFileNumber(best.name, ".obj");
    for (const f of objs) {
      const n = parseFileNumber(f.name, ".obj");
      if (n > bestN) {
        best = f;
        bestN = n;
      }
    }
    return best;
  }
  const steps = arr.filter((f) => {
    const e = extOf(f.name);
    return e === ".step" || e === ".stp";
  });
  if (steps.length) {
    return [...steps].sort((a, b) => a.name.localeCompare(b.name))[0];
  }
  const inps = arr.filter((f) => extOf(f.name) === ".inp").sort((a, b) => a.name.localeCompare(b.name));
  return inps[0] || null;
}

function findFile(fileList, baseName) {
  const want = baseName.toLowerCase();
  return Array.from(fileList || []).find((f) => f.name?.toLowerCase() === want) || null;
}

/**
 * @param {{ normalizedBaseUrl?: () => string }} [opts]
 */
export function mountResultsViewer(opts = {}) {
  const getBaseUrl =
    typeof opts.normalizedBaseUrl === "function" ? opts.normalizedBaseUrl : () => "";

  const root = document.createElement("div");
  root.id = "resultsViewerModal";
  root.className = "resultsViewerModal hidden";
  root.setAttribute("aria-hidden", "true");
  root.innerHTML = `
    <div class="resultsViewerBackdrop" data-rv-close="1"></div>
    <div class="resultsViewerShell" role="dialog" aria-modal="true" aria-labelledby="resultsViewerTitle">
      <header class="resultsViewerHd">
        <div class="resultsViewerHdLeft">
          <span class="resultsViewerBadge" aria-hidden="true"></span>
          <div class="resultsViewerHdMain">
            <div class="resultsViewerHdTitleRow">
              <h2 class="resultsViewerTitle" id="resultsViewerTitle">拓扑优化结果查看器</h2>
              <div class="resultsViewerHdHelpWrap">
                <button type="button" class="resultsViewerHelpBtn" id="rvHelpBtn" aria-expanded="false" aria-controls="rvHelpPopover" title="使用说明">
                  <span class="resultsViewerHelpBtnIc" aria-hidden="true">?</span>
                </button>
                <div id="rvHelpPopover" class="resultsViewerHelpPopover" role="region" aria-label="使用说明" aria-hidden="true">
                  <div class="resultsViewerHelpPopoverHd">使用说明</div>
                  <div class="resultsViewerHelpPopoverBd">
                    <p class="resultsViewerHelpPopoverP">导入 <span class="mono">runs/&lt;job&gt;/</span> 或 <span class="mono">examples/beso/</span> · 筛选后预览 <span class="mono">.vtk / .step / .obj / .inp</span>；<span class="mono">file*.vtk</span>、<span class="mono">file*_state0.inp</span>、<span class="mono">file*_state1.inp</span> 等为<strong>不同序列</strong>，可在工具条切换播放。</p>
                    <p class="resultsViewerHelpPopoverP"><span class="mono">STEP</span> 使用 <span class="mono">occt-import-js</span>（OpenCascade WASM）三角化；<span class="mono">VTK</span> / <span class="mono">INP(C3D4)</span> 为四面体展开三角面；<span class="mono">INP</span> 三维优先走服务端 <span class="mono">FreeCAD</span> 转换（需本机后端与 FreeCAD）；<span class="mono">VTK</span> 与 <span class="mono">state0</span>/<span class="mono">state1</span> 等为<strong>独立序列</strong>。单帧大文件解析可能需数秒。</p>
                    <p class="resultsViewerHelpPopoverP"><strong>播放快捷键</strong>（焦点不在输入框时）：<span class="mono">Space</span> 播放/暂停；<span class="mono">←</span> <span class="mono">→</span> 上一帧/下一帧；<span class="mono">Home</span> / <span class="mono">End</span> 首帧/末帧。拖动进度条时右侧帧号会随刻度预览；刻度确认后再加载对应帧。</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div class="resultsViewerHdRight">
          <button type="button" class="resultsViewerClose" id="rvCloseBtn" title="关闭"><span aria-hidden="true">✕</span></button>
        </div>
      </header>
      <div class="resultsViewerToolbar">
        <button type="button" class="btn btnPrimary" id="rvPickBtn">导入文件夹</button>
        <input type="file" id="rvDirInput" class="hidden" webkitdirectory directory multiple />
        <span class="resultsViewerMeta" id="rvMeta">尚未导入</span>
      </div>
      <div class="resultsViewerVtkSeq hidden" id="rvVtkSeqBar" aria-label="迭代网格序列">
        <div class="resultsViewerVtkSeqHd">
          <span class="chip resultsViewerVtkSeqChip">迭代网格</span>
          <label class="resultsViewerMeshTrackLab hidden" id="rvMeshTrackLab">播放序列
            <select id="rvMeshTrackSelect" class="resultsViewerMeshTrackSelect" aria-label="选择迭代序列"></select>
          </label>
          <div class="resultsViewerSeqHintWrap">
            <button type="button" class="resultsViewerSeqHintBtn" id="rvSeqHintBtn" aria-expanded="false" aria-controls="rvSeqHintPop" title="序列排序说明">?</button>
            <div id="rvSeqHintPop" class="resultsViewerSeqHintPop" role="tooltip" aria-hidden="true">各序列独立按 <span class="mono">file</span> 编号排序</div>
          </div>
        </div>
        <div class="resultsViewerVtkSeqControls">
          <div class="resultsViewerVtkTransport" role="group" aria-label="播放控制">
            <button type="button" class="btn resultsViewerVtkTbBtn" id="rvVtkFirst" aria-label="第一帧" title="第一帧 (Home)">
              <svg class="resultsViewerVtkTbSvg" viewBox="0 0 24 24" aria-hidden="true" fill="currentColor"><path d="M5 5h2v14H5V5zm4 0h2v14H9V5zm5 2l8 5-8 5V7z"/></svg>
            </button>
            <button type="button" class="btn resultsViewerVtkTbBtn" id="rvVtkPrev" aria-label="上一帧" title="上一帧 (←)">
              <svg class="resultsViewerVtkTbSvg" viewBox="0 0 24 24" aria-hidden="true" fill="currentColor"><path d="M8 5l10 7-10 7V5z"/></svg>
            </button>
            <button type="button" class="btn btnPrimary resultsViewerVtkPlayBtn" id="rvVtkPlay" aria-label="播放" title="播放/暂停 (Space)">
              <svg class="resultsViewerVtkTbSvg resultsViewerVtkIc--play" viewBox="0 0 24 24" aria-hidden="true" fill="currentColor"><path d="M8 5v14l11-7L8 5z"/></svg>
              <svg class="resultsViewerVtkTbSvg resultsViewerVtkIc--pause hidden" viewBox="0 0 24 24" aria-hidden="true" fill="currentColor"><path d="M6 5h4v14H6V5zm8 0h4v14h-4V5z"/></svg>
            </button>
            <button type="button" class="btn resultsViewerVtkTbBtn" id="rvVtkNext" aria-label="下一帧" title="下一帧 (→)">
              <svg class="resultsViewerVtkTbSvg" viewBox="0 0 24 24" aria-hidden="true" fill="currentColor"><path d="M16 18h2V6h-2v12zM6 5l8.5 7L6 19V5z"/></svg>
            </button>
            <button type="button" class="btn resultsViewerVtkTbBtn" id="rvVtkLast" aria-label="最后一帧" title="最后一帧 (End)">
              <svg class="resultsViewerVtkTbSvg" viewBox="0 0 24 24" aria-hidden="true" fill="currentColor"><path d="M16 6h2v12h-2V6zM6 5l8.5 7L6 19V5z"/></svg>
            </button>
          </div>
          <div class="resultsViewerVtkSliderCol">
            <input type="range" class="resultsViewerVtkSlider" id="rvVtkSlider" min="0" max="0" value="0" aria-valuetext="" />
          </div>
          <label class="resultsViewerVtkJumpLab">跳转
            <input type="number" id="rvVtkJump" class="resultsViewerVtkJump" min="1" max="1" step="1" inputmode="numeric" title="输入帧号后按回车或失焦跳转" aria-label="跳转到帧号" />
          </label>
          <label class="resultsViewerVtkSpeedLab">间隔 (ms)
            <span class="resultsViewerIntervalSpin" title="播放每帧停留时间（将自动记住）">
              <button type="button" class="btn resultsViewerIntervalBtn" id="rvIntervalDown" aria-label="减少间隔">−</button>
              <input type="number" id="rvIntervalMs" class="resultsViewerIntervalMs" min="50" max="120000" step="1" value="800" inputmode="numeric" />
              <button type="button" class="btn resultsViewerIntervalBtn" id="rvIntervalUp" aria-label="增加间隔">+</button>
            </span>
          </label>
          <button type="button" class="btn resultsViewerVtkLoopBtn" id="rvVtkLoop" aria-pressed="true" title="开启：播放到末尾后回到首帧；关闭：在末尾自动停止">循环</button>
          <span class="resultsViewerVtkSeqLabel mono" id="rvVtkSeqLabel">—</span>
        </div>
      </div>
      <div class="resultsViewerMainRow">
        <aside class="resultsViewerRail">
          <div class="resultsViewerFilters" id="rvFilters">
            <button type="button" class="rvFilter active" data-ext="all">全部</button>
            <button type="button" class="rvFilter" data-ext=".stp">STEP</button>
            <button type="button" class="rvFilter" data-ext=".obj">OBJ</button>
            <button type="button" class="rvFilter" data-ext=".inp">INP</button>
            <button type="button" class="rvFilter" data-ext=".vtk">VTK</button>
          </div>
          <input type="search" class="resultsViewerSearch" id="rvSearch" placeholder="筛选文件名…" autocomplete="off" />
          <div class="resultsViewerFileList" id="rvFileList"></div>
        </aside>
        <section class="resultsViewerPreviewCol" id="rvPreviewCol">
          <div class="resultsViewerPaneHd">预览 <span class="chip" id="rvObjLabel">—</span></div>
          <div class="resultsViewerCanvasWrap" id="rvCanvasWrap">
            <pre class="resultsViewerTextPreview hidden" id="rvTextPreview" spellcheck="false"></pre>
            <div class="resultsViewerCanvasEmpty" id="rvCanvasEmpty" aria-hidden="false">
              <div class="resultsViewerCanvasEmptyGlow" aria-hidden="true"></div>
              <div class="resultsViewerCanvasEmptyCard">
                <div class="resultsViewerCanvasEmptyIcon" aria-hidden="true">
                  <svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M24 6L8 14v20l16 8 16-8V14L24 6z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" opacity=".35"/><path d="M24 14l10 5v12l-10 5-10-5V19l10-5z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>
                </div>
                <h3 class="resultsViewerCanvasEmptyTitle">等待三维预览</h3>
                <p class="resultsViewerCanvasEmptyLead">导入优化输出目录，或将文件 / 文件夹拖入下方深色区域即可切换数据源。</p>
                <ul class="resultsViewerCanvasEmptyList">
                  <li>网格：<span class="mono">.vtk</span>、<span class="mono">.inp</span>（C3D4）</li>
                  <li>几何：<span class="mono">.step</span> / <span class="mono">.obj</span></li>
                  <li>多序列 <span class="mono">fileNNN.vtk</span> 可在上方轨道播放</li>
                </ul>
              </div>
            </div>
            <div class="resultsViewerCanvasHint hidden" id="rvCanvasHint"></div>
            <div class="resultsViewerCanvasHud" id="rvCanvasHud" aria-label="三维视图控制">
              <div class="resultsViewerViewToolbar" role="toolbar">
                <button type="button" class="resultsViewerViewBtn" id="rvBtnSpin" title="自动旋转" aria-pressed="false">
                  <svg class="resultsViewerViewSvg" viewBox="0 0 24 24" aria-hidden="true" preserveAspectRatio="xMidYMid meet"><path fill="currentColor" d="M12 5.2V2.5L7.8 6.7 12 11V8.3c2.5 0 4.5 2 4.5 4.5 0 .9-.3 1.8-.8 2.5l1.6 1.6c.8-1.1 1.2-2.4 1.2-4.1 0-3.6-2.9-6.5-6.5-6.5zm-1.2 9.1-1.6-1.6c-.8 1.1-1.2 2.4-1.2 4.1 0 3.6 2.9 6.5 6.5 6.5V21l4.2-4.2L16 12.3V15c-2.5 0-4.5-2-4.5-4.5 0-.9.3-1.8.8-2.5z"/></svg>
                </button>
                <button type="button" class="resultsViewerViewBtn" id="rvBtnResetCam" title="复原视图（上次适配后的相机）">
                  <svg class="resultsViewerViewSvg resultsViewerViewSvg--reset" viewBox="0 0 24 24" aria-hidden="true" preserveAspectRatio="xMidYMid meet" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="2.35"/><path d="M12 4.25V2.75M12 21.25v-1.5M4.25 12H2.75M21.25 12H19.75M6.9 6.9 5.75 5.75M18.25 18.25 17.1 17.1M6.9 17.1 5.75 18.25M18.25 5.75 17.1 6.9"/></svg>
                </button>
                <button type="button" class="resultsViewerViewBtn" id="rvBtnZoomIn" title="放大">
                  <svg class="resultsViewerViewSvg" viewBox="0 0 24 24" aria-hidden="true" preserveAspectRatio="xMidYMid meet"><circle cx="12" cy="12" r="6.5" fill="none" stroke="currentColor" stroke-width="1.85"/><path fill="none" stroke="currentColor" stroke-width="1.85" stroke-linecap="round" d="M12 8.2v7.6M8.2 12h7.6M20.2 20.2l-4.1-4.1"/></svg>
                </button>
                <button type="button" class="resultsViewerViewBtn" id="rvBtnZoomOut" title="缩小">
                  <svg class="resultsViewerViewSvg" viewBox="0 0 24 24" aria-hidden="true" preserveAspectRatio="xMidYMid meet"><circle cx="12" cy="12" r="6.5" fill="none" stroke="currentColor" stroke-width="1.85"/><path fill="none" stroke="currentColor" stroke-width="1.85" stroke-linecap="round" d="M8.2 12h7.6M20.2 20.2l-4.1-4.1"/></svg>
                </button>
                <button type="button" class="resultsViewerViewBtn" id="rvBtnFit" title="适配模型（重置相机与包围盒）">
                  <svg class="resultsViewerViewSvg" viewBox="0 0 24 24" aria-hidden="true" preserveAspectRatio="xMidYMid meet" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M8 5H5v3M16 5h3v3M8 19H5v-3M16 19h3v-3"/></svg>
                </button>
                <button type="button" class="resultsViewerViewBtn resultsViewerViewBtn--fs" id="rvBtnFs" title="全屏预览区" aria-pressed="false">
                  <svg class="resultsViewerViewSvg rvFs-i-expand" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3H3v6M15 3h6v6M9 21H3v-6M15 21h6v-6"/></svg>
                  <svg class="resultsViewerViewSvg rvFs-i-collapse hidden" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M10 4H4v6M14 4h6v6M10 20H4v-6M14 20h6v-6"/></svg>
                </button>
              </div>
            </div>
            <div class="resultsViewerCtxMenu hidden" id="rvCtxMenu" role="menu" aria-label="画布菜单">
              <div class="resultsViewerCtxHd">视图</div>
              <button type="button" class="resultsViewerCtxItem" role="menuitem" data-rv-ctx="fit"><span class="resultsViewerCtxIc" aria-hidden="true">◇</span>适配模型</button>
              <button type="button" class="resultsViewerCtxItem" role="menuitem" data-rv-ctx="reset"><span class="resultsViewerCtxIc" aria-hidden="true">◎</span>复原视图</button>
              <button type="button" class="resultsViewerCtxItem" role="menuitem" data-rv-ctx="spin"><span class="resultsViewerCtxIc" aria-hidden="true">↻</span>切换自动旋转</button>
              <button type="button" class="resultsViewerCtxItem" role="menuitem" data-rv-ctx="wire"><span class="resultsViewerCtxIc" aria-hidden="true">▦</span>线框模式</button>
              <button type="button" class="resultsViewerCtxItem" role="menuitem" data-rv-ctx="grid"><span class="resultsViewerCtxIc" aria-hidden="true">▤</span>显示 / 隐藏网格</button>
              <div class="resultsViewerCtxSep" role="separator"></div>
              <button type="button" class="resultsViewerCtxItem" role="menuitem" data-rv-ctx="zoomin"><span class="resultsViewerCtxIc" aria-hidden="true">＋</span>放大</button>
              <button type="button" class="resultsViewerCtxItem" role="menuitem" data-rv-ctx="zoomout"><span class="resultsViewerCtxIc" aria-hidden="true">－</span>缩小</button>
              <div class="resultsViewerCtxSep" role="separator"></div>
              <div class="resultsViewerCtxHd">窗口</div>
              <button type="button" class="resultsViewerCtxItem" role="menuitem" data-rv-ctx="fullscreen"><span class="resultsViewerCtxIc" aria-hidden="true">⤢</span>全屏 / 退出全屏</button>
              <div class="resultsViewerCtxSep" role="separator"></div>
              <button type="button" class="resultsViewerCtxItem" role="menuitem" data-rv-ctx="copyname">复制当前文件名</button>
            </div>
          </div>
        </section>
        <section class="resultsViewerPane resultsViewerPaneCharts">
          <div class="resultsViewerPaneHd">指标曲线 <span class="chip">Mass / FI</span></div>
          <div class="resultsViewerChartGrid" id="rvChartGrid"></div>
        </section>
      </div>
    </div>
  `;
  document.body.appendChild(root);

  const backdrop = root.querySelector(".resultsViewerBackdrop");
  const shell = root.querySelector(".resultsViewerShell");
  const btnClose = root.querySelector("#rvCloseBtn");
  const btnPick = root.querySelector("#rvPickBtn");
  const inpDir = root.querySelector("#rvDirInput");
  const meta = root.querySelector("#rvMeta");
  const hint = root.querySelector("#rvCanvasHint");
  const emptyState = root.querySelector("#rvCanvasEmpty");
  const objLabel = root.querySelector("#rvObjLabel");
  const rvHelpBtn = root.querySelector("#rvHelpBtn");
  const rvHelpPopover = root.querySelector("#rvHelpPopover");

  function closeHelpPopover() {
    if (!rvHelpPopover || !rvHelpBtn) return;
    rvHelpPopover.classList.remove("resultsViewerHelpPopover--open");
    rvHelpPopover.setAttribute("aria-hidden", "true");
    rvHelpBtn.setAttribute("aria-expanded", "false");
  }

  function openHelpPopover() {
    if (!rvHelpPopover || !rvHelpBtn) return;
    closeSeqHintPop();
    rvHelpPopover.setAttribute("aria-hidden", "false");
    requestAnimationFrame(() => {
      rvHelpPopover.classList.add("resultsViewerHelpPopover--open");
    });
    rvHelpBtn.setAttribute("aria-expanded", "true");
  }

  function toggleHelpPopover() {
    if (rvHelpPopover?.classList.contains("resultsViewerHelpPopover--open")) closeHelpPopover();
    else openHelpPopover();
  }

  function hideRichCanvasEmpty() {
    emptyState?.classList.add("hidden");
  }

  function showRichCanvasEmpty() {
    if (!emptyState) return;
    emptyState.classList.remove("hidden");
    hint?.classList.add("hidden");
    hint?.classList.remove("resultsViewerCanvasHint--banner");
  }

  function showTransientCanvasHint(msg) {
    hideRichCanvasEmpty();
    if (!hint) return;
    hint.textContent = msg;
    hint.classList.remove("hidden");
    hint.classList.add("resultsViewerCanvasHint--banner");
  }

  function hideTransientCanvasHint() {
    if (!hint) return;
    hint.classList.add("hidden");
    hint.classList.remove("resultsViewerCanvasHint--banner");
  }

  const chartGrid = root.querySelector("#rvChartGrid");
  const wrap = root.querySelector("#rvCanvasWrap");
  const canvasHud = root.querySelector("#rvCanvasHud");
  const btnSpin = root.querySelector("#rvBtnSpin");
  const btnResetCam = root.querySelector("#rvBtnResetCam");
  const btnZoomIn = root.querySelector("#rvBtnZoomIn");
  const btnZoomOut = root.querySelector("#rvBtnZoomOut");
  const btnFit = root.querySelector("#rvBtnFit");
  const btnFs = root.querySelector("#rvBtnFs");
  const previewCol = root.querySelector("#rvPreviewCol");
  const ctxMenu = root.querySelector("#rvCtxMenu");
  const fileListEl = root.querySelector("#rvFileList");
  const searchEl = root.querySelector("#rvSearch");
  const filtersEl = root.querySelector("#rvFilters");
  const textPreview = root.querySelector("#rvTextPreview");
  const rvVtkSeqBar = root.querySelector("#rvVtkSeqBar");
  const rvVtkSlider = root.querySelector("#rvVtkSlider");
  const rvVtkSeqLabel = root.querySelector("#rvVtkSeqLabel");
  const rvVtkPlay = root.querySelector("#rvVtkPlay");
  const rvVtkFirst = root.querySelector("#rvVtkFirst");
  const rvVtkPrev = root.querySelector("#rvVtkPrev");
  const rvVtkNext = root.querySelector("#rvVtkNext");
  const rvVtkLast = root.querySelector("#rvVtkLast");
  const rvIntervalMs = root.querySelector("#rvIntervalMs");
  const rvIntervalDown = root.querySelector("#rvIntervalDown");
  const rvIntervalUp = root.querySelector("#rvIntervalUp");
  const rvMeshTrackLab = root.querySelector("#rvMeshTrackLab");
  const rvMeshTrackSelect = root.querySelector("#rvMeshTrackSelect");
  const rvSeqHintBtn = root.querySelector("#rvSeqHintBtn");
  const rvSeqHintPop = root.querySelector("#rvSeqHintPop");
  const rvVtkJump = root.querySelector("#rvVtkJump");
  const rvVtkLoop = root.querySelector("#rvVtkLoop");

  const LS_PLAYBACK_MS = "beso_rv_playback_interval_ms";
  const LS_PLAYBACK_LOOP = "beso_rv_playback_loop";
  let meshPlaybackLoop = true;

  function closeSeqHintPop() {
    if (!rvSeqHintPop || !rvSeqHintBtn) return;
    rvSeqHintPop.classList.remove("resultsViewerSeqHintPop--open");
    rvSeqHintPop.setAttribute("aria-hidden", "true");
    rvSeqHintBtn.setAttribute("aria-expanded", "false");
  }

  function openSeqHintPop() {
    if (!rvSeqHintPop || !rvSeqHintBtn) return;
    closeHelpPopover();
    rvSeqHintPop.setAttribute("aria-hidden", "false");
    requestAnimationFrame(() => {
      rvSeqHintPop.classList.add("resultsViewerSeqHintPop--open");
    });
    rvSeqHintBtn.setAttribute("aria-expanded", "true");
  }

  function toggleSeqHintPop() {
    if (rvSeqHintPop?.classList.contains("resultsViewerSeqHintPop--open")) closeSeqHintPop();
    else openSeqHintPop();
  }

  function loadSavedPlaybackPrefs() {
    try {
      const rawMs = localStorage.getItem(LS_PLAYBACK_MS);
      if (rawMs != null && rvIntervalMs) rvIntervalMs.value = String(clampPlaybackIntervalMs(rawMs));
      const rawLoop = localStorage.getItem(LS_PLAYBACK_LOOP);
      if (rawLoop === "0") meshPlaybackLoop = false;
      else if (rawLoop === "1") meshPlaybackLoop = true;
    } catch {
      /* ignore */
    }
    syncLoopBtnUi();
  }

  function savePlaybackIntervalMs() {
    try {
      localStorage.setItem(LS_PLAYBACK_MS, String(readPlaybackIntervalMs()));
    } catch {
      /* ignore */
    }
  }

  function savePlaybackLoopPref() {
    try {
      localStorage.setItem(LS_PLAYBACK_LOOP, meshPlaybackLoop ? "1" : "0");
    } catch {
      /* ignore */
    }
  }

  function syncPlayBtnUi() {
    if (!rvVtkPlay) return;
    rvVtkPlay.classList.toggle("resultsViewerVtkPlayBtn--playing", vtkPlaying);
    rvVtkPlay.setAttribute("aria-label", vtkPlaying ? "暂停" : "播放");
    const playIc = rvVtkPlay.querySelector(".resultsViewerVtkIc--play");
    const pauseIc = rvVtkPlay.querySelector(".resultsViewerVtkIc--pause");
    if (playIc) playIc.classList.toggle("hidden", vtkPlaying);
    if (pauseIc) pauseIc.classList.toggle("hidden", !vtkPlaying);
  }

  function syncLoopBtnUi() {
    if (!rvVtkLoop) return;
    rvVtkLoop.setAttribute("aria-pressed", meshPlaybackLoop ? "true" : "false");
    rvVtkLoop.classList.toggle("resultsViewerVtkLoopBtn--off", !meshPlaybackLoop);
  }

  function seqLabelTextAtFrameIndex(idx) {
    const n = meshSeqFrames.length;
    if (n < 1) return "—";
    const clamped = Math.max(0, Math.min(n - 1, idx));
    const fr = meshSeqFrames[clamped];
    const fn = fr ? `${fr.kind.toUpperCase()} · ${fr.file.name}` : "—";
    return `${clamped + 1} / ${n} · ${fn}`;
  }

  function applyVtkSeqLabel(scrubIdx = null) {
    if (!rvVtkSeqLabel) return;
    const n = meshSeqFrames.length;
    if (n < 1) {
      rvVtkSeqLabel.textContent = "—";
      rvVtkSeqLabel.classList.remove("resultsViewerVtkSeqLabel--scrub");
      return;
    }
    const raw = scrubIdx == null ? meshSeqIndex : parseInt(String(scrubIdx), 10);
    const idx = Number.isFinite(raw) ? Math.max(0, Math.min(n - 1, raw)) : meshSeqIndex;
    const t = seqLabelTextAtFrameIndex(idx);
    rvVtkSeqLabel.textContent = t;
    rvVtkSeqLabel.classList.toggle("resultsViewerVtkSeqLabel--scrub", scrubIdx != null && idx !== meshSeqIndex);
  }

  function clampPlaybackIntervalMs(v) {
    const n = Math.round(Number(v));
    if (!Number.isFinite(n)) return 800;
    return Math.max(50, Math.min(120000, n));
  }

  function readPlaybackIntervalMs() {
    return clampPlaybackIntervalMs(rvIntervalMs?.value);
  }

  function syncIntervalInputDisplay() {
    if (!rvIntervalMs) return;
    rvIntervalMs.value = String(readPlaybackIntervalMs());
  }

  let blobUrls = [];
  let threeDispose = null;
  let spinEnabled = false;
  let allFiles = [];
  let activeExtFilter = "all";
  let searchDebounce = null;
  let selectedRelPath = "";
  /** @type {MeshTrack[]} */
  let allMeshTracks = [];
  let activeMeshTrackId = "";
  /** @type {{ kind: 'vtk' | 'inp', file: File, n: number }[]} */
  let meshSeqFrames = [];
  let meshSeqIndex = 0;
  let vtkPlaying = false;
  /** @type {ReturnType<typeof setTimeout> | null} */
  let vtkPlayTimer = null;
  let vtkLoadBusy = false;

  loadSavedPlaybackPrefs();

  const objLoader = new OBJLoader();

  METRIC_NAMES.forEach((name) => {
    const card = document.createElement("div");
    card.className = "resultsViewerImgCard";
    card.dataset.metric = name;
    card.innerHTML = `
      <div class="resultsViewerImgHd"><span>${name.replace(".png", "")}</span></div>
      <div class="resultsViewerImgBody">
        <img alt="" />
        <div class="resultsViewerImgPlaceholder">
          <span class="resultsViewerImgPhMark" aria-hidden="true"></span>
          <span class="resultsViewerImgPhTitle">暂无图表</span>
          <span class="resultsViewerImgPhSub mono">${name}</span>
        </div>
      </div>`;
    chartGrid.appendChild(card);
  });

  function revokeBlobs() {
    blobUrls.forEach((u) => {
      try {
        URL.revokeObjectURL(u);
      } catch {
        /* ignore */
      }
    });
    blobUrls = [];
  }

  function destroyThree() {
    if (typeof threeDispose === "function") {
      threeDispose();
      threeDispose = null;
    }
    threeApi = null;
    wrap?.classList.remove("rvHas3d");
    wrap.querySelectorAll("canvas").forEach((c) => c.remove());
  }

  function hideTextPreview() {
    textPreview.classList.add("hidden");
    textPreview.textContent = "";
    wrap?.classList.remove("rvTextMode");
  }

  function showTextPreview(text, title) {
    destroyThree();
    hideRichCanvasEmpty();
    hideTransientCanvasHint();
    textPreview.textContent = text;
    textPreview.classList.remove("hidden");
    wrap?.classList.add("rvTextMode");
    objLabel.textContent = title || "INP";
  }

  let threeApi = null;

  function initThree() {
    destroyThree();
    hideTextPreview();
    hideRichCanvasEmpty();
    hideTransientCanvasHint();
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x061426);
    const camera = new THREE.PerspectiveCamera(42, 1, 0.02, 5000);
    camera.position.set(2.2, 1.6, 2.8);
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    if (canvasHud && wrap.contains(canvasHud)) {
      wrap.insertBefore(renderer.domElement, canvasHud);
    } else {
      wrap.appendChild(renderer.domElement);
    }
    renderer.domElement.classList.add("resultsViewerWebglCanvas");
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.06;
    scene.add(new THREE.AmbientLight(0xffffff, 0.38));
    const dl = new THREE.DirectionalLight(0xffffff, 0.95);
    dl.position.set(4, 6, 3);
    scene.add(dl);
    let grid = new THREE.GridHelper(3.5, 18, 0x334155, 0x1e293b);
    grid.position.y = -0.85;
    scene.add(grid);
    let meshRoot = null;
    const spinAxis = new THREE.Vector3(0, 1, 0);
    const spinQuat = new THREE.Quaternion().setFromAxisAngle(spinAxis, 0.0022);
    let raf = 0;
    let w = 1;
    let h = 1;
    /** @type {null | { pos: THREE.Vector3; target: THREE.Vector3; near: number; far: number; minD: number; maxD: number }} */
    let savedCameraView = null;
    let wireframeMode = false;
    const domCleanup = [];

    function fit() {
      const r = wrap.getBoundingClientRect();
      w = Math.max(120, Math.floor(r.width));
      h = Math.max(120, Math.floor(r.height));
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h, false);
    }
    const ro = new ResizeObserver(() => fit());
    ro.observe(wrap);
    fit();

    function tick() {
      raf = requestAnimationFrame(tick);
      if (spinEnabled && meshRoot) meshRoot.quaternion.multiply(spinQuat);
      controls.update();
      renderer.render(scene, camera);
    }
    tick();

    function captureCameraView() {
      savedCameraView = {
        pos: camera.position.clone(),
        target: controls.target.clone(),
        near: camera.near,
        far: camera.far,
        minD: controls.minDistance,
        maxD: controls.maxDistance,
      };
    }

    function restoreCameraView() {
      if (!savedCameraView) return;
      camera.position.copy(savedCameraView.pos);
      controls.target.copy(savedCameraView.target);
      camera.near = savedCameraView.near;
      camera.far = savedCameraView.far;
      camera.updateProjectionMatrix();
      controls.minDistance = savedCameraView.minD;
      controls.maxDistance = savedCameraView.maxD;
      controls.update();
    }

    function dollyBy(factor) {
      const off = camera.position.clone().sub(controls.target);
      const dist = off.length() * factor;
      const lo = Math.max(controls.minDistance * 1.02, dist);
      const hi = Math.min(controls.maxDistance * 0.98, lo);
      off.normalize().multiplyScalar(hi);
      camera.position.copy(controls.target).add(off);
      controls.update();
    }

    function applyWireframeToMeshes() {
      if (!meshRoot) return;
      meshRoot.traverse((c) => {
        if (c.isMesh && c.material) {
          const mats = Array.isArray(c.material) ? c.material : [c.material];
          for (const m of mats) {
            if (m && "wireframe" in m) m.wireframe = wireframeMode;
          }
        }
      });
    }

    function toggleWireframe() {
      wireframeMode = !wireframeMode;
      applyWireframeToMeshes();
    }

    function blockHistoryMouse(ev) {
      if (ev.button === 1 || ev.button === 3 || ev.button === 4) {
        ev.preventDefault();
      }
    }

    function onWheelNav(ev) {
      if (Math.abs(ev.deltaX) > Math.abs(ev.deltaY) * 1.2) {
        ev.preventDefault();
      }
    }

    renderer.domElement.addEventListener("mousedown", blockHistoryMouse, { capture: true, passive: false });
    renderer.domElement.addEventListener("auxclick", blockHistoryMouse, { capture: true, passive: false });
    renderer.domElement.addEventListener("wheel", onWheelNav, { passive: false });
    domCleanup.push(() => {
      renderer.domElement.removeEventListener("mousedown", blockHistoryMouse, { capture: true });
      renderer.domElement.removeEventListener("auxclick", blockHistoryMouse, { capture: true });
      renderer.domElement.removeEventListener("wheel", onWheelNav);
    });

    threeDispose = () => {
      domCleanup.forEach((fn) => {
        try {
          fn();
        } catch {
          /* ignore */
        }
      });
      domCleanup.length = 0;
      cancelAnimationFrame(raf);
      ro.disconnect();
      controls.dispose();
      renderer.dispose();
      if (meshRoot) {
        scene.remove(meshRoot);
        meshRoot.traverse((c) => {
          if (c.isMesh) {
            c.geometry?.dispose?.();
            if (Array.isArray(c.material)) c.material.forEach((m) => m.dispose?.());
            else c.material?.dispose?.();
          }
        });
        meshRoot = null;
      }
      renderer.domElement.remove();
    };

    /**
     * @param {THREE.Object3D} rootObj
     * @param {{ preserveView?: boolean }} [opts]
     */
    function frameObject(rootObj, opts = {}) {
      const preserveView = Boolean(opts.preserveView);
      const box = new THREE.Box3().setFromObject(rootObj);
      if (box.isEmpty()) return;
      const c = box.getCenter(new THREE.Vector3());
      const s = box.getSize(new THREE.Vector3());
      const r = Math.max(s.x, s.y, s.z, 1e-6) * 0.5;
      rootObj.position.sub(c);
      if (preserveView) {
        controls.update();
        fit();
        return;
      }
      const dist = Math.max(r * 2.4, 1.5);
      camera.position.set(dist * 0.9, dist * 0.55, dist * 0.95);
      camera.near = Math.max(0.01, dist / 400);
      camera.far = Math.max(2000, dist * 30);
      camera.updateProjectionMatrix();
      controls.target.set(0, 0, 0);
      controls.minDistance = Math.max(0.15, dist * 0.08);
      controls.maxDistance = Math.max(6, dist * 12);
      controls.update();
      fit();
      captureCameraView();
    }

    /**
     * @param {THREE.Object3D} rootObj
     * @param {{ preserveView?: boolean }} [opts] preserveView：序列播放时保持相机与旋转角，仅换网格
     */
    function setRoot(rootObj, opts = {}) {
      const preserveView = Boolean(opts.preserveView);
      /** @type {THREE.Quaternion | null} */
      let prevQuat = null;
      if (preserveView && meshRoot) {
        prevQuat = meshRoot.quaternion.clone();
      }
      if (meshRoot) {
        scene.remove(meshRoot);
        meshRoot.traverse((c) => {
          if (c.isMesh) {
            c.geometry?.dispose?.();
            if (Array.isArray(c.material)) c.material.forEach((m) => m.dispose?.());
            else c.material?.dispose?.();
          }
        });
      }
      meshRoot = rootObj;
      scene.add(meshRoot);
      frameObject(meshRoot, { preserveView });
      if (preserveView && prevQuat) {
        meshRoot.quaternion.copy(prevQuat);
      }
      applyWireframeToMeshes();
    }

    function fitViewNow() {
      if (!meshRoot) return;
      frameObject(meshRoot, { preserveView: false });
      applyWireframeToMeshes();
    }

    function toggleSceneGrid() {
      grid.visible = !grid.visible;
    }

    function resizeView() {
      fit();
      controls.update();
    }

    wrap.classList.add("rvHas3d");

    return {
      setRoot,
      scene,
      camera,
      controls,
      renderer,
      restoreCameraView,
      fitViewNow,
      dollyBy,
      toggleWireframe,
      resizeView,
      toggleSceneGrid,
    };
  }

  async function previewObj(file) {
    hideTextPreview();
    const text = await file.text();
    if (!threeApi) threeApi = initThree();
    const obj = objLoader.parse(text);
    applyMaterialToTree(obj);
    threeApi.setRoot(obj);
    objLabel.textContent = file.name;
    hideTransientCanvasHint();
  }

  function applyMaterialToTree(rootObj) {
    rootObj.traverse((c) => {
      if (c.isMesh) {
        c.material = new THREE.MeshStandardMaterial({
          color: 0x7dd3fc,
          metalness: 0.12,
          roughness: 0.42,
          side: THREE.DoubleSide,
        });
      }
    });
  }

  async function previewStep(file) {
    hideTextPreview();
    showTransientCanvasHint("正在加载 STEP（OpenCascade WASM）…");
    await new Promise((r) => requestAnimationFrame(r));

    const occt = await loadOcctImportJs();
    const buf = new Uint8Array(await file.arrayBuffer());
    const params = {
      linearUnit: "millimeter",
      linearDeflectionType: "bounding_box_ratio",
      linearDeflection: 0.004,
      angularDeflection: 0.35,
    };
    const result = occt.ReadStepFile(buf, params);
    if (!result?.success) {
      throw new Error((result && (result.error || result.message)) || "STEP 解析失败");
    }
    const list = result.meshes;
    if (!list?.length) {
      throw new Error("STEP 中未解析出网格");
    }

    if (!threeApi) threeApi = initThree();
    const group = new THREE.Group();
    for (const rm of list) {
      const posRaw = rm?.attributes?.position?.array;
      if (!posRaw?.length) continue;
      const posFlat = flattenNumberArray(posRaw);
      if (posFlat.length < 9) continue;

      const geom = new THREE.BufferGeometry();
      geom.setAttribute("position", new THREE.Float32BufferAttribute(new Float32Array(posFlat), 3));

      const nRaw = rm?.attributes?.normal?.array;
      if (nRaw?.length) {
        const nFlat = flattenNumberArray(nRaw);
        if (nFlat.length === posFlat.length) {
          geom.setAttribute("normal", new THREE.Float32BufferAttribute(new Float32Array(nFlat), 3));
        } else {
          geom.computeVertexNormals();
        }
      } else {
        geom.computeVertexNormals();
      }

      const idxRaw = rm?.index?.array;
      if (idxRaw?.length) {
        const idxFlat = flattenNumberArray(idxRaw);
        geom.setIndex(new THREE.BufferAttribute(new Uint32Array(idxFlat), 1));
      }

      const col = rm.color;
      const mat = new THREE.MeshStandardMaterial({
        color: col && col.length >= 3 ? new THREE.Color(col[0], col[1], col[2]) : 0x93c5fd,
        metalness: 0.1,
        roughness: 0.45,
        side: THREE.DoubleSide,
      });
      group.add(new THREE.Mesh(geom, mat));
    }
    if (!group.children.length) {
      throw new Error("STEP 三角化后无可显示网格");
    }
    threeApi.setRoot(group);
    objLabel.textContent = file.name;
    hideTransientCanvasHint();
  }

  async function previewInpTextOnly(file) {
    const maxBytes = Math.min(file.size, 480_000);
    const slice = file.slice(0, maxBytes);
    const text = await slice.text();
    const more = file.size > maxBytes ? `\n\n… （文件共 ${file.size} 字节，仅展示前 ${maxBytes} 字节）` : "";
    showTextPreview(text + more, file.name);
  }

  /** @param {{ preserveView?: boolean }} [opts] */
  async function previewInpAsMesh3d(file, opts = {}) {
    hideTextPreview();
    const quietLoad = Boolean(opts.suppressLoadingUi);
    if (quietLoad) hideTransientCanvasHint();
    if (!quietLoad) {
      showTransientCanvasHint("正在加载 INP 网格（FreeCAD 或本地解析）…");
      await new Promise((r) => requestAnimationFrame(r));
    }

    const base = (getBaseUrl() || "").replace(/\/+$/, "");
    if (base) {
      try {
        const fd = new FormData();
        fd.append("file", file, file.name);
        const r = await fetch(`${base}/api/preview/inp-mesh-vtk`, {
          method: "POST",
          body: fd,
        });
        if (r.ok) {
          const vtkText = await r.text();
          const { geometry } = parseLegacyAsciiUnstructuredGridTets(vtkText);
          if (!threeApi) threeApi = initThree();
          const mat = new THREE.MeshStandardMaterial({
            color: 0x34d399,
            metalness: 0.08,
            roughness: 0.42,
            side: THREE.DoubleSide,
          });
          threeApi.setRoot(new THREE.Mesh(geometry, mat), { preserveView: Boolean(opts.preserveView) });
          objLabel.textContent = `${file.name}（服务端 VTK）`;
          if (!quietLoad) hideTransientCanvasHint();
          return;
        }
      } catch {
        /* 回退本地解析 */
      }
    }

    try {
      const text = await file.text();
      const { geometry } = parseInpC3D4ToBufferGeometry(text);
      if (!threeApi) threeApi = initThree();
      const mat = new THREE.MeshStandardMaterial({
        color: 0x6ee7b7,
        metalness: 0.08,
        roughness: 0.42,
        side: THREE.DoubleSide,
      });
      threeApi.setRoot(new THREE.Mesh(geometry, mat), { preserveView: Boolean(opts.preserveView) });
      objLabel.textContent = `${file.name}（本地 C3D4）`;
      if (!quietLoad) hideTransientCanvasHint();
    } catch (e) {
      showTransientCanvasHint(`INP 三维预览不可用：${e?.message || e}。可查看文本片段。`);
      await previewInpTextOnly(file);
    }
  }

  function stopVtkPlayback() {
    vtkPlaying = false;
    if (vtkPlayTimer) {
      clearTimeout(vtkPlayTimer);
      vtkPlayTimer = null;
    }
    syncPlayBtnUi();
  }

  function syncMeshSeqIndexFromFile(file) {
    const rel = file.webkitRelativePath || file.name;
    for (const track of allMeshTracks) {
      const j = track.frames.findIndex((fr) => (fr.file.webkitRelativePath || fr.file.name) === rel);
      if (j < 0) continue;
      if (track.id !== activeMeshTrackId) {
        stopVtkPlayback();
        activeMeshTrackId = track.id;
        meshSeqFrames = [...track.frames];
        if (rvMeshTrackSelect) rvMeshTrackSelect.value = track.id;
      }
      meshSeqIndex = j;
      return;
    }
  }

  function populateMeshTrackSelect() {
    if (!rvMeshTrackSelect || !rvMeshTrackLab) return;
    rvMeshTrackSelect.innerHTML = "";
    for (const t of allMeshTracks) {
      const opt = document.createElement("option");
      opt.value = t.id;
      opt.textContent = t.label;
      rvMeshTrackSelect.appendChild(opt);
    }
    if (activeMeshTrackId && allMeshTracks.some((x) => x.id === activeMeshTrackId)) {
      rvMeshTrackSelect.value = activeMeshTrackId;
    } else if (allMeshTracks[0]) {
      rvMeshTrackSelect.value = allMeshTracks[0].id;
      activeMeshTrackId = allMeshTracks[0].id;
    }
    const multi = allMeshTracks.length > 1;
    rvMeshTrackLab.classList.toggle("hidden", !multi);
    rvMeshTrackSelect.disabled = !multi;
  }

  function updateVtkSeqBarUi() {
    const n = meshSeqFrames.length;
    if (!rvVtkSeqBar) return;
    const hasMeshTracks = allMeshTracks.some((t) => t.frames.length > 0);
    if (!hasMeshTracks || n < 1) {
      rvVtkSeqBar.classList.add("hidden");
      closeSeqHintPop();
      return;
    }
    rvVtkSeqBar.classList.remove("hidden");
    if (rvMeshTrackSelect && activeMeshTrackId) {
      rvMeshTrackSelect.value = activeMeshTrackId;
    }
    if (rvMeshTrackLab) {
      rvMeshTrackLab.classList.toggle("hidden", allMeshTracks.length <= 1);
    }
    if (rvMeshTrackSelect) {
      rvMeshTrackSelect.disabled = allMeshTracks.length <= 1;
    }
    const maxI = Math.max(0, n - 1);
    /** 播放中自动切帧加载时不锁 UI，避免进度条与按钮频繁禁用、且可随时暂停 */
    const uiLocked = vtkLoadBusy && !vtkPlaying;
    if (rvVtkSlider) {
      rvVtkSlider.min = "0";
      rvVtkSlider.max = String(maxI);
      rvVtkSlider.value = String(Math.min(meshSeqIndex, maxI));
      const si = Math.min(meshSeqIndex, maxI);
      const fr0 = meshSeqFrames[si];
      const nm = fr0 ? `${fr0.kind.toUpperCase()} · ${fr0.file.name}` : "—";
      rvVtkSlider.setAttribute("aria-valuetext", `第 ${si + 1} 帧，共 ${n} 帧，${nm}`);
    }
    applyVtkSeqLabel();
    if (rvVtkJump) {
      rvVtkJump.min = "1";
      rvVtkJump.max = String(Math.max(1, n));
      rvVtkJump.disabled = n < 1 || uiLocked;
      if (document.activeElement !== rvVtkJump) rvVtkJump.value = String(meshSeqIndex + 1);
    }
    if (rvVtkFirst) rvVtkFirst.disabled = n < 1 || uiLocked;
    if (rvVtkPrev) rvVtkPrev.disabled = n < 1 || uiLocked;
    if (rvVtkNext) rvVtkNext.disabled = n < 1 || uiLocked;
    if (rvVtkLast) rvVtkLast.disabled = n < 1 || uiLocked;
    if (rvVtkSlider) rvVtkSlider.disabled = n < 1 || uiLocked;
    if (rvVtkLoop) rvVtkLoop.disabled = n < 2 || uiLocked;
    if (rvVtkPlay) {
      rvVtkPlay.disabled = n < 2 || uiLocked;
      syncPlayBtnUi();
    }
  }

  function scheduleVtkAdvance() {
    if (vtkPlayTimer) clearTimeout(vtkPlayTimer);
    const delay = readPlaybackIntervalMs();
    vtkPlayTimer = setTimeout(async () => {
      vtkPlayTimer = null;
      if (!vtkPlaying || meshSeqFrames.length < 2) return;
      const n = meshSeqFrames.length;
      let next = meshSeqIndex + 1;
      if (next >= n) {
        if (!meshPlaybackLoop) {
          vtkPlaying = false;
          syncPlayBtnUi();
          updateVtkSeqBarUi();
          return;
        }
        next = 0;
      }
      await showMeshFrameAtIndex(next, { silent: true });
      if (vtkPlaying) scheduleVtkAdvance();
    }, delay);
  }

  /** @param {{ preserveView?: boolean }} [opts] */
  async function previewVtk(file, opts = {}) {
    hideTextPreview();
    const quietLoad = Boolean(opts.suppressLoadingUi);
    if (quietLoad) hideTransientCanvasHint();
    if (!quietLoad) {
      showTransientCanvasHint("正在解析 VTK（四面体网格）…");
      await new Promise((r) => requestAnimationFrame(r));
    }
    const text = await file.text();
    const { geometry } = parseLegacyAsciiUnstructuredGridTets(text);
    if (!threeApi) threeApi = initThree();
    const mat = new THREE.MeshStandardMaterial({
      color: 0x38bdf8,
      metalness: 0.08,
      roughness: 0.42,
      side: THREE.DoubleSide,
    });
    const mesh = new THREE.Mesh(geometry, mat);
    threeApi.setRoot(mesh, { preserveView: Boolean(opts.preserveView) });
    objLabel.textContent = file.name;
    if (!quietLoad) hideTransientCanvasHint();
  }

  /** @param {{ kind: 'vtk' | 'inp', file: File, n: number }} frame @param {{ preserveView?: boolean, suppressLoadingUi?: boolean }} [opts] */
  async function previewMeshFrame(frame, opts = {}) {
    const pass = {
      preserveView: Boolean(opts.preserveView),
      suppressLoadingUi: Boolean(opts.suppressLoadingUi),
    };
    if (frame.kind === "vtk") await previewVtk(frame.file, pass);
    else await previewInpAsMesh3d(frame.file, pass);
  }

  /** @param {number} idx @param {{ silent?: boolean }} [opts] */
  async function showMeshFrameAtIndex(idx, opts = {}) {
    const n = meshSeqFrames.length;
    if (n < 1) return;
    const i = Math.max(0, Math.min(n - 1, idx));
    meshSeqIndex = i;
    if (!opts.silent) stopVtkPlayback();
    updateVtkSeqBarUi();
    vtkLoadBusy = true;
    updateVtkSeqBarUi();
    try {
      const preserveView = Boolean(opts.silent && threeApi);
      await previewMeshFrame(meshSeqFrames[i], {
        preserveView,
        suppressLoadingUi: Boolean(opts.silent),
      });
      const f = meshSeqFrames[i].file;
      selectedRelPath = f.webkitRelativePath || f.name;
    } catch (e) {
      showTransientCanvasHint(`网格加载失败：${e?.message || e}`);
    } finally {
      vtkLoadBusy = false;
      updateVtkSeqBarUi();
      refreshFileList();
    }
  }

  async function loadPreviewForFile(file) {
    if (!file) return;
    selectedRelPath = file.webkitRelativePath || file.name;
    const ex = extOf(file.name);
    try {
      if (ex === ".vtk") {
        stopVtkPlayback();
        syncMeshSeqIndexFromFile(file);
        updateVtkSeqBarUi();
        await previewVtk(file);
      } else if (ex === ".obj") {
        stopVtkPlayback();
        await previewObj(file);
      } else if (ex === ".step" || ex === ".stp") {
        stopVtkPlayback();
        await previewStep(file);
      } else if (ex === ".inp") {
        stopVtkPlayback();
        syncMeshSeqIndexFromFile(file);
        updateVtkSeqBarUi();
        await previewInpAsMesh3d(file);
      } else {
        showTransientCanvasHint("不支持该扩展名预览");
      }
    } catch (e) {
      showTransientCanvasHint(`加载失败：${e?.message || e}`);
    }
    refreshFileList();
  }

  function isPreviewableFile(f) {
    const ex = extOf(f.name);
    return ex === ".step" || ex === ".stp" || ex === ".obj" || ex === ".inp" || ex === ".vtk";
  }

  function fileMatchesFilter(f) {
    if (!isPreviewableFile(f)) return false;
    const ex = extOf(f.name);
    if (activeExtFilter !== "all") {
      if (activeExtFilter === ".stp") {
        if (ex !== ".stp" && ex !== ".step") return false;
      } else if (ex !== activeExtFilter) {
        return false;
      }
    }
    const q = (searchEl?.value || "").trim().toLowerCase();
    if (!q) return true;
    const rel = (f.webkitRelativePath || f.name).toLowerCase();
    return rel.includes(q);
  }

  function refreshFileList() {
    if (!fileListEl) return;
    fileListEl.innerHTML = "";
    const filtered = allFiles.filter(fileMatchesFilter);
    filtered.sort((a, b) => (a.webkitRelativePath || a.name).localeCompare(b.webkitRelativePath || b.name));
    if (!filtered.length) {
      const empty = document.createElement("div");
      empty.className = "resultsViewerFileEmpty";
      empty.textContent = "无匹配文件";
      fileListEl.appendChild(empty);
      return;
    }
    for (const f of filtered) {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "resultsViewerFileRow";
      const rel = f.webkitRelativePath || f.name;
      if (rel === selectedRelPath) row.classList.add("active");
      const exn = extOf(f.name);
      const icon =
        exn === ".step" || exn === ".stp"
          ? "⬡"
          : exn === ".obj"
            ? "◆"
            : exn === ".inp"
              ? "▤"
              : exn === ".vtk"
                ? "◇"
                : "·";
      row.innerHTML = `<span class="resultsViewerFileIcon">${icon}</span><span class="resultsViewerFileName">${escapeHtml(
        f.name,
      )}</span>`;
      row.title = rel;
      row.addEventListener("click", () => void loadPreviewForFile(f));
      fileListEl.appendChild(row);
    }
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function applyPngs(fileList) {
    METRIC_NAMES.forEach((name) => {
      const card = chartGrid.querySelector(`[data-metric="${name}"]`);
      const img = card?.querySelector("img");
      const ph = card?.querySelector(".resultsViewerImgPlaceholder");
      const f = findFile(fileList, name);
      if (!img || !ph) return;
      if (f) {
        const url = URL.createObjectURL(f);
        blobUrls.push(url);
        img.src = url;
        img.classList.add("visible");
        ph.classList.add("hidden");
      } else {
        img.removeAttribute("src");
        img.classList.remove("visible");
        ph.classList.remove("hidden");
      }
    });
  }

  const RV_SCAN_MAX_FILES = 48;
  const RV_SCAN_MAX_BYTES = 42 * 1024 * 1024;
  const RV_DROP_MAX_FILES = 400;

  /**
   * @param {FileSystemDirectoryReader} dirReader
   * @returns {Promise<FileSystemEntry[]>}
   */
  async function readEntriesAll(dirReader) {
    /** @type {FileSystemEntry[]} */
    const acc = [];
    let batch;
    do {
      batch = await new Promise((res) => {
        try {
          dirReader.readEntries(res);
        } catch {
          res([]);
        }
      });
      acc.push(...batch);
    } while (batch.length > 0);
    return acc;
  }

  /**
   * @param {FileSystemEntry} entry
   * @param {string} relBase
   * @param {File[]} out
   */
  async function walkFsEntry(entry, relBase, out) {
    if (!entry || out.length >= RV_DROP_MAX_FILES) return;
    if (entry.isFile) {
      await new Promise((res) => {
        entry.file(
          /** @param {File} file */
          (file) => {
            const rel = relBase || file.name;
            try {
              Object.defineProperty(file, "webkitRelativePath", { value: rel, configurable: true });
            } catch {
              /* ignore */
            }
            out.push(file);
            res();
          },
          () => res(),
        );
      });
      return;
    }
    if (!entry.isDirectory) return;
    const reader = entry.createReader();
    const kids = await readEntriesAll(reader);
    for (const ch of kids) {
      if (out.length >= RV_DROP_MAX_FILES) break;
      const nextBase = relBase ? `${relBase}/${ch.name}` : ch.name;
      await walkFsEntry(ch, nextBase, out);
    }
  }

  /**
   * @param {DataTransfer} dt
   * @returns {Promise<File[]>}
   */
  async function collectFilesFromDataTransfer(dt) {
    const out = [];
    const items = dt.items?.length ? [...dt.items] : [];
    if (items.length) {
      for (const item of items) {
        if (out.length >= RV_DROP_MAX_FILES) break;
        const ent = item.webkitGetAsEntry?.();
        if (ent) {
          await walkFsEntry(ent, ent.isDirectory ? ent.name : "", out);
          continue;
        }
        if (item.kind === "file") {
          const f = item.getAsFile();
          if (f) {
            try {
              Object.defineProperty(f, "webkitRelativePath", { value: f.name, configurable: true });
            } catch {
              /* ignore */
            }
            out.push(f);
          }
        }
      }
    }
    if (out.length) return out;
    if (dt.files?.length) return Array.from(dt.files);
    return [];
  }

  /**
   * 与「导入文件夹」一致：用已有 File 列表刷新列表、序列轨与默认预览。
   * @param {File[]} fileList
   */
  function applyImportedFiles(fileList) {
    const fl = Array.isArray(fileList) ? fileList : [];
    if (fl.length > 0) hideRichCanvasEmpty();
    stopVtkPlayback();
    revokeBlobs();
    destroyThree();
    hideTextPreview();
    threeApi = null;
    allFiles = fl;
    allMeshTracks = discoverMeshTracks(allFiles);
    activeMeshTrackId = pickDefaultMeshTrackId(allMeshTracks);
    const curTr = allMeshTracks.find((t) => t.id === activeMeshTrackId) || allMeshTracks[0];
    meshSeqFrames = curTr ? [...curTr.frames] : [];
    meshSeqIndex = 0;
    populateMeshTrackSelect();
    activeExtFilter = "all";
    filtersEl?.querySelectorAll(".rvFilter").forEach((b) => {
      b.classList.toggle("active", b.dataset.ext === "all");
    });
    if (searchEl) searchEl.value = "";
    const rootName = fl[0]?.webkitRelativePath?.split("/")[0] || fl[0]?.name || "(文件夹)";
    const nPrev = allFiles.filter(isPreviewableFile).length;
    meta.textContent = `${rootName} · ${allFiles.length} 个文件（可预览 ${nPrev}）`;
    applyPngs(fl);
    updateVtkSeqBarUi();
    refreshFileList();
    const def = pickDefaultMeshFile(fl);
    if (def) void loadPreviewForFile(def);
    else {
      if (fl.length === 0) {
        hideTransientCanvasHint();
        showRichCanvasEmpty();
      } else {
        showTransientCanvasHint("未找到可预览的 .vtk / .step / .obj / .inp，可调整左侧筛选");
      }
      objLabel.textContent = "—";
    }
  }

  function onDirChange(ev) {
    const fl = ev.target?.files;
    if (!fl?.length) return;
    applyImportedFiles(Array.from(fl));
  }

  /**
   * 通过 /api/scan-directory + /runs/… 拉取工作区内目录下的已扫描文件，等价于编程方式「导入文件夹」。
   * @param {string} scanDir 绝对路径（与后端 scan_dir 一致）
   */
  async function openFromScanDir(scanDir) {
    const s = String(scanDir || "").trim();
    if (!s) throw new Error("scan_dir 为空");
    const base = String(getBaseUrl() || "").replace(/\/$/, "");
    const url = `${base}/api/scan-directory?scan_dir=${encodeURIComponent(s)}`;
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) {
      const t = await r.text().catch(() => "");
      throw new Error(`扫描目录失败 ${r.status}: ${t.slice(0, 240)}`);
    }
    const bundle = await r.json();
    const items = Array.isArray(bundle.files) ? bundle.files : [];
    /** @type {File[]} */
    const out = [];
    for (const it of items.slice(0, RV_SCAN_MAX_FILES)) {
      const abs = String(it.path || "").replace(/\\/g, "/");
      const low = abs.toLowerCase();
      const i = low.indexOf("/runs/");
      if (i < 0) continue;
      const rel = abs.slice(i + "/runs/".length);
      const segs = rel
        .split("/")
        .filter(Boolean)
        .map((x) => encodeURIComponent(x))
        .join("/");
      const fu = `${base}/runs/${segs}`;
      try {
        const fr = await fetch(fu, { cache: "no-store" });
        if (!fr.ok) continue;
        const buf = await fr.arrayBuffer();
        if (buf.byteLength > RV_SCAN_MAX_BYTES) continue;
        const name = String(it.name || rel.split("/").pop() || "file");
        const pseudo = `scan/${name}`;
        const file = new File([buf], name, { type: "application/octet-stream" });
        try {
          Object.defineProperty(file, "webkitRelativePath", { value: pseudo, configurable: true });
        } catch {
          /* ignore */
        }
        out.push(file);
      } catch {
        /* skip */
      }
    }
    open();
    if (!out.length) {
      applyImportedFiles([]);
      if (meta)
        meta.textContent = `已连接目录（扫描 ${items.length} 个输入项）但未能从 /runs/ 拉取可预览文件；请用「导入文件夹」或确认文件在 runs 下。`;
      return;
    }
    applyImportedFiles(out);
    const tail = s.replace(/\\/g, "/").split("/").filter(Boolean).pop() || "scan";
    if (meta) meta.textContent = `${tail} · 自服务器拉取 ${out.length} 个文件`;
  }

  function closeCtxMenu() {
    ctxMenu?.classList.add("hidden");
  }

  function openCtxMenu(clientX, clientY) {
    if (!ctxMenu || !wrap) return;
    ctxMenu.classList.remove("hidden");
    /** Shell 含 transform 时 fixed 相对 shell，故菜单相对画布区绝对定位 */
    const place = () => {
      const rect = wrap.getBoundingClientRect();
      const pad = 6;
      const w = ctxMenu.offsetWidth || 176;
      const h = ctxMenu.offsetHeight || 320;
      const relX = clientX - rect.left;
      const relY = clientY - rect.top;
      let lx = relX;
      let ly = relY;
      const maxX = Math.max(pad, rect.width - w - pad);
      const maxY = Math.max(pad, rect.height - h - pad);
      if (lx + w + pad > rect.width) lx = maxX;
      if (ly + h + pad > rect.height) ly = maxY;
      lx = Math.min(Math.max(pad, lx), maxX);
      ly = Math.min(Math.max(pad, ly), maxY);
      ctxMenu.style.left = `${lx}px`;
      ctxMenu.style.top = `${ly}px`;
    };
    requestAnimationFrame(() => requestAnimationFrame(place));
  }

  function isPreviewColFullscreen() {
    const el = document.fullscreenElement || /** @type {any} */ (document).webkitFullscreenElement;
    return Boolean(previewCol && el === previewCol);
  }

  function exitPreviewFullscreenIfNeeded() {
    try {
      if (!isPreviewColFullscreen()) return;
      if (document.exitFullscreen) void document.exitFullscreen();
      else if (/** @type {any} */ (document).webkitExitFullscreen) /** @type {any} */ (document).webkitExitFullscreen();
    } catch {
      /* ignore */
    }
  }

  async function togglePreviewColumnFullscreen() {
    if (!previewCol) return;
    try {
      if (!isPreviewColFullscreen()) {
        if (previewCol.requestFullscreen) await previewCol.requestFullscreen();
        else if (/** @type {any} */ (previewCol).webkitRequestFullscreen)
          /** @type {any} */ (previewCol).webkitRequestFullscreen();
        else {
          showTransientCanvasHint("当前浏览器不支持全屏 API");
          return;
        }
      } else {
        exitPreviewFullscreenIfNeeded();
      }
    } catch (err) {
      showTransientCanvasHint(`全屏操作失败：${err?.message || err}`);
    }
  }

  function syncFsUi() {
    const on = isPreviewColFullscreen();
    previewCol?.classList.toggle("rvColFs", on);
    if (btnFs) {
      btnFs.classList.toggle("rvFsActive", on);
      btnFs.setAttribute("aria-pressed", on ? "true" : "false");
      btnFs.setAttribute("title", on ? "退出全屏 (Esc)" : "全屏预览区");
      btnFs.querySelector(".rvFs-i-expand")?.classList.toggle("hidden", on);
      btnFs.querySelector(".rvFs-i-collapse")?.classList.toggle("hidden", !on);
    }
    threeApi?.resizeView?.();
  }

  function onPreviewFsChange() {
    syncFsUi();
  }

  document.addEventListener("fullscreenchange", onPreviewFsChange);
  document.addEventListener("webkitfullscreenchange", onPreviewFsChange);

  function syncSpinUi() {
    if (!btnSpin) return;
    btnSpin.classList.toggle("rvViewActive", spinEnabled);
    btnSpin.setAttribute("aria-pressed", spinEnabled ? "true" : "false");
  }

  function runRvCameraAction(/** @type {string} */ act) {
    if (act === "spin") {
      spinEnabled = !spinEnabled;
      syncSpinUi();
      return;
    }
    if (act === "fullscreen") {
      void togglePreviewColumnFullscreen();
      return;
    }
    if (act === "copyname") {
      const t = (objLabel?.textContent || "").trim();
      if (t && t !== "—") {
        void navigator.clipboard?.writeText(t).catch(() => {});
      }
      return;
    }
    if (!threeApi) return;
    if (act === "fit") threeApi.fitViewNow();
    else if (act === "reset") threeApi.restoreCameraView();
    else if (act === "zoomin") threeApi.dollyBy(0.86);
    else if (act === "zoomout") threeApi.dollyBy(1.18);
    else if (act === "wire") threeApi.toggleWireframe();
    else if (act === "grid") threeApi.toggleSceneGrid();
  }

  wrap?.addEventListener("contextmenu", (e) => {
    const cv = e.target?.closest?.(".resultsViewerWebglCanvas");
    if (!cv || !wrap.contains(cv)) return;
    e.preventDefault();
    openCtxMenu(e.clientX, e.clientY);
  });

  let rvDragDepth = 0;
  wrap?.addEventListener("dragenter", (e) => {
    if (!e.dataTransfer) return;
    e.preventDefault();
    rvDragDepth += 1;
    wrap.classList.add("rvDropActive");
  });
  wrap?.addEventListener("dragleave", (e) => {
    e.preventDefault();
    rvDragDepth = Math.max(0, rvDragDepth - 1);
    if (rvDragDepth === 0) wrap.classList.remove("rvDropActive");
  });
  wrap?.addEventListener("dragover", (e) => {
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
  });
  wrap?.addEventListener("drop", async (e) => {
    e.preventDefault();
    rvDragDepth = 0;
    wrap.classList.remove("rvDropActive");
    try {
      const files = await collectFilesFromDataTransfer(e.dataTransfer);
      if (files.length) applyImportedFiles(files);
    } catch (err) {
      showTransientCanvasHint(`拖入解析失败：${err?.message || err}`);
    }
  });

  ctxMenu?.addEventListener("mousedown", (e) => e.stopPropagation());
  ctxMenu?.addEventListener("click", (e) => {
    const b = e.target.closest?.("[data-rv-ctx]");
    if (!b) return;
    const act = b.getAttribute("data-rv-ctx") || "";
    closeCtxMenu();
    runRvCameraAction(act);
  });

  root.addEventListener(
    "mousedown",
    (e) => {
      if (ctxMenu?.classList.contains("hidden")) return;
      if (e.target.closest?.("#rvCtxMenu")) return;
      closeCtxMenu();
    },
    true,
  );

  filtersEl?.addEventListener("click", (e) => {
    const btn = e.target.closest?.(".rvFilter");
    if (!btn) return;
    activeExtFilter = btn.dataset.ext || "all";
    filtersEl.querySelectorAll(".rvFilter").forEach((b) => b.classList.toggle("active", b === btn));
    refreshFileList();
  });

  searchEl?.addEventListener("input", () => {
    window.clearTimeout(searchDebounce);
    searchDebounce = window.setTimeout(() => refreshFileList(), 160);
  });

  function open() {
    root.classList.remove("hidden");
    root.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
    root.classList.add("isOpen");
    shell?.classList.add("isOpen");
    requestAnimationFrame(() => {
      root.classList.add("isOpen");
      shell?.classList.add("isOpen");
    });
  }

  function close() {
    stopVtkPlayback();
    closeCtxMenu();
    closeHelpPopover();
    closeSeqHintPop();
    exitPreviewFullscreenIfNeeded();
    root.classList.remove("isOpen");
    shell?.classList.remove("isOpen");
    document.body.style.overflow = "";
    window.setTimeout(() => {
      root.classList.add("hidden");
      root.setAttribute("aria-hidden", "true");
      if (inpDir) inpDir.value = "";
    }, 320);
  }

  btnClose?.addEventListener("click", close);
  rvHelpBtn?.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleHelpPopover();
  });
  shell?.addEventListener("click", (e) => {
    if (rvHelpPopover?.classList.contains("resultsViewerHelpPopover--open") && !e.target.closest(".resultsViewerHdHelpWrap")) {
      closeHelpPopover();
    }
    if (rvSeqHintPop?.classList.contains("resultsViewerSeqHintPop--open") && !e.target.closest(".resultsViewerSeqHintWrap")) {
      closeSeqHintPop();
    }
  });
  backdrop?.addEventListener("click", (e) => {
    if (e.target?.dataset?.rvClose) close();
  });
  btnPick?.addEventListener("click", () => inpDir?.click());
  inpDir?.addEventListener("change", onDirChange);
  syncSpinUi();
  syncFsUi();
  btnSpin?.addEventListener("click", () => {
    spinEnabled = !spinEnabled;
    syncSpinUi();
  });
  btnResetCam?.addEventListener("click", () => {
    if (threeApi) threeApi.restoreCameraView();
  });
  btnZoomIn?.addEventListener("click", () => {
    if (threeApi) threeApi.dollyBy(0.86);
  });
  btnZoomOut?.addEventListener("click", () => {
    if (threeApi) threeApi.dollyBy(1.18);
  });
  btnFit?.addEventListener("click", () => {
    if (threeApi) threeApi.fitViewNow();
  });
  btnFs?.addEventListener("click", () => void togglePreviewColumnFullscreen());

  rvSeqHintBtn?.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleSeqHintPop();
  });

  rvVtkPlay?.addEventListener("click", () => {
    if (meshSeqFrames.length < 2) return;
    if (vtkPlaying) {
      vtkPlaying = false;
      if (vtkPlayTimer) {
        clearTimeout(vtkPlayTimer);
        vtkPlayTimer = null;
      }
      syncPlayBtnUi();
      updateVtkSeqBarUi();
      return;
    }
    if (vtkLoadBusy && !vtkPlaying) return;
    vtkPlaying = true;
    syncPlayBtnUi();
    scheduleVtkAdvance();
  });
  rvVtkFirst?.addEventListener("click", () => {
    stopVtkPlayback();
    void showMeshFrameAtIndex(0);
  });
  rvVtkPrev?.addEventListener("click", () => {
    stopVtkPlayback();
    void showMeshFrameAtIndex(meshSeqIndex - 1);
  });
  rvVtkNext?.addEventListener("click", () => {
    stopVtkPlayback();
    void showMeshFrameAtIndex(meshSeqIndex + 1);
  });
  rvVtkLast?.addEventListener("click", () => {
    stopVtkPlayback();
    void showMeshFrameAtIndex(meshSeqFrames.length - 1);
  });
  rvVtkSlider?.addEventListener("input", () => {
    if (!rvVtkSlider) return;
    const v = parseInt(rvVtkSlider.value, 10);
    if (Number.isFinite(v)) applyVtkSeqLabel(v);
  });
  rvVtkSlider?.addEventListener("change", () => {
    stopVtkPlayback();
    const v = parseInt(rvVtkSlider.value, 10);
    if (Number.isFinite(v)) void showMeshFrameAtIndex(v);
  });
  function bumpIntervalMs(delta) {
    if (!rvIntervalMs) return;
    const v = readPlaybackIntervalMs() + delta;
    rvIntervalMs.value = String(clampPlaybackIntervalMs(v));
    if (vtkPlaying) {
      if (vtkPlayTimer) clearTimeout(vtkPlayTimer);
      scheduleVtkAdvance();
    }
  }

  rvIntervalDown?.addEventListener("click", () => {
    bumpIntervalMs(-50);
    savePlaybackIntervalMs();
  });
  rvIntervalUp?.addEventListener("click", () => {
    bumpIntervalMs(50);
    savePlaybackIntervalMs();
  });
  rvIntervalMs?.addEventListener("change", () => {
    syncIntervalInputDisplay();
    savePlaybackIntervalMs();
    if (vtkPlaying) {
      if (vtkPlayTimer) clearTimeout(vtkPlayTimer);
      scheduleVtkAdvance();
    }
  });
  rvIntervalMs?.addEventListener("blur", () => {
    syncIntervalInputDisplay();
    savePlaybackIntervalMs();
  });

  rvMeshTrackSelect?.addEventListener("change", () => {
    stopVtkPlayback();
    activeMeshTrackId = rvMeshTrackSelect.value;
    const tr = allMeshTracks.find((t) => t.id === activeMeshTrackId);
    meshSeqFrames = tr ? [...tr.frames] : [];
    meshSeqIndex = 0;
    updateVtkSeqBarUi();
    void showMeshFrameAtIndex(0);
  });

  rvVtkJump?.addEventListener("change", () => {
    stopVtkPlayback();
    const n = meshSeqFrames.length;
    let v = parseInt(String(rvVtkJump?.value), 10);
    if (!Number.isFinite(v) || n < 1) {
      updateVtkSeqBarUi();
      return;
    }
    v = Math.max(1, Math.min(n, v));
    void showMeshFrameAtIndex(v - 1);
  });

  rvVtkLoop?.addEventListener("click", () => {
    meshPlaybackLoop = !meshPlaybackLoop;
    syncLoopBtnUi();
    savePlaybackLoopPref();
  });

  window.addEventListener("keydown", (e) => {
    if (!root.classList.contains("isOpen")) return;
    const t = e.target instanceof Element ? e.target : null;
    const typing = Boolean(t && (t.closest("input, textarea, select") || t.closest('[contenteditable="true"]')));

    if (e.key === "Escape") {
      if (isPreviewColFullscreen()) {
        exitPreviewFullscreenIfNeeded();
        e.preventDefault();
        return;
      }
      if (rvHelpPopover?.classList.contains("resultsViewerHelpPopover--open")) {
        closeHelpPopover();
        e.preventDefault();
        return;
      }
      if (rvSeqHintPop?.classList.contains("resultsViewerSeqHintPop--open")) {
        closeSeqHintPop();
        e.preventDefault();
        return;
      }
      if (ctxMenu && !ctxMenu.classList.contains("hidden")) {
        closeCtxMenu();
        return;
      }
      close();
      return;
    }

    const seqBarOn = rvVtkSeqBar && !rvVtkSeqBar.classList.contains("hidden") && meshSeqFrames.length >= 1;
    if (!typing && seqBarOn && !(vtkLoadBusy && !vtkPlaying)) {
      const spaceBlocked = Boolean(
        t?.closest?.("button:not(#rvVtkPlay), a, .rvFilter, [role=menuitem], input, textarea, select"),
      );
      if (e.code === "Space" && meshSeqFrames.length >= 2) {
        if (spaceBlocked) return;
        e.preventDefault();
        rvVtkPlay?.click();
        return;
      }
      const arrowBlocked = t === rvVtkSlider || Boolean(t?.closest?.(".resultsViewerFileList"));
      if (e.key === "ArrowLeft" && !arrowBlocked) {
        e.preventDefault();
        stopVtkPlayback();
        void showMeshFrameAtIndex(meshSeqIndex - 1);
        return;
      }
      if (e.key === "ArrowRight" && !arrowBlocked) {
        e.preventDefault();
        stopVtkPlayback();
        void showMeshFrameAtIndex(meshSeqIndex + 1);
        return;
      }
      const homeEndBlocked = Boolean(t?.closest?.(".resultsViewerFileList"));
      if (e.key === "Home" && !homeEndBlocked) {
        e.preventDefault();
        stopVtkPlayback();
        void showMeshFrameAtIndex(0);
        return;
      }
      if (e.key === "End" && !homeEndBlocked) {
        e.preventDefault();
        stopVtkPlayback();
        void showMeshFrameAtIndex(meshSeqFrames.length - 1);
        return;
      }
    }
  });

  return {
    open,
    close,
    openFromScanDir,
    applyImportedFiles,
    destroy: () => {
      stopVtkPlayback();
      closeHelpPopover();
      closeSeqHintPop();
      exitPreviewFullscreenIfNeeded();
      document.removeEventListener("fullscreenchange", onPreviewFsChange);
      document.removeEventListener("webkitfullscreenchange", onPreviewFsChange);
      revokeBlobs();
      destroyThree();
      root.remove();
    },
  };
}
