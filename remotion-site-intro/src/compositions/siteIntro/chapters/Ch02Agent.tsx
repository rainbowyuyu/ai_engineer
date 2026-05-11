import React from "react";
import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import {
  ACCENT,
  MUTED,
  SEQUENCE_DURATION,
  TEXT,
  stackLayerOpacity,
} from "../constants";
import { ChromeBrowser } from "../components/ChromeBrowser";
import { ChatBubble } from "../components/ChatBubble";
import { AGENT_MODE_LABELS, CHAT_SCRIPT_CH2 } from "../scripts";

const CHAPTER_INDEX = 2;

export const Ch02Agent: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const seqDur = SEQUENCE_DURATION[CHAPTER_INDEX];
  const stackOp = stackLayerOpacity(frame, seqDur, CHAPTER_INDEX);

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
          width: "min(1180px, 90vw)",
          borderRadius: 20,
          overflow: "hidden",
          boxShadow:
            "0 32px 80px rgba(15,23,42,.14), 0 0 0 1px rgba(15,23,42,.06)",
          background: "linear-gradient(180deg, #ffffff, #f8fafc)",
        }}
      >
        <ChromeBrowser url="https://localhost · 侧栏智能体 · 多轮对话">
        <div style={{ padding: "16px 20px 10px" }}>
          <div style={{ fontSize: 13, fontWeight: 900, color: MUTED, letterSpacing: 1.6, marginBottom: 10 }}>
            模式与工具
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {AGENT_MODE_LABELS.map((label, i) => {
              const on = interpolate(
                frame,
                [40 + i * 70, 95 + i * 70, 160 + i * 70, 240 + i * 70],
                [0.25, 1, 1, 0.35],
                { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
              );
              return (
                <div
                  key={label}
                  style={{
                    padding: "8px 12px",
                    borderRadius: 999,
                    fontSize: 14,
                    fontWeight: 800,
                    color: on > 0.8 ? "#fff" : TEXT,
                    background: `rgba(37,99,235,${0.06 + on * 0.82})`,
                    border: `1px solid rgba(37,99,235,${0.18 + on * 0.55})`,
                  }}
                >
                  {label}
                </div>
              );
            })}
          </div>
        </div>
        <div
          style={{
            padding: "10px 22px 28px",
            maxHeight: 520,
            overflow: "hidden",
          }}
        >
          {CHAT_SCRIPT_CH2.map((msg, i) => {
            const start = 120 + i * 95;
            const bOp = interpolate(frame, [start, start + 40], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.out(Easing.cubic),
            });
            const y = interpolate(frame, [start, start + 34], [18, 0], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.out(Easing.cubic),
            });
            return (
              <ChatBubble
                key={i}
                role={msg.role}
                text={msg.text}
                opacity={bOp}
                y={y}
              />
            );
          })}
        </div>
        <div
          style={{
            padding: "12px 18px",
            borderTop: "1px solid rgba(15,23,42,.06)",
            fontSize: 14,
            color: ACCENT,
            fontWeight: 800,
            background: "rgba(37,99,235,.04)",
          }}
        >
          提示：动效仅使用 interpolate / spring；不使用 CSS 动画类驱动时间轴。
        </div>
        </ChromeBrowser>
      </div>
    </AbsoluteFill>
  );
};
