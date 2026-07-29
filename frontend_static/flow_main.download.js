/** @file Chat / markdown deliverable download link resolution */

/**
 * @param {string} href
 * @param {{ baseUrl?: string, jobId?: string|null, scanDir?: string, packId?: string|null }} ctx
 */
export function isLikelyDownloadHref(href) {
  const h = String(href || "").trim();
  if (!h || h.startsWith("#") || /^javascript:/i.test(h)) return false;
  return true;
}

/**
 * @param {string} href
 * @param {{ baseUrl?: string, jobId?: string|null, scanDir?: string, packId?: string|null }} ctx
 */
export function resolveChatDownloadHref(href, ctx = {}) {
  const raw = String(href || "").trim();
  if (!isLikelyDownloadHref(raw)) return null;
  const base = String(ctx.baseUrl || "").replace(/\/$/, "").replace(/\/ui$/i, "");

  if (/^https?:\/\//i.test(raw)) {
    try {
      const u = new URL(raw);
      if (base && u.pathname.startsWith("/ui/") && !u.pathname.startsWith("/ui/api")) {
        const inner = u.pathname.replace(/^\/ui\//, "/");
        return `${base}${inner.startsWith("/") ? inner : `/${inner}`}${u.search}`;
      }
    } catch {
      /* ignore */
    }
    return raw;
  }

  if (raw.startsWith("/")) return base ? `${base}${raw}` : raw;

  const fname = raw.replace(/^.*[/\\]/, "");
  if (ctx.packId) return base ? `${base}/runs/_deliverables/${ctx.packId}/${encodeURIComponent(fname)}` : null;
  if (ctx.jobId) return base ? `${base}/runs/${encodeURIComponent(ctx.jobId)}/${encodeURIComponent(fname)}` : null;

  return null;
}

/**
 * @param {string} href
 * @param {{ baseUrl?: string, jobId?: string|null, scanDir?: string, packId?: string|null }} ctx
 */
export async function openChatDownload(href, ctx = {}) {
  const base = String(ctx.baseUrl || "").replace(/\/$/, "").replace(/\/ui$/i, "");
  const direct = resolveChatDownloadHref(href, ctx);
  const fname = String(href || "")
    .trim()
    .replace(/^.*[/\\]/, "");

  if (direct) {
    const a = document.createElement("a");
    a.href = direct;
    a.target = "_blank";
    a.rel = "noopener";
    if (fname) a.download = fname;
    document.body.appendChild(a);
    a.click();
    a.remove();
    return;
  }

  const params = new URLSearchParams({ filename: fname });
  if (ctx.jobId) params.set("job_id", String(ctx.jobId));
  if (ctx.scanDir) params.set("scan_dir", String(ctx.scanDir));
  if (ctx.packId) params.set("pack_id", String(ctx.packId));
  const r = await fetch(`${base}/api/workspace/resolve-download?${params.toString()}`, { cache: "no-store" });
  let data = {};
  try {
    data = await r.json();
  } catch {
    /* ignore */
  }
  if (!r.ok) {
    const detail = typeof data.detail === "string" ? data.detail : `无法下载 ${fname}`;
    throw new Error(detail);
  }
  const url = data.url ? (String(data.url).startsWith("http") ? data.url : `${base}${data.url}`) : null;
  if (!url) throw new Error(`无法解析下载链接: ${href}`);

  const a = document.createElement("a");
  a.href = url;
  a.target = "_blank";
  a.rel = "noopener";
  a.download = fname || "";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

/**
 * @param {MouseEvent} e
 * @param {{ baseUrl?: string, jobId?: string|null, scanDir?: string, packId?: string|null }} ctx
 */
export async function handleChatDownloadClick(e, ctx = {}) {
  const a = e.target.closest?.("a[href]");
  if (!a) return false;
  const href = a.getAttribute("data-dl-href") || a.getAttribute("href");
  if (!isLikelyDownloadHref(href)) return false;

  e.preventDefault();
  e.stopPropagation();
  await openChatDownload(href, ctx);
  return true;
}
