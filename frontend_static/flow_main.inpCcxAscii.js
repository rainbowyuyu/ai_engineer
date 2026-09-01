/**
 * 轻量解析 CalculiX INP 中的 *NODE + *ELEMENT, TYPE=C3D4（遇 *STEP 即停止，避免读入整段分析历史）。
 * 用于无后端 / FreeCAD 不可用时的网格三维预览回退。
 */
import * as THREE from "three";

function splitCsvLine(line) {
  return line
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

/** 单行或多节点紧凑行：每 4 段为一组 id,x,y,z */
function parseNodeChunks(parts) {
  const out = [];
  for (let i = 0; i + 3 < parts.length; ) {
    const id = parseInt(parts[i], 10);
    const x = parseFloat(parts[i + 1]);
    const y = parseFloat(parts[i + 2]);
    const z = parseFloat(parts[i + 3]);
    if (Number.isFinite(id) && Number.isFinite(x) && Number.isFinite(y) && Number.isFinite(z)) {
      out.push({ id, x, y, z });
      i += 4;
    } else {
      break;
    }
  }
  return out;
}

/** C3D4：每 5 段 elId, n1..n4 */
function parseC3d4Chunks(parts) {
  const tets = [];
  for (let i = 0; i + 4 < parts.length; i += 5) {
    const n1 = parseInt(parts[i + 1], 10);
    const n2 = parseInt(parts[i + 2], 10);
    const n3 = parseInt(parts[i + 3], 10);
    const n4 = parseInt(parts[i + 4], 10);
    if (Number.isFinite(n1) && Number.isFinite(n2) && Number.isFinite(n3) && Number.isFinite(n4)) {
      tets.push([n1, n2, n3, n4]);
    }
  }
  return tets;
}

/**
 * @param {string} text 完整或前缀 INP 文本
 * @returns {{ geometry: THREE.BufferGeometry, numNodes: number, numTets: number }}
 */
export function parseInpC3D4ToBufferGeometry(text) {
  const nodes = new Map();
  const tets = [];
  const lines = text.split(/\r?\n/);
  let mode = null;

  for (let li = 0; li < lines.length; li++) {
    const raw = lines[li];
    const trimmed = raw.trim();
    const u = trimmed.toUpperCase();
    if (u.startsWith("*STEP") || u === "*STEP") {
      break;
    }
    if (!trimmed || trimmed.startsWith("**")) {
      continue;
    }
    if (trimmed.startsWith("*")) {
      if (u.startsWith("*NODE")) {
        mode = "node";
      } else if (u.includes("C3D4") && u.startsWith("*ELEMENT")) {
        mode = "c3d4";
      } else {
        mode = null;
      }
      continue;
    }
    if (mode === "node") {
      for (const rec of parseNodeChunks(splitCsvLine(trimmed))) {
        nodes.set(rec.id, rec);
      }
    } else if (mode === "c3d4") {
      tets.push(...parseC3d4Chunks(splitCsvLine(trimmed)));
    }
  }

  if (!tets.length) {
    throw new Error("INP：未解析到 C3D4 体单元（或尚未到达 *ELEMENT 段）");
  }

  const pushTri = (buf, w, posById, ia, ib, ic) => {
    const get = (id) => {
      const p = posById.get(id);
      if (!p) throw new Error(`INP：缺少节点 ${id}`);
      return p;
    };
    for (const id of [ia, ib, ic]) {
      const p = get(id);
      buf[w++] = p.x;
      buf[w++] = p.y;
      buf[w++] = p.z;
    }
    return w;
  };

  const triVerts = new Float32Array(tets.length * 4 * 3 * 3);
  let w = 0;
  for (const [a, b, c, d] of tets) {
    w = pushTri(triVerts, w, nodes, a, b, c);
    w = pushTri(triVerts, w, nodes, a, b, d);
    w = pushTri(triVerts, w, nodes, a, c, d);
    w = pushTri(triVerts, w, nodes, b, c, d);
  }

  const geom = new THREE.BufferGeometry();
  geom.setAttribute("position", new THREE.BufferAttribute(triVerts.subarray(0, w), 3));
  geom.computeVertexNormals();
  return { geometry: geom, numNodes: nodes.size, numTets: tets.length };
}

function _headerParam(uLine, key) {
  const re = new RegExp(`${key}\\s*=\\s*([^,\\s]+)`, "i");
  const m = re.exec(uLine);
  return m ? m[1].trim() : "";
}

function _resolveBoundaryTarget(token, nsets) {
  const id = parseInt(token, 10);
  if (Number.isFinite(id) && String(id) === token.trim()) return [id];
  const name = token.trim();
  const ids = nsets.get(name.toLowerCase()) || nsets.get(name);
  return ids ? [...ids] : [];
}

/**
 * 解析 CalculiX INP 的节点、NSET、各 *STEP 内 *BOUNDARY / *CLOAD（用于结果查看器约束/载荷叠加）。
 * @param {string} text
 * @returns {{
 *   nodes: Map<number,{x:number,y:number,z:number}>,
 *   nsets: Map<string, number[]>,
 *   steps: Array<{
 *     index: number,
 *     kind: string,
 *     boundaryRows: Array<{ref:string, dofFrom:number, dofTo:number}>,
 *     cloads: Array<{nid:number, dof:number, mag:number}>,
 *     fixedNodeIds: number[],
 *   }>,
 *   summary: { nodeCount:number, stepCount:number, fixedCount:number, cloadCount:number, forceSumAbs:number }
 * }}
 */
export function parseInpFemBc(text) {
  /** @type {Map<number,{x:number,y:number,z:number}>} */
  const nodes = new Map();
  /** @type {Map<string, number[]>} */
  const nsets = new Map();
  const steps = [];
  const lines = String(text || "").split(/\r?\n/);

  let mode = null;
  /** @type {string} */
  let currentNset = "";
  /** @type {null | typeof steps[0]} */
  let curStep = null;

  const ensureStep = () => {
    if (!curStep) {
      curStep = {
        index: steps.length + 1,
        kind: "Static",
        boundaryRows: [],
        cloads: [],
        fixedNodeIds: [],
      };
      steps.push(curStep);
    }
    return curStep;
  };

  for (let li = 0; li < lines.length; li++) {
    const trimmed = lines[li].trim();
    if (!trimmed) continue;
    const u = trimmed.toUpperCase();
    if (trimmed.startsWith("**")) continue;

    if (trimmed.startsWith("*")) {
      if (u.startsWith("*NODE") && !u.startsWith("*NODE FILE") && !u.startsWith("*NODE PRINT")) {
        mode = "node";
        currentNset = "";
        continue;
      }
      if (u.startsWith("*NSET")) {
        mode = "nset";
        currentNset = _headerParam(trimmed, "NSET") || _headerParam(trimmed, "Nset") || "";
        if (currentNset && !nsets.has(currentNset.toLowerCase())) {
          nsets.set(currentNset.toLowerCase(), []);
          nsets.set(currentNset, nsets.get(currentNset.toLowerCase()));
        }
        continue;
      }
      if (u.startsWith("*STEP")) {
        mode = "step_meta";
        curStep = {
          index: steps.length + 1,
          kind: "Static",
          boundaryRows: [],
          cloads: [],
          fixedNodeIds: [],
        };
        steps.push(curStep);
        continue;
      }
      if (u.startsWith("*END STEP")) {
        mode = null;
        curStep = null;
        continue;
      }
      if (u.startsWith("*STATIC") || u.startsWith("*FREQUENCY") || u.startsWith("*BUCKLE") || u.startsWith("*DYNAMIC")) {
        const st = ensureStep();
        st.kind = trimmed.replace(/^\*/, "").split(",")[0].trim() || st.kind;
        mode = "step_meta";
        continue;
      }
      if (u.startsWith("*BOUNDARY")) {
        mode = "boundary";
        ensureStep();
        continue;
      }
      if (u.startsWith("*CLOAD")) {
        mode = "cload";
        ensureStep();
        continue;
      }
      mode = null;
      continue;
    }

    if (mode === "node") {
      for (const rec of parseNodeChunks(splitCsvLine(trimmed))) {
        nodes.set(rec.id, { x: rec.x, y: rec.y, z: rec.z });
      }
      continue;
    }
    if (mode === "nset" && currentNset) {
      const arr = nsets.get(currentNset.toLowerCase()) || [];
      for (const p of splitCsvLine(trimmed)) {
        const id = parseInt(p, 10);
        if (Number.isFinite(id)) arr.push(id);
      }
      nsets.set(currentNset.toLowerCase(), arr);
      nsets.set(currentNset, arr);
      continue;
    }
    if (mode === "boundary" && curStep) {
      const parts = splitCsvLine(trimmed);
      if (parts.length < 2) continue;
      const ref = parts[0];
      const dofFrom = parseInt(parts[1], 10);
      const dofTo = parts.length >= 3 && Number.isFinite(parseInt(parts[2], 10)) ? parseInt(parts[2], 10) : dofFrom;
      if (!Number.isFinite(dofFrom)) continue;
      curStep.boundaryRows.push({ ref, dofFrom, dofTo });
      continue;
    }
    if (mode === "cload" && curStep) {
      const parts = splitCsvLine(trimmed);
      if (parts.length < 3) continue;
      const nid = parseInt(parts[0], 10);
      const dof = parseInt(parts[1], 10);
      const mag = parseFloat(parts[2]);
      if (Number.isFinite(nid) && Number.isFinite(dof) && Number.isFinite(mag)) {
        curStep.cloads.push({ nid, dof, mag });
      }
    }
  }

  for (const st of steps) {
    const fixed = new Set();
    for (const row of st.boundaryRows) {
      for (const nid of _resolveBoundaryTarget(row.ref, nsets)) fixed.add(nid);
    }
    st.fixedNodeIds = [...fixed].sort((a, b) => a - b);
  }

  const last = steps[steps.length - 1];
  let forceSumAbs = 0;
  if (last) {
    for (const c of last.cloads) forceSumAbs += Math.abs(c.mag);
  }

  return {
    nodes,
    nsets,
    steps,
    summary: {
      nodeCount: nodes.size,
      stepCount: steps.length,
      fixedCount: last?.fixedNodeIds.length || 0,
      cloadCount: last?.cloads.length || 0,
      forceSumAbs,
    },
  };
}

/**
 * 在原始 INP 坐标下构建固定约束点 + 载荷箭头 Group（可挂到已居中 meshRoot 下）。
 * @param {ReturnType<typeof parseInpFemBc>} bc
 * @param {{ stepIndex?: number, maxMarkers?: number, maxArrows?: number }} [opts]
 * @returns {{ group: THREE.Group, usedStep: object|null, skippedFixed: number, skippedLoads: number }}
 */
export function buildFemBcOverlayGroup(bc, opts = {}) {
  const group = new THREE.Group();
  group.name = "rvFemBcOverlay";
  if (!bc?.steps?.length) {
    return { group, usedStep: null, skippedFixed: 0, skippedLoads: 0 };
  }
  const want = Math.max(1, Math.min(bc.steps.length, Number(opts.stepIndex) || bc.steps.length));
  const step = bc.steps[want - 1];
  const maxMarkers = Math.max(20, Number(opts.maxMarkers) || 2500);
  const maxArrows = Math.max(10, Number(opts.maxArrows) || 800);

  const fixedIds = step.fixedNodeIds.filter((id) => bc.nodes.has(id));
  const skipF = Math.max(0, fixedIds.length - maxMarkers);
  const showFixed = skipF > 0 ? fixedIds.filter((_, i) => i % Math.ceil(fixedIds.length / maxMarkers) === 0) : fixedIds;

  if (showFixed.length) {
    const pos = new Float32Array(showFixed.length * 3);
    for (let i = 0; i < showFixed.length; i++) {
      const p = bc.nodes.get(showFixed[i]);
      pos[i * 3] = p.x;
      pos[i * 3 + 1] = p.y;
      pos[i * 3 + 2] = p.z;
    }
    const geom = new THREE.BufferGeometry();
    geom.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    const pts = new THREE.Points(
      geom,
      new THREE.PointsMaterial({
        color: 0xf43f5e,
        size: 8,
        sizeAttenuation: false,
        depthTest: false,
        depthWrite: false,
        transparent: true,
        opacity: 0.95,
      }),
    );
    pts.name = "rvFixedNodes";
    pts.renderOrder = 10;
    group.add(pts);
  }

  const cloads = step.cloads.filter((c) => bc.nodes.has(c.nid));
  let maxAbs = 0;
  for (const c of cloads) maxAbs = Math.max(maxAbs, Math.abs(c.mag));
  const skipL = Math.max(0, cloads.length - maxArrows);
  const showLoads =
    skipL > 0 ? cloads.filter((_, i) => i % Math.ceil(cloads.length / maxArrows) === 0) : cloads;

  // 黄色载荷作用点（与固定红点对称，避免仅靠箭头时顶视被实体遮挡）
  if (showLoads.length) {
    const pos = new Float32Array(showLoads.length * 3);
    for (let i = 0; i < showLoads.length; i++) {
      const p = bc.nodes.get(showLoads[i].nid);
      pos[i * 3] = p.x;
      pos[i * 3 + 1] = p.y;
      pos[i * 3 + 2] = p.z;
    }
    const geom = new THREE.BufferGeometry();
    geom.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    const loadPts = new THREE.Points(
      geom,
      new THREE.PointsMaterial({
        color: 0xfbbf24,
        size: 9,
        sizeAttenuation: false,
        depthTest: false,
        depthWrite: false,
        transparent: true,
        opacity: 0.98,
      }),
    );
    loadPts.name = "rvCloadNodes";
    loadPts.renderOrder = 10;
    group.add(loadPts);
  }

  // 箭头长度相对模型尺度；尖端落在节点上（力指向结构内部时仍能看见）
  let diag = 1;
  if (bc.nodes.size) {
    let xmin = Infinity,
      ymin = Infinity,
      zmin = Infinity,
      xmax = -Infinity,
      ymax = -Infinity,
      zmax = -Infinity;
    for (const p of bc.nodes.values()) {
      xmin = Math.min(xmin, p.x);
      ymin = Math.min(ymin, p.y);
      zmin = Math.min(zmin, p.z);
      xmax = Math.max(xmax, p.x);
      ymax = Math.max(ymax, p.y);
      zmax = Math.max(zmax, p.z);
    }
    diag = Math.hypot(xmax - xmin, ymax - ymin, zmax - zmin) || 1;
  }
  const baseLen = Math.max(diag * 0.08, 1);

  for (const c of showLoads) {
    const p = bc.nodes.get(c.nid);
    const dir = new THREE.Vector3(
      c.dof === 1 ? Math.sign(c.mag) || 1 : 0,
      c.dof === 2 ? Math.sign(c.mag) || 1 : 0,
      c.dof === 3 ? Math.sign(c.mag) || 1 : 0,
    );
    if (dir.lengthSq() < 1e-12) dir.set(0, 0, -1);
    dir.normalize();
    const len = baseLen * (0.45 + 0.55 * (maxAbs > 0 ? Math.abs(c.mag) / maxAbs : 1));
    const tip = new THREE.Vector3(p.x, p.y, p.z);
    // 箭头尖端在节点：起点沿力方向反方向偏移
    const origin = tip.clone().addScaledVector(dir, -len);
    const arrow = new THREE.ArrowHelper(dir, origin, len, 0xfbbf24, len * 0.32, len * 0.2);
    arrow.name = "rvCloadArrow";
    arrow.renderOrder = 11;
    arrow.traverse((ch) => {
      if (ch.material) {
        const mats = Array.isArray(ch.material) ? ch.material : [ch.material];
        for (const m of mats) {
          m.depthTest = false;
          m.depthWrite = false;
          m.transparent = true;
          m.opacity = 0.95;
        }
      }
    });
    group.add(arrow);
  }

  return { group, usedStep: step, skippedFixed: skipF, skippedLoads: skipL };
}
