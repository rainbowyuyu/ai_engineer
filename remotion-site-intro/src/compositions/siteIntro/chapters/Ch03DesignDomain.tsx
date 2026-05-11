import React from "react";
import {
  AbsoluteFill,
  Img,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {
  ACCENT2,
  MUTED,
  SEQUENCE_DURATION,
  TEXT,
  stackLayerOpacity,
} from "../constants";
import { ChromeBrowser } from "../components/ChromeBrowser";
import { StepRail } from "../components/StepRail";

const CHAPTER_INDEX = 3;
const SCREEN = "onboarding/ch03-design-domain.png";

const STEPS = ["几何与导入", "体网格", "载荷 INP", "收尾与导出"] as const;

export const Ch03DesignDomain: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const seqDur = SEQUENCE_DURATION[CHAPTER_INDEX];
  const stackOp = stackLayerOpacity(frame, seqDur, CHAPTER_INDEX);

  const activeIndex = Math.min(
    STEPS.length - 1,
    Math.floor(
      interpolate(frame, [100, 1650], [0, 3.99], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      }),
    ),
  );

  const enter = spring({
    frame: frame - 8,
    fps,
    config: { damping: 17, mass: 0.82 },
  });
  const op = interpolate(enter, [0, 1], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const pulse = interpolate(Math.sin(frame * 0.09), [-1, 1], [0.55, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        pointerEvents: "none",
        opacity: stackOp * op,
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
        <ChromeBrowser url="https://localhost · 子流程 · 设计域（OC4）">
        <div style={{ display: "flex", minHeight: 560 }}>
          <div
            style={{
              width: 340,
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
              步骤链
            </div>
            <StepRail
              frame={frame}
              labels={[...STEPS]}
              activeIndex={activeIndex}
            />
          </div>
          <div style={{ flex: 1, position: "relative" }}>
            <Img
              src={staticFile(SCREEN)}
              style={{
                width: "100%",
                height: "100%",
                objectFit: "cover",
                opacity: 0.88,
              }}
            />
            <div
              style={{
                position: "absolute",
                inset: 0,
                padding: 24,
                display: "flex",
                flexDirection: "column",
                gap: 14,
                background:
                  "linear-gradient(90deg, rgba(255,255,255,.86), rgba(255,255,255,.55))",
              }}
            >
              <div
                style={{
                  fontSize: 15,
                  fontWeight: 900,
                  color: ACCENT2,
                  letterSpacing: 1.4,
                }}
              >
                STEP / 网格工作区（示意）
              </div>
              <div
                style={{
                  flex: 1,
                  borderRadius: 18,
                  border: `1px solid rgba(16,185,129,${0.15 + pulse * 0.35})`,
                  background: "rgba(255,255,255,.72)",
                  display: "grid",
                  placeItems: "center",
                  fontSize: 22,
                  fontWeight: 800,
                  color: TEXT,
                }}
              >
                当前步骤：{STEPS[activeIndex]}
              </div>
              <div
                style={{
                  borderRadius: 14,
                  padding: "12px 14px",
                  background: "rgba(15,23,42,.04)",
                  border: "1px solid rgba(15,23,42,.08)",
                  fontSize: 16,
                  color: MUTED,
                  fontWeight: 600,
                  lineHeight: 1.45,
                }}
              >
                底部提示：按方法论完成几何→网格→载荷；错误分支不在此演示，仅展示成功路径语义。
              </div>
            </div>
          </div>
        </div>
        </ChromeBrowser>
      </div>
    </AbsoluteFill>
  );
};
