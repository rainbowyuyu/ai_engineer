import React from "react";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {
  ACCENT,
  MUTED,
  SEQUENCE_DURATION,
  TEXT,
  stackLayerOpacity,
} from "../constants";
import { ChromeBrowser } from "../components/ChromeBrowser";
import { StepRail } from "../components/StepRail";

const CHAPTER_INDEX = 4;

const ORCH_STEPS = ["准备", "拓扑优化", "后处理", "汇总"] as const;

const LOG_LINES = [
  "[编排] 载入上一步 INP …",
  "[流式] 解析材料与截面 …",
  "[流式] BESO 迭代 12 / 80 …",
  "[流式] 写出 VTK / STEP …",
  "[汇总] 指标：柔度 ↓ 18.4% · 质量 ↓ 6.1%",
];

export const Ch04Orchestrate: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const seqDur = SEQUENCE_DURATION[CHAPTER_INDEX];
  const stackOp = stackLayerOpacity(frame, seqDur, CHAPTER_INDEX);

  const activeIndex = Math.min(
    ORCH_STEPS.length - 1,
    Math.floor(
      interpolate(frame, [90, 1200], [0, 3.99], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      }),
    ),
  );

  const enter = spring({
    frame: frame - 10,
    fps,
    config: { damping: 16, mass: 0.8 },
  });
  const shell = interpolate(enter, [0, 1], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        pointerEvents: "none",
        opacity: stackOp * shell,
      }}
    >
      <div
        style={{
          width: "min(1220px, 90vw)",
          borderRadius: 20,
          overflow: "hidden",
          boxShadow:
            "0 32px 80px rgba(15,23,42,.14), 0 0 0 1px rgba(15,23,42,.06)",
          background: "#fff",
        }}
      >
        <ChromeBrowser url="https://localhost · 子流程 · 构型优化编排">
        <div style={{ display: "flex", minHeight: 540 }}>
          <div
            style={{
              width: 320,
              borderRight: "1px solid rgba(15,23,42,.06)",
              padding: 22,
              background: "#f8fafc",
            }}
          >
            <div
              style={{
                fontSize: 12,
                fontWeight: 900,
                letterSpacing: 2,
                color: MUTED,
                marginBottom: 14,
              }}
            >
              四步编排
            </div>
            <StepRail
              frame={frame}
              labels={[...ORCH_STEPS]}
              activeIndex={activeIndex}
            />
          </div>
          <div
            style={{
              flex: 1,
              padding: 22,
              background:
                "linear-gradient(180deg, rgba(15,23,42,.04), rgba(255,255,255,.9))",
              display: "flex",
              flexDirection: "column",
              gap: 12,
            }}
          >
            <div
              style={{
                fontSize: 15,
                fontWeight: 900,
                color: ACCENT,
                letterSpacing: 1.2,
              }}
            >
              编排流 · 伪终端 / 日志
            </div>
            <div
              style={{
                flex: 1,
                borderRadius: 16,
                padding: 16,
                background: "#0b1220",
                border: "1px solid rgba(15,23,42,.35)",
                fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
                fontSize: 15,
                lineHeight: 1.65,
                color: "rgba(226,232,240,.92)",
                overflow: "hidden",
              }}
            >
              {LOG_LINES.map((line, i) => {
                const o = interpolate(frame, [70 + i * 45, 110 + i * 45], [0, 1], {
                  extrapolateLeft: "clamp",
                  extrapolateRight: "clamp",
                  easing: Easing.out(Easing.cubic),
                });
                const x = interpolate(frame, [70 + i * 45, 105 + i * 45], [10, 0], {
                  extrapolateLeft: "clamp",
                  extrapolateRight: "clamp",
                  easing: Easing.out(Easing.cubic),
                });
                return (
                  <div
                    key={line}
                    style={{
                      opacity: o,
                      transform: `translateX(${x}px)`,
                      whiteSpace: "pre-wrap",
                    }}
                  >
                    {line}
                  </div>
                );
              })}
              <div
                style={{
                  marginTop: 14,
                  height: 10,
                  width: `${40 + interpolate(frame % 60, [0, 60], [0, 40], {
                    extrapolateLeft: "clamp",
                    extrapolateRight: "clamp",
                  })}%`,
                  borderRadius: 6,
                  background: "rgba(148,163,184,.35)",
                }}
              />
            </div>
            <div
              style={{
                borderRadius: 14,
                padding: "12px 14px",
                border: "1px solid rgba(15,23,42,.08)",
                background: "rgba(255,255,255,.86)",
                fontSize: 16,
                color: TEXT,
                fontWeight: 600,
              }}
            >
              右侧面板语义：流式日志 + 汇总卡片；与侧栏任务联动查看历史。
            </div>
          </div>
        </div>
        </ChromeBrowser>
      </div>
    </AbsoluteFill>
  );
};
