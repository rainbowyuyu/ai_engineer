/** @file CAD drawing intent + workspace path extraction for landing chat */

const CAD_EXT = "(?:inp|iges|igs|stp|step|obj|vtk|stl)";

/** @param {string} text */
export function extractWorkspaceCadPaths(text) {
  const paths = new Set();
  const s = String(text || "");
  const re = new RegExp(`@?((?:[^\\s@/\\\\]+[\\\\/])+[^\\s@\\\\]+\\.${CAD_EXT})\\b`, "gi");
  let m;
  while ((m = re.exec(s))) {
    let p = String(m[1] || "")
      .replace(/^@/, "")
      .replace(/\\/g, "/");
    if (p.startsWith("./")) p = p.slice(2);
    paths.add(p);
  }
  return [...paths];
}

/** @param {string} fileName */
export function isCadDrawingFileName(fileName) {
  return /\.(inp|iges|igs|stp|step|obj|vtk|stl)$/i.test(String(fileName || ""));
}

/**
 * @param {string} text
 * @param {string[]} paths
 * @param {{ hasUploadedCad?: boolean }} [opts]
 */
export function isCadDrawingIntent(text, paths, opts = {}) {
  const hasCad = Boolean(paths?.length) || Boolean(opts.hasUploadedCad);
  if (!hasCad) return false;
  if (/@/.test(text) && paths?.length) return true;
  return /绘制|画图|工程图|图纸|出图|三视图|四视图|总布置|cad\s*图|layout|预览图|线框/i.test(text);
}

/**
 * @param {{ path?: string, fileId?: string, title?: string, engine?: string, sheetSize?: string, layout?: string }} body
 * @param {string} baseUrl
 */
export async function requestCadDrawingPack(body, baseUrl) {
  const payload =
    typeof body === "string"
      ? { path: body, engine: "auto", sheet_size: "A3", layout: "ga" }
      : {
          path: body.path || undefined,
          file_id: body.fileId || undefined,
          title: body.title || undefined,
          engine: body.engine || "auto",
          sheet_size: body.sheetSize || "A3",
          layout: body.layout || "ga",
        };
  const r = await fetch(`${baseUrl.replace(/\/$/, "")}/api/cad/drawing-pack`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  let data = {};
  try {
    data = await r.json();
  } catch {
    /* ignore */
  }
  if (!r.ok) {
    const detail = typeof data.detail === "string" ? data.detail : r.statusText;
    throw new Error(detail || "工程图生成失败");
  }
  return data;
}
