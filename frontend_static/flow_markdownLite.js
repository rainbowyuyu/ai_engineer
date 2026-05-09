/**
 * 轻量 Markdown → HTML（设计域 / 智能体面板用，无外部依赖）。
 * 仅支持常见子集：标题、列表、粗体、行内代码、围栏代码块、换行。
 */

function escHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/**
 * @param {string} raw
 * @returns {string}
 */
export function markdownLiteToHtml(raw) {
  let t = String(raw ?? "");
  if (!t.trim()) return "";

  const codeBlocks = [];
  t = t.replace(/```([\s\S]*?)```/g, (_, code) => {
    const i = codeBlocks.length;
    codeBlocks.push(`<pre class="mdLitePre"><code>${escHtml(code.replace(/^\n/, "").replace(/\n$/, ""))}</code></pre>`);
    return `\0CODEBLOCK${i}\0`;
  });

  const lines = t.split(/\r?\n/);
  const out = [];
  let inUl = false;

  const flushUl = () => {
    if (inUl) {
      out.push("</ul>");
      inUl = false;
    }
  };

  for (const line of lines) {
    const h3 = line.match(/^###\s+(.+)$/);
    const h2 = line.match(/^##\s+(.+)$/);
    const h1 = line.match(/^#\s+(.+)$/);
    const li = line.match(/^\s*[-*]\s+(.+)$/);
    if (h1 || h2 || h3) {
      flushUl();
      const hx = h3 ? 3 : h2 ? 2 : 1;
      const c = escHtml((h3 || h2 || h1)[1].trim());
      out.push(`<h${hx} class="mdLiteH${hx}">${inlineMd(c)}</h${hx}>`);
      continue;
    }
    if (li) {
      if (!inUl) {
        out.push('<ul class="mdLiteUl">');
        inUl = true;
      }
      out.push(`<li class="mdLiteLi">${inlineMd(escHtml(li[1].trim()))}</li>`);
      continue;
    }
    flushUl();
    if (!line.trim()) {
      out.push("<br/>");
      continue;
    }
    out.push(`<p class="mdLiteP">${inlineMd(escHtml(line))}</p>`);
  }
  flushUl();

  let html = out.join("");
  html = html.replace(/\0CODEBLOCK(\d+)\0/g, (_, i) => codeBlocks[Number(i)] || "");
  return html;
}

/**
 * @param {string} s 已 escHtml 的纯文本
 */
function inlineMd(s) {
  return s
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code class=\"mdLiteCode\">$1</code>");
}
