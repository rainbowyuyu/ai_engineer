/**
 * Smooth guided replan journey: detect → diagnose → think → replan → resume
 * Each step card streams its copy so users can follow the recovery narrative.
 */

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function mdLite(s) {
  return esc(s)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\n/g, "<br>");
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

/** Split into visible grapheme-ish units for typewriter (CJK-friendly). */
function streamUnits(text) {
  const s = String(text || "");
  if (typeof Intl !== "undefined" && Intl.Segmenter) {
    try {
      return [...new Intl.Segmenter(undefined, { granularity: "grapheme" }).segment(s)].map((x) => x.segment);
    } catch {
      /* fall through */
    }
  }
  return [...s];
}

/**
 * Typewriter into an element. Uses plain text while typing, then mdLite on finish.
 * @returns {Promise<void>}
 */
async function streamTextInto(el, text, opts = {}) {
  if (!el) return;
  const instant = Boolean(opts.instant);
  const cps = Number(opts.cps) || 28; // chars per second (slower = clearer)
  const chunk = Math.max(1, Number(opts.chunk) || 1);
  const units = streamUnits(text);
  if (instant || !units.length) {
    el.innerHTML = mdLite(text);
    el.classList.remove("rpStreamCaret");
    return;
  }
  el.classList.add("rpStreamCaret");
  el.textContent = "";
  let buf = "";
  const tickMs = Math.max(22, Math.round(1000 / cps));
  for (let i = 0; i < units.length; i += chunk) {
    buf += units.slice(i, i + chunk).join("");
    el.textContent = buf;
    if (opts.onTick) opts.onTick();
    await sleep(tickMs);
  }
  el.innerHTML = mdLite(text);
  el.classList.remove("rpStreamCaret");
}

export function buildReplanJourneyShell(title, caseId) {
  return `
    <div class="rpJourney" data-case-id="${esc(caseId || "")}">
      <div class="rpJourneyHd">
        <div class="rpJourneyTitle">${esc(title || "失败驱动重规划")}</div>
        <div class="rpJourneyPulse" aria-hidden="true"><i></i><i></i><i></i></div>
      </div>
      <ol class="rpTimeline" role="list"></ol>
      <div class="rpJourneyFt" hidden>
        <p class="rpJourneyHint"></p>
        <div class="rpJourneyActions"></div>
      </div>
    </div>
  `;
}

/** Empty shell — content streams in via playReplanJourney */
function stepShellHtml(step, index, total) {
  const tone = step.tone || "info";
  return `
    <li class="rpStep rpStep--${esc(tone)} rpStep--pending" data-step-id="${esc(step.id)}" style="--rp-i:${index}">
      <div class="rpStepRail"><span class="rpStepDot"></span>${index < total - 1 ? '<span class="rpStepLine"></span>' : ""}</div>
      <div class="rpStepCard">
        <div class="rpStepMeta"><span class="rpStepIdx">${index + 1}/${total}</span><span class="rpStepSub rpStreamSub"></span></div>
        <div class="rpStepTitle"></div>
        <div class="rpStepBody"></div>
        <div class="rpMetrics" hidden></div>
        <ul class="rpTheta" hidden></ul>
      </div>
    </li>
  `;
}

function fillStepInstant(node, step) {
  const sub = node.querySelector(".rpStreamSub");
  const title = node.querySelector(".rpStepTitle");
  const body = node.querySelector(".rpStepBody");
  const metricsEl = node.querySelector(".rpMetrics");
  const thetaEl = node.querySelector(".rpTheta");
  if (sub) sub.textContent = step.subtitle || "";
  if (title) title.innerHTML = mdLite(step.title || "");
  if (body) body.innerHTML = mdLite(step.body || "");
  if (metricsEl && step.metrics && Object.keys(step.metrics).length) {
    metricsEl.hidden = false;
    metricsEl.innerHTML = Object.entries(step.metrics)
      .slice(0, 6)
      .map(([k, v]) => `<span class="rpMetric"><em>${esc(k)}</em>${esc(v)}</span>`)
      .join("");
  }
  if (thetaEl && Array.isArray(step.theta_diff) && step.theta_diff.length) {
    thetaEl.hidden = false;
    thetaEl.innerHTML = step.theta_diff.map((t) => `<li>${mdLite(t)}</li>`).join("");
  }
}

async function streamStepCard(node, step, opts = {}) {
  const instant = Boolean(opts.instant);
  const onTick = opts.onTick;
  const sub = node.querySelector(".rpStreamSub");
  const title = node.querySelector(".rpStepTitle");
  const body = node.querySelector(".rpStepBody");
  const metricsEl = node.querySelector(".rpMetrics");
  const thetaEl = node.querySelector(".rpTheta");

  if (instant) {
    fillStepInstant(node, step);
    return;
  }

  // subtitle first (quick)
  if (sub) {
    await streamTextInto(sub, step.subtitle || "", { cps: 36, chunk: 2, onTick });
    await sleep(180);
  }
  // title
  if (title) {
    await streamTextInto(title, step.title || "", { cps: 22, chunk: 1, onTick });
    await sleep(280);
  }
  // body — slowest, so users can read the diagnosis
  if (body) {
    await streamTextInto(body, step.body || "", { cps: 18, chunk: 1, onTick });
    await sleep(320);
  }

  // metrics pills one-by-one
  if (metricsEl && step.metrics && Object.keys(step.metrics).length) {
    metricsEl.hidden = false;
    metricsEl.innerHTML = "";
    for (const [k, v] of Object.entries(step.metrics).slice(0, 6)) {
      const span = document.createElement("span");
      span.className = "rpMetric rpMetric--in";
      span.innerHTML = `<em>${esc(k)}</em>${esc(v)}`;
      metricsEl.appendChild(span);
      onTick?.();
      await sleep(260);
    }
  }

  // theta lines one-by-one
  if (thetaEl && Array.isArray(step.theta_diff) && step.theta_diff.length) {
    thetaEl.hidden = false;
    thetaEl.innerHTML = "";
    for (const t of step.theta_diff) {
      const li = document.createElement("li");
      li.className = "rpThetaItem--in";
      thetaEl.appendChild(li);
      await streamTextInto(li, t, { cps: 20, chunk: 1, onTick });
      await sleep(200);
    }
  }
}

function scrollJourneyIntoView(root) {
  const scrollers = [
    root.closest(".landingChatScroll"),
    root.closest(".ddAgentUnifiedScroll"),
    root.closest("#orchestrateStream")?.parentElement,
    document.getElementById("chatLanding"),
  ].filter(Boolean);
  for (const sc of scrollers) {
    try {
      sc.scrollTo({ top: sc.scrollHeight, behavior: "smooth" });
    } catch {
      sc.scrollTop = sc.scrollHeight;
    }
  }
}

/**
 * Mount journey shell and progressively reveal steps with in-card streaming.
 * @returns {{ wrap: HTMLElement|null, done: Promise<void>, getRoot: () => HTMLElement|null }}
 */
export function playReplanJourney(hostEl, data, opts = {}) {
  const root = hostEl?.querySelector?.(".rpJourney") || hostEl;
  if (!root) return { wrap: null, done: Promise.resolve(), getRoot: () => null };

  const timeline = root.querySelector(".rpTimeline");
  const ft = root.querySelector(".rpJourneyFt");
  const hint = root.querySelector(".rpJourneyHint");
  const actionsEl = root.querySelector(".rpJourneyActions");
  const steps = Array.isArray(data.guided_steps) ? data.guided_steps : [];
  const titleEl = root.querySelector(".rpJourneyTitle");
  if (titleEl && data.title) titleEl.textContent = data.title;

  if (timeline) timeline.innerHTML = "";

  const onResume = typeof opts.onResume === "function" ? opts.onResume : null;
  const onComplete = typeof opts.onComplete === "function" ? opts.onComplete : null;
  const instant = Boolean(opts.instant);
  const reduceMotion =
    typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const baseUrl = String(opts.baseUrl || "").replace(/\/+$/, "");
  const skipStream = instant || reduceMotion;

  const done = (async () => {
    for (let i = 0; i < steps.length; i++) {
      const step = steps[i] || {};
      if (!timeline) break;
      const tmp = document.createElement("div");
      tmp.innerHTML = stepShellHtml(step, i, steps.length).trim();
      const node = tmp.firstElementChild;
      if (!node) continue;
      timeline.appendChild(node);
      void node.offsetWidth;
      node.classList.remove("rpStep--pending");
      node.classList.add("rpStep--active");
      scrollJourneyIntoView(root);

      await streamStepCard(node, step, {
        instant: skipStream,
        onTick: () => scrollJourneyIntoView(root),
      });

      // hold so user can finish reading before next step
      const hold = skipStream ? 40 : Math.max(900, Number(step.delay_ms) || 1400);
      await sleep(hold);
      node.classList.remove("rpStep--active");
      node.classList.add("rpStep--done");
      if (!skipStream) await sleep(280);
    }

    const resume = data.resume || steps[steps.length - 1]?.resume || {};
    if (ft) {
      ft.hidden = false;
      if (hint) {
        if (skipStream) {
          hint.textContent = resume.hint || "流程已可继续。";
        } else {
          await streamTextInto(hint, resume.hint || "流程已可继续。", {
            cps: 24,
            chunk: 1,
            onTick: () => scrollJourneyIntoView(root),
          });
        }
      }
      if (actionsEl) {
        actionsEl.innerHTML = "";
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "rpCta";
        btn.textContent = resume.cta || "继续";
        btn.addEventListener("click", () => onResume?.(resume, data));
        actionsEl.appendChild(btn);
        const eid = data.result?.event?.event_id || data.event_id;
        if (eid && baseUrl) {
          const a = document.createElement("a");
          a.className = "rpLink";
          a.target = "_blank";
          a.rel = "noopener noreferrer";
          a.href = `${baseUrl}/api/replan/events/${encodeURIComponent(eid)}`;
          a.textContent = "审计轨迹";
          actionsEl.appendChild(a);
        }
      }
    }
    root.classList.add("rpJourney--complete");
    const pulse = root.querySelector(".rpJourneyPulse");
    if (pulse) pulse.hidden = true;
    scrollJourneyIntoView(root);
    onComplete?.(data);
  })();

  return { wrap: root, done, getRoot: () => root };
}

/** Normalize live WS / mesh guided payloads into demo-shaped journey data */
export function normalizeReplanJourneyData(raw) {
  if (!raw || typeof raw !== "object") return null;
  if (Array.isArray(raw.guided_steps) && raw.guided_steps.length) {
    return {
      case_id: raw.case_id || null,
      title: raw.title || "失败驱动重规划",
      guided_steps: raw.guided_steps,
      resume: raw.resume || null,
      result: raw.result || {
        event: raw.event_id ? { event_id: raw.event_id } : null,
        actions: raw.actions || [],
        theta_before: raw.theta_before || {},
        theta_after: raw.theta_after || {},
      },
      event_id: raw.event_id || raw.result?.event?.event_id || null,
      feedback_before: raw.feedback_before || null,
      outcome: raw.outcome || null,
      ok: raw.ok !== false,
      theta_after: raw.theta_after || raw.result?.theta_after || null,
    };
  }
  return null;
}

export function replanDataToJourneyPayload(data) {
  const norm = normalizeReplanJourneyData(data) || data;
  return {
    html: buildReplanJourneyShell(norm.title || "失败驱动重规划", norm.case_id),
    plainSummary: `${norm.title || "重规划"} · 逐步恢复`,
    journeyData: norm,
    isJourney: true,
  };
}
