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
import { Checklist } from "../components/Checklist";
import { CHAT_SCRIPT_CH5, TUTORIAL_CHECKLIST } from "../scripts";

const CHAPTER_INDEX = 5;

export const Ch05Tutorial: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const seqDur = SEQUENCE_DURATION[CHAPTER_INDEX];
  const stackOp = stackLayerOpacity(frame, seqDur, CHAPTER_INDEX);

  const enter = spring({
    frame: frame - 8,
    fps,
    config: { damping: 16, mass: 0.78 },
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
          width: "min(1220px, 92vw)",
          display: "grid",
          gridTemplateColumns: "1.05fr 0.95fr",
          gap: 22,
          alignItems: "stretch",
        }}
      >
        <div
          style={{
            borderRadius: 20,
            overflow: "hidden",
            boxShadow:
              "0 32px 80px rgba(15,23,42,.12), 0 0 0 1px rgba(15,23,42,.06)",
            background: "linear-gradient(180deg, #ffffff, #f8fafc)",
          }}
        >
          <ChromeBrowser url="https://localhost · 示例与教程（模拟）">
          <div style={{ padding: "18px 22px 26px" }}>
            <div
              style={{
                fontSize: 13,
                fontWeight: 900,
                color: MUTED,
                letterSpacing: 1.6,
                marginBottom: 12,
              }}
            >
              固定脚本对话
            </div>
            {CHAT_SCRIPT_CH5.map((msg, i) => {
              const start = 90 + i * 88;
              const bOp = interpolate(frame, [start, start + 36], [0, 1], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
                easing: Easing.out(Easing.cubic),
              });
              const y = interpolate(frame, [start, start + 32], [16, 0], {
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
          </ChromeBrowser>
        </div>
        <div
          style={{
            borderRadius: 20,
            padding: 20,
            background:
              "radial-gradient(700px 420px at 20% 0%, rgba(37,99,235,.10), transparent 55%), #ffffff",
            border: "1px solid rgba(15,23,42,.08)",
            boxShadow: "0 24px 70px rgba(15,23,42,.10)",
            display: "flex",
            flexDirection: "column",
            gap: 14,
          }}
        >
          <div style={{ fontSize: 22, fontWeight: 900, color: TEXT }}>
            教程感清单（checkbox 逐条点亮）
          </div>
          <div style={{ fontSize: 15, color: MUTED, fontWeight: 600, lineHeight: 1.5 }}>
            将 `public/onboarding/*.png` 替换为你的高清截图即可提升成片质感；本段以清单动画为主。
          </div>
          <Checklist frame={frame} items={TUTORIAL_CHECKLIST} staggerFrom={420} />
          <div
            style={{
              marginTop: "auto",
              padding: "12px 14px",
              borderRadius: 14,
              background: "rgba(37,99,235,.06)",
              border: "1px solid rgba(37,99,235,.18)",
              color: ACCENT,
              fontWeight: 800,
              fontSize: 14,
            }}
          >
            仓库示例：可参考 `examples/beso` 的说明性标题；视频内不硬编码长路径。
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
