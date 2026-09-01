/**
 * 本地结果查看器：导入文件夹，按类型筛选，预览 STEP / STL / OBJ / INP / VTK 与四张指标 PNG；
 * 支持 BESO 多轨迭代序列：`fileNNN.vtk`、`fileNNN_state0.inp`、`fileNNN_state1.inp`、`fileNNN.inp` 分开，可在工具条选择要播放的序列。
 */
import * as THREE from "three";
import { OBJLoader } from "three/examples/jsm/loaders/OBJLoader.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import {
  parseInpC3D4ToBufferGeometry,
  parseInpFemBc,
  buildFemBcOverlayGroup,
} from "./flow_main.inpCcxAscii.js";
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
const RV_PREVIEW_EXTS = new Set([".vtk", ".inp", ".obj", ".step", ".stp", ".stl"]);
const RV_STATIC_MOUNT_PREFIXES = new Set(["runs", "examples", "third_party", "uploads"]);
const RV_FILE_ACCEPT = ".vtk,.inp,.obj,.step,.stp,.stl";

function normFsPath(p) {
  return String(p || "").replace(/\\/g, "/").replace(/\/+$/, "");
}

function workspaceRelativeFetchUrl(base, absPath, workspaceRoot) {
  const root = normFsPath(workspaceRoot);
  const abs = normFsPath(absPath);
  if (!root || !abs.toLowerCase().startsWith(`${root.toLowerCase()}/`)) return null;
  const rel = abs.slice(root.length).replace(/^\/+/, "");
  const top = rel.split("/")[0] || "";
  if (!RV_STATIC_MOUNT_PREFIXES.has(top)) return null;
  const segs = rel.split("/").filter(Boolean).map((x) => encodeURIComponent(x));
  return `${String(base || "").replace(/\/+$/, "")}/${segs.join("/")}`;
}

function isResultsViewerFetchItem(it) {
  const ext = String(it?.ext || extOf(it?.name || "")).toLowerCase();
  if (RV_PREVIEW_EXTS.has(ext)) return true;
  const nm = String(it?.name || "").toLowerCase();
  if (nm === "measurements.json" || nm === "design_spec.json") return true;
  return METRIC_NAMES.some((m) => m.toLowerCase() === nm);
}

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
    const prefer = steps.find((f) => /rebuilt|fitted|smoothed/i.test(f.name));
    if (prefer) return prefer;
    return [...steps].sort((a, b) => a.name.localeCompare(b.name))[0];
  }
  const stls = arr.filter((f) => extOf(f.name) === ".stl");
  if (stls.length) {
    const prefer = stls.find((f) => /smoothed|preview|overlay|raw_boundary/i.test(f.name));
    if (prefer) return prefer;
    return [...stls].sort((a, b) => a.name.localeCompare(b.name))[0];
  }
  const inps = arr.filter((f) => extOf(f.name) === ".inp").sort((a, b) => a.name.localeCompare(b.name));
  return inps[0] || null;
}

const PARAMETRIC_SCALE_MIN = 0.35;
const PARAMETRIC_SCALE_MAX = 1.75;
const PARAMETRIC_WALL_MIN = 20;
const PARAMETRIC_WALL_MAX = 1200;
const PARAMETRIC_MAX_STATIONS = 8;

function findMeasurementsFile(files) {
  return (
    Array.from(files || []).find((f) => {
      const rel = (f.webkitRelativePath || f.name || "").toLowerCase();
      return rel.endsWith("measurements.json") || f.name?.toLowerCase() === "measurements.json";
    }) || null
  );
}

function clampParametric(v, lo, hi) {
  return Math.min(hi, Math.max(lo, v));
}

function interpLegRadius(leg, t) {
  const fracs = Array.isArray(leg.station_fracs) && leg.station_fracs.length ? leg.station_fracs : [0, 1 / 3, 2 / 3, 1];
  const radii =
    Array.isArray(leg.station_radii_mm) && leg.station_radii_mm.length === fracs.length
      ? leg.station_radii_mm
      : fracs.map(() => Number(leg.radius_mm) || 3000);
  const tv = clampParametric(Number(t), 0, 1);
  if (tv <= fracs[0]) return radii[0];
  if (tv >= fracs[fracs.length - 1]) return radii[fracs.length - 1];
  for (let i = 0; i < fracs.length - 1; i += 1) {
    if (fracs[i] <= tv && tv <= fracs[i + 1]) {
      const span = Math.max(fracs[i + 1] - fracs[i], 1e-9);
      const u = (tv - fracs[i]) / span;
      return radii[i] * (1 - u) + radii[i + 1] * u;
    }
  }
  return radii[radii.length - 1];
}

/** @returns {{ t: number, scale: number, locked?: boolean }[]} */
function defaultLegStationsFromMeas(leg) {
  const fracs = Array.isArray(leg.station_fracs) && leg.station_fracs.length ? leg.station_fracs : [0, 1 / 3, 2 / 3, 1];
  const scales = Array.isArray(leg.radius_scales) && leg.radius_scales.length === fracs.length ? leg.radius_scales : fracs.map(() => 1);
  return fracs.map((t, i) => ({
    t: Number(t),
    scale: Number(scales[i] ?? 1),
    locked: i === 0 || i === fracs.length - 1,
  }));
}

function normalizeLegStations(stations) {
  const cleaned = (stations || [])
    .map((s) => ({
      t: clampParametric(Number(s.t), 0, 1),
      scale: clampParametric(Number(s.scale), PARAMETRIC_SCALE_MIN, PARAMETRIC_SCALE_MAX),
      locked: Boolean(s.locked),
    }))
    .sort((a, b) => a.t - b.t);
  if (!cleaned.length) return [{ t: 0, scale: 1, locked: true }, { t: 1, scale: 1, locked: true }];
  if (cleaned[0].t > 1e-4) cleaned.unshift({ t: 0, scale: cleaned[0].scale, locked: true });
  else cleaned[0] = { ...cleaned[0], t: 0, locked: true };
  if (1 - cleaned[cleaned.length - 1].t > 1e-4) cleaned.push({ t: 1, scale: cleaned[cleaned.length - 1].scale, locked: true });
  else cleaned[cleaned.length - 1] = { ...cleaned[cleaned.length - 1], t: 1, locked: true };
  const out = [];
  for (const st of cleaned) {
    if (out.length && Math.abs(st.t - out[out.length - 1].t) < 0.008) out[out.length - 1] = { ...st, locked: st.locked || out[out.length - 1].locked };
    else out.push({ ...st });
  }
  out[0].locked = true;
  out[out.length - 1].locked = true;
  return out;
}

function addOrientedFrustum(group, p0, p1, rBottom, rTop, color, opts = {}) {
  const segLen = p0.distanceTo(p1);
  if (segLen < 1) return;
  const hollow = Boolean(opts.hollow);
  const wall = Math.max(Number(opts.wall) || 0, 0);
  const mk = (rb, rt, side, opacity = 1) => {
    const geom = new THREE.CylinderGeometry(rt, rb, segLen, 36);
    const mat = new THREE.MeshStandardMaterial({
      color,
      metalness: 0.12,
      roughness: 0.42,
      side,
      transparent: opacity < 1,
      opacity,
    });
    const mesh = new THREE.Mesh(geom, mat);
    const mid = p0.clone().add(p1).multiplyScalar(0.5);
    mesh.position.copy(mid);
    const dir = p1.clone().sub(p0).normalize();
    mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
    group.add(mesh);
  };
  mk(rBottom, rTop, THREE.DoubleSide, hollow ? 0.92 : 1);
  if (hollow && wall > 0) {
    const ri0 = Math.max(rBottom - wall, 1);
    const ri1 = Math.max(rTop - wall, 1);
    if (ri0 > 1.5 && ri1 > 1.5) mk(ri0, ri1, THREE.BackSide, 0.85);
  }
}

/**
 * @param {object} meas
 * @param {{ t: number, scale: number }[][]} legStations
 * @param {boolean[]} legHollow
 * @param {number[]} legWallMm
 * @param {number} hubScale
 */
function buildParametricThreeGroup(meas, legStations, legHollow, legWallMm, hubScale) {
  const group = new THREE.Group();
  const legColors = [0x7dd3fc, 0xa5b4fc, 0x6ee7b7];
  const legs = Array.isArray(meas?.legs) ? meas.legs : [];
  legs.forEach((leg, li) => {
    const axis = new THREE.Vector3(...(leg.axis || [0, 0, 1])).normalize();
    const base = new THREE.Vector3(...(leg.base || [0, 0, 0]));
    const length = Math.max(Number(leg.length_mm) || 1, 1);
    const stations = normalizeLegStations(legStations[li] || defaultLegStationsFromMeas(leg));
    const color = legColors[li % legColors.length];
    const hollow = Boolean(legHollow[li]);
    const wall = Number(legWallMm[li]) || 200;
    for (let si = 0; si < stations.length - 1; si += 1) {
      const s0 = stations[si];
      const s1 = stations[si + 1];
      const r0 = Math.max(interpLegRadius(leg, s0.t) * (s0.scale ?? 1), 1);
      const r1 = Math.max(interpLegRadius(leg, s1.t) * (s1.scale ?? 1), 1);
      const p0 = base.clone().add(axis.clone().multiplyScalar(s0.t * length));
      const p1 = base.clone().add(axis.clone().multiplyScalar(s1.t * length));
      addOrientedFrustum(group, p0, p1, r0, r1, color, { hollow, wall });
    }
  });
  const hub = meas?.hub;
  if (hub) {
    const hr = Math.max(Number(hub.radius_mm) * hubScale, 100);
    const h = Math.max(Number(hub.thickness_mm) || 500, 100);
    const z0 = Number(hub.z_bottom_mm) || 0;
    const geom = new THREE.CylinderGeometry(hr, hr, h, 48);
    const mat = new THREE.MeshStandardMaterial({
      color: 0xfcd34d,
      metalness: 0.1,
      roughness: 0.4,
      side: THREE.DoubleSide,
    });
    const mesh = new THREE.Mesh(geom, mat);
    mesh.position.set(Number(hub.center_xy?.[0]) || 0, Number(hub.center_xy?.[1]) || 0, z0 + h / 2);
    mesh.rotation.x = Math.PI / 2;
    group.add(mesh);
  }
  return group;
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
                    <p class="resultsViewerHelpPopoverP">导入 <span class="mono">runs/&lt;job&gt;/</span> 或 <span class="mono">examples/beso/</span> · 筛选后预览 <span class="mono">.vtk / .step / .stl / .obj / .inp</span>；<span class="mono">file*.vtk</span>、<span class="mono">file*_state0.inp</span>、<span class="mono">file*_state1.inp</span> 等为<strong>不同序列</strong>，可在工具条切换播放。</p>
                    <p class="resultsViewerHelpPopoverP"><span class="mono">STEP</span> 使用 <span class="mono">occt-import-js</span>（OpenCascade WASM）三角化；<span class="mono">STL</span> 为浏览器端三角网格；<span class="mono">VTK</span> / <span class="mono">INP(C3D4)</span> 为四面体展开三角面；<span class="mono">INP</span> 三维优先走服务端 <span class="mono">FreeCAD</span> 转换（需本机后端与 FreeCAD）；<span class="mono">VTK</span> 与 <span class="mono">state0</span>/<span class="mono">state1</span> 等为<strong>独立序列</strong>。单帧大文件解析可能需数秒。</p>
                    <p class="resultsViewerHelpPopoverP"><strong>播放快捷键</strong>（焦点不在输入框时）：<span class="mono">Space</span> 播放/暂停；<span class="mono">←</span> <span class="mono">→</span> 上一帧/下一帧；<span class="mono">Home</span> / <span class="mono">End</span> 首帧/末帧。拖动进度条时右侧帧号会随刻度预览；刻度确认后再加载对应帧。</p>
                    <p class="resultsViewerHelpPopoverP"><strong>约束 / 载荷</strong>：预览区右下角开关打开后，从同目录 <span class="mono">Analysis-beso.inp</span> 等解析 <span class="mono">*BOUNDARY</span>（红点固定）与 <span class="mono">*CLOAD</span>（黄箭头），并显示荷载分步摘要。</p>
                    <p class="resultsViewerHelpPopoverP"><strong>尺寸</strong>：打开尺寸开关后，优先读取同目录 <span class="mono">design_spec.json</span>（FreeCAD 实测圆心/半径/边长）。标注三凹角圆心距为边长、挖去圆 R、外轮廓跨度、水面线、水上/水下高度与载荷圆直径；无规格文件时则按包围盒与 INP 载荷点推断。</p>
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
        <button type="button" class="btn" id="rvPickFilesBtn">导入文件</button>
        <input type="file" id="rvDirInput" class="hidden" webkitdirectory directory multiple />
        <input type="file" id="rvFilesInput" class="hidden" multiple accept=".vtk,.inp,.obj,.step,.stp,.stl" />
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
            <button type="button" class="rvFilter" data-ext=".stl">STL</button>
            <button type="button" class="rvFilter" data-ext=".obj">OBJ</button>
            <button type="button" class="rvFilter" data-ext=".inp">INP</button>
            <button type="button" class="rvFilter" data-ext=".vtk">VTK</button>
          </div>
          <input type="search" class="resultsViewerSearch" id="rvSearch" placeholder="筛选文件名…" autocomplete="off" />
          <div class="resultsViewerParametric hidden" id="rvParametric" aria-label="变径柱参数调节">
            <div class="resultsViewerParametricHd">
              <span class="chip">变径柱</span>
              <span class="resultsViewerParametricSub" id="rvParametricSub">结果查看</span>
              <button type="button" class="btn resultsViewerParametricModeBtn" id="rvParametricMode" aria-pressed="false" title="进入/退出调节模式">调节</button>
            </div>
            <div class="resultsViewerParametricBd hidden" id="rvParametricBd"></div>
            <div class="resultsViewerParametricFt">
              <button type="button" class="btn" id="rvParametricReset" disabled title="仅调节模式可用">重置</button>
              <span class="resultsViewerParametricStatus mono" id="rvParametricStatus"></span>
            </div>
          </div>
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
                <p class="resultsViewerCanvasEmptyLead">请先点「导入文件夹」（如 <span class="mono">beso7/addition</span> 或 <span class="mono">beso_output</span>），或「导入文件」/ 拖入 <span class="mono">.stl</span>、<span class="mono">.step</span>。</p>
                <ul class="resultsViewerCanvasEmptyList">
                  <li>网格：<span class="mono">.vtk</span>、<span class="mono">.inp</span>（C3D4）</li>
                  <li>几何：<span class="mono">.step</span>、<span class="mono">.stl</span>、<span class="mono">.obj</span></li>
                  <li>多序列 <span class="mono">fileNNN.vtk</span> 可在上方轨道播放</li>
                </ul>
              </div>
            </div>
            <div class="resultsViewerCanvasHint hidden" id="rvCanvasHint"></div>
            <aside class="resultsViewerBcPanel hidden" id="rvBcPanel" aria-label="约束与载荷信息">
              <div class="resultsViewerBcPanelHd">
                <span class="resultsViewerBcPanelTitle">约束 / 载荷</span>
                <label class="resultsViewerBcStepLab hidden" id="rvBcStepLab">分步
                  <select class="resultsViewerBcStepSelect" id="rvBcStepSelect" title="选择 *STEP"></select>
                </label>
              </div>
              <div class="resultsViewerBcPanelBd" id="rvBcPanelBd">
                <p class="resultsViewerBcEmpty">打开开关后解析 INP 中的固定约束与集中力。</p>
              </div>
              <div class="resultsViewerBcLegend" aria-hidden="true">
                <span class="resultsViewerBcLeg"><i class="resultsViewerBcDot resultsViewerBcDot--fix"></i>固定</span>
                <span class="resultsViewerBcLeg"><i class="resultsViewerBcDot resultsViewerBcDot--load"></i>载荷</span>
              </div>
            </aside>
            <aside class="resultsViewerDimPanel hidden" id="rvDimPanel" aria-label="尺寸信息">
              <div class="resultsViewerDimPanelHd">
                <span class="resultsViewerDimPanelTitle">设计尺寸</span>
              </div>
              <div class="resultsViewerDimPanelBd" id="rvDimPanelBd">
                <p class="resultsViewerBcEmpty">打开开关后显示高度、边长、载荷圆等设计标注（优先 design_spec.json）。</p>
              </div>
            </aside>
            <div class="resultsViewerCanvasHud" id="rvCanvasHud" aria-label="三维视图控制">
              <div class="resultsViewerViewToolbar" role="toolbar">
                <button type="button" class="resultsViewerViewBtn resultsViewerViewBtn--bc" id="rvBtnBc" title="显示固定约束 / 荷载分步" aria-pressed="false">
                  <svg class="resultsViewerViewSvg" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v6M8 7h8"/><path d="M6 14h12v6H6z"/><path d="M9 14v6M15 14v6"/><path d="M4 11h16"/></svg>
                </button>
                <button type="button" class="resultsViewerViewBtn resultsViewerViewBtn--dim" id="rvBtnDim" title="显示设计尺寸 / 水面 / 载荷圆" aria-pressed="false">
                  <svg class="resultsViewerViewSvg" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20V10M4 20h10"/><path d="M4 10h6v6"/><path d="M14 4h6v6M20 4l-6 6"/><path d="M8 14l8-8"/></svg>
                </button>
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
              <button type="button" class="resultsViewerCtxItem" role="menuitem" data-rv-ctx="bc"><span class="resultsViewerCtxIc" aria-hidden="true">⬇</span>约束 / 载荷叠加</button>
              <button type="button" class="resultsViewerCtxItem" role="menuitem" data-rv-ctx="dim"><span class="resultsViewerCtxIc" aria-hidden="true">▤</span>尺寸 / 包围盒</button>
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
  const btnPickFiles = root.querySelector("#rvPickFilesBtn");
  const inpDir = root.querySelector("#rvDirInput");
  const inpFiles = root.querySelector("#rvFilesInput");
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
  const btnBc = root.querySelector("#rvBtnBc");
  const btnDim = root.querySelector("#rvBtnDim");
  const rvBcPanel = root.querySelector("#rvBcPanel");
  const rvBcPanelBd = root.querySelector("#rvBcPanelBd");
  const rvBcStepLab = root.querySelector("#rvBcStepLab");
  const rvBcStepSelect = root.querySelector("#rvBcStepSelect");
  const rvDimPanel = root.querySelector("#rvDimPanel");
  const rvDimPanelBd = root.querySelector("#rvDimPanelBd");
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
  const rvParametric = root.querySelector("#rvParametric");
  const rvParametricBd = root.querySelector("#rvParametricBd");
  const rvParametricReset = root.querySelector("#rvParametricReset");
  const rvParametricStatus = root.querySelector("#rvParametricStatus");
  const rvParametricMode = root.querySelector("#rvParametricMode");
  const rvParametricSub = root.querySelector("#rvParametricSub");

  let bcOverlayEnabled = false;
  let dimOverlayEnabled = false;
  let bcStepIndex = 0; // 1-based; 0 = last step
  /** @type {File | null} */
  let bcSourceFile = null;
  /** @type {ReturnType<typeof parseInpFemBc> | null} */
  let bcParsed = null;
  /** @type {string} */
  let bcParsedKey = "";
  /** @type {File | null} */
  let lastPreviewFile = null;
  /** @type {null | { dx:number, dy:number, dz:number, diag:number, vol:number, unit:string, zMin?:number, zMax?:number, sideMm?:number|null, cornerRadiusMm?:number|null, heightTotalMm?:number|null, belowWlMm?:number|null, aboveWlMm?:number|null, waterlineZ?:number|null, loadDiamMm?:number|null, loadForceN?:number|null, notes?:string[], title?:string, source?:string }} */
  let lastDimStats = null;
  /** @type {object | null} */
  let designSpec = null;

  /** @type {{ active: boolean, editMode: boolean, selectedLeg: number, selectedSt: number, data: object|null, legStations: {t:number,scale:number,locked?:boolean}[][], legHollow: boolean[], legWallMm: number[], hubScale: number, measAbs: string|null, outAbs: string|null, rebuildTimer: ReturnType<typeof setTimeout>|null, rebuildGen: number, drag: object|null }} */
  const parametric = {
    active: false,
    editMode: false,
    selectedLeg: 0,
    selectedSt: 0,
    data: null,
    legStations: [],
    legHollow: [],
    legWallMm: [],
    hubScale: 1,
    measAbs: null,
    outAbs: null,
    rebuildTimer: null,
    rebuildGen: 0,
    drag: null,
  };

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
  const stlLoader = new STLLoader();

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

  function fmtForce(n) {
    const a = Math.abs(n);
    if (a >= 1e9) return `${(n / 1e9).toFixed(3)}e9`;
    if (a >= 1e6) return `${(n / 1e6).toFixed(3)}e6`;
    if (a >= 1e3) return `${(n / 1e3).toFixed(2)}e3`;
    return n.toFixed(3);
  }

  function pickBcSourceFile(/** @type {File | null} */ current) {
    const arr = Array.from(allFiles || []);
    const preferNames = [
      /^analysis-beso\.inp$/i,
      /^fem_reference\.inp$/i,
      /^03_for_beso\.inp$/i,
      /^.*_merged_for_beso\.inp$/i,
    ];
    for (const re of preferNames) {
      const hit = arr.find((f) => re.test(f.name));
      if (hit) return hit;
    }
    if (current && extOf(current.name) === ".inp") return current;
    if (current) {
      const m = /^file(\d+)/i.exec(current.name);
      if (m) {
        const n = m[1];
        const plain = arr.find((f) => new RegExp(`^file${n}\\.inp$`, "i").test(f.name));
        if (plain) return plain;
        const s0 = arr.find((f) => new RegExp(`^file${n}_state0\\.inp$`, "i").test(f.name));
        if (s0) return s0;
      }
    }
    const withBcHint = arr
      .filter((f) => extOf(f.name) === ".inp")
      .sort((a, b) => b.size - a.size);
    return withBcHint[0] || null;
  }

  function syncBcToggleUi() {
    if (!btnBc) return;
    btnBc.classList.toggle("rvViewActive", bcOverlayEnabled);
    btnBc.setAttribute("aria-pressed", bcOverlayEnabled ? "true" : "false");
    rvBcPanel?.classList.toggle("hidden", !bcOverlayEnabled);
    wrap?.classList.toggle("rvBcOn", bcOverlayEnabled);
  }

  function renderBcPanel(/** @type {ReturnType<typeof parseInpFemBc> | null} */ bc, meta = {}) {
    if (!rvBcPanelBd) return;
    if (!bcOverlayEnabled) return;
    if (!bc) {
      rvBcPanelBd.innerHTML = `<p class="resultsViewerBcEmpty">${meta.error || "未找到含 *BOUNDARY / *CLOAD 的 INP。请导入 Analysis-beso.inp 或完整 FEM 参考。"}</p>`;
      rvBcStepLab?.classList.add("hidden");
      return;
    }
    const steps = bc.steps || [];
    const idx = bcStepIndex > 0 && bcStepIndex <= steps.length ? bcStepIndex : steps.length;
    const st = steps[idx - 1];
    if (rvBcStepSelect && rvBcStepLab) {
      if (steps.length > 1) {
        rvBcStepLab.classList.remove("hidden");
        rvBcStepSelect.innerHTML = steps
          .map(
            (s) =>
              `<option value="${s.index}" ${s.index === idx ? "selected" : ""}>Step ${s.index} · ${s.kind}</option>`,
          )
          .join("");
      } else {
        rvBcStepLab.classList.add("hidden");
      }
    }
    if (!st) {
      rvBcPanelBd.innerHTML = `<p class="resultsViewerBcEmpty">INP 中未解析到 *STEP 载荷段。</p>`;
      return;
    }
    let fx = 0,
      fy = 0,
      fz = 0;
    for (const c of st.cloads) {
      if (c.dof === 1) fx += c.mag;
      else if (c.dof === 2) fy += c.mag;
      else if (c.dof === 3) fz += c.mag;
    }
    const srcName = bcSourceFile?.name || "—";
    const skipNote =
      meta.skippedFixed || meta.skippedLoads
        ? `<p class="resultsViewerBcNote">显示已抽样（固定略 ${meta.skippedFixed || 0}，载荷略 ${meta.skippedLoads || 0}）。</p>`
        : "";
    rvBcPanelBd.innerHTML = `
      <div class="resultsViewerBcRows">
        <div class="resultsViewerBcRow"><span>来源</span><span class="mono">${srcName}</span></div>
        <div class="resultsViewerBcRow"><span>分步</span><span>Step ${st.index} / ${steps.length} · ${st.kind}</span></div>
        <div class="resultsViewerBcRow"><span>固定节点</span><span class="mono">${st.fixedNodeIds.length}</span></div>
        <div class="resultsViewerBcRow"><span>集中力</span><span class="mono">${st.cloads.length} 点</span></div>
        <div class="resultsViewerBcRow"><span>ΣFx</span><span class="mono">${fmtForce(fx)} N</span></div>
        <div class="resultsViewerBcRow"><span>ΣFy</span><span class="mono">${fmtForce(fy)} N</span></div>
        <div class="resultsViewerBcRow"><span>ΣFz</span><span class="mono">${fmtForce(fz)} N</span></div>
        <div class="resultsViewerBcRow"><span>节点总数</span><span class="mono">${bc.summary.nodeCount}</span></div>
      </div>
      ${skipNote}
    `;
  }

  async function ensureBcParsed(/** @type {File} */ file) {
    const key = `${file.name}|${file.size}|${file.lastModified}`;
    if (bcParsed && bcParsedKey === key) return bcParsed;
    const text = await file.text();
    bcParsed = parseInpFemBc(text);
    bcParsedKey = key;
    return bcParsed;
  }

  async function refreshBcOverlay() {
    if (!bcOverlayEnabled) {
      threeApi?.setBcOverlay?.(null);
      rvBcPanel?.classList.add("hidden");
      return;
    }
    rvBcPanel?.classList.remove("hidden");
    if (!threeApi) {
      renderBcPanel(null, { error: "请先加载三维网格预览，再打开约束/载荷。" });
      return;
    }
    const src = pickBcSourceFile(lastPreviewFile);
    bcSourceFile = src;
    if (!src) {
      threeApi.setBcOverlay?.(null);
      renderBcPanel(null);
      return;
    }
    try {
      const bc = await ensureBcParsed(src);
      if (!bc.steps.length && !bc.summary.fixedCount && !bc.summary.cloadCount) {
        threeApi.setBcOverlay?.(null);
        renderBcPanel(null, { error: `${src.name} 未含有效 *BOUNDARY / *CLOAD。` });
        return;
      }
      const stepIndex = bcStepIndex > 0 ? bcStepIndex : bc.steps.length;
      const { group, usedStep, skippedFixed, skippedLoads } = buildFemBcOverlayGroup(bc, {
        stepIndex,
      });
      threeApi.setBcOverlay?.(group);
      renderBcPanel(bc, { skippedFixed, skippedLoads, usedStep });
    } catch (e) {
      threeApi.setBcOverlay?.(null);
      renderBcPanel(null, { error: `解析失败：${e?.message || e}` });
    }
  }

  function toggleBcOverlay() {
    bcOverlayEnabled = !bcOverlayEnabled;
    syncBcToggleUi();
    void refreshBcOverlay();
  }

  function fmtLenMm(mm) {
    const a = Math.abs(mm);
    if (!Number.isFinite(mm)) return "—";
    if (a >= 1e6) return `${(mm / 1e6).toFixed(3)} km`;
    if (a >= 1000) return `${(mm / 1000).toFixed(a >= 10000 ? 1 : 2)} m`;
    if (a >= 1) return `${mm.toFixed(1)} mm`;
    return `${mm.toFixed(3)} mm`;
  }

  function fmtForceN(n) {
    if (!Number.isFinite(n)) return "—";
    const a = Math.abs(n);
    if (a >= 1e6) return `${(n / 1e6).toFixed(2)}×10⁶ N`;
    if (a >= 1e3) return `${(n / 1e3).toFixed(2)}×10³ N`;
    return `${n.toFixed(1)} N`;
  }

  function fmtVolMm3(v) {
    const a = Math.abs(v);
    if (a >= 1e9) return `${(v / 1e9).toFixed(3)} m³`;
    if (a >= 1e6) return `${(v / 1e6).toFixed(2)} L`;
    return `${v.toExponential(3)} mm³`;
  }

  async function loadDesignSpecFromFiles(/** @type {File[]} */ files) {
    designSpec = null;
    const hit = (files || []).find((f) => f.name.toLowerCase() === "design_spec.json");
    if (!hit) return null;
    try {
      designSpec = JSON.parse(await hit.text());
    } catch {
      designSpec = null;
    }
    return designSpec;
  }

  function inferLoadCircleFromBc(/** @type {ReturnType<typeof parseInpFemBc> | null} */ bc) {
    if (!bc?.steps?.length) return null;
    const st = bc.steps[bc.steps.length - 1];
    const pts = [];
    for (const c of st.cloads || []) {
      const p = bc.nodes.get(c.nid);
      if (p) pts.push(p);
    }
    if (pts.length < 3) return null;
    let cx = 0,
      cy = 0,
      cz = 0;
    for (const p of pts) {
      cx += p.x;
      cy += p.y;
      cz += p.z;
    }
    cx /= pts.length;
    cy /= pts.length;
    cz /= pts.length;
    let rMax = 0;
    for (const p of pts) {
      rMax = Math.max(rMax, Math.hypot(p.x - cx, p.y - cy));
    }
    let fSum = 0;
    for (const c of st.cloads) fSum += c.mag;
    return { cx, cy, cz, diameterMm: rMax * 2, forceN: fSum };
  }

  function makeDimLabelSprite(text, colorHex = "#7dd3fc") {
    const canvas = document.createElement("canvas");
    canvas.width = 384;
    canvas.height = 72;
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      return new THREE.Sprite(new THREE.SpriteMaterial({ color: 0x7dd3fc }));
    }
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "rgba(15,23,42,0.82)";
    const pad = 8;
    ctx.beginPath();
    ctx.roundRect?.(pad, pad, canvas.width - pad * 2, canvas.height - pad * 2, 12);
    if (!ctx.roundRect) ctx.fillRect(pad, pad, canvas.width - pad * 2, canvas.height - pad * 2);
    else {
      ctx.fill();
    }
    ctx.strokeStyle = colorHex;
    ctx.lineWidth = 3;
    if (ctx.roundRect) {
      ctx.beginPath();
      ctx.roundRect(pad, pad, canvas.width - pad * 2, canvas.height - pad * 2, 12);
      ctx.stroke();
    }
    ctx.fillStyle = colorHex;
    ctx.font = "bold 28px ui-sans-serif, system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(text, canvas.width / 2, canvas.height / 2 + 1);
    const tex = new THREE.CanvasTexture(canvas);
    tex.needsUpdate = true;
    const mat = new THREE.SpriteMaterial({
      map: tex,
      transparent: true,
      depthTest: false,
      depthWrite: false,
    });
    const sp = new THREE.Sprite(mat);
    sp.renderOrder = 12;
    return sp;
  }

  /**
   * Dig-out circles at the three sharp vertices of an equilateral prism.
   * Side length = center-to-center = `sideMm` (设计边长).
   * Radius = `radiusMm` (挖去圆半径，对应建模边线回退/名义柱径比例).
   * @param {number} sideMm
   * @param {number} radiusMm
   */
  function computePrismCornerGeometry(sideMm, radiusMm) {
    const S = Number(sideMm);
    const R = Number(radiusMm);
    if (!(S > 0) || !(R > 0)) return null;
    const h = (S * Math.sqrt(3)) / 2;
    // Centers of dig-out circles = theoretical sharp vertices (边长 = 圆心距)
    const centers = [
      [0, (2 * h) / 3],
      [S / 2, -h / 3],
      [-S / 2, -h / 3],
    ];
    return {
      verts: centers.map((c) => c.slice()),
      centers,
      radiusMm: R,
      edgeSetbackMm: R,
      sideMm: S,
    };
  }

  /**
   * @param {THREE.Box3} box local AABB
   * @param {{ waterlineZ?: number|null, loadCircle?: {cx:number,cy:number,cz:number,diameterMm:number,application?:string}|null, sideMm?: number|null, belowWlMm?: number|null, aboveWlMm?: number|null, cornerRadiusMm?: number|null, cornerCentersXy?: number[][]|null, sharpVerticesXy?: number[][]|null }} [ann]
   * @returns {THREE.Group}
   */
  function buildDimOverlayGroup(box, ann = {}) {
    const group = new THREE.Group();
    group.name = "rvDimOverlay";
    if (!box || box.isEmpty()) return group;
    const min = box.min.clone();
    const max = box.max.clone();
    const size = box.getSize(new THREE.Vector3());
    const dx = size.x;
    const dy = size.y;
    const dz = size.z;
    const diag = size.length();
    const off = Math.max(diag * 0.04, Math.max(dx, dy, dz) * 0.03, 1);

    const edgeMat = new THREE.LineBasicMaterial({
      color: 0x38bdf8,
      transparent: true,
      opacity: 0.45,
      depthTest: false,
    });
    const dimMat = new THREE.LineBasicMaterial({
      color: 0xa5f3fc,
      transparent: true,
      opacity: 0.95,
      depthTest: false,
    });
    const wlMat = new THREE.LineBasicMaterial({
      color: 0x22d3ee,
      transparent: true,
      opacity: 0.7,
      depthTest: false,
    });
    const loadMat = new THREE.LineBasicMaterial({
      color: 0xfbbf24,
      transparent: true,
      opacity: 0.95,
      depthTest: false,
    });
    const notchMat = new THREE.LineBasicMaterial({
      color: 0xf87171,
      transparent: true,
      opacity: 0.9,
      depthTest: false,
    });

    // AABB wireframe
    const bbCorners = [
      [min.x, min.y, min.z],
      [max.x, min.y, min.z],
      [max.x, max.y, min.z],
      [min.x, max.y, min.z],
      [min.x, min.y, max.z],
      [max.x, min.y, max.z],
      [max.x, max.y, max.z],
      [min.x, max.y, max.z],
    ];
    const edgeIdx = [
      [0, 1], [1, 2], [2, 3], [3, 0],
      [4, 5], [5, 6], [6, 7], [7, 4],
      [0, 4], [1, 5], [2, 6], [3, 7],
    ];
    const edgePos = [];
    for (const [a, b] of edgeIdx) edgePos.push(...bbCorners[a], ...bbCorners[b]);
    const edgeGeom = new THREE.BufferGeometry();
    edgeGeom.setAttribute("position", new THREE.Float32BufferAttribute(edgePos, 3));
    const edges = new THREE.LineSegments(edgeGeom, edgeMat);
    edges.renderOrder = 9;
    group.add(edges);

    /** @param {THREE.Vector3} a @param {THREE.Vector3} b @param {THREE.Vector3} outward @param {string} label @param {number} [color] */
    function addDim(a, b, outward, label, color) {
      const n = outward.clone().normalize().multiplyScalar(off);
      const p0 = a.clone().add(n);
      const p1 = b.clone().add(n);
      const tick = outward.clone().normalize().multiplyScalar(off * 0.35);
      const positions = [
        a.x, a.y, a.z, p0.x, p0.y, p0.z,
        p0.x, p0.y, p0.z, p1.x, p1.y, p1.z,
        p1.x, p1.y, p1.z, b.x, b.y, b.z,
        p0.x - tick.x, p0.y - tick.y, p0.z - tick.z, p0.x + tick.x, p0.y + tick.y, p0.z + tick.z,
        p1.x - tick.x, p1.y - tick.y, p1.z - tick.z, p1.x + tick.x, p1.y + tick.y, p1.z + tick.z,
      ];
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
      const mat = color
        ? new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.95, depthTest: false })
        : dimMat;
      const line = new THREE.LineSegments(g, mat);
      line.renderOrder = 10;
      group.add(line);
      const mid = p0.clone().add(p1).multiplyScalar(0.5).add(n.clone().multiplyScalar(0.35));
      const sp = makeDimLabelSprite(label, color ? `#${color.toString(16).padStart(6, "0")}` : "#7dd3fc");
      const s = Math.max(diag * 0.14, 1);
      sp.scale.set(s, s * 0.22, 1);
      sp.position.copy(mid);
      group.add(sp);
    }

    /** full or partial dashed circle in XY */
    function addDashedCircle(cx, cy, cz, radius, mat, segs = 72, ang0 = 0, ang1 = Math.PI * 2) {
      const circ = [];
      const span = ang1 - ang0;
      const nSeg = Math.max(8, Math.ceil((segs * Math.abs(span)) / (Math.PI * 2)));
      for (let i = 0; i < nSeg; i += 2) {
        const a0 = ang0 + (i / nSeg) * span;
        const a1 = ang0 + ((i + 1) / nSeg) * span;
        circ.push(
          cx + radius * Math.cos(a0), cy + radius * Math.sin(a0), cz,
          cx + radius * Math.cos(a1), cy + radius * Math.sin(a1), cz,
        );
      }
      const cg = new THREE.BufferGeometry();
      cg.setAttribute("position", new THREE.Float32BufferAttribute(circ, 3));
      const cl = new THREE.LineSegments(cg, mat);
      cl.renderOrder = 11;
      group.add(cl);
    }

    const wlZ = ann.waterlineZ;
    const hasWl =
      wlZ != null && Number.isFinite(wlZ) && wlZ > min.z + 1 && wlZ < max.z - 1;
    const below = ann.belowWlMm != null ? ann.belowWlMm : hasWl ? wlZ - min.z : null;
    const above = ann.aboveWlMm != null ? ann.aboveWlMm : hasWl ? max.z - wlZ : null;
    const zBotDes = hasWl && below != null ? wlZ - below : min.z;
    const zTopDes = hasWl && above != null ? wlZ + above : max.z;
    const zSide = zBotDes;

    // Dig-out: prefer FreeCAD-measured centers/R from design_spec
    const Rdig =
      ann.cornerCircleRadiusMm != null
        ? Number(ann.cornerCircleRadiusMm)
        : ann.cornerRadiusMm != null
          ? Number(ann.cornerRadiusMm)
          : null;
    let cornerGeom = null;
    if (Array.isArray(ann.cornerCentersXy) && ann.cornerCentersXy.length >= 3 && Rdig != null) {
      cornerGeom = {
        centers: ann.cornerCentersXy,
        verts: Array.isArray(ann.sharpVerticesXy) ? ann.sharpVerticesXy : ann.cornerCentersXy,
        radiusMm: Rdig,
        sideMm: ann.sideMm != null ? Number(ann.sideMm) : null,
      };
    } else if (ann.sideMm != null && Rdig != null) {
      cornerGeom = computePrismCornerGeometry(ann.sideMm, Rdig);
    }

    if (cornerGeom && cornerGeom.centers?.length >= 3) {
      const cs = cornerGeom.centers;
      const Rarc = cornerGeom.radiusMm;

      // Bottom side = lowest mid-Y between consecutive centers
      let bestI = 0;
      let bestY = Infinity;
      for (let i = 0; i < 3; i++) {
        const yMid = (cs[i][1] + cs[(i + 1) % 3][1]) / 2;
        if (yMid < bestY) {
          bestY = yMid;
          bestI = i;
        }
      }
      const cA = new THREE.Vector3(cs[bestI][0], cs[bestI][1], zSide);
      const cB = new THREE.Vector3(cs[(bestI + 1) % 3][0], cs[(bestI + 1) % 3][1], zSide);

      const edge = new THREE.Vector3().subVectors(cB, cA);
      const outward = new THREE.Vector3(-edge.y, edge.x, 0);
      if (outward.lengthSq() < 1e-12) outward.set(0, -1, 0);
      const midEdge = cA.clone().add(cB).multiplyScalar(0.5);
      if (outward.dot(midEdge) < 0) outward.negate();
      outward.normalize();

      // 边长：端点在实测圆心，标注值为圆心距（与 design_spec.side_length_mm 一致）
      const n = outward.clone().multiplyScalar(off * 1.25);
      const d0 = cA.clone().add(n);
      const d1 = cB.clone().add(n);
      const tick = outward.clone().multiplyScalar(off * 0.4);
      const sidePositions = [
        cA.x, cA.y, cA.z, d0.x, d0.y, d0.z,
        cB.x, cB.y, cB.z, d1.x, d1.y, d1.z,
        d0.x, d0.y, d0.z, d1.x, d1.y, d1.z,
        d0.x - tick.x, d0.y - tick.y, d0.z - tick.z, d0.x + tick.x, d0.y + tick.y, d0.z + tick.z,
        d1.x - tick.x, d1.y - tick.y, d1.z - tick.z, d1.x + tick.x, d1.y + tick.y, d1.z + tick.z,
      ];
      const sideGeom = new THREE.BufferGeometry();
      sideGeom.setAttribute("position", new THREE.Float32BufferAttribute(sidePositions, 3));
      group.add(Object.assign(new THREE.LineSegments(sideGeom, dimMat), { renderOrder: 10 }));

      const sideLen = ann.sideMm != null ? Number(ann.sideMm) : cA.distanceTo(cB);
      const sideSp = makeDimLabelSprite(`边长 ${fmtLenMm(sideLen)}`, "#7dd3fc");
      const sSide = Math.max(diag * 0.14, 1);
      sideSp.scale.set(sSide, sSide * 0.22, 1);
      sideSp.position.copy(d0.clone().add(d1).multiplyScalar(0.5).add(outward.clone().multiplyScalar(off * 0.4)));
      group.add(sideSp);

      for (let i = 0; i < 3; i++) {
        const c = cs[i];
        const c0 = new THREE.Vector3(c[0], c[1], zSide);
        const hs = Math.max(Rarc * 0.08, off * 0.45);
        const cross = [
          c[0] - hs, c[1], zSide, c[0] + hs, c[1], zSide,
          c[0], c[1] - hs, zSide, c[0], c[1] + hs, zSide,
        ];
        const xg = new THREE.BufferGeometry();
        xg.setAttribute("position", new THREE.Float32BufferAttribute(cross, 3));
        group.add(Object.assign(new THREE.LineSegments(xg, notchMat), { renderOrder: 12 }));

        // Full circle through actual notch (FCStd 三点圆拟合)
        addDashedCircle(c[0], c[1], zSide, Rarc, notchMat, 96);

        const toward = new THREE.Vector3(-c[0], -c[1], 0);
        if (toward.lengthSq() < 1e-12) toward.set(0, 1, 0);
        toward.normalize();
        const c1 = c0.clone().add(toward.clone().multiplyScalar(Rarc));
        const rg = new THREE.BufferGeometry();
        rg.setAttribute(
          "position",
          new THREE.Float32BufferAttribute([c0.x, c0.y, c0.z, c1.x, c1.y, c1.z], 3),
        );
        group.add(Object.assign(new THREE.LineSegments(rg, notchMat), { renderOrder: 11 }));
        const rMid = c0.clone().add(c1).multiplyScalar(0.5);
        rMid.add(new THREE.Vector3(-toward.y, toward.x, 0).multiplyScalar(off * 0.35));
        const rSp = makeDimLabelSprite(`R ${fmtLenMm(Rarc)}`, "#f87171");
        const s = Math.max(diag * 0.11, 1);
        rSp.scale.set(s, s * 0.22, 1);
        rSp.position.copy(rMid);
        group.add(rSp);
      }
    } else {
      const sideLabel = ann.sideMm != null ? `边长 ${fmtLenMm(ann.sideMm)}` : `跨度 X ${fmtLenMm(dx)}`;
      addDim(
        new THREE.Vector3(min.x, min.y, min.z),
        new THREE.Vector3(max.x, min.y, min.z),
        new THREE.Vector3(0, -1, 0),
        sideLabel,
      );
    }

    if (hasWl) {
      const wlPos = [
        min.x, min.y, wlZ, max.x, min.y, wlZ,
        max.x, min.y, wlZ, max.x, max.y, wlZ,
        max.x, max.y, wlZ, min.x, max.y, wlZ,
        min.x, max.y, wlZ, min.x, min.y, wlZ,
      ];
      const wlGeom = new THREE.BufferGeometry();
      wlGeom.setAttribute("position", new THREE.Float32BufferAttribute(wlPos, 3));
      group.add(Object.assign(new THREE.LineSegments(wlGeom, wlMat), { renderOrder: 10 }));
      const wlSp = makeDimLabelSprite("水面 z=0", "#22d3ee");
      const s = Math.max(diag * 0.12, 1);
      wlSp.scale.set(s, s * 0.22, 1);
      wlSp.position.set(max.x + off * 1.2, (min.y + max.y) / 2, wlZ);
      group.add(wlSp);

      addDim(
        new THREE.Vector3(max.x, min.y, zBotDes),
        new THREE.Vector3(max.x, min.y, wlZ),
        new THREE.Vector3(1, 0, 0),
        `水下 ${fmtLenMm(below)}`,
        0x38bdf8,
      );
      addDim(
        new THREE.Vector3(max.x, min.y, wlZ),
        new THREE.Vector3(max.x, min.y, zTopDes),
        new THREE.Vector3(1, 0, 0),
        `水上 ${fmtLenMm(above)}`,
        0x67e8f9,
      );
      const totalH = below != null && above != null ? below + above : dz;
      addDim(
        new THREE.Vector3(max.x, max.y, zBotDes),
        new THREE.Vector3(max.x, max.y, zTopDes),
        new THREE.Vector3(1, 0.2, 0),
        `总高 ${fmtLenMm(totalH)}`,
        0xe0f2fe,
      );
    } else {
      addDim(
        new THREE.Vector3(max.x, min.y, min.z),
        new THREE.Vector3(max.x, min.y, max.z),
        new THREE.Vector3(1, 0, 0),
        `高 Z ${fmtLenMm(dz)}`,
      );
    }

    // Load circle: ring + diameter annotation (绕圆，不是边长式)
    const lc = ann.loadCircle;
    if (lc && lc.diameterMm > 0) {
      const r = lc.diameterMm / 2;
      // Full ring matching load circumference
      addDashedCircle(lc.cx, lc.cy, lc.cz, r, loadMat, 96);
      // Diameter line across the circle
      const ang = Math.PI * 0.15;
      const p0 = new THREE.Vector3(
        lc.cx + r * Math.cos(ang),
        lc.cy + r * Math.sin(ang),
        lc.cz,
      );
      const p1 = new THREE.Vector3(
        lc.cx - r * Math.cos(ang),
        lc.cy - r * Math.sin(ang),
        lc.cz,
      );
      const dg = new THREE.BufferGeometry();
      dg.setAttribute(
        "position",
        new THREE.Float32BufferAttribute([p0.x, p0.y, p0.z, p1.x, p1.y, p1.z], 3),
      );
      group.add(Object.assign(new THREE.LineSegments(dg, loadMat), { renderOrder: 12 }));
      // End ticks on diameter
      const tdir = new THREE.Vector3(-(p1.y - p0.y), p1.x - p0.x, 0).normalize().multiplyScalar(r * 0.08);
      const ticks = [
        p0.x - tdir.x, p0.y - tdir.y, p0.z, p0.x + tdir.x, p0.y + tdir.y, p0.z,
        p1.x - tdir.x, p1.y - tdir.y, p1.z, p1.x + tdir.x, p1.y + tdir.y, p1.z,
      ];
      const tg = new THREE.BufferGeometry();
      tg.setAttribute("position", new THREE.Float32BufferAttribute(ticks, 3));
      group.add(Object.assign(new THREE.LineSegments(tg, loadMat), { renderOrder: 12 }));

      const app = lc.application === "circumference_edge" ? "圆周" : "圆";
      const loadSp = makeDimLabelSprite(`载荷${app} Ø${fmtLenMm(lc.diameterMm)}`, "#fbbf24");
      const s = Math.max(diag * 0.12, Math.max(r * 0.55, 1));
      loadSp.scale.set(s, s * 0.22, 1);
      // Label sits on the ring (not like a prism-side dim)
      loadSp.position.set(lc.cx, lc.cy + r * 1.15, lc.cz);
      group.add(loadSp);
    }

    return group;
  }

  function renderDimPanel(stats) {
    if (!rvDimPanelBd) return;
    if (!dimOverlayEnabled) return;
    if (!stats) {
      rvDimPanelBd.innerHTML = `<p class="resultsViewerBcEmpty">请先加载三维网格后再打开尺寸。</p>`;
      return;
    }
    const notes = (stats.notes || [])
      .map((n) => `<li>${n}</li>`)
      .join("");
    const title = stats.title ? `<div class="resultsViewerDimTitle">${stats.title}</div>` : "";
    const engRows = [];
    if (stats.heightTotalMm != null) {
      engRows.push(
        `<div class="resultsViewerBcRow"><span>总高</span><span class="mono">${fmtLenMm(stats.heightTotalMm)}</span></div>`,
      );
    }
    if (stats.belowWlMm != null) {
      engRows.push(
        `<div class="resultsViewerBcRow"><span>水面以下</span><span class="mono">${fmtLenMm(stats.belowWlMm)}</span></div>`,
      );
    }
    if (stats.aboveWlMm != null) {
      engRows.push(
        `<div class="resultsViewerBcRow"><span>水面以上</span><span class="mono">${fmtLenMm(stats.aboveWlMm)}</span></div>`,
      );
    }
    if (stats.sideMm != null) {
      engRows.push(
        `<div class="resultsViewerBcRow"><span>边长(圆心距)</span><span class="mono">${fmtLenMm(stats.sideMm)}</span></div>`,
      );
    }
    if (stats.outerSpanXMm != null) {
      engRows.push(
        `<div class="resultsViewerBcRow"><span>外轮廓跨度 X</span><span class="mono">${fmtLenMm(stats.outerSpanXMm)}</span></div>`,
      );
    }
    if (stats.cornerRadiusMm != null) {
      engRows.push(
        `<div class="resultsViewerBcRow"><span>挖去圆半径</span><span class="mono">${fmtLenMm(stats.cornerRadiusMm)}</span></div>`,
      );
    }
    if (stats.loadDiamMm != null) {
      engRows.push(
        `<div class="resultsViewerBcRow"><span>载荷圆直径</span><span class="mono">${fmtLenMm(stats.loadDiamMm)}</span></div>`,
      );
    }
    if (stats.loadForceN != null) {
      engRows.push(
        `<div class="resultsViewerBcRow"><span>载荷合力</span><span class="mono">${fmtForceN(stats.loadForceN)} (−Z)</span></div>`,
      );
    }
    rvDimPanelBd.innerHTML = `
      ${title}
      ${engRows.length ? `<div class="resultsViewerBcRows resultsViewerDimEng">${engRows.join("")}</div>` : ""}
      ${notes ? `<ul class="resultsViewerDimNotes">${notes}</ul>` : ""}
      <div class="resultsViewerDimSubHd">包围盒</div>
      <div class="resultsViewerBcRows">
        <div class="resultsViewerBcRow"><span>长 X</span><span class="mono">${fmtLenMm(stats.dx)}</span></div>
        <div class="resultsViewerBcRow"><span>宽 Y</span><span class="mono">${fmtLenMm(stats.dy)}</span></div>
        <div class="resultsViewerBcRow"><span>高 Z</span><span class="mono">${fmtLenMm(stats.dz)}</span></div>
        <div class="resultsViewerBcRow"><span>对角线</span><span class="mono">${fmtLenMm(stats.diag)}</span></div>
        <div class="resultsViewerBcRow"><span>盒体积</span><span class="mono">${fmtVolMm3(stats.vol)}</span></div>
        <div class="resultsViewerBcRow"><span>来源</span><span class="mono">${stats.source || "mesh"}</span></div>
      </div>
    `;
  }

  function syncDimToggleUi() {
    if (!btnDim) return;
    btnDim.classList.toggle("rvViewActive", dimOverlayEnabled);
    btnDim.setAttribute("aria-pressed", dimOverlayEnabled ? "true" : "false");
    rvDimPanel?.classList.toggle("hidden", !dimOverlayEnabled);
    wrap?.classList.toggle("rvDimOn", dimOverlayEnabled);
  }

  async function refreshDimOverlay() {
    if (!dimOverlayEnabled) {
      threeApi?.setDimOverlay?.(null);
      lastDimStats = null;
      rvDimPanel?.classList.add("hidden");
      return;
    }
    rvDimPanel?.classList.remove("hidden");
    if (!threeApi?.measureMeshLocalBox) {
      renderDimPanel(null);
      return;
    }
    const box = threeApi.measureMeshLocalBox();
    if (!box || box.isEmpty()) {
      threeApi.setDimOverlay?.(null);
      renderDimPanel(null);
      return;
    }
    const size = box.getSize(new THREE.Vector3());
    const zMin = box.min.z;
    const zMax = box.max.z;

    // Prefer design_spec.json; else infer waterline at z=0 if it crosses the bbox
    const spec = designSpec || {};
    const wlZ =
      spec.waterline_z_mm != null && Number.isFinite(Number(spec.waterline_z_mm))
        ? Number(spec.waterline_z_mm)
        : zMin < -1 && zMax > 1
          ? 0
          : null;
    let belowWl =
      spec.height_below_wl_mm != null ? Number(spec.height_below_wl_mm) : wlZ != null ? wlZ - zMin : null;
    let aboveWl =
      spec.height_above_wl_mm != null ? Number(spec.height_above_wl_mm) : wlZ != null ? zMax - wlZ : null;
    // Ignore thin load-disk protrusion in "above water" if design_spec given
    const heightTotal =
      spec.height_total_mm != null
        ? Number(spec.height_total_mm)
        : belowWl != null && aboveWl != null
          ? belowWl + (spec.height_above_wl_mm != null ? Number(spec.height_above_wl_mm) : aboveWl)
          : size.z;
    const sideMm =
      spec.side_length_mm != null ? Number(spec.side_length_mm) : Math.max(size.x, size.y);
    // Prefer FreeCAD-measured circle R + centers from design_spec.json
    const digRadiusMm =
      spec.corner_circle_radius_mm != null
        ? Number(spec.corner_circle_radius_mm)
        : spec.corner_edge_setback_mm != null
          ? Number(spec.corner_edge_setback_mm)
          : spec.corner_notch_radius_mm != null
            ? Number(spec.corner_notch_radius_mm)
            : null;
    let cornerCentersXy = Array.isArray(spec.corner_centers_xy_mm) ? spec.corner_centers_xy_mm : null;
    let sharpVerticesXy = Array.isArray(spec.sharp_vertices_xy_mm) ? spec.sharp_vertices_xy_mm : null;
    if (!cornerCentersXy || cornerCentersXy.length < 3) {
      const g =
        digRadiusMm != null && sideMm != null ? computePrismCornerGeometry(sideMm, digRadiusMm) : null;
      cornerCentersXy = g?.centers || null;
      sharpVerticesXy = sharpVerticesXy || g?.verts || null;
    }

    let loadCircle = null;
    let loadDiam = spec.load_circle_diameter_mm != null ? Number(spec.load_circle_diameter_mm) : null;
    let loadForce = spec.load_force_n != null ? Number(spec.load_force_n) : null;
    const loadApp = spec.load_application || null;
    const loadCtr = Array.isArray(spec.load_circle_center_xyz_mm) ? spec.load_circle_center_xyz_mm : null;
    try {
      const src = pickBcSourceFile(lastPreviewFile);
      if (src) {
        const bc = await ensureBcParsed(src);
        const inferred = inferLoadCircleFromBc(bc);
        if (inferred) {
          loadCircle = {
            cx: loadCtr ? Number(loadCtr[0]) : inferred.cx,
            cy: loadCtr ? Number(loadCtr[1]) : inferred.cy,
            cz: loadCtr ? Number(loadCtr[2]) : inferred.cz,
            diameterMm: loadDiam != null ? loadDiam : inferred.diameterMm,
            application: loadApp || "circumference_edge",
          };
          if (loadForce == null) loadForce = inferred.forceN;
          if (loadDiam == null) loadDiam = inferred.diameterMm;
        }
      }
    } catch {
      /* optional */
    }
    if (!loadCircle && loadDiam != null) {
      loadCircle = {
        cx: loadCtr ? Number(loadCtr[0]) : (box.min.x + box.max.x) / 2,
        cy: loadCtr ? Number(loadCtr[1]) : (box.min.y + box.max.y) / 2,
        cz: loadCtr ? Number(loadCtr[2]) : zMax,
        diameterMm: loadDiam,
        application: loadApp || "face",
      };
    }

    const outerSpanX =
      spec.outer_span_x_mm != null
        ? Number(spec.outer_span_x_mm)
        : spec.bbox_x_mm != null
          ? Number(spec.bbox_x_mm)
          : size.x;

    const notes =
      Array.isArray(spec.notes) && spec.notes.length
        ? spec.notes.map(String)
        : [
            `三棱柱高度 ${fmtLenMm(heightTotal)}` +
              (belowWl != null && aboveWl != null
                ? `（水面以下 ${fmtLenMm(belowWl)}，水面以上 ${fmtLenMm(spec.height_above_wl_mm != null ? Number(spec.height_above_wl_mm) : aboveWl)}）`
                : ""),
            `边长（凹角圆心距） ${fmtLenMm(sideMm)}；外轮廓跨度 X ${fmtLenMm(outerSpanX)}`,
            digRadiusMm != null ? `凹角挖去圆半径 ${fmtLenMm(digRadiusMm)}（FCStd 实测）` : null,
            loadDiam != null
              ? `受力：Ø${fmtLenMm(loadDiam)} 载荷` +
                (loadApp === "circumference_edge" ? "圆周" : "圆面") +
                (loadForce != null ? `，重力 ${fmtForceN(Math.abs(loadForce))}` : "")
              : null,
          ].filter(Boolean);

    lastDimStats = {
      dx: size.x,
      dy: size.y,
      dz: size.z,
      diag: size.length(),
      vol: size.x * size.y * size.z,
      unit: "mm（CalculiX / FreeCAD 惯例）",
      zMin,
      zMax,
      sideMm,
      cornerRadiusMm: digRadiusMm,
      outerSpanXMm: outerSpanX,
      heightTotalMm: heightTotal,
      belowWlMm: belowWl,
      aboveWlMm: spec.height_above_wl_mm != null ? Number(spec.height_above_wl_mm) : aboveWl,
      waterlineZ: wlZ,
      loadDiamMm: loadDiam,
      loadForceN: loadForce != null ? Math.abs(loadForce) : null,
      notes,
      title: spec.title || "设计尺寸",
      source: designSpec?.source || (designSpec ? "design_spec.json" : "mesh 推断"),
    };

    threeApi.setDimOverlay?.(
      buildDimOverlayGroup(box, {
        waterlineZ: wlZ,
        loadCircle,
        sideMm,
        belowWlMm: lastDimStats.belowWlMm,
        aboveWlMm: lastDimStats.aboveWlMm,
        cornerRadiusMm: digRadiusMm,
        cornerCircleRadiusMm: digRadiusMm,
        cornerCentersXy,
        sharpVerticesXy,
      }),
    );
    renderDimPanel(lastDimStats);
  }

  function toggleDimOverlay() {
    dimOverlayEnabled = !dimOverlayEnabled;
    syncDimToggleUi();
    void refreshDimOverlay();
  }

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
    /** @type {THREE.Object3D | null} */
    let bcOverlayRoot = null;
    /** @type {THREE.Object3D | null} */
    let dimOverlayRoot = null;
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

    function disposeObjectTree(obj) {
      if (!obj) return;
      obj.traverse((c) => {
        if (c.geometry?.dispose) c.geometry.dispose();
        if (c.material) {
          const mats = Array.isArray(c.material) ? c.material : [c.material];
          for (const m of mats) {
            m.map?.dispose?.();
            m.dispose?.();
          }
        }
      });
    }

    function setBcOverlay(/** @type {THREE.Object3D | null} */ overlay) {
      if (bcOverlayRoot) {
        if (meshRoot) meshRoot.remove(bcOverlayRoot);
        else scene.remove(bcOverlayRoot);
        disposeObjectTree(bcOverlayRoot);
        bcOverlayRoot = null;
      }
      if (!overlay) return;
      bcOverlayRoot = overlay;
      if (meshRoot) meshRoot.add(bcOverlayRoot);
      else scene.add(bcOverlayRoot);
    }

    function setDimOverlay(/** @type {THREE.Object3D | null} */ overlay) {
      if (dimOverlayRoot) {
        if (meshRoot) meshRoot.remove(dimOverlayRoot);
        else scene.remove(dimOverlayRoot);
        disposeObjectTree(dimOverlayRoot);
        dimOverlayRoot = null;
      }
      if (!overlay) return;
      dimOverlayRoot = overlay;
      if (meshRoot) meshRoot.add(dimOverlayRoot);
      else scene.add(dimOverlayRoot);
    }

    function isOverlayNode(/** @type {THREE.Object3D | null} */ o) {
      for (let p = o; p; p = p.parent) {
        if (p.name === "rvFemBcOverlay" || p.name === "rvDimOverlay") return true;
      }
      return false;
    }

    /** 仅统计网格 Mesh 的局部包围盒（排除约束/尺寸叠加） */
    function measureMeshLocalBox() {
      const wbox = new THREE.Box3();
      if (!meshRoot) return wbox;
      meshRoot.updateMatrixWorld(true);
      meshRoot.traverse((c) => {
        if (!c.isMesh || !c.geometry) return;
        if (isOverlayNode(c)) return;
        wbox.expandByObject(c);
      });
      if (wbox.isEmpty()) return wbox;
      const inv = new THREE.Matrix4().copy(meshRoot.matrixWorld).invert();
      const pts = [
        new THREE.Vector3(wbox.min.x, wbox.min.y, wbox.min.z),
        new THREE.Vector3(wbox.max.x, wbox.min.y, wbox.min.z),
        new THREE.Vector3(wbox.min.x, wbox.max.y, wbox.min.z),
        new THREE.Vector3(wbox.min.x, wbox.min.y, wbox.max.z),
        new THREE.Vector3(wbox.max.x, wbox.max.y, wbox.min.z),
        new THREE.Vector3(wbox.max.x, wbox.min.y, wbox.max.z),
        new THREE.Vector3(wbox.min.x, wbox.max.y, wbox.max.z),
        new THREE.Vector3(wbox.max.x, wbox.max.y, wbox.max.z),
      ];
      const local = new THREE.Box3();
      for (const p of pts) local.expandByPoint(p.applyMatrix4(inv));
      return local;
    }

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
      if (bcOverlayRoot) {
        scene.remove(bcOverlayRoot);
        disposeObjectTree(bcOverlayRoot);
        bcOverlayRoot = null;
      }
      if (dimOverlayRoot) {
        scene.remove(dimOverlayRoot);
        disposeObjectTree(dimOverlayRoot);
        dimOverlayRoot = null;
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
      // 卸下 overlay，换根后再挂回（坐标仍在原 INP 系）
      const keepBc = bcOverlayRoot;
      const keepDim = dimOverlayRoot;
      if (bcOverlayRoot && meshRoot) meshRoot.remove(bcOverlayRoot);
      if (dimOverlayRoot && meshRoot) meshRoot.remove(dimOverlayRoot);
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
      if (keepBc) {
        bcOverlayRoot = keepBc;
        meshRoot.add(bcOverlayRoot);
      }
      if (keepDim) {
        dimOverlayRoot = keepDim;
        meshRoot.add(dimOverlayRoot);
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
      setBcOverlay,
      setDimOverlay,
      measureMeshLocalBox,
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

  async function previewStl(file) {
    hideTextPreview();
    showTransientCanvasHint("正在加载 STL…");
    await new Promise((r) => requestAnimationFrame(r));
    const buf = await file.arrayBuffer();
    const geometry = stlLoader.parse(buf);
    geometry.computeVertexNormals();
    if (!threeApi) threeApi = initThree();
    const mat = new THREE.MeshStandardMaterial({
      color: 0xa5b4fc,
      metalness: 0.1,
      roughness: 0.44,
      side: THREE.DoubleSide,
    });
    threeApi.setRoot(new THREE.Mesh(geometry, mat));
    objLabel.textContent = file.name;
    hideTransientCanvasHint();
  }

  async function previewStep(file) {
    hideTextPreview();
    showTransientCanvasHint("正在加载 STEP（OpenCascade WASM）…");
    await new Promise((r) => requestAnimationFrame(r));

    const occt = await loadOcctImportJs();
    const buf = new Uint8Array(await file.arrayBuffer());
    if (buf.byteLength < 64) {
      throw new Error("STEP 文件过小或为空，请确认导出是否成功");
    }
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
      lastPreviewFile = f;
      if (dimOverlayEnabled) refreshDimOverlay();
      if (bcOverlayEnabled && !preserveView) await refreshBcOverlay();
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
    lastPreviewFile = file;
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
      } else if (ex === ".stl") {
        stopVtkPlayback();
        await previewStl(file);
      } else if (ex === ".inp") {
        stopVtkPlayback();
        syncMeshSeqIndexFromFile(file);
        updateVtkSeqBarUi();
        await previewInpAsMesh3d(file);
      } else {
        showTransientCanvasHint("不支持该扩展名预览");
      }
      if (bcOverlayEnabled) await refreshBcOverlay();
      if (dimOverlayEnabled) refreshDimOverlay();
    } catch (e) {
      showTransientCanvasHint(`加载失败：${e?.message || e}`);
    }
    refreshFileList();
  }

  function isPreviewableFile(f) {
    const ex = extOf(f.name);
    return (
      ex === ".step" || ex === ".stp" || ex === ".stl" || ex === ".obj" || ex === ".inp" || ex === ".vtk"
    );
  }

  function fileMatchesFilter(f) {
    if (!isPreviewableFile(f)) return false;
    const ex = extOf(f.name);
    if (activeExtFilter !== "all") {
      if (activeExtFilter === ".stp") {
        if (ex !== ".stp" && ex !== ".step") return false;
      } else if (activeExtFilter === ".stl") {
        if (ex !== ".stl") return false;
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
          : exn === ".stl"
            ? "▣"
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
   * @param {{ measurementsAbs?: string, outDirAbs?: string }} [ctx]
   */
  async function applyImportedFiles(fileList, ctx = {}) {
    const fl = Array.isArray(fileList) ? fileList : [];
    if (fl.length > 0) hideRichCanvasEmpty();
    stopVtkPlayback();
    revokeBlobs();
    destroyThree();
    hideTextPreview();
    threeApi = null;
    bcParsed = null;
    bcParsedKey = "";
    bcSourceFile = null;
    lastPreviewFile = null;
    await loadDesignSpecFromFiles(fl);
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
    await setupParametricPanel(fl, ctx);
    const def = pickDefaultMeshFile(fl);
    if (parametric.active) {
      /* 变径柱实时预览已由 setupParametricPanel 展示 */
    } else if (def) void loadPreviewForFile(def);
    else {
      if (fl.length === 0) {
        hideTransientCanvasHint();
        showRichCanvasEmpty();
      } else {
        showTransientCanvasHint("未找到可预览的 .vtk / .step / .stl / .obj / .inp，可调整左侧筛选");
      }
      objLabel.textContent = "—";
    }
  }

  function onDirChange(ev) {
    const fl = ev.target?.files;
    if (!fl?.length) return;
    applyImportedFiles(Array.from(fl));
  }

  function onFilesChange(ev) {
    const fl = ev.target?.files;
    if (!fl?.length) return;
    applyImportedFiles(Array.from(fl));
  }

  async function fetchWorkspaceRoot(base) {
    const r = await fetch(`${base}/api/cad-explorer/status`, { cache: "no-store" });
    if (!r.ok) throw new Error(`无法获取 workspace_root (${r.status})`);
    const j = await r.json();
    return String(j.workspace_root || "");
  }

  /**
   * 通过 /api/scan-directory + 工作区静态挂载（/runs、/examples 等）拉取可预览文件。
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
    let workspaceRoot = String(bundle.workspace_root || "");
    if (!workspaceRoot) {
      try {
        workspaceRoot = await fetchWorkspaceRoot(base);
      } catch {
        workspaceRoot = "";
      }
    }
    /** @type {File[]} */
    const out = [];
    for (const it of items.slice(0, RV_SCAN_MAX_FILES)) {
      if (!isResultsViewerFetchItem(it)) continue;
      const abs = String(it.path || "");
      const fu =
        workspaceRoot && abs
          ? workspaceRelativeFetchUrl(base, abs, workspaceRoot)
          : null;
      if (!fu) continue;
      try {
        const fr = await fetch(fu, { cache: "no-store" });
        if (!fr.ok) continue;
        const buf = await fr.arrayBuffer();
        if (buf.byteLength > RV_SCAN_MAX_BYTES) continue;
        const name = String(it.name || abs.split(/[/\\]/).pop() || "file");
        const relPath = workspaceRoot ? normFsPath(abs).slice(normFsPath(workspaceRoot).length).replace(/^\/+/, "") : name;
        const pseudo = relPath || name;
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
      if (meta) {
        meta.textContent =
          `已扫描 ${items.length} 项，但未能从工作区静态路径拉取 STEP/STL/VTK 等；请点「导入文件夹」选择 ` +
          `examples/beso/beso7/addition，或将 .stl/.step 拖入预览区。`;
      }
      return;
    }
    const measItem = items.find((it) => String(it.name || "").toLowerCase() === "measurements.json");
    const method1Dir = s.replace(/\\/g, "/").includes("method1_parametric")
      ? s
      : `${s.replace(/\\/g, "/").replace(/\/+$/, "")}/method1_parametric`;
    applyImportedFiles(out, {
      measurementsAbs: measItem?.path || `${method1Dir}/measurements.json`,
      outDirAbs: method1Dir,
    });
    const tail = s.replace(/\\/g, "/").split("/").filter(Boolean).pop() || "scan";
    if (meta) meta.textContent = `${tail} · 自服务器拉取 ${out.length} 个可预览文件`;
  }

  function buildParametricParamsPayload() {
    return {
      leg_stations: parametric.legStations.map((sts) =>
        normalizeLegStations(sts).map((s) => ({ t: s.t, scale: s.scale })),
      ),
      leg_hollow: [...parametric.legHollow],
      leg_wall_mm: [...parametric.legWallMm],
      hub_radius_scale: parametric.hubScale,
    };
  }

  function parametricPreviewAndSync() {
    previewParametricNow({ preserveView: true });
    scheduleParametricServerRebuild();
  }

  function syncParametricModeUi() {
    const editing = Boolean(parametric.active && parametric.editMode);
    rvParametric?.classList.toggle("resultsViewerParametric--editing", editing);
    rvParametricBd?.classList.toggle("hidden", !editing);
    if (rvParametricMode) {
      rvParametricMode.setAttribute("aria-pressed", editing ? "true" : "false");
      rvParametricMode.textContent = editing ? "退出调节" : "调节";
      rvParametricMode.classList.toggle("resultsViewerParametricModeBtn--on", editing);
    }
    if (rvParametricSub) {
      rvParametricSub.textContent = editing ? "选中控制点 · 摇杆调半径/高度" : "结果查看 · 点「调节」编辑";
    }
    if (rvParametricReset) rvParametricReset.disabled = !editing;
  }

  function setParametricEditMode(on) {
    parametric.editMode = Boolean(on);
    if (parametric.editMode) {
      parametric.selectedLeg = Math.max(0, Math.min(parametric.selectedLeg, (parametric.legStations.length || 1) - 1));
      const sts = parametric.legStations[parametric.selectedLeg] || [];
      if (!sts[parametric.selectedSt]) parametric.selectedSt = Math.max(0, sts.length - 1);
    }
    parametric.drag = null;
    syncParametricModeUi();
    if (parametric.editMode) renderParametricJoysticks();
  }

  function updateSelectedJoystickReadout() {
    const li = parametric.selectedLeg;
    const si = parametric.selectedSt;
    const leg = parametric.data?.legs?.[li];
    const st = parametric.legStations[li]?.[si];
    if (!leg || !st) return;
    const baseR = interpLegRadius(leg, st.t);
    const effR = baseR * (st.scale ?? 1);
    const pad = rvParametricBd?.querySelector(".rvParamJoyPad");
    if (!pad) return;
    const stick = pad.querySelector(".rvParamJoyStick");
    const meta = pad.querySelector(".rvParamJoyMeta");
    const nx = ((st.scale ?? 1) - PARAMETRIC_SCALE_MIN) / (PARAMETRIC_SCALE_MAX - PARAMETRIC_SCALE_MIN);
    const ny = st.locked ? 0.5 : 1 - st.t;
    if (stick instanceof HTMLElement) {
      stick.style.setProperty("--jx", `${(nx * 2 - 1) * 34}%`);
      stick.style.setProperty("--jy", `${(ny * 2 - 1) * 34}%`);
    }
    if (meta) {
      meta.textContent = `t ${(st.t * 100).toFixed(0)}% · ×${(st.scale ?? 1).toFixed(2)} · R ${effR.toFixed(0)}`;
    }
    const chips = rvParametricBd?.querySelectorAll(`.rvParamStChip[data-leg="${li}"]`);
    chips?.forEach((chip) => {
      const idx = Number(chip.getAttribute("data-st"));
      const s = parametric.legStations[li]?.[idx];
      if (!s) return;
      chip.style.left = `${((s.t) * 100).toFixed(1)}%`;
      chip.classList.toggle("rvParamStChip--active", idx === si);
      const tag = chip.querySelector(".rvParamStChipVal");
      if (tag) tag.textContent = `×${(s.scale ?? 1).toFixed(2)}`;
    });
  }

  function renderParametricJoysticks() {
    if (!rvParametricBd || !parametric.data) return;
    if (!parametric.editMode) {
      rvParametricBd.innerHTML = "";
      return;
    }
    rvParametricBd.innerHTML = "";
    const legs = Array.isArray(parametric.data.legs) ? parametric.data.legs : [];
    legs.forEach((leg, li) => {
      if (!parametric.legStations[li]) parametric.legStations[li] = defaultLegStationsFromMeas(leg);
      parametric.legStations[li] = normalizeLegStations(parametric.legStations[li]);
      if (parametric.legHollow[li] == null) parametric.legHollow[li] = false;
      if (parametric.legWallMm[li] == null) parametric.legWallMm[li] = 200;

      const block = document.createElement("div");
      block.className = "resultsViewerParametricLeg";
      if (li === parametric.selectedLeg) block.classList.add("resultsViewerParametricLeg--active");

      const title = document.createElement("button");
      title.type = "button";
      title.className = "resultsViewerParametricLegTitle";
      title.dataset.pickLeg = String(li);
      title.textContent = `柱 ${li + 1} · R≈${Number(leg.radius_mm || 0).toFixed(0)}`;
      block.appendChild(title);

      const opts = document.createElement("div");
      opts.className = "resultsViewerParametricOpts";
      const hollowLab = document.createElement("label");
      hollowLab.className = "resultsViewerParametricCheck";
      const hollowCb = document.createElement("input");
      hollowCb.type = "checkbox";
      hollowCb.checked = Boolean(parametric.legHollow[li]);
      hollowCb.dataset.leg = String(li);
      hollowCb.className = "rvParamHollow";
      hollowLab.append(hollowCb, document.createTextNode(" 镂空"));
      const wallLab = document.createElement("label");
      wallLab.className = "resultsViewerParametricWallLab";
      wallLab.innerHTML = `壁厚 <input type="number" class="rvParamWall" data-leg="${li}" min="${PARAMETRIC_WALL_MIN}" max="${PARAMETRIC_WALL_MAX}" step="10" value="${parametric.legWallMm[li]}" />`;
      opts.append(hollowLab, wallLab);
      block.appendChild(opts);

      const rail = document.createElement("div");
      rail.className = "rvParamStRail";
      rail.dataset.leg = String(li);
      rail.title = "点击选中控制点；仅选中点显示摇杆";
      const railFill = document.createElement("div");
      railFill.className = "rvParamStRailFill";
      rail.appendChild(railFill);
      const stations = parametric.legStations[li];
      stations.forEach((st, si) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "rvParamStChip";
        if (st.locked) chip.classList.add("rvParamStChip--locked");
        if (li === parametric.selectedLeg && si === parametric.selectedSt) chip.classList.add("rvParamStChip--active");
        chip.dataset.leg = String(li);
        chip.dataset.st = String(si);
        chip.style.left = `${(st.t * 100).toFixed(1)}%`;
        chip.innerHTML = `<span class="rvParamStChipDot"></span><span class="rvParamStChipVal">×${(st.scale ?? 1).toFixed(2)}</span>`;
        chip.title = st.locked ? "端点 · 仅调半径" : "中间点 · 调高度与半径 · 双击删除";
        if (!st.locked) {
          chip.addEventListener("dblclick", (ev) => {
            ev.preventDefault();
            ev.stopPropagation();
            if (stations.length <= 2) return;
            parametric.legStations[li] = stations.filter((_, j) => j !== si);
            parametric.selectedLeg = li;
            parametric.selectedSt = Math.min(si, parametric.legStations[li].length - 1);
            renderParametricJoysticks();
            parametricPreviewAndSync();
          });
        }
        rail.appendChild(chip);
      });
      block.appendChild(rail);

      if (li === parametric.selectedLeg) {
        const st = stations[parametric.selectedSt] || stations[0];
        const si = stations.indexOf(st);
        if (si >= 0) parametric.selectedSt = si;
        const joyRow = document.createElement("div");
        joyRow.className = "rvParamJoyRow";
        const pad = document.createElement("div");
        pad.className = "rvParamJoyPad";
        pad.dataset.leg = String(li);
        pad.dataset.st = String(parametric.selectedSt);
        pad.title = st?.locked ? "左右推摇杆改半径" : "左右=半径，上下=高度";
        pad.innerHTML = `
          <div class="rvParamJoyBase" aria-hidden="true"></div>
          <div class="rvParamJoyStick" role="slider" tabindex="0">
            <span class="rvParamJoyStickNeck"></span>
            <span class="rvParamJoyStickCap"></span>
          </div>
          <div class="rvParamJoyCross" aria-hidden="true"></div>`;
        const meta = document.createElement("div");
        meta.className = "rvParamJoyMeta mono";
        joyRow.append(pad, meta);
        block.appendChild(joyRow);

        const addBtn = document.createElement("button");
        addBtn.type = "button";
        addBtn.className = "btn rvParamAddSt";
        addBtn.dataset.leg = String(li);
        addBtn.textContent = "+ 点";
        addBtn.disabled = stations.length >= PARAMETRIC_MAX_STATIONS;
        block.appendChild(addBtn);
      }

      rvParametricBd.appendChild(block);
    });

    const hub = parametric.data.hub;
    if (hub) {
      const block = document.createElement("div");
      block.className = "resultsViewerParametricLeg";
      const title = document.createElement("div");
      title.className = "resultsViewerParametricLegTitle resultsViewerParametricLegTitle--static";
      title.textContent = `顶盘 · R≈${Number(hub.radius_mm).toFixed(0)}`;
      block.appendChild(title);
      const row = document.createElement("label");
      row.className = "resultsViewerParametricRow";
      row.innerHTML = `<span class="resultsViewerParametricLab">外圆</span><input type="range" class="resultsViewerParametricRange" id="rvParametricHubRange" min="${PARAMETRIC_SCALE_MIN}" max="${PARAMETRIC_SCALE_MAX}" step="0.01" value="${parametric.hubScale}" /><span class="resultsViewerParametricVal mono" id="rvParametricHubVal">×${parametric.hubScale.toFixed(2)}</span>`;
      block.appendChild(row);
      rvParametricBd.appendChild(block);
    }
    updateSelectedJoystickReadout();
  }

  function addMiddleStation(legIdx) {
    const sts = normalizeLegStations(parametric.legStations[legIdx] || []);
    if (sts.length >= PARAMETRIC_MAX_STATIONS) return;
    let bestGap = 0;
    let bestT = 0.5;
    for (let i = 0; i < sts.length - 1; i += 1) {
      const g = sts[i + 1].t - sts[i].t;
      if (g > bestGap) {
        bestGap = g;
        bestT = (sts[i].t + sts[i + 1].t) / 2;
      }
    }
    sts.splice(sts.length - 1, 0, { t: bestT, scale: 1 });
    parametric.legStations[legIdx] = normalizeLegStations(sts);
    parametric.selectedLeg = legIdx;
    parametric.selectedSt = sts.findIndex((s) => Math.abs(s.t - bestT) < 1e-6);
    if (parametric.selectedSt < 0) parametric.selectedSt = Math.max(0, sts.length - 2);
  }

  function onJoyPadPointerDown(pad, ev) {
    if (!(pad instanceof HTMLElement) || !parametric.editMode) return;
    ev.preventDefault();
    const legIdx = Number(pad.dataset.leg);
    const stIdx = Number(pad.dataset.st);
    const stations = parametric.legStations[legIdx];
    const station = stations?.[stIdx];
    if (!station) return;
    const locked = Boolean(station.locked);
    const minT = stIdx > 0 ? stations[stIdx - 1].t + 0.04 : 0;
    const maxT = stIdx < stations.length - 1 ? stations[stIdx + 1].t - 0.04 : 1;
    parametric.drag = {
      kind: "joypad",
      legIdx,
      stIdx,
      locked,
      minT,
      maxT,
      pad,
      pointerId: ev.pointerId,
    };
    try {
      pad.setPointerCapture(ev.pointerId);
    } catch {
      /* ignore */
    }
    applyJoyPadPointer(ev);
  }

  function applyJoyPadPointer(ev) {
    const d = parametric.drag;
    if (!d || d.kind !== "joypad" || !d.pad) return;
    const stations = parametric.legStations[d.legIdx];
    const station = stations?.[d.stIdx];
    if (!station) return;
    const rect = d.pad.getBoundingClientRect();
    const nx = clampParametric((ev.clientX - rect.left) / Math.max(rect.width, 1), 0, 1);
    const ny = clampParametric((ev.clientY - rect.top) / Math.max(rect.height, 1), 0, 1);
    station.scale = clampParametric(
      PARAMETRIC_SCALE_MIN + nx * (PARAMETRIC_SCALE_MAX - PARAMETRIC_SCALE_MIN),
      PARAMETRIC_SCALE_MIN,
      PARAMETRIC_SCALE_MAX,
    );
    if (!d.locked) {
      station.t = clampParametric(1 - ny, d.minT, d.maxT);
    }
    parametric.legStations[d.legIdx] = normalizeLegStations(stations);
    // Keep selected index stable after normalize reorder
    const sorted = parametric.legStations[d.legIdx];
    let nearest = 0;
    let best = Infinity;
    for (let i = 0; i < sorted.length; i += 1) {
      const dd = Math.abs(sorted[i].t - station.t) + Math.abs(sorted[i].scale - station.scale) * 0.01;
      if (dd < best) {
        best = dd;
        nearest = i;
      }
    }
    parametric.selectedSt = nearest;
    d.stIdx = nearest;
    d.locked = Boolean(sorted[nearest]?.locked);
    if (nearest > 0) d.minT = sorted[nearest - 1].t + 0.04;
    else d.minT = 0;
    if (nearest < sorted.length - 1) d.maxT = sorted[nearest + 1].t - 0.04;
    else d.maxT = 1;
    updateSelectedJoystickReadout();
    previewParametricNow({ preserveView: true });
  }

  function onJoyHandlePointerMove(ev) {
    if (!parametric.drag) return;
    if (parametric.drag.kind === "joypad") applyJoyPadPointer(ev);
  }

  function onJoyHandlePointerUp(ev) {
    if (!parametric.drag) return;
    const pad = parametric.drag.pad;
    try {
      pad?.releasePointerCapture?.(ev.pointerId);
    } catch {
      /* ignore */
    }
    parametric.drag = null;
    renderParametricJoysticks();
    scheduleParametricServerRebuild();
  }

  function previewParametricNow({ preserveView = true } = {}) {
    if (!parametric.active || !parametric.data) return;
    hideTextPreview();
    if (!threeApi) threeApi = initThree();
    const rootObj = buildParametricThreeGroup(
      parametric.data,
      parametric.legStations,
      parametric.legHollow,
      parametric.legWallMm,
      parametric.hubScale,
    );
    threeApi.setRoot(rootObj, { preserveView });
    objLabel.textContent = parametric.editMode ? "变径柱 · 调节预览" : "变径柱 · 结果预览";
    hideTransientCanvasHint();
  }

  function scheduleParametricServerRebuild() {
    if (!parametric.measAbs) return;
    const base = String(getBaseUrl() || "").replace(/\/+$/, "");
    if (!base) return;
    if (parametric.rebuildTimer) clearTimeout(parametric.rebuildTimer);
    parametric.rebuildTimer = setTimeout(async () => {
      parametric.rebuildTimer = null;
      const gen = ++parametric.rebuildGen;
      if (rvParametricStatus) rvParametricStatus.textContent = "服务端重建…";
      try {
        const r = await fetch(`${base}/api/beso7/parametric-rebuild`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            measurements_path: parametric.measAbs,
            out_dir: parametric.outAbs || undefined,
            params: buildParametricParamsPayload(),
            preview_only: true,
          }),
        });
        if (!r.ok) {
          const t = await r.text().catch(() => "");
          throw new Error(t.slice(0, 200) || `HTTP ${r.status}`);
        }
        const j = await r.json();
        if (gen !== parametric.rebuildGen) return;
        if (rvParametricStatus) rvParametricStatus.textContent = "已同步 preview.stl";
        if (j.preview_url) {
          /* 高精度 STL 可选加载；实时预览已由 Three.js 完成 */
        }
      } catch (e) {
        if (gen === parametric.rebuildGen && rvParametricStatus) {
          rvParametricStatus.textContent = `重建: ${e?.message || e}`;
        }
      }
    }, 650);
  }

  function onParametricInput(ev) {
    const t = ev.target;
    if (!t || parametric.active === false || !parametric.editMode) return;
    if (t.id === "rvParametricHubRange") {
      parametric.hubScale = Number(t.value);
      const hubVal = root.querySelector("#rvParametricHubVal");
      if (hubVal) hubVal.textContent = `×${parametric.hubScale.toFixed(2)}`;
      parametricPreviewAndSync();
      return;
    }
    if (t.classList?.contains("rvParamHollow")) {
      const li = Number(t.dataset.leg);
      parametric.legHollow[li] = Boolean(t.checked);
      parametricPreviewAndSync();
      return;
    }
    if (t.classList?.contains("rvParamWall")) {
      const li = Number(t.dataset.leg);
      parametric.legWallMm[li] = clampParametric(Number(t.value) || 200, PARAMETRIC_WALL_MIN, PARAMETRIC_WALL_MAX);
      parametricPreviewAndSync();
    }
  }

  function onParametricClick(ev) {
    const t = ev.target;
    if (!(t instanceof HTMLElement) || !parametric.editMode) return;
    const pickLeg = t.closest?.("[data-pick-leg]");
    if (pickLeg instanceof HTMLElement) {
      parametric.selectedLeg = Number(pickLeg.dataset.pickLeg);
      parametric.selectedSt = 0;
      renderParametricJoysticks();
      return;
    }
    const chip = t.closest?.(".rvParamStChip");
    if (chip instanceof HTMLElement) {
      parametric.selectedLeg = Number(chip.dataset.leg);
      parametric.selectedSt = Number(chip.dataset.st);
      renderParametricJoysticks();
      return;
    }
    if (t.classList.contains("rvParamAddSt")) {
      addMiddleStation(Number(t.dataset.leg));
      renderParametricJoysticks();
      parametricPreviewAndSync();
    }
  }

  function resetParametricScales() {
    if (!parametric.editMode) return;
    const legs = Array.isArray(parametric.data?.legs) ? parametric.data.legs : [];
    parametric.legStations = legs.map((leg) => defaultLegStationsFromMeas(leg));
    parametric.legHollow = legs.map(() => false);
    parametric.legWallMm = legs.map(() => 200);
    parametric.hubScale = 1;
    parametric.selectedLeg = 0;
    parametric.selectedSt = 0;
    renderParametricJoysticks();
    previewParametricNow({ preserveView: false });
    scheduleParametricServerRebuild();
  }

  async function setupParametricPanel(fileList, ctx = {}) {
    parametric.active = false;
    parametric.editMode = false;
    parametric.data = null;
    parametric.measAbs = ctx.measurementsAbs || null;
    parametric.outAbs = ctx.outDirAbs || null;
    parametric.drag = null;
    parametric.selectedLeg = 0;
    parametric.selectedSt = 0;
    rvParametric?.classList.add("hidden");
    syncParametricModeUi();
    if (rvParametricStatus) rvParametricStatus.textContent = "";
    const mf = findMeasurementsFile(fileList);
    if (!mf) return;
    try {
      const data = JSON.parse(await mf.text());
      if (!Array.isArray(data?.legs) || !data.legs.length) return;
      parametric.data = data;
      parametric.legStations = data.legs.map((leg) => defaultLegStationsFromMeas(leg));
      parametric.legHollow = data.legs.map(() => false);
      parametric.legWallMm = data.legs.map(() => 200);
      parametric.hubScale = 1;
      parametric.active = true;
      parametric.editMode = false;
      rvParametric?.classList.remove("hidden");
      syncParametricModeUi();
      previewParametricNow({ preserveView: false });
      if (rvParametricStatus) {
        rvParametricStatus.textContent = "点「调节」进入编辑；退出后正常看结果";
      }
    } catch {
      /* ignore invalid json */
    }
  }

  rvParametricBd?.addEventListener("input", onParametricInput);
  rvParametricBd?.addEventListener("change", onParametricInput);
  rvParametricBd?.addEventListener("click", onParametricClick);
  rvParametricBd?.addEventListener("pointerdown", (ev) => {
    const pad = ev.target?.closest?.(".rvParamJoyPad");
    if (pad) onJoyPadPointerDown(pad, ev);
  });
  // Use document-level move/up so drag survives small DOM updates
  document.addEventListener("pointermove", onJoyHandlePointerMove);
  document.addEventListener("pointerup", onJoyHandlePointerUp);
  document.addEventListener("pointercancel", onJoyHandlePointerUp);
  rvParametricReset?.addEventListener("click", () => resetParametricScales());
  rvParametricMode?.addEventListener("click", () => {
    if (!parametric.active) return;
    setParametricEditMode(!parametric.editMode);
    if (rvParametricStatus) {
      rvParametricStatus.textContent = parametric.editMode
        ? parametric.measAbs
          ? "选中控制点 · 拖摇杆 · 自动重建"
          : "选中控制点 · 拖摇杆（本地预览）"
        : "结果查看模式";
    }
    previewParametricNow({ preserveView: true });
  });

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
    if (act === "bc") {
      toggleBcOverlay();
      return;
    }
    if (act === "dim") {
      toggleDimOverlay();
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
  btnPickFiles?.addEventListener("click", () => inpFiles?.click());
  inpDir?.addEventListener("change", onDirChange);
  inpFiles?.addEventListener("change", onFilesChange);
  syncSpinUi();
  syncBcToggleUi();
  syncDimToggleUi();
  syncFsUi();
  btnSpin?.addEventListener("click", () => {
    spinEnabled = !spinEnabled;
    syncSpinUi();
  });
  btnBc?.addEventListener("click", () => toggleBcOverlay());
  btnDim?.addEventListener("click", () => toggleDimOverlay());
  rvBcStepSelect?.addEventListener("change", () => {
    bcStepIndex = parseInt(rvBcStepSelect.value, 10) || 0;
    void refreshBcOverlay();
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
