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
