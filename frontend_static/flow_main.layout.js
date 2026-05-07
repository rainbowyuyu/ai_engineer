export function createLayoutManager(deps) {
  const { refs, state } = deps;
  const railStops = [refs.railStop1, refs.railStop2, refs.railStop3, refs.railStop4];
  const railConns = [refs.railConn1, refs.railConn2, refs.railConn3];

  function ensureRailLabels() {
    railStops.forEach((el) => {
      if (!el) return;
      if (!el.dataset.label) el.dataset.label = el.textContent || "";
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

  // Minimal markdown renderer for orchestration stream.
  function renderMd(md) {
    const lines = String(md || "").split("\n");
    let out = "";
    let inList = false;
    const inline = (text) =>
      escapeHtml(text)
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/`([^`]+)`/g, "<code>$1</code>");
    for (const raw of lines) {
      const line = raw.trimEnd();
      if (!line.trim()) {
        if (inList) {
          out += "</ul>";
          inList = false;
        }
        out += '<div class="mdGap"></div>';
        continue;
      }
      if (line.startsWith("### ")) {
        if (inList) {
          out += "</ul>";
          inList = false;
        }
        out += `<h4>${inline(line.slice(4))}</h4>`;
        continue;
      }
      if (line.startsWith("## ")) {
        if (inList) {
          out += "</ul>";
          inList = false;
        }
        out += `<h3>${inline(line.slice(3))}</h3>`;
        continue;
      }
      if (line.startsWith("- ")) {
        if (!inList) {
          out += "<ul>";
          inList = true;
        }
        out += `<li>${inline(line.slice(2))}</li>`;
        continue;
      }
      if (inList) {
        out += "</ul>";
        inList = false;
      }
      out += `<p>${inline(line)}</p>`;
    }
    if (inList) out += "</ul>";
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

    if (step === 1) {
      refs.panelStep1?.classList.add("stageVisible");
      if (refs.flowStageRight) refs.flowStageRight.style.display = "none";
    } else if (step === 2) {
      refs.flowStageRight?.classList.add("stageVisibleGrid");
      refs.panelStep2?.classList.add("stageVisible");
    } else if (step === 3) {
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

  function addLandingBubble(role, text) {
    if (!refs.chatLanding) return;
    const b = document.createElement("div");
    b.className = `bubble ${role}`;
    b.textContent = text;
    refs.chatLanding.appendChild(b);
    refs.chatLanding.scrollTop = refs.chatLanding.scrollHeight;
  }

  function showStage(mode) {
    refs.landingMain?.classList.toggle("hidden", mode !== "landing");
    refs.designDomainMain?.classList.toggle("hidden", mode !== "designDomain");
    refs.orchestrateMain?.classList.toggle("hidden", mode !== "orchestrate");
    refs.flowMain?.classList.toggle("hidden", mode !== "flow");
    refs.flowStepper?.classList.toggle("hidden", mode !== "flow");
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
          "## 步骤 1｜搜索相关文件\n- 解析目标与约束，读取上传上下文\n- 扫描工作目录与 `inp`、集合与载荷\n- **IGES**：可进入「设计域」四步；体网格与 CAD 转换共用 **Plan** 弹窗；顶栏「← 设计域」可随时返回调整",
        active: 1,
        conn: 0,
      },
      {
        text: "## 步骤 2｜生成代码\n- 构建 `run_generated` 链路与脚本配置",
        active: 2,
        conn: 1,
      },
      {
        text: "## 步骤 3｜预览指标\n- 绑定 INP 与载荷映射，准备曲线与网格预览",
        active: 3,
        conn: 2,
      },
      {
        text: "## 步骤 4｜汇总与执行就绪\n- 校验清单后点击 **执行任务**",
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
      const t = setInterval(() => {
        streamMd += line[charIdx] || "";
        refs.orchestrateStream.innerHTML = renderMd(streamMd);
        refs.orchestrateStream.scrollTop = refs.orchestrateStream.scrollHeight;
        charIdx += 1;
        if (charIdx >= line.length) {
          clearInterval(t);
          phaseIdx += 1;
          setTimeout(typePhase, 380);
        }
      }, 16);
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
      btn.textContent = c ? "\u203a" : "\u2039";
      btn.setAttribute("aria-expanded", c ? "false" : "true");
      btn.title = c ? "展开任务栏" : "收起侧栏";
    }
    const aside = refs.landingMain.querySelector(".taskSidebar");
    if (aside) aside.setAttribute("aria-expanded", c ? "false" : "true");
    try {
      localStorage.setItem("beso.sidebar.collapsed", c ? "1" : "0");
    } catch {}
  }

  return {
    setStep,
    addBubble,
    addLandingBubble,
    showStage,
    goHome,
    streamOrchestration,
    renderSelectedInputs,
    setSidebarCollapsed,
  };
}
