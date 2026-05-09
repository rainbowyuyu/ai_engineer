/**
 * 设计域预览：按需加载 highlight.js，将源码高亮为 HTML（JSON / Python 等）。
 * 失败时回退为转义后的纯文本 <pre>。
 */

export function escHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function extOfPath(name) {
  const i = String(name || "").lastIndexOf(".");
  return i >= 0 ? String(name).slice(i).toLowerCase() : "";
}

/** @type {any} */
let _hljs = null;

async function ensureHljs() {
  if (_hljs) return _hljs;
  try {
    const mod = await import("https://cdn.jsdelivr.net/npm/highlight.js@11.10.0/+esm");
    _hljs = mod.default || mod;
  } catch {
    _hljs = null;
  }
  return _hljs;
}

/**
 * @param {string} ext
 * @returns {string | null} highlight.js 语言 id
 */
export function extToHljsLang(ext) {
  const e = String(ext || "").toLowerCase();
  const map = {
    ".json": "json",
    ".py": "python",
    ".pyw": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".jsx": "javascript",
    ".html": "xml",
    ".htm": "xml",
    ".xml": "xml",
    ".svg": "xml",
    ".css": "css",
    ".scss": "scss",
    ".less": "less",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".ini": "ini",
    ".toml": "toml",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".h": "c",
    ".c": "c",
    ".sql": "sql",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".swift": "swift",
    ".r": "r",
    ".dockerfile": "dockerfile",
    ".cmake": "cmake",
    ".make": "makefile",
    ".mk": "makefile",
    ".vue": "xml",
  };
  return map[e] ?? null;
}

/**
 * @param {string} ext
 * @returns {boolean} 无 highlight 语言时仍以等宽块预览（如 INP / 日志）
 */
export function extWantsPlainPreview(ext) {
  const e = String(ext || "").toLowerCase();
  return e === ".txt" || e === ".log" || e === ".inp" || e === ".geo" || e === ".msh" || e === ".dat";
}

/**
 * @param {string} relPath
 * @returns {boolean}
 */
export function pathWantsRichPreview(relPath) {
  const ext = extOfPath(relPath);
  return Boolean(extToHljsLang(ext)) || extWantsPlainPreview(ext);
}

function prettifyJsonIfPossible(src) {
  const t = String(src ?? "").trim();
  if (!t) return String(src ?? "");
  try {
    return `${JSON.stringify(JSON.parse(t), null, 2)}\n`;
  } catch {
    return String(src ?? "");
  }
}

/**
 * @param {string} code
 * @param {string} lang
 * @returns {Promise<string>} 片段 HTML（不含外层 chrome）
 */
export async function highlightCodeToHtml(code, lang) {
  const raw = lang === "json" ? prettifyJsonIfPossible(code) : String(code ?? "");
  const hljs = await ensureHljs();
  if (!hljs) {
    return `<pre class="ddIdeHljsPre ddIdeHljsPre--plain"><code>${escHtml(raw)}</code></pre>`;
  }
  const L = String(lang || "").trim() || "plaintext";
  try {
    if (hljs.getLanguage?.(L)) {
      const { value } = hljs.highlight(raw, { language: L, ignoreIllegals: true });
      return `<pre class="hljs ddIdeHljsPre"><code class="language-${escHtml(L)}">${value}</code></pre>`;
    }
  } catch {
    /* fall through */
  }
  try {
    const { value } = hljs.highlightAuto(raw);
    return `<pre class="hljs ddIdeHljsPre"><code>${value}</code></pre>`;
  } catch {
    return `<pre class="ddIdeHljsPre ddIdeHljsPre--plain"><code>${escHtml(raw)}</code></pre>`;
  }
}

export function plainCodeBlockHtml(code) {
  return `<pre class="ddIdeHljsPre ddIdeHljsPre--plain"><code>${escHtml(code)}</code></pre>`;
}

/**
 * @param {string} relPath
 * @param {string} lang
 * @param {string} innerHtml 来自 {@link highlightCodeToHtml} 或 {@link plainCodeBlockHtml}
 */
export function wrapCodePreviewChrome(relPath, lang, innerHtml) {
  const lp = String(lang || "code").trim();
  return (
    `<header class="ddIdeCodePreviewHd">` +
    `<span class="ddIdeCodePreviewBadge">${escHtml(lp)}</span>` +
    `<span class="ddIdeCodePreviewRel mono">${escHtml(relPath)}</span>` +
    `</header>` +
    `<div class="ddIdeCodePreviewBody">${innerHtml}</div>`
  );
}
