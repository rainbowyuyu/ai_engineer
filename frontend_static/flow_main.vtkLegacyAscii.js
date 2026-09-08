/**
 * 解析 BESO / ParaView / FreeCAD 导出的 VTK Legacy ASCII，UNSTRUCTURED_GRID + 四面体（CELL_TYPES=10）。
 * 支持经典行格式 `4 i j k l` 与 VTK 5.1 的 OFFSETS + CONNECTIVITY 块。
 * 返回索引几何（POINTS 共用），避免把四面体展开成海量重复顶点；配合 flatShading 显示。
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
 * @param {{ stride?: number, maxCells?: number }} [opts]
 * @returns {{ geometry: THREE.BufferGeometry, numPoints: number, numCells: number, usedCells: number, stride: number }}
 */
export function parseLegacyAsciiUnstructuredGridTets(text, opts = {}) {
  const stride = Math.max(1, Math.floor(Number(opts.stride) || 1));
  const maxCells = Math.max(0, Math.floor(Number(opts.maxCells) || 0));
  const probe = String(text || "").slice(0, 240).toUpperCase();
  if (/\bBINARY\b/.test(probe) && !/\bASCII\b/.test(probe)) {
    throw new Error("VTK: 收到 BINARY 格式（需要 ASCII Legacy VTK）");
  }
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
    // VTK 5.1 偶发写成 CELLS\t 或仅 CELLS；也兼容直接进入 OFFSETS 块
    if (u.startsWith("CELLS ") || u === "CELLS" || u.startsWith("OFFSETS")) break;
    i++;
  }
  if (i >= lines.length) throw new Error("VTK: 未找到 CELLS");
  let nCellsHdr = 0;
  const cellLine = lines[i].trim();
  const cellU = cellLine.toUpperCase();
  if (cellU.startsWith("CELLS")) {
    const ch = cellLine.split(/\s+/);
    nCellsHdr = parseInt(ch[1], 10);
    i++;
  }

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
    /** 流式读取经典 CELLS：支持一行一单元，也支持多单元挤在同一行 */
    const buf = [];
    while (cells.length < nCells && i < lines.length) {
      const ln = lines[i++].trim();
      if (!ln || ln.startsWith("#")) continue;
      const u = ln.toUpperCase();
      if (u.startsWith("CELL_TYPES") || u.startsWith("OFFSETS") || u.startsWith("POINT_DATA") || u.startsWith("CELL_DATA")) {
        break;
      }
      for (const t of ln.split(/\s+/)) {
        if (!t) continue;
        const v = parseInt(t, 10);
        if (!Number.isFinite(v)) continue;
        buf.push(v);
        while (buf.length >= 1) {
          const nk = buf[0];
          if (nk !== 4) {
            throw new Error(`VTK: 仅支持四面体（每单元 4 节点），读到 n=${nk}`);
          }
          if (buf.length < 5) break;
          cells.push([buf[1], buf[2], buf[3], buf[4]]);
          buf.splice(0, 5);
          if (cells.length >= nCells) break;
        }
      }
    }
    if (cells.length < nCells) throw new Error("VTK: CELLS 数据不完整（经典格式）");
  }

  const pos = new Float32Array(coords);
  /** @type {number[]} */
  const index = [];
  let used = 0;
  for (let ci = 0; ci < cells.length; ci++) {
    if (stride > 1 && ci % stride !== 0) continue;
    if (maxCells > 0 && used >= maxCells) break;
    const [a, b, c, d] = cells[ci];
    index.push(a, b, c, a, b, d, a, c, d, b, c, d);
    used++;
  }
  if (!index.length) throw new Error("VTK: 无可用四面体单元");

  const geom = new THREE.BufferGeometry();
  geom.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geom.setIndex(new THREE.BufferAttribute(new Uint32Array(index), 1));
  geom.computeBoundingSphere();
  return {
    geometry: geom,
    numPoints: nPts,
    numCells: cells.length,
    usedCells: used,
    stride,
  };
}
