/**
 * Oil Motion scroll intro — baked project video frame-scrub → LLM chat.
 * Visuals composed from docs/assets + brand mark (product CSS language).
 */
const STORAGE_KEY = "beso_oil_intro_done_v3";
const TIMELINE_URL = "./oil_motion_ai_engineer/build/timeline.json";

function prefersReducedMotion() {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

function shouldShowIntro() {
  try {
    const q = new URLSearchParams(window.location.search || "");
    if (q.get("intro") === "0" || q.get("skip_intro") === "1") return false;
    if (q.get("demo") || q.get("live") || q.get("stage")) return false;
    if (q.get("intro") === "1" || q.get("oil") === "1") return true;
    return sessionStorage.getItem(STORAGE_KEY) !== "1";
  } catch {
    return true;
  }
}

function markSeen() {
  try {
    sessionStorage.setItem(STORAGE_KEY, "1");
  } catch {
    /* ignore */
  }
}

function pickMedia(timeline) {
  const media = timeline?.media || {};
  const narrow =
    typeof window.matchMedia === "function" && window.matchMedia("(max-width: 720px)").matches;
  return {
    src: narrow ? media.mobile || media.desktop : media.desktop || media.mobile,
    poster: media.poster || "./oil_motion_ai_engineer/final/poster.png",
  };
}

function captionForProgress(timeline, progress) {
  const states = timeline?.states || [];
  if (!states.length) return { title: "The AI Engineer", caption: "" };
  const dur = Math.max(1e-6, Number(timeline.duration) || states[states.length - 1].hold || 1);
  const t = progress * dur;
  let best = states[0];
  for (const s of states) {
    if (Number(s.hold) <= t + 1e-6) best = s;
  }
  return { title: best.title || best.id, caption: best.caption || "" };
}

function mountIntroDom(poster) {
  let root = document.getElementById("besoOilIntro");
  if (root) return root;
  root = document.createElement("div");
  root.id = "besoOilIntro";
  root.className = "besoOilIntro besoOilIntro--product";
  root.setAttribute("role", "region");
  root.setAttribute("aria-label", "The AI Engineer 滚动叙事入口");
  root.innerHTML = `
    <div class="besoOilIntroTrack" id="besoOilIntroTrack">
      <div class="besoOilIntroSticky">
        <div class="besoOilIntroStage besoOilIntroStage--product">
          <video
            class="besoOilIntroVideo"
            id="besoOilIntroVideo"
            muted
            playsinline
            preload="auto"
            ${poster ? `poster="${poster}"` : ""}
          ></video>
          <div class="besoOilIntroChrome">
            <div class="besoOilIntroChromeTop">
              <img class="besoOilIntroMark" src="./assets/beso-agent-mark.svg" width="28" height="28" alt="" />
              <div class="besoOilIntroChromeBrand">
                <strong>The AI Engineer</strong>
                <span>项目构型叙事 · 滚动驱动视频</span>
              </div>
            </div>
            <div class="besoOilIntroHud">
              <div class="besoOilIntroBar" aria-hidden="true"><i id="besoOilIntroBarFill"></i></div>
              <p class="besoOilIntroHint" id="besoOilIntroHint">向下滚动，视频画面随进度变化</p>
              <p class="besoOilIntroLiveCap" id="besoOilIntroLiveCap" hidden></p>
            </div>
          </div>
          <button type="button" class="besoOilIntroSkip" id="besoOilIntroSkip">跳过 · 进入对话</button>
          <button type="button" class="besoOilIntroEnter hidden" id="besoOilIntroEnter">进入大模型工作台 →</button>
        </div>
      </div>
    </div>
  `;
  const app = document.querySelector(".app");
  if (app?.parentNode) app.parentNode.insertBefore(root, app);
  else document.body.prepend(root);
  return root;
}

function finishIntro(root, { smooth = true } = {}) {
  if (!root || root.classList.contains("besoOilIntro--done")) return;
  markSeen();
  root.classList.add("besoOilIntro--done");
  document.body.classList.remove("besoOilIntroActive");
  document.body.classList.add("besoOilIntroFinished");
  try {
    const track = root.querySelector(".besoOilIntroTrack");
    if (track) track.style.height = "0px";
  } catch {
    /* ignore */
  }
  const focusChat = () => {
    try {
      window.scrollTo({ top: 0, behavior: smooth ? "smooth" : "auto" });
      const composer =
        document.getElementById("landingComposerDock") || document.getElementById("chatLanding");
      composer?.scrollIntoView?.({ behavior: smooth ? "smooth" : "auto", block: "center" });
      const ta = document.querySelector(
        "#landingComposerDock textarea, #promptLanding, textarea.homeComposerInput",
      );
      if (ta && typeof ta.focus === "function") setTimeout(() => ta.focus(), 320);
    } catch {
      /* ignore */
    }
  };
  focusChat();
  setTimeout(() => {
    try {
      root.remove();
    } catch {
      /* ignore */
    }
    focusChat();
  }, 720);
}

async function loadTimeline() {
  const res = await fetch(TIMELINE_URL, { cache: "no-cache" });
  if (!res.ok) throw new Error(`timeline ${res.status}`);
  return res.json();
}

export async function initBesoOilIntro() {
  if (!shouldShowIntro()) {
    document.body.classList.add("besoOilIntroFinished");
    return { skipped: true };
  }

  let timeline;
  try {
    timeline = await loadTimeline();
  } catch (err) {
    console.warn("[oil-intro] timeline load failed, skip", err);
    document.body.classList.add("besoOilIntroFinished");
    return { skipped: true, reason: "timeline" };
  }

  const { src, poster } = pickMedia(timeline);
  if (!src) {
    document.body.classList.add("besoOilIntroFinished");
    return { skipped: true, reason: "media" };
  }

  const reduced = prefersReducedMotion();
  const root = mountIntroDom(poster);
  document.body.classList.add("besoOilIntroActive");

  const video = document.getElementById("besoOilIntroVideo");
  const barFill = document.getElementById("besoOilIntroBarFill");
  const hintEl = document.getElementById("besoOilIntroHint");
  const skipBtn = document.getElementById("besoOilIntroSkip");
  const enterBtn = document.getElementById("besoOilIntroEnter");
  const track = document.getElementById("besoOilIntroTrack");

  video.src = src;
  video.pause();
  try {
    video.load();
  } catch {
    /* ignore */
  }

  const fps = Number(timeline.fps) || 30;
  const frameCount = Math.max(
    1,
    Number(timeline.frameCount) || Math.round((Number(timeline.duration) || 1) * fps),
  );
  let duration = Number(timeline.duration) || frameCount / fps;

  let completed = false;
  let targetTime = 0;
  let seeking = false;
  let seekUnlockTimer = 0;
  let raf = 0;
  let lastCap = "";

  const unlockSeek = () => {
    seeking = false;
    if (seekUnlockTimer) {
      clearTimeout(seekUnlockTimer);
      seekUnlockTimer = 0;
    }
  };

  video.addEventListener("seeked", unlockSeek);
  video.addEventListener("loadedmetadata", () => {
    if (Number.isFinite(video.duration) && video.duration > 0) {
      duration = video.duration;
    }
  });

  const commitSeek = () => {
    raf = 0;
    if (completed || !video) return;
    const dur = Math.max(duration, 0.001);
    const t = Math.min(Math.max(0, targetTime), Math.max(0, dur - 1 / fps));
    if (seeking) return;
    if (Math.abs((video.currentTime || 0) - t) < 1 / (fps * 2)) return;
    seeking = true;
    try {
      video.currentTime = t;
    } catch {
      unlockSeek();
      return;
    }
    // Prevent permanent stuck if seeked never fires
    seekUnlockTimer = window.setTimeout(unlockSeek, 180);
  };

  const queueSeek = (t) => {
    targetTime = t;
    if (!raf) raf = requestAnimationFrame(commitSeek);
  };

  const applyProgress = (p) => {
    const progress = Math.max(0, Math.min(1, p));
    if (barFill) barFill.style.width = `${(progress * 100).toFixed(2)}%`;

    const targetFrame = Math.round(progress * (frameCount - 1));
    const t = (targetFrame / Math.max(1, frameCount - 1)) * duration;
    queueSeek(t);

    const cap = captionForProgress(timeline, progress);
    const key = `${cap.title}|${cap.caption}`;
    if (key !== lastCap) {
      lastCap = key;
      // Captions are baked into the project video frames; HUD only mirrors for a11y.
      root.setAttribute("aria-label", `${cap.title}. ${cap.caption}`);
    }

    const nearEnd = progress >= 0.9;
    enterBtn?.classList.toggle("hidden", !nearEnd);
    if (hintEl) {
      hintEl.textContent = nearEnd
        ? "叙事结束 · 点击或继续滑到底进入对话"
        : "向下滚动，视频画面随进度变化（舞台固定）";
    }

    if (progress >= 0.995 && !completed) {
      completed = true;
      finishIntro(root, { smooth: true });
    }
  };

  const readProgress = () => {
    if (!track || completed) return 0;
    const rect = track.getBoundingClientRect();
    const total = Math.max(1, track.offsetHeight - window.innerHeight);
    const scrolled = Math.min(total, Math.max(0, -rect.top));
    return scrolled / total;
  };

  const onScroll = () => applyProgress(readProgress());

  const goChat = (smooth) => {
    if (completed) return;
    completed = true;
    finishIntro(root, { smooth });
  };

  skipBtn?.addEventListener("click", () => goChat(false));
  enterBtn?.addEventListener("click", () => goChat(true));

  const landing = document.getElementById("landingMain");
  let io = null;
  if (landing && typeof IntersectionObserver === "function") {
    io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting && e.intersectionRatio >= 0.35 && readProgress() >= 0.88) {
            goChat(true);
          }
        }
      },
      { threshold: [0.35] },
    );
    io.observe(landing);
  }

  if (reduced) {
    applyProgress(0.96);
    if (hintEl) hintEl.textContent = "已降低动态效果 · 可直接进入对话";
    enterBtn?.classList.remove("hidden");
  } else {
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    onScroll();
  }

  return {
    skipped: false,
    destroy() {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (raf) cancelAnimationFrame(raf);
      unlockSeek();
      try {
        io?.disconnect?.();
      } catch {
        /* ignore */
      }
    },
  };
}

if (document.readyState === "loading") {
  document.addEventListener(
    "DOMContentLoaded",
    () => {
      void initBesoOilIntro();
    },
    { once: true },
  );
} else {
  void initBesoOilIntro();
}
