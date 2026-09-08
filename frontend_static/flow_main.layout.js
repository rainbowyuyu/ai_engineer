/**
 * @file Landing layout / chat bubbles
 */
import { handleChatDownloadClick, resolveChatDownloadHref } from "./flow_main.download.js";

export function createLayoutManager(deps) {
  const { refs, state, normalizedBaseUrl, getDownloadContext } = deps;
  const railStops = [refs.railStop1, refs.railStop2, refs.railStop3, refs.railStop4];
  const railConns = [refs.railConn1, refs.railConn2, refs.railConn3];

  function ensureRailLabels() {
    railStops.forEach((el) => {
      if (!el) return;
      if (!el.dataset.label) {
        el.dataset.label = el.getAttribute("data-rail-label") || el.textContent || "";
      }
    });
  }

  function updateRailVisibility(activeIndex = 1, conn = 0) {
    ensureRailLabels();
    railStops.forEach((el, i) => {
      if (!el) return;
      const idx = i + 1;
      const isDone = idx < activeIndex;
      const isActive = idx === activeIndex;
      el.classList.toggle("active", isActive);
      el.classList.toggle("done", isDone);
      const reveal = isDone || isActive;
      el.classList.toggle("pending", !reveal);
      el.textContent = reveal ? (el.dataset.label || "") : "";
    });
    railConns.forEach((el, i) => {
      if (!el) return;
      el.classList.toggle("active", i + 1 <= (conn || 0));
    });
  }

  function escapeHtml(s) {
    return String(s || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;");
  }

  function landingAttachmentExtLabel(fileName) {
    const s = String(fileName || "");
    const i = s.lastIndexOf(".");
    if (i <= 0 || i >= s.length - 1) return "文件";
    return s.slice(i + 1).toUpperCase().slice(0, 12);
  }

  function landingAttachmentMetaLine(fileName, fileSizeBytes) {
    const ext = landingAttachmentExtLabel(fileName);
    const n = Number(fileSizeBytes);
    if (!Number.isFinite(n) || n < 0) return ext;
    let sz = "";
    if (n < 1024) sz = `${Math.round(n)} B`;
    else if (n < 1024 * 1024) {
      const kb = n / 1024;
      sz = `${kb < 10 ? kb.toFixed(2) : kb.toFixed(1)} KB`;
    } else sz = `${(n / (1024 * 1024)).toFixed(1)} MB`;
    return `${ext} ${sz}`;
  }

  /** Markdown：标题、列表、行内加粗/代码、``` 围栏代码块；流式时用不完整块也可接受 */
  function renderMd(md) {
    const parts = String(md || "").split("```");
    let html = "";
    for (let i = 0; i < parts.length; i++) {
      if (i % 2 === 0) {
        html += renderMdParagraph(parts[i]);
      } else {
        const rawFence = parts[i];
        const nl = rawFence.indexOf("\n");
        const code = nl === -1 ? rawFence : rawFence.slice(nl + 1);
        const esc = escapeHtml(code.replace(/\n+$/, ""));
        html += `<pre class="mdFence" tabindex="0"><code class="mdFenceCode">${esc}</code></pre>`;
      }
    }
    return html;
  }

  function closeList(listKind, out) {
    if (listKind === "ul") return `${out}</ul>`;
    if (listKind === "ol") return `${out}</ol>`;
    return out;
  }

  function renderMdParagraph(block) {
    const lines = String(block || "").split("\n");
    let out = "";
    /** @type {"ul"|"ol"|null} */
    let listKind = null;
    const inline = (text) =>
      escapeHtml(text)
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/`([^`]+)`/g, "<code>$1</code>")
        .replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, label, href) => {
          const ctx = {
            baseUrl: typeof normalizedBaseUrl === "function" ? normalizedBaseUrl() : "",
            jobId: state?.jobId || null,
            scanDir: state?.uploadedSourceDir || "",
            packId: state?.lastDeliverablesPackId || null,
            ...(typeof getDownloadContext === "function" ? getDownloadContext() : {}),
          };
          const resolved = resolveChatDownloadHref(href, ctx) || href;
          const safeHref = escapeHtml(resolved);
          const safeLabel = escapeHtml(label);
          return `<a class="mdDownloadLink" href="${safeHref}" data-dl-href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">${safeLabel}</a>`;
        });
    const bulletItem = (line) => line.startsWith("- ") || line.startsWith("* ");
    const bulletBody = (line) => (line.startsWith("- ") ? line.slice(2) : line.slice(2));
    const orderedMatch = (line) => line.match(/^(\d+)\.\s(.*)$/);

    /** GFM 风格：表头行 + 对齐分隔行 + 至少一行数据 */
    function splitTableRow(s) {
      const raw = String(s || "").trim();
      if (!raw.includes("|")) return null;
      const parts = raw.split("|").map((x) => x.trim());
      const cells = [];
      for (let p = 0; p < parts.length; p++) {
        if (p === 0 && parts[p] === "") continue;
        if (p === parts.length - 1 && parts[p] === "") continue;
        cells.push(parts[p]);
      }
      return cells.length >= 2 ? cells : null;
    }
    function isSeparatorCells(cells) {
      return cells.every((c) => {
        const x = String(c).replace(/\s/g, "");
        return /^:?-{3,}:?$/.test(x);
      });
    }
    function tryParseTableAt(i) {
      const c0 = splitTableRow(lines[i] || "");
      if (!c0) return null;
      const c1 = splitTableRow(lines[i + 1] || "");
      if (!c1 || c1.length !== c0.length || !isSeparatorCells(c1)) return null;
      const aligns = c1.map((c) => {
        const x = String(c).replace(/\s/g, "");
        if (x.startsWith(":") && x.endsWith(":")) return "center";
        if (x.endsWith(":")) return "right";
        return "left";
      });
      let end = i + 2;
      const body = [];
      while (end < lines.length) {
        const t = String(lines[end] || "").trim();
        if (!t) break;
        const row = splitTableRow(lines[end]);
        if (!row || row.length !== c0.length) break;
        body.push(row);
        end += 1;
      }
      if (!body.length) return null;
      let html = '<div class="mdTableWrap"><table class="mdTable"><thead><tr>';
      c0.forEach((h, j) => {
        html += `<th style="text-align:${aligns[j] || "left"}">${inline(h)}</th>`;
      });
      html += "</tr></thead><tbody>";
      for (const row of body) {
        html += "<tr>";
        row.forEach((cell, j) => {
          html += `<td style="text-align:${aligns[j] || "left"}">${inline(cell)}</td>`;
        });
        html += "</tr>";
      }
      html += "</tbody></table></div>";
      return { html, nextIndex: end };
    }

    for (let i = 0; i < lines.length; i++) {
      const raw = lines[i];
      const line = raw.trimEnd();
      const trimmed = line.trim();

      const tbl = tryParseTableAt(i);
      if (tbl) {
        if (listKind) {
          out = closeList(listKind, out);
          listKind = null;
        }
        out += tbl.html;
        i = tbl.nextIndex - 1;
        continue;
      }

      if (!trimmed) {
        if (listKind) {
          out = closeList(listKind, out);
          listKind = null;
        }
        out += '<div class="mdGap"></div>';
        continue;
      }
      /* 必须按 # 数量从多到少匹配，否则 #### 会被当成 ### */
      if (line.startsWith("#### ")) {
        if (listKind) {
          out = closeList(listKind, out);
          listKind = null;
        }
        out += `<h4 class="mdHeading mdHeading--4">${inline(line.slice(5))}</h4>`;
        continue;
      }
      if (line.startsWith("### ")) {
        if (listKind) {
          out = closeList(listKind, out);
          listKind = null;
        }
        out += `<h3 class="mdHeading mdHeading--3">${inline(line.slice(4))}</h3>`;
        continue;
      }
      if (line.startsWith("## ")) {
        if (listKind) {
          out = closeList(listKind, out);
          listKind = null;
        }
        out += `<h2 class="mdHeading mdHeading--2">${inline(line.slice(3))}</h2>`;
        continue;
      }
      if (line.startsWith("# ")) {
        if (listKind) {
          out = closeList(listKind, out);
          listKind = null;
        }
        out += `<h2 class="mdHeading mdHeading--1">${inline(line.slice(2))}</h2>`;
        continue;
      }
      if (/^-{3,}\s*$/.test(trimmed) || /^\*{3,}\s*$/.test(trimmed) || /^_{3,}\s*$/.test(trimmed) || /^=+\s*$/.test(trimmed)) {
        if (listKind) {
          out = closeList(listKind, out);
          listKind = null;
        }
        out += '<hr class="mdHr" />';
        continue;
      }
      const om = orderedMatch(trimmed);
      if (om) {
        if (listKind !== "ol") {
          if (listKind) out = closeList(listKind, out);
          out += "<ol>";
          listKind = "ol";
        }
        out += `<li>${inline(om[2])}</li>`;
        continue;
      }
      if (bulletItem(line)) {
        if (listKind !== "ul") {
          if (listKind) out = closeList(listKind, out);
          out += "<ul>";
          listKind = "ul";
        }
        out += `<li>${inline(bulletBody(line))}</li>`;
        continue;
      }
      if (listKind) {
        out = closeList(listKind, out);
        listKind = null;
      }
      out += `<p>${inline(line)}</p>`;
    }
    if (listKind) out = closeList(listKind, out);
    return out;
  }

  function setStep(step) {
    state.currentStep = step;
    if (refs.flowMain) refs.flowMain.setAttribute("data-step", String(step));
    const hide = (el) => {
      if (!el) return;
      el.classList.remove("stageVisible", "stageVisibleGrid");
      el.style.display = "none";
    };
    [refs.panelStep1, refs.panelStep2, refs.panelStep3A, refs.panelStep3B, refs.panelStep4, refs.flowStageRight].forEach(hide);

    // 步骤 5/6 已拆为独立子流程卡片；flow 面板仅展示拓扑 1–4
    const panelStep = step >= 4 ? 4 : step;
    if (panelStep === 1) {
      refs.panelStep1?.classList.add("stageVisible");
      if (refs.flowStageRight) refs.flowStageRight.style.display = "none";
    } else if (panelStep === 2) {
      refs.flowStageRight?.classList.add("stageVisibleGrid");
      refs.panelStep2?.classList.add("stageVisible");
    } else if (panelStep === 3) {
      refs.flowStageRight?.classList.add("stageVisibleGrid");
      refs.panelStep3A?.classList.add("stageVisible");
      refs.panelStep3B?.classList.add("stageVisible");
    } else {
      refs.flowStageRight?.classList.add("stageVisibleGrid");
      refs.panelStep4?.classList.add("stageVisible");
    }

    const mark = (el, idx) => {
      if (!el) return;
      if (idx < step) {
        el.style.background = "rgba(22,163,74,.10)";
        el.style.borderColor = "rgba(22,163,74,.4)";
        el.style.color = "#15803d";
      } else if (idx === step) {
        el.style.background = "rgba(43,93,247,.10)";
        el.style.borderColor = "rgba(43,93,247,.4)";
        el.style.color = "#1d4ed8";
      } else {
        el.style.background = "rgba(255,255,255,.65)";
        el.style.borderColor = "rgba(15,23,42,.12)";
        el.style.color = "#64748b";
      }
    };
    mark(refs.flowStep1, 1);
    mark(refs.flowStep2, 2);
    mark(refs.flowStep3, 3);
    mark(refs.flowStep4, 4);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function addBubble(role, text) {
    if (!refs.chatEl) return;
    const b = document.createElement("div");
    b.className = `bubble ${role}`;
    b.textContent = text;
    refs.chatEl.appendChild(b);
    refs.chatEl.scrollTop = refs.chatEl.scrollHeight;
  }

  let landingBubbleActionsWired = false;

  function wireLandingBubbleActionsOnce() {
    if (landingBubbleActionsWired || !refs.chatLanding) return;
    landingBubbleActionsWired = true;
    refs.chatLanding.addEventListener("click", async (e) => {
      const mdLink = e.target.closest?.(".bubbleText--md a[href], .mdTable a[href]");
      if (mdLink && refs.chatLanding.contains(mdLink)) {
        const ctx = {
          baseUrl: typeof normalizedBaseUrl === "function" ? normalizedBaseUrl() : "",
          jobId: state?.jobId || null,
          scanDir: state?.uploadedSourceDir || "",
          packId: state?.lastDeliverablesPackId || null,
          ...(typeof getDownloadContext === "function" ? getDownloadContext() : {}),
        };
        try {
          const handled = await handleChatDownloadClick(e, ctx);
          if (handled) return;
        } catch (err) {
          addLandingBubble("agent", `下载失败：${err?.message || err}`);
          return;
        }
      }
      const btn = e.target.closest("[data-bubble-action]");
      if (!btn || !refs.chatLanding.contains(btn)) return;
      const turn = btn.closest(".landingTurn");
      const raw = turn?.dataset?.rawText != null ? String(turn.dataset.rawText) : "";
      const action = btn.getAttribute("data-bubble-action");
      if (action === "copy") {
        try {
          await navigator.clipboard.writeText(raw);
          const prev = btn.getAttribute("aria-label");
          btn.setAttribute("aria-label", "已复制");
          setTimeout(() => btn.setAttribute("aria-label", prev || "复制"), 1600);
        } catch {
          try {
            const ta = document.createElement("textarea");
            ta.value = raw;
            ta.style.position = "fixed";
            ta.style.left = "-9999px";
            document.body.appendChild(ta);
            ta.select();
            document.execCommand("copy");
            ta.remove();
          } catch {
            /* ignore */
          }
        }
        return;
      }
      if (action === "share") {
        const title = "AI Engineer";
        try {
          if (navigator.share) {
            await navigator.share({ title, text: raw });
          } else {
            await navigator.clipboard.writeText(raw);
            const prev = btn.getAttribute("aria-label");
            btn.setAttribute("aria-label", "已复制到剪贴板");
            setTimeout(() => btn.setAttribute("aria-label", prev || "分享"), 1600);
          }
        } catch (err) {
          if (err && err.name === "AbortError") return;
          try {
            await navigator.clipboard.writeText(raw);
          } catch {
            /* ignore */
          }
        }
        return;
      }
      if (action === "regenerate") {
        if (!turn?.classList.contains("landingTurn--agent")) return;
        refs.chatLanding.dispatchEvent(
          new CustomEvent("beso:landing-regenerate", { bubbles: true, detail: { raw } }),
        );
        return;
      }
      if (action === "like" || action === "dislike") {
        const bar = btn.closest(".bubbleActions");
        if (!bar) return;
        const likeBtn = bar.querySelector('[data-bubble-action="like"]');
        const dislikeBtn = bar.querySelector('[data-bubble-action="dislike"]');
        const partner = action === "like" ? dislikeBtn : likeBtn;
        const turningOn = btn.getAttribute("aria-pressed") !== "true";
        if (partner) {
          partner.setAttribute("aria-pressed", "false");
          partner.classList.remove("bubbleIconBtn--on");
        }
        if (turningOn) {
          btn.setAttribute("aria-pressed", "true");
          btn.classList.add("bubbleIconBtn--on");
        } else {
          btn.setAttribute("aria-pressed", "false");
          btn.classList.remove("bubbleIconBtn--on");
        }
        return;
      }
    });
  }

  function bubbleToolbarHtml() {
    return `
      <div class="bubbleActions" role="toolbar" aria-label="消息操作">
        <button type="button" class="bubbleIconBtn" data-bubble-action="copy" title="复制" aria-label="复制">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
            <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
          </svg>
        </button>
        <button type="button" class="bubbleIconBtn" data-bubble-action="share" title="分享" aria-label="分享">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M4 12v8a2 2 0 002 2h12a2 2 0 002-2v-8M16 6l-4-4-4 4M12 2v14"/>
          </svg>
        </button>
        <button type="button" class="bubbleIconBtn" data-bubble-action="regenerate" title="重新生成" aria-label="重新生成">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
            <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/>
            <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/>
            <path d="M3 16v4h4M21 8V4h-4"/>
          </svg>
        </button>
        <button type="button" class="bubbleIconBtn" data-bubble-action="like" title="有用" aria-label="有用" aria-pressed="false">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M7 10v12"/>
            <path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-6a2 2 0 0 1 2-2h2.9a2 2 0 0 0 1.69-.9l1.65-3.8A2 2 0 0 1 10.4 6H13"/>
          </svg>
        </button>
        <button type="button" class="bubbleIconBtn" data-bubble-action="dislike" title="需改进" aria-label="需改进" aria-pressed="false">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M17 14V2"/>
            <path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2h-2.9a2 2 0 0 0-1.69.9l-1.65 3.8A2 2 0 0 1 13.6 18H11"/>
          </svg>
        </button>
      </div>
    `;
  }

  /**
   * @param {"user"|"agent"} role
   * @param {string} text
   * @param {{ format?: "plain"|"md"|"html"|"checklist"; withToolbar?: boolean; debut?: boolean; checklistHtml?: string }} [opts]
   */
  function addLandingBubble(role, text, opts = {}) {
    if (!refs.chatLanding) return;
    wireLandingBubbleActionsOnce();
    const raw = String(text ?? "");
    const wrap = document.createElement("div");
    wrap.className = `landingTurn landingTurn--${role}`;
    if (opts.debut) wrap.classList.add("landingTurn--debut");
    wrap.dataset.rawText = raw;
    const bubble = document.createElement("div");
    bubble.className = `bubble ${role}`;
    const inner = document.createElement("div");
    const useChecklist = role === "agent" && opts.format === "checklist" && opts.checklistHtml;
    const useHtml = opts.format === "html";
    const useMd = (role === "agent" || role === "user") && opts.format === "md";
    inner.className = useChecklist
      ? "bubbleText bubbleText--checklist"
      : useHtml
        ? "bubbleText bubbleText--html"
        : useMd
          ? "bubbleText bubbleText--md"
          : "bubbleText";
    if (useChecklist) {
      inner.innerHTML = String(opts.checklistHtml || "");
    } else if (useHtml) {
      inner.innerHTML = raw;
    } else if (useMd) {
      inner.innerHTML = renderMd(raw);
    } else {
      inner.textContent = raw;
    }
    bubble.appendChild(inner);
    const att = role === "user" && opts.attachment && String(opts.attachment.file_name || opts.attachment.name || "").trim();
    if (att) {
      const fn = String(opts.attachment.file_name || opts.attachment.name || "").trim();
      const card = document.createElement("div");
      card.className = "landingFileCard landingFileCard--sent";
      card.setAttribute("role", "group");
      card.setAttribute("aria-label", `附件 ${fn}`);
      const iconWrap = document.createElement("div");
      iconWrap.className = "landingFileCardIcon";
      iconWrap.setAttribute("aria-hidden", "true");
      iconWrap.innerHTML = `
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z" stroke="currentColor" stroke-width="1.75" stroke-linejoin="round"/>
          <path d="M14 2v6h6" stroke="currentColor" stroke-width="1.75" stroke-linejoin="round"/>
          <path d="M8.5 14.5h7M8.5 17.5h5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        </svg>`;
      const body = document.createElement("div");
      body.className = "landingFileCardBody";
      const titleEl = document.createElement("span");
      titleEl.className = "landingFileCardTitle";
      titleEl.textContent = fn;
      const metaEl = document.createElement("span");
      metaEl.className = "landingFileCardMeta";
      metaEl.textContent = landingAttachmentMetaLine(fn, opts.attachment.file_size);
      body.appendChild(titleEl);
      body.appendChild(metaEl);
      card.appendChild(iconWrap);
      card.appendChild(body);
      wrap.appendChild(card);
    }
    wrap.appendChild(bubble);
    const withToolbar = opts.withToolbar !== false;
    if (withToolbar && raw.trim()) {
      const tmp = document.createElement("div");
      tmp.innerHTML = bubbleToolbarHtml().trim();
      const barEl = tmp.firstElementChild;
      if (barEl) wrap.appendChild(barEl);
    }
    refs.chatLanding.appendChild(wrap);
    refs.chatLanding.scrollTop = refs.chatLanding.scrollHeight;
  }

  /** 大模型请求中：高级「思考中」占位，收到流式首包后可 reuseWrap 平滑升级为输出气泡 */
  function addLandingThinking() {
    if (!refs.chatLanding) return null;
    const wrap = document.createElement("div");
    wrap.className = "landingTurn landingTurn--agent landingTurn--thinking";
    wrap.setAttribute("aria-live", "polite");
    wrap.setAttribute("aria-busy", "true");
    wrap.classList.add("landingTurn--thinkingIn");
    wrap.innerHTML = `
      <div class="bubble agent landingThinkingBubble">
        <div class="landingThinkingTop">
          <span class="landingThinkingOrb" aria-hidden="true"></span>
          <div class="landingThinkingTitles">
            <span class="landingThinkingBrand">AI Engineer</span>
            <span class="landingThinkingSub">AI 工程助手 · 连接大模型与仿真上下文</span>
          </div>
        </div>
        <div class="landingThinkingHints" aria-hidden="true">
          <span class="landingThinkingHint">正在建立安全连接…</span>
          <span class="landingThinkingHint">对齐您的工程语境与术语…</span>
          <span class="landingThinkingHint">组织专业、可执行的回复…</span>
        </div>
        <p class="landingThinkingPrimary">正在思考，请稍候</p>
        <div class="landingThinkingTrack" aria-hidden="true"><span class="landingThinkingTrackFill"></span></div>
        <div class="landingThinkingPulse" aria-hidden="true"><i></i><i></i><i></i></div>
      </div>`;
    refs.chatLanding.appendChild(wrap);
    refs.chatLanding.scrollTop = refs.chatLanding.scrollHeight;
    return wrap;
  }

  function removeLandingThinking(el) {
    try {
      el?.remove();
    } catch {
      /* ignore */
    }
  }

  /** @deprecated 使用 addLandingThinking */
  const addLandingTyping = addLandingThinking;
  /** @deprecated 使用 removeLandingThinking */
  const removeLandingTyping = removeLandingThinking;

  /** 流式助手气泡：appendDelta 追加 token，finalize 结束并挂载复制条；opts.reuseWrap 复用「思考中」同一卡片以无缝衔接 */
  function beginLandingAgentStream(opts = {}) {
    const reuseWrap = opts && opts.reuseWrap;
    wireLandingBubbleActionsOnce();
    if (!refs.chatLanding) return null;
    let wrap;
    if (reuseWrap && reuseWrap.parentNode === refs.chatLanding) {
      wrap = reuseWrap;
      wrap.classList.remove("landingTurn--thinking", "landingTurn--thinkingIn");
      wrap.classList.add("landingTurn--streaming");
      wrap.removeAttribute("aria-busy");
      wrap.innerHTML = "";
    } else if (reuseWrap) {
      return null;
    } else {
      wrap = document.createElement("div");
      wrap.className = "landingTurn landingTurn--agent landingTurn--streaming";
      refs.chatLanding.appendChild(wrap);
    }
    const bubble = document.createElement("div");
    bubble.className = "bubble agent";
    const inner = document.createElement("div");
    inner.className = "bubbleText bubbleText--md landingStreamBody";
    bubble.appendChild(inner);
    wrap.appendChild(bubble);
    if (!reuseWrap) refs.chatLanding.scrollTop = refs.chatLanding.scrollHeight;
    else refs.chatLanding.scrollTop = refs.chatLanding.scrollHeight;
    let buf = "";
    /** 流式阶段避免每 token 跑 renderMd（重排 + 解析卡顿），用纯文本 + rAF 合并绘制；结束时再 renderMd。 */
    inner.className = "bubbleText landingStreamBody landingStreamBodyLive";
    /** @type {number|null} */
    let rafPaint = null;
    /** @type {ReturnType<typeof setTimeout>|null} */
    let motionFlushTimer = null;
    /** @type {number|null} */
    let rafScroll = null;
    const reduceMotion =
      typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;
    const paintPlain = () => {
      inner.textContent = buf;
      if (rafScroll != null) cancelAnimationFrame(rafScroll);
      rafScroll = requestAnimationFrame(() => {
        rafScroll = null;
        refs.chatLanding.scrollTop = refs.chatLanding.scrollHeight;
      });
    };
    const schedulePaint = () => {
      if (reduceMotion) {
        if (motionFlushTimer != null) return;
        motionFlushTimer = window.setTimeout(() => {
          motionFlushTimer = null;
          paintPlain();
        }, 140);
        return;
      }
      if (rafPaint != null) return;
      rafPaint = requestAnimationFrame(() => {
        rafPaint = null;
        paintPlain();
      });
    };
    function appendDelta(chunk) {
      buf += String(chunk || "");
      schedulePaint();
    }
    function finalize(fullText) {
      if (motionFlushTimer != null) {
        clearTimeout(motionFlushTimer);
        motionFlushTimer = null;
      }
      if (rafPaint != null) {
        cancelAnimationFrame(rafPaint);
        rafPaint = null;
      }
      if (rafScroll != null) {
        cancelAnimationFrame(rafScroll);
        rafScroll = null;
      }
      buf = String(fullText ?? buf);
      wrap.classList.remove("landingTurn--streaming");
      wrap.dataset.rawText = buf;
      inner.className = "bubbleText bubbleText--md landingStreamBody";
      inner.innerHTML = renderMd(buf);
      const tmp = document.createElement("div");
      tmp.innerHTML = bubbleToolbarHtml().trim();
      const barEl = tmp.firstElementChild;
      if (barEl && buf.trim()) wrap.appendChild(barEl);
      refs.chatLanding.scrollTop = refs.chatLanding.scrollHeight;
    }
    return { wrap, appendDelta, finalize };
  }

  /** 对话内可点击子流程卡片（进度条可在外部用 sync 更新） */
  function addLandingWorkflowCard(model) {
    wireLandingBubbleActionsOnce();
    if (!refs.chatLanding) return null;
    const kindRaw = String(model.kind || "orchestrate").toLowerCase();
    const kind =
      kindRaw === "design_domain"
        ? "design_domain"
        : kindRaw === "restruction" || kindRaw === "analysis"
          ? "restruction"
          : kindRaw === "validation" || kindRaw === "review" || kindRaw === "ai_review"
            ? "validation"
            : "orchestrate";
    const title =
      model.title ||
      (kind === "design_domain"
        ? "设计域（OC4）"
        : kind === "restruction"
          ? "尺寸时域分析"
          : kind === "validation"
            ? "AI Review"
            : "构型优化编排");
    const step = Number(model.step);
    const progress = Number(model.progress);
    const statusLabel = String(model.status || "进行中");
    const total =
      kind === "orchestrate" ? 4 : kind === "restruction" ? 2 : kind === "validation" ? 1 : 0;
    const stepClamped = Number.isFinite(step) && step >= 1 && total > 0 ? Math.min(total, step) : 0;
    const stepTxt =
      kind === "validation"
        ? stepClamped
          ? "评审"
          : ""
        : kind === "restruction"
          ? stepClamped
            ? `阶段 ${stepClamped}/${total}`
            : ""
          : stepClamped
            ? `步骤 ${stepClamped}/${total}`
            : "";
    const pct = Number.isFinite(progress) ? Math.max(0, Math.min(100, progress)) : 0;
    const tid = String(model.taskId || "").trim();
    const continueTo = String(model.continueTo || "").trim();
    const continueLabel = String(model.continueLabel || "").trim();
    let phaseRail = "";
    if (kind === "orchestrate") {
      phaseRail = `<div class="landingWorkflowPhases" aria-hidden="true">
            ${[1, 2, 3, 4]
              .map((i) => {
                const labels = ["搜", "码", "预", "汇"];
                const cls =
                  stepClamped > i ? "is-done" : stepClamped === i ? "is-current" : "is-todo";
                return `<span class="landingWorkflowPhase ${cls}" title="步骤 ${i}">${labels[i - 1]}</span>`;
              })
              .join("")}
          </div>`;
    } else if (kind === "restruction") {
      phaseRail = `<div class="landingWorkflowPhases" aria-hidden="true">
            ${[1, 2]
              .map((i) => {
                const labels = ["静力", "时域"];
                const cls =
                  stepClamped > i ? "is-done" : stepClamped === i ? "is-current" : "is-todo";
                return `<span class="landingWorkflowPhase ${cls}" title="${labels[i - 1]}">${labels[i - 1]}</span>`;
              })
              .join("")}
          </div>`;
    } else if (kind === "validation") {
      const cls = stepClamped >= 1 || pct >= 50 ? "is-current" : "is-todo";
      const doneCls = pct >= 100 || String(statusLabel).includes("完成") ? "is-done" : cls;
      phaseRail = `<div class="landingWorkflowPhases landingWorkflowPhases--review" aria-hidden="true">
            <span class="landingWorkflowPhase ${doneCls}" title="AI Review">
              <svg class="landingWorkflowPhaseIcon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="1"/><path d="M9 13l2.2 2.2L16 10.4"/></svg>
              评审
            </span>
          </div>`;
    }
    const hint =
      kind === "design_domain"
        ? "点击返回设计域工作台"
        : kind === "restruction"
          ? "点击进入尺寸时域分析"
          : kind === "validation"
            ? "点击进入 AI Review"
            : "点击进入构型优化编排 / 拓扑流程";
    const actionsHtml =
      continueTo && continueLabel
        ? `<div class="landingWorkflowCardActions">
            <button type="button" class="landingWorkflowContinueBtn" data-workflow-continue="${escapeHtml(continueTo)}" ${
              tid ? `data-task-id="${escapeHtml(tid)}"` : ""
            }>${escapeHtml(continueLabel)}</button>
          </div>`
        : "";
    const wrap = document.createElement("div");
    wrap.className = "landingTurn landingTurn--card";
    wrap.dataset.cardKind = kind;
    wrap.innerHTML = `
      <button type="button" class="landingWorkflowCard" data-workflow-jump="${kind}" ${tid ? `data-task-id="${escapeHtml(tid)}"` : ""} title="在右侧主区域继续：${escapeHtml(title)}">
        <div class="landingWorkflowCardHd">${escapeHtml(title)}</div>
        <div class="landingWorkflowCardMeta">
          <span class="pill landingWorkflowCardStatus">${escapeHtml(statusLabel)}</span>
          ${stepTxt ? `<span class="landingWorkflowCardStep">${escapeHtml(stepTxt)}</span>` : `<span class="landingWorkflowCardStep"></span>`}
        </div>
        ${phaseRail}
        <div class="landingWorkflowBar" aria-hidden="true"><span class="landingWorkflowBarFill" style="width:${pct}%"></span></div>
        <div class="landingWorkflowCardHint">${escapeHtml(hint)}</div>
      </button>
      ${actionsHtml}
    `;
    refs.chatLanding.appendChild(wrap);
    refs.chatLanding.scrollTop = refs.chatLanding.scrollHeight;
    return wrap.querySelector(".landingWorkflowCard");
  }

  /** 更新已有子流程卡片的状态 / 进度 / 继续按钮（不重复插入） */
  function updateLandingWorkflowCard(kind, patch = {}) {
    if (!refs.chatLanding) return null;
    const k = String(kind || "").toLowerCase();
    const tid = String(patch.taskId || "").trim();
    const cards = [
      ...refs.chatLanding.querySelectorAll(`.landingWorkflowCard[data-workflow-jump="${k}"]`),
    ];
    let btn = cards.find((el) => !tid || el.getAttribute("data-task-id") === tid) || cards[0];
    if (!btn) return null;
    const turn = btn.closest(".landingTurn");
    if (patch.status != null) {
      const pill = btn.querySelector(".landingWorkflowCardStatus");
      if (pill) pill.textContent = String(patch.status);
    }
    if (patch.step != null || patch.progress != null) {
      const step = Number(patch.step);
      const progress = Number(patch.progress);
      const total = k === "orchestrate" ? 4 : k === "restruction" ? 2 : k === "validation" ? 1 : 0;
      const stepEl = btn.querySelector(".landingWorkflowCardStep");
      if (stepEl && Number.isFinite(step) && total > 0) {
        stepEl.textContent =
          k === "validation" ? "评审" : k === "restruction" ? `阶段 ${Math.min(total, step)}/${total}` : `步骤 ${Math.min(total, step)}/${total}`;
      }
      const fill = btn.querySelector(".landingWorkflowBarFill");
      if (fill && Number.isFinite(progress)) fill.style.width = `${Math.max(0, Math.min(100, progress))}%`;
      const phases = btn.querySelectorAll(".landingWorkflowPhase");
      if (phases?.length && Number.isFinite(step)) {
        const cur = Math.min(total, Math.max(0, step));
        phases.forEach((el, idx) => {
          const i = idx + 1;
          el.classList.toggle("is-done", cur > i);
          el.classList.toggle("is-current", cur === i);
          el.classList.toggle("is-todo", cur < i);
        });
      }
    }
    const continueTo = patch.continueTo != null ? String(patch.continueTo).trim() : null;
    const continueLabel = patch.continueLabel != null ? String(patch.continueLabel).trim() : null;
    if (continueTo !== null && turn) {
      let actions = turn.querySelector(".landingWorkflowCardActions");
      if (!continueTo || !continueLabel) {
        actions?.remove();
      } else {
        if (!actions) {
          actions = document.createElement("div");
          actions.className = "landingWorkflowCardActions";
          turn.appendChild(actions);
        }
        actions.innerHTML = `<button type="button" class="landingWorkflowContinueBtn" data-workflow-continue="${escapeHtml(continueTo)}" ${
          tid ? `data-task-id="${escapeHtml(tid)}"` : ""
        }>${escapeHtml(continueLabel)}</button>`;
      }
    }
    return btn;
  }

  /** 助手工具轨迹：可折叠列表，不参与 Qwen role 回传 */
  function addLandingToolTraceCard(trace) {
    wireLandingBubbleActionsOnce();
    if (!refs.chatLanding) return null;
    const arr = Array.isArray(trace) ? trace : [];
    const rows = arr
      .map((t) => {
        const ok = Boolean(t?.ok);
        const name = escapeHtml(String(t?.name || "tool"));
        const sum = escapeHtml(String(t?.summary || "").slice(0, 220));
        const icon = ok ? "✓" : "✗";
        return `<li class="landingToolTraceRow"><span class="landingToolTraceIcon" aria-hidden="true">${icon}</span><span class="landingToolTraceName">${name}</span><span class="landingToolTraceSum">${sum}</span></li>`;
      })
      .join("");
    const wrap = document.createElement("div");
    wrap.className = "landingTurn landingTurn--toolTrace";
    wrap.innerHTML = `
      <details class="landingToolTrace">
        <summary class="landingToolTraceSumBtn">工具调用（${arr.length}）· 展开</summary>
        <ul class="landingToolTraceList">${rows || "<li>（无条目）</li>"}</ul>
      </details>`;
    refs.chatLanding.appendChild(wrap);
    refs.chatLanding.scrollTop = refs.chatLanding.scrollHeight;
    return wrap;
  }

  function showStage(mode) {
    refs.landingMain?.classList.toggle("hidden", mode !== "landing");
    refs.designDomainMain?.classList.toggle("hidden", mode !== "designDomain");
    refs.restructionMain?.classList.toggle("hidden", mode !== "restruction");
    refs.orchestrateMain?.classList.toggle("hidden", mode !== "orchestrate");
    refs.flowMain?.classList.toggle("hidden", mode !== "flow");
    refs.flowStepper?.classList.toggle("hidden", mode !== "flow");
  }

  /**
   * 进入设计域 / 构型优化编排等子流程前：短暂全屏过渡 + 旋转指示，便于用户感知即将跳转。
   * @param {{ kind?: "design_domain"|"orchestrate", minMs?: number, instant?: boolean, skip?: boolean }} opts
   * ``instant`` / ``skip``：不展示过渡层，立即 resolve（用于设计域等需秒开场景）。
   */
  function playLandingSubflowBridge(opts = {}) {
    if (opts.instant === true || opts.skip === true) return Promise.resolve();
    const kindRaw = String(opts.kind || "design_domain").toLowerCase();
    const kind =
      kindRaw === "orchestrate" ? "orchestrate" : kindRaw === "restruction" ? "restruction" : "design_domain";
    const minMs = Math.max(720, Math.min(3400, Number(opts.minMs) > 0 ? Number(opts.minMs) : 1480));
    const title =
      kind === "orchestrate"
        ? "即将进入构型优化编排"
        : kind === "restruction"
          ? "即将进入尺寸时域分析"
          : "即将进入设计域（OC4）";
    const subtitle =
      kind === "orchestrate"
        ? "正在切换到编排工作台…"
        : kind === "restruction"
          ? "正在打开静力尺寸与 Zwind 时域分析台…"
          : "正在打开网格与载荷工作台…";
    const anchor = refs.landingMain;
    if (!anchor) return Promise.resolve();
    return new Promise((resolve) => {
      const ov = document.createElement("div");
      ov.className = "landingSubflowBridgeOverlay";
      ov.setAttribute("role", "status");
      ov.setAttribute("aria-live", "polite");
      ov.innerHTML = `
        <div class="landingSubflowBridgeCard">
          <div class="landingSubflowBridgeRing" aria-hidden="true"></div>
          <div class="landingSubflowBridgeText">
            <div class="landingSubflowBridgeTitle">${escapeHtml(title)}</div>
            <div class="landingSubflowBridgeSub">${escapeHtml(subtitle)}</div>
          </div>
        </div>
      `;
      anchor.appendChild(ov);
      requestAnimationFrame(() => {
        requestAnimationFrame(() => ov.classList.add("landingSubflowBridgeOverlay--visible"));
      });
      const finish = () => {
        if (!ov.isConnected) {
          resolve();
          return;
        }
        ov.classList.remove("landingSubflowBridgeOverlay--visible");
        ov.classList.add("landingSubflowBridgeOverlay--exit");
        setTimeout(() => {
          ov.remove();
          resolve();
        }, 400);
      };
      setTimeout(finish, minMs);
    });
  }

  function goHome() {
    showStage("landing");
    setStep(1);
  }

  function streamOrchestration(onDone, opts = {}) {
    const preambleMd = typeof opts.preambleMd === "string" ? opts.preambleMd.trim() : "";
    const phases = [
      {
        text:
          "## 步骤 1｜扫描目录并建立运行上下文\n" +
          "- **锁定工作区**：以当前上传文件所在 `runs/<任务>/` 为根（或你在侧栏/流程里填写的扫描目录），列出目录内 `*.inp`、`*.vtk`、日志与附属 `*INCLUDE` 文件。\n" +
          "- **主 INP 体检**：检查优化用 `*ELSET`、`*STEP`、`*MATERIAL`、`*SOLID SECTION`、`*BOUNDARY`、`*CLOAD` 等是否与 BESO/CalculiX 预期一致；缺材料或 STEP 顺序错误会在后续执行时报错，本步尽量提前暴露。\n" +
          "- **几何分流**：若仅有 **IGES/STEP** 而无体网格 INP，应先走 **设计域**（STEP→体网格→`03_for_beso.inp`）；若已是四面体/六面体体网格 INP，则在本步完成后可直接进入「生成代码」。\n" +
          "- **OC4 论文对齐（Chen et al., 2026, Ocean Engineering）**：设计域对应半潜三根边柱围成区域；载荷/边界概念上为系泊侧强约束 + 塔顶/主柱等效风推；编排完成后 BESO 默认按 **stiffness（柔度最小化）** 与 **约 15% 保留体积比** 写入 `beso_conf.py`（可在生成代码步再调）。\n" +
          "- **你可操作**：在流程页确认「自动关联扫描」树、必要时触发 **IGES → INP** 转换；顶栏 **← 设计域** 可随时回去改网格或载荷。",
        active: 1,
        conn: 0,
      },
      {
        text:
          "## 步骤 2｜生成运行脚本与任务清单\n" +
          "- **写入清单**：生成或更新 `task_manifest.json`（或等效描述），记录主 INP、载荷/集合类辅助 INP、`step_mapping` 与扫描路径，供执行器按序拷贝进运行目录。\n" +
          "- **生成 `beso_conf.py`**：写入 `mass_goal_ratio`（目标保留质量比）、`filter_list` 中 simple 滤波半径、`save_iteration_results`（与「每 N 轮保存中间结果」对应）、`optimization_base`（OC4 设计域收尾默认 **stiffness** 以贴合 Chen 2026 柔度最小化表述；亦可改为 `failure_index`）等；OC4 双域时还会区分 `design_space` / `nondesign_space`。\n" +
          "- **脚本与入口**：产出 `run_generated` 调用链或包装脚本，使同一工作目录内可重复调用 **CalculiX（ccx）** 与 **BESO（Python）**；本步结束前不会在后台真正开始大规模迭代。\n" +
          "- **你可操作**：在下一步的「生成代码」面板核对各文件内容，再点 **接受本步骤并继续**。",
        active: 2,
        conn: 1,
      },
      {
        text:
          "## 步骤 3｜绑定预览数据（VTK / 指标曲线）\n" +
          "- **映射绑定**：把清单里的主 INP 与辅助 INP 绑定到 **Mass、FI_mean、FI_max** 等曲线数据源，以及 **VTK 帧序列**（若目录中已有 `file*.vtk` 或运行中会生成）。\n" +
          "- **分步界面**：为右侧 **3D 预览** 与 **指标曲线** 面板准备路径；优化开始后日志会增量刷新，本步完成意味着「执行阶段」可以正确找到预览文件。\n" +
          "- **你可操作**：若扫描树缺文件，回到步骤 1 重新扫描或补传；确认无误后 **接受本步骤并继续** 进入汇总。",
        active: 3,
        conn: 2,
      },
      {
        text:
          "## 步骤 4｜产物汇总与一键执行\n" +
          "- **清单汇总**：在「生成文件和日志汇总」中合并 **输入映射**、**代码/脚本清单**、**日志摘要**，形成可审计的一次「计划运行」视图。\n" +
          "- **执行前检查**：确认主 INP 已在运行目录、`beso_conf.py` 与 `ccx` 路径可用、磁盘空间足够（`save_every=1` 时每轮都会写 OBJ/INP，体积增长快）。\n" +
          "- **开始计算**：点击 **执行任务** 启动后台线程：顺序调用 CalculiX 与 BESO；完成后可用 **拓扑优化结果查看器** 浏览 OBJ/STEP 与曲线。\n" +
          "- **你可操作**：执行期间仍可 **← 设计域** 调整几何后重新「完成并进入编排」再执行任务。",
        active: 4,
        conn: 3,
      },
    ];
    if (!refs.orchestrateStream) return;
    refs.orchestrateStream.innerHTML = "";
    updateRailVisibility(1, 0);

    let phaseIdx = 0;
    let streamMd = preambleMd ? `${preambleMd}\n\n` : "";
    if (streamMd) {
      refs.orchestrateStream.innerHTML = renderMd(streamMd);
      refs.orchestrateStream.scrollTop = refs.orchestrateStream.scrollHeight;
    }
    const typePhase = () => {
      if (phaseIdx >= phases.length) {
        setTimeout(() => onDone?.(), 1700);
        return;
      }
      const p = phases[phaseIdx];
      updateRailVisibility(p.active, p.conn || 0);

      let charIdx = 0;
      const line = `${p.text}\n\n`;
      /** 按块打字 + 较低刷新率，避免每字 renderMd 造成主线程长时间卡顿 */
      const CHUNK_CHARS = 32;
      const TICK_MS = 52;
      const t = setInterval(() => {
        const end = Math.min(charIdx + CHUNK_CHARS, line.length);
        streamMd += line.slice(charIdx, end);
        charIdx = end;
        refs.orchestrateStream.innerHTML = renderMd(streamMd);
        refs.orchestrateStream.scrollTop = refs.orchestrateStream.scrollHeight;
        if (charIdx >= line.length) {
          clearInterval(t);
          phaseIdx += 1;
          setTimeout(typePhase, 440);
        }
      }, TICK_MS);
    };
    typePhase();
  }

  function renderSelectedInputs(selected) {
    if (!selected || !refs.mappingPreview) return;
    const aux = selected.aux_inps || {};
    const stepMap = selected.step_mapping || {};
    const stepLines = Object.keys(stepMap).length
      ? Object.entries(stepMap).map(([k, v]) => `${k} -> step ${v}`).join("\n")
      : "(none)";
    refs.mappingPreview.textContent =
      `primary: ${selected.primary_inp || "(none)"}\n` +
      `load_case: ${(aux.load_case || []).join(", ") || "(none)"}\n` +
      `set_definition: ${(aux.set_definition || []).join(", ") || "(none)"}\n` +
      `other_inp: ${(aux.other_inp || []).join(", ") || "(none)"}\n` +
      `step_mapping:\n${stepLines}`;
  }

  function setSidebarCollapsed(collapsed) {
    if (!refs.landingMain) return;
    const c = Boolean(collapsed);
    refs.landingMain.classList.toggle("sidebarCollapsed", c);
    const btn = refs.toggleSidebarBtn;
    if (btn) {
      btn.setAttribute("aria-expanded", c ? "false" : "true");
      const label = c ? "展开任务栏" : "收起侧栏";
      btn.title = label;
      btn.setAttribute("aria-label", label);
    }
    const aside = refs.landingMain.querySelector(".taskSidebar");
    if (aside) aside.setAttribute("aria-expanded", c ? "false" : "true");
    try {
      localStorage.setItem("beso.sidebar.collapsed", c ? "1" : "0");
    } catch {}
  }

  function addLandingChecklistCard(payload, opts = {}) {
    if (!refs.chatLanding) return null;
    wireLandingBubbleActionsOnce();
    const wrap = document.createElement("div");
    wrap.className = "landingTurn landingTurn--agent landingTurn--checklist";
    wrap.dataset.rawText = String(opts.plainSummary || "Phase I 设计清单");
    if (payload.checklistId) wrap.dataset.checklistId = payload.checklistId;
    const bubble = document.createElement("div");
    bubble.className = "bubble agent";
    const inner = document.createElement("div");
    inner.className = "bubbleText bubbleText--checklist";
    inner.innerHTML = String(payload.html || "");
    bubble.appendChild(inner);
    wrap.appendChild(bubble);
    refs.chatLanding.appendChild(wrap);
    refs.chatLanding.scrollTop = refs.chatLanding.scrollHeight;
    return wrap;
  }

  function addLandingReplanJourney(payload, opts = {}) {
    if (!refs.chatLanding) return null;
    wireLandingBubbleActionsOnce();
    const wrap = document.createElement("div");
    wrap.className = "landingTurn landingTurn--agent landingTurn--replanJourney rpJourneyHost";
    wrap.dataset.rawText = String(opts.plainSummary || "失败驱动重规划");
    if (payload.caseId || payload.journeyData?.case_id) {
      wrap.dataset.caseId = String(payload.caseId || payload.journeyData.case_id);
    }
    const bubble = document.createElement("div");
    bubble.className = "bubble agent";
    const inner = document.createElement("div");
    inner.className = "bubbleText bubbleText--replanJourney";
    inner.innerHTML = String(payload.html || "");
    bubble.appendChild(inner);
    wrap.appendChild(bubble);
    refs.chatLanding.appendChild(wrap);
    refs.chatLanding.scrollTop = refs.chatLanding.scrollHeight;
    return wrap;
  }

  /** 工程图预览卡片 + 应用内预览窗 */
  function ensureCadDrawingLightbox() {
    let root = document.getElementById("cadDrawingLightbox");
    if (root) return root;
    root = document.createElement("div");
    root.id = "cadDrawingLightbox";
    root.className = "cadDrawLb";
    root.hidden = true;
    root.innerHTML = `
      <div class="cadDrawLbBackdrop" data-cad-lb="close"></div>
      <div class="cadDrawLbPanel" role="dialog" aria-modal="true" aria-labelledby="cadDrawLbTitle">
        <header class="cadDrawLbHead">
          <div class="cadDrawLbHeadText">
            <h2 id="cadDrawLbTitle" class="cadDrawLbTitle">工程图预览</h2>
            <p class="cadDrawLbSub" id="cadDrawLbSub"></p>
          </div>
          <button type="button" class="cadDrawLbIconBtn" data-cad-lb="close" title="关闭" aria-label="关闭">×</button>
        </header>
        <div class="cadDrawLbStage">
          <img class="cadDrawLbImg" id="cadDrawLbImg" alt="工程图" draggable="false" />
        </div>
        <footer class="cadDrawLbFoot">
          <div class="cadDrawLbZoom">
            <button type="button" class="cadDrawLbBtn" data-cad-lb="zoom-out" title="缩小">−</button>
            <button type="button" class="cadDrawLbBtn" data-cad-lb="zoom-reset" title="适应">适应</button>
            <button type="button" class="cadDrawLbBtn" data-cad-lb="zoom-in" title="放大">+</button>
          </div>
          <div class="cadDrawLbActions">
            <a class="cadDrawLbBtn cadDrawLbBtn--primary" id="cadDrawLbDlPng" download target="_blank" rel="noopener">下载 PNG</a>
            <a class="cadDrawLbBtn" id="cadDrawLbDlPdf" download target="_blank" rel="noopener" hidden>下载 PDF</a>
            <a class="cadDrawLbBtn" id="cadDrawLbDlManifest" download target="_blank" rel="noopener" hidden>清单</a>
            <button type="button" class="cadDrawLbBtn" data-cad-lb="copy" title="复制图片链接">复制链接</button>
            <button type="button" class="cadDrawLbBtn" data-cad-lb="close">关闭</button>
          </div>
        </footer>
      </div>
    `;
    document.body.appendChild(root);

    let scale = 1;
    const img = () => root.querySelector("#cadDrawLbImg");
    const applyScale = () => {
      const el = img();
      if (el) el.style.transform = `scale(${scale})`;
    };
    const close = () => {
      root.classList.remove("is-open");
      scale = 1;
      applyScale();
      setTimeout(() => {
        root.hidden = true;
      }, 220);
    };
    root._cadLb = {
      open(payload) {
        const title = root.querySelector("#cadDrawLbTitle");
        const sub = root.querySelector("#cadDrawLbSub");
        const el = img();
        const dl = root.querySelector("#cadDrawLbDlPng");
        const dlPdf = root.querySelector("#cadDrawLbDlPdf");
        const man = root.querySelector("#cadDrawLbDlManifest");
        if (title) title.textContent = payload.title || "总布置式工程图（预览）";
        if (sub) sub.textContent = payload.subtitle || "";
        if (el) {
          el.src = payload.src || "";
          el.style.transform = "scale(1)";
        }
        scale = 1;
        if (dl) {
          dl.href = payload.src || "#";
          dl.download = payload.downloadName || "drawing_sheet.png";
        }
        if (dlPdf) {
          if (payload.pdfUrl) {
            dlPdf.hidden = false;
            dlPdf.href = payload.pdfUrl;
            dlPdf.download = payload.pdfDownloadName || "drawing_sheet.pdf";
          } else {
            dlPdf.hidden = true;
          }
        }
        if (man) {
          if (payload.manifestUrl) {
            man.hidden = false;
            man.href = payload.manifestUrl;
            man.download = "pack_manifest.json";
          } else {
            man.hidden = true;
          }
        }
        root.hidden = false;
        requestAnimationFrame(() => root.classList.add("is-open"));
      },
      close,
    };
    root.addEventListener("click", async (e) => {
      const act = e.target.closest?.("[data-cad-lb]")?.getAttribute("data-cad-lb");
      if (!act) return;
      if (act === "close") {
        close();
        return;
      }
      if (act === "zoom-in") {
        scale = Math.min(3, scale + 0.2);
        applyScale();
        return;
      }
      if (act === "zoom-out") {
        scale = Math.max(0.4, scale - 0.2);
        applyScale();
        return;
      }
      if (act === "zoom-reset") {
        scale = 1;
        applyScale();
        return;
      }
      if (act === "copy") {
        const src = img()?.src || "";
        try {
          await navigator.clipboard.writeText(src);
        } catch {
          /* ignore */
        }
      }
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && root.classList.contains("is-open")) close();
    });
    return root;
  }

  function openCadDrawingLightbox(payload) {
    const root = ensureCadDrawingLightbox();
    root._cadLb?.open(payload);
  }

  function addLandingCadDrawingCard(data, baseUrl) {
    if (!refs.chatLanding) return null;
    wireLandingBubbleActionsOnce();
    const base = String(baseUrl || "").replace(/\/$/, "");
    const wrap = document.createElement("div");
    wrap.className = "landingTurn landingTurn--agent landingTurn--cadDrawing";
    const bubble = document.createElement("div");
    bubble.className = "bubble agent";
    const inner = document.createElement("div");
    inner.className = "bubbleText landingCadDrawingCard";

    const stem = `${(data?.pack?.source_name || "drawing").replace(/\.[^.]+$/, "")}_sheet`;
    const title = document.createElement("div");
    title.className = "landingCadDrawingTitle";
    title.textContent = data?.pack?.source_name || "总布置式工程图（预览）";
    const meta = document.createElement("div");
    meta.className = "landingCadDrawingMeta";
    const engRaw = data?.engine || data?.pack?.engine || "";
    const engLabel =
      engRaw === "freecad"
        ? "AI Engineer · 线框轮廓"
        : engRaw === "freecad_mesh" || engRaw === "mesh"
          ? "AI Engineer · 轮廓投影"
          : engRaw
            ? `AI Engineer · ${engRaw}`
            : "AI Engineer";
    const scale = data?.scale || data?.pack?.scale || "";
    const sheetSize = data?.sheet_size || data?.pack?.sheet_size || "";
    meta.textContent = [engLabel, scale, sheetSize, data?.source_path || ""].filter(Boolean).join(" · ");

    const sheet = String(data?.sheet_url || "").trim();
    const sheetUrl = sheet ? (sheet.startsWith("http") ? sheet : `${base}${sheet}`) : "";
    const pdf = String(data?.pdf_url || data?.pack?.sheet_pdf_url || "").trim();
    let pdfUrl = "";
    if (pdf) {
      pdfUrl = pdf.startsWith("http") ? pdf : `${base}${pdf.startsWith("/") ? pdf : `/${pdf}`}`;
    } else if (data?.pack?.sheet_pdf && sheetUrl) {
      pdfUrl = sheetUrl.replace(/drawing_sheet\.png$/i, "drawing_sheet.pdf");
    }
    const man = String(data?.manifest_url || "").trim();
    const manUrl = man ? (man.startsWith("http") ? man : `${base}${man}`) : "";

    const img = document.createElement("img");
    img.className = "landingCadDrawingImg";
    img.alt = "总布置式工程图预览";
    img.loading = "lazy";
    if (sheetUrl) img.src = sheetUrl;

    const openLb = () => {
      if (!sheetUrl) return;
      openCadDrawingLightbox({
        title: data?.pack?.source_name || "总布置式工程图（预览）",
        subtitle: [data?.source_path || "", scale, sheetSize].filter(Boolean).join(" · "),
        src: sheetUrl,
        pdfUrl,
        manifestUrl: manUrl,
        downloadName: `${stem}.png`,
        pdfDownloadName: `${stem}.pdf`,
      });
    };
    img.addEventListener("click", openLb);

    const actions = document.createElement("div");
    actions.className = "landingCadDrawingActions";
    const btnPreview = document.createElement("button");
    btnPreview.type = "button";
    btnPreview.className = "landingCadDrawingBtn landingCadDrawingBtn--primary";
    btnPreview.textContent = "预览";
    btnPreview.addEventListener("click", openLb);
    const aDl = document.createElement("a");
    aDl.className = "landingCadDrawingBtn";
    aDl.textContent = "下载 PNG";
    aDl.href = sheetUrl || "#";
    aDl.download = `${stem}.png`;
    aDl.target = "_blank";
    aDl.rel = "noopener";
    actions.appendChild(btnPreview);
    actions.appendChild(aDl);
    if (pdfUrl) {
      const aPdf = document.createElement("a");
      aPdf.className = "landingCadDrawingBtn";
      aPdf.textContent = "下载 PDF";
      aPdf.href = pdfUrl;
      aPdf.download = `${stem}.pdf`;
      aPdf.target = "_blank";
      aPdf.rel = "noopener";
      actions.appendChild(aPdf);
    }
    if (manUrl) {
      const aMan = document.createElement("a");
      aMan.className = "landingCadDrawingBtn";
      aMan.textContent = "清单";
      aMan.href = manUrl;
      aMan.download = "pack_manifest.json";
      aMan.target = "_blank";
      aMan.rel = "noopener";
      actions.appendChild(aMan);
    }

    const foot = document.createElement("div");
    foot.className = "landingCadDrawingFoot";
    foot.textContent = "总布置式预览 · PNG/PDF · 非审图出图";

    inner.appendChild(title);
    inner.appendChild(meta);
    inner.appendChild(img);
    inner.appendChild(actions);
    inner.appendChild(foot);
    bubble.appendChild(inner);
    wrap.appendChild(bubble);
    refs.chatLanding.appendChild(wrap);
    refs.chatLanding.scrollTop = refs.chatLanding.scrollHeight;
    return wrap;
  }

  /** Phase V · Automated Reviewer — sync rich card to landing homepage */
  function addLandingValidationCard(data, baseUrl) {
    if (!refs.chatLanding) return null;
    wireLandingBubbleActionsOnce();
    const base = String(baseUrl || "").replace(/\/$/, "");
    const wrap = document.createElement("div");
    wrap.className = "landingTurn landingTurn--agent landingTurn--validation";
    const bubble = document.createElement("div");
    bubble.className = "bubble agent";
    const inner = document.createElement("div");
    inner.className = "bubbleText landingValidationCard";

    const gate = data?.halt_gate || {};
    const title = document.createElement("div");
    title.className = "landingValidationTitle";
    title.textContent = "Phase V · Automated Reviewer 验证";
    const gateEl = document.createElement("div");
    gateEl.className = `landingValidationGate ${gate.ok ? "is-pass" : "is-fail"}`;
    gateEl.innerHTML =
      `综合分 <strong>S=${data?.overall_score ?? "—"}</strong>` +
      ` · 等级 <strong>${data?.grade || "—"}</strong>` +
      ` · 终止门：${gate.ok ? "可终止探索" : gate.reason || "未通过"}`;

    const grid = document.createElement("div");
    grid.className = "landingValidationGrid";
    for (const f of (data?.figures || []).slice(0, 4)) {
      const u = String(f.url || "");
      if (!u) continue;
      const src = u.startsWith("http") ? u : `${base}${u}`;
      const fig = document.createElement("figure");
      fig.className = "landingValidationFig";
      const img = document.createElement("img");
      img.src = src;
      img.alt = f.label || "验证图";
      img.loading = "lazy";
      const cap = document.createElement("figcaption");
      cap.textContent = f.label || "";
      fig.appendChild(img);
      fig.appendChild(cap);
      grid.appendChild(fig);
    }

    const foot = document.createElement("div");
    foot.className = "landingValidationFoot";
    const links = [];
    if (data?.report_md_url) {
      links.push(`<a href="${base}${data.report_md_url}" target="_blank" rel="noopener">validation_report.md</a>`);
    }
    if (data?.score_json_url) {
      links.push(`<a href="${base}${data.score_json_url}" target="_blank" rel="noopener">score.json</a>`);
    }
    foot.innerHTML = links.length ? links.join(" · ") : "验证产物已同步至主页";

    inner.appendChild(title);
    inner.appendChild(gateEl);
    if (grid.childNodes.length) inner.appendChild(grid);
    inner.appendChild(foot);
    bubble.appendChild(inner);
    wrap.appendChild(bubble);
    refs.chatLanding.appendChild(wrap);
    refs.chatLanding.scrollTop = refs.chatLanding.scrollHeight;
    return wrap;
  }

  /** Replace existing checklist card in place (avoid duplicate pending/locked cards). */
  function replaceLandingChecklistCard(data, baseUrl) {
    if (!refs.chatLanding) return null;
    const id = String(data?.checklistId || data?.checklist_id || data?.checklist?.meta?.checklist_id || "").trim();
    const html = data?.html || "";
    if (!html) return null;
    let host = null;
    if (id) {
      try {
        host = refs.chatLanding.querySelector(`.dcCard[data-checklist-id="${id.replace(/"/g, "")}"]`);
      } catch {
        host = null;
      }
      if (!host) {
        host = refs.chatLanding.querySelector(`.landingTurn--checklist[data-checklist-id="${id.replace(/"/g, "")}"] .dcCard`);
      }
    }
    if (!host) host = refs.chatLanding.querySelector(".landingTurn--checklist .dcCard, .dcCard");
    if (!host) {
      return addLandingChecklistCard(data, { plainSummary: data?.plainSummary });
    }
    const turn = host.closest(".landingTurn");
    const bubbleText = turn?.querySelector(".bubbleText") || host.parentElement;
    if (bubbleText) {
      bubbleText.innerHTML = html;
      if (turn) {
        turn.dataset.rawText = data?.plainSummary || turn.dataset.rawText || "";
        if (id) turn.dataset.checklistId = id;
      }
      refs.chatLanding.scrollTop = refs.chatLanding.scrollHeight;
      return turn;
    }
    return null;
  }

  return {
    setStep,
    addBubble,
    addLandingBubble,
    addLandingChecklistCard,
    replaceLandingChecklistCard,
    addLandingReplanJourney,
    addLandingCadDrawingCard,
    addLandingValidationCard,
    addLandingThinking,
    removeLandingThinking,
    addLandingTyping,
    removeLandingTyping,
    beginLandingAgentStream,
    addLandingWorkflowCard,
    updateLandingWorkflowCard,
    addLandingToolTraceCard,
    showStage,
    goHome,
    streamOrchestration,
    playLandingSubflowBridge,
    renderSelectedInputs,
    setSidebarCollapsed,
  };
}
