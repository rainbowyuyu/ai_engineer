/**
 * 解析 BESO / ParaView / FreeCAD 导出的 VTK Legacy ASCII，UNSTRUCTURED_GRID + 四面体（CELL_TYPES=10）。
 * 支持经典行格式 `4 i j k l` 与 VTK 5.1 的 OFFSETS + CONNECTIVITY 块。
 * 将每个四面体展开为 4 个三角面用于 THREE.Mesh 显示。
 */
import * as THREE from "three";

/**
 * @param {string[]} lines
 * @param {number} startI
 * @param {(trimmed: string) => boolean} stopWhen
 * @returns {{ ints: number[], nextI: number }}
 */
function collectIntLinesUntil(lines, startI, stopWhen) {
  const ints = [];
  let i = startI;
  while (i < lines.length) {
    const raw = lines[i];
    const ln = raw.trim();
    if (!ln || ln.startsWith("#")) {
      i++;
      continue;
    }
    if (stopWhen(ln)) break;
    for (const t of ln.split(/\s+/)) {
      if (!t) continue;
      const v = parseInt(t, 10);
      if (Number.isFinite(v)) ints.push(v);
    }
    i++;
  }
  return { ints, nextI: i };
}

/**
 * @param {string} text
 * @returns {{ geometry: THREE.BufferGeometry, numPoints: number, numCells: number }}
 */
export function parseLegacyAsciiUnstructuredGridTets(text) {
  const lines = text.split(/\r?\n/);
  let i = 0;
  while (i < lines.length) {
    const u = lines[i].trim().toUpperCase();
    if (u.startsWith("POINTS ")) break;
    i++;
  }
  if (i >= lines.length) throw new Error("VTK: 未找到 POINTS");
  const hdr = lines[i].trim().split(/\s+/);
  const nPts = parseInt(hdr[1], 10);
  if (!Number.isFinite(nPts) || nPts < 4) throw new Error("VTK: POINTS 数量无效");
  i++;
  const coords = [];
  while (coords.length < nPts * 3 && i < lines.length) {
    const ln = lines[i++].trim();
    if (!ln || ln.startsWith("#")) continue;
    for (const t of ln.split(/\s+/)) {
      if (t) coords.push(parseFloat(t));
    }
  }
  if (coords.length < nPts * 3) throw new Error("VTK: POINTS 数据不完整");

  while (i < lines.length) {
    const u = lines[i].trim().toUpperCase();
    if (u.startsWith("CELLS ")) break;
    i++;
  }
  if (i >= lines.length) throw new Error("VTK: 未找到 CELLS");
  const ch = lines[i].trim().split(/\s+/);
  const nCellsHdr = parseInt(ch[1], 10);
  i++;

  /** @type {number[][]} */
  let cells = [];

  while (i < lines.length) {
    const skip = lines[i].trim();
    if (skip && !skip.startsWith("#")) break;
    i++;
  }
  const firstCell = (lines[i] || "").trim().toUpperCase();
  if (firstCell.startsWith("OFFSETS")) {
    i++;
    const offRes = collectIntLinesUntil(lines, i, (ln) => ln.toUpperCase().startsWith("CONNECTIVITY"));
    const offsets = offRes.ints;
    i = offRes.nextI;
    if (!offsets.length) throw new Error("VTK: OFFSETS 为空");
    const connHead = (lines[i] || "").trim().toUpperCase();
    if (!connHead.startsWith("CONNECTIVITY")) throw new Error("VTK: 未找到 CONNECTIVITY");
    i++;
    const connTarget = offsets[offsets.length - 1];
    if (!Number.isFinite(connTarget) || connTarget < 4) throw new Error("VTK: OFFSETS 末尾无效");
    const connRes = collectIntLinesUntil(lines, i, (ln) => ln.toUpperCase().startsWith("CELL_TYPES"));
    const conn = connRes.ints;
    i = connRes.nextI;
    if (conn.length < connTarget) throw new Error("VTK: CONNECTIVITY 数据不完整");
    const nCells = offsets.length - 1;
    for (let ci = 0; ci < nCells; ci++) {
      const s = offsets[ci];
      const e = offsets[ci + 1];
      const slice = conn.slice(s, e);
      if (slice.length !== 4) {
        throw new Error(`VTK: 仅支持四面体单元，第 ${ci} 个单元节点数为 ${slice.length}`);
      }
      cells.push(slice);
    }
  } else {
    const nCells = nCellsHdr;
    while (cells.length < nCells && i < lines.length) {
      const ln = lines[i++].trim();
      if (!ln || ln.startsWith("#")) continue;
      const p = ln.split(/\s+/).map((x) => parseInt(x, 10));
      const nk = p[0];
      if (nk === 4 && p.length === 5) {
        cells.push([p[1], p[2], p[3], p[4]]);
      }
    }
    if (cells.length < nCells) throw new Error("VTK: CELLS 数据不完整（经典格式）");
  }

  const pos = new Float32Array(coords);
  const triVerts = new Float32Array(cells.length * 4 * 3 * 3);
  let w = 0;
  const pushTri = (ia, ib, ic) => {
    for (const ix of [ia, ib, ic]) {
      const o = ix * 3;
      triVerts[w++] = pos[o];
      triVerts[w++] = pos[o + 1];
      triVerts[w++] = pos[o + 2];
    }
  };
  for (const [a, b, c, d] of cells) {
    pushTri(a, b, c);
    pushTri(a, b, d);
    pushTri(a, c, d);
    pushTri(b, c, d);
  }
  const geom = new THREE.BufferGeometry();
  geom.setAttribute("position", new THREE.BufferAttribute(triVerts, 3));
  geom.computeVertexNormals();
  return { geometry: geom, numPoints: nPts, numCells: cells.length };
}
