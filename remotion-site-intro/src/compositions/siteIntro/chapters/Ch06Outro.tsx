import React from "react";
import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { SEQUENCE_DURATION, stackLayerOpacity } from "../constants";

const CHAPTER_INDEX = 6;

export const Ch06Outro: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const seqDur = SEQUENCE_DURATION[CHAPTER_INDEX];
  const stackOp = stackLayerOpacity(frame, seqDur, CHAPTER_INDEX);

  const s = spring({
    frame: frame - 20,
    fps,
    config: { damping: 14, mass: 0.65 },
  });
  const op = interpolate(s, [0, 1], [0, 1], { extrapolateRight: "clamp" });
  const line = interpolate(frame, [80, 130], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
  const cta2 = interpolate(frame, [140, 200], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });

  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        background:
          "radial-gradient(900px 520px at 50% 40%, rgba(37,99,235,.16), transparent 62%), radial-gradient(700px 480px at 70% 70%, rgba(16,185,129,.12), transparent 55%)",
        opacity: stackOp * op,
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          textAlign: "center",
          maxWidth: 1040,
          padding: "0 40px",
        }}
      >
        <div
          style={{
            fontSize: 58,
            fontWeight: 800,
            color: "#fff",
            textShadow: "0 2px 28px rgba(0,0,0,.25)",
          }}
        >
          AI Engineer
        </div>
        <div
          style={{
            marginTop: 16,
            fontSize: 28,
            fontWeight: 500,
            color: "rgba(255,255,255,.88)",
            lineHeight: 1.5,
            opacity: line,
          }}
        >
          工程意图 → 可执行工作流 → 可验证交付物
        </div>
        <div
          style={{
            marginTop: 36,
            display: "flex",
            gap: 18,
            justifyContent: "center",
            flexWrap: "wrap",
            opacity: cta2,
          }}
        >
          {[
            { t: "打开工作台", sub: "本地 / 部署入口（占位文案）" },
            { t: "阅读文档", sub: "安装、子流程与编排说明（占位文案）" },
          ].map((c) => (
            <div
              key={c.t}
              style={{
                minWidth: 280,
                padding: "18px 22px",
                borderRadius: 16,
                background: "rgba(255,255,255,.14)",
                border: "1px solid rgba(255,255,255,.35)",
                color: "#fff",
                textAlign: "left",
              }}
            >
              <div style={{ fontSize: 22, fontWeight: 900 }}>{c.t}</div>
              <div style={{ marginTop: 8, fontSize: 15, color: "rgba(255,255,255,.82)" }}>
                {c.sub}
              </div>
            </div>
          ))}
        </div>
      </div>
    </AbsoluteFill>
  );
};
