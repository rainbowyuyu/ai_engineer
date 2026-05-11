import React from "react";
import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import {
  ACCENT,
  MUTED,
  SEQUENCE_DURATION,
  TEXT,
  stackLayerOpacity,
} from "../constants";

const CHAPTER_INDEX = 0;

export const Ch00Hook: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const seqDur = SEQUENCE_DURATION[CHAPTER_INDEX];
  const stackOp = stackLayerOpacity(frame, seqDur, CHAPTER_INDEX);

  const t = spring({ frame, fps, config: { damping: 14, mass: 0.7 } });
  const titleY = interpolate(t, [0, 1], [28, 0], { easing: Easing.out(Easing.cubic) });
  const titleOp = interpolate(t, [0, 1], [0, 1]);
  const subOp = interpolate(frame, [12, 38], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.quad),
  });
  const badgeOp = interpolate(frame, [22, 48], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const zoom = interpolate(
    frame,
    [0, seqDur - 40],
    [1, 1.03],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.inOut(Easing.quad),
    },
  );

  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        pointerEvents: "none",
        opacity: stackOp,
      }}
    >
      <div
        style={{
          textAlign: "center",
          maxWidth: 1100,
          padding: "0 48px",
          transform: `translateY(${titleY}px) scale(${zoom})`,
        }}
      >
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 10,
            padding: "8px 16px",
            borderRadius: 999,
            background: "rgba(37,99,235,.08)",
            border: "1px solid rgba(37,99,235,.22)",
            color: ACCENT,
            fontSize: 22,
            fontWeight: 600,
            letterSpacing: 0.3,
            marginBottom: 22,
            opacity: badgeOp,
          }}
        >
          AI Engineer · 结构仿真与拓扑优化工作台
        </div>
        <div
          style={{
            fontSize: 86,
            fontWeight: 800,
            letterSpacing: -1.5,
            color: TEXT,
            lineHeight: 1.05,
            opacity: titleOp,
          }}
        >
          一句话，跑通工程闭环
        </div>
        <div
          style={{
            marginTop: 20,
            fontSize: 32,
            color: MUTED,
            fontWeight: 500,
            lineHeight: 1.45,
            opacity: subOp,
          }}
        >
          上传模型 · 对话审阅 · 设计域体网格 · BESO 编排 · 结果查看器回放
        </div>
      </div>
    </AbsoluteFill>
  );
};
