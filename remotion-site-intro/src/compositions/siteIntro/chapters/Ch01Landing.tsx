import React from "react";
import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {
  ACCENT,
  ACCENT2,
  MUTED,
  SEQUENCE_DURATION,
  TEXT,
  stackLayerOpacity,
} from "../constants";
import { ChromeBrowser } from "../components/ChromeBrowser";

const CHAPTER_INDEX = 1;
const SCREEN = "onboarding/ch01-landing.png";

export const Ch01Landing: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const seqDur = SEQUENCE_DURATION[CHAPTER_INDEX];
  const stackOp = stackLayerOpacity(frame, seqDur, CHAPTER_INDEX);

  const enter = spring({
    frame: frame - 24,
    fps,
    config: { damping: 18, mass: 0.85 },
  });
  const scale = interpolate(enter, [0, 1], [0.94, 1], { extrapolateRight: "clamp" });
  const op = interpolate(enter, [0, 1], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const floatY = interpolate(Math.sin(frame * 0.04), [-1, 1], [-3, 3]);

  const designHl = interpolate(
    frame,
    [120, 220, 380, 520],
    [0.35, 1, 1, 0.45],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const orchHl = interpolate(
    frame,
    [520, 620, 880, 1020],
    [0.35, 1, 1, 0.45],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  const rail = interpolate(frame, [40, 120], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
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
          position: "relative",
          width: "min(1240px, 88vw)",
          transform: `scale(${scale}) translateY(${floatY}px)`,
          borderRadius: 20,
          boxShadow:
            "0 32px 80px rgba(15,23,42,.14), 0 0 0 1px rgba(15,23,42,.06), inset 0 1px 0 rgba(255,255,255,.85)",
          background: "linear-gradient(180deg, #ffffff 0%, #fafbff 100%)",
          overflow: "hidden",
        }}
      >
        <ChromeBrowser url="https://localhost · AI Engineer · 主页工作台">
        <div style={{ display: "flex", height: 560 }}>
          <div
            style={{
              width: 230,
              borderRight: "1px solid rgba(15,23,42,.06)",
              background: "#f4f4f5",
              padding: "16px 12px",
              opacity: rail,
            }}
          >
            <div
              style={{
                fontSize: 11,
                fontWeight: 800,
                color: "#94a3b8",
                letterSpacing: 1.2,
                marginBottom: 10,
              }}
            >
              任务
            </div>
            {[0, 1, 2, 3, 4].map((i) => {
              const w = interpolate(frame, [50 + i * 8, 90 + i * 8], [0.2, 1], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
                easing: Easing.out(Easing.cubic),
              });
              return (
                <div
                  key={i}
                  style={{
                    height: 42,
                    borderRadius: 10,
                    marginBottom: 8,
                    background: "#fff",
                    border: "1px solid rgba(15,23,42,.06)",
                    transform: `scaleX(${w})`,
                    transformOrigin: "left center",
                  }}
                />
              );
            })}
          </div>
          <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
            <div
              style={{
                padding: "16px 22px 10px",
                display: "flex",
                gap: 12,
                alignItems: "center",
                borderBottom: "1px solid rgba(15,23,42,.06)",
              }}
            >
              <div
                style={{
                  fontSize: 13,
                  fontWeight: 800,
                  color: MUTED,
                  letterSpacing: 1.6,
                }}
              >
                子流程
              </div>
              {[
                { t: "设计域（OC4）", k: "d" as const },
                { t: "构型优化编排", k: "o" as const },
              ].map((b) => {
                const hl = b.k === "d" ? designHl : orchHl;
                return (
                  <div
                    key={b.k}
                    style={{
                      padding: "8px 14px",
                      borderRadius: 999,
                      fontSize: 14,
                      fontWeight: 800,
                      color: hl > 0.75 ? "#fff" : TEXT,
                      background:
                        b.k === "d"
                          ? `rgba(37,99,235,${0.08 + hl * 0.85})`
                          : `rgba(16,185,129,${0.08 + hl * 0.75})`,
                      border: `1px solid ${
                        b.k === "d"
                          ? `rgba(37,99,235,${0.2 + hl * 0.5})`
                          : `rgba(16,185,129,${0.2 + hl * 0.45})`
                      }`,
                      boxShadow:
                        hl > 0.85
                          ? "0 10px 26px rgba(15,23,42,.12)"
                          : "none",
                    }}
                  >
                    {b.t}
                  </div>
                );
              })}
            </div>
            <div style={{ flex: 1, position: "relative" }}>
              <Img
                src={staticFile(SCREEN)}
                style={{
                  width: "100%",
                  height: "100%",
                  objectFit: "cover",
                  opacity: 0.92,
                }}
              />
              <div
                style={{
                  position: "absolute",
                  inset: 0,
                  background:
                    "linear-gradient(180deg, rgba(247,248,251,.15), rgba(255,255,255,.72))",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "flex-end",
                  padding: 22,
                }}
              >
                <div
                  style={{
                    borderRadius: 18,
                    padding: "16px 18px",
                    background: "rgba(255,255,255,.92)",
                    border: "1px solid rgba(15,23,42,.10)",
                    boxShadow: "0 18px 46px rgba(15,23,42,.10)",
                  }}
                >
                  <div
                    style={{
                      fontSize: 12,
                      fontWeight: 900,
                      letterSpacing: 2,
                      color: MUTED,
                      marginBottom: 10,
                    }}
                  >
                    输入区
                  </div>
                  <div
                    style={{
                      height: 10,
                      width: "62%",
                      borderRadius: 6,
                      background: "rgba(15,23,42,.08)",
                      marginBottom: 12,
                    }}
                  />
                  <div
                    style={{
                      height: 10,
                      width: "44%",
                      borderRadius: 6,
                      background: "rgba(15,23,42,.06)",
                    }}
                  />
                  <div
                    style={{
                      marginTop: 12,
                      display: "flex",
                      gap: 10,
                      flexWrap: "wrap",
                    }}
                  >
                    {["上传 IGES", "引用任务", "深度思考"].map((x, i) => {
                      const o = interpolate(frame, [140 + i * 18, 190 + i * 18], [0, 1], {
                        extrapolateLeft: "clamp",
                        extrapolateRight: "clamp",
                      });
                      return (
                        <div
                          key={x}
                          style={{
                            opacity: o,
                            padding: "6px 10px",
                            borderRadius: 999,
                            fontSize: 13,
                            fontWeight: 800,
                            color: ACCENT,
                            border: "1px solid rgba(37,99,235,.22)",
                            background: "rgba(37,99,235,.06)",
                          }}
                        >
                          {x}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        </ChromeBrowser>
        <div
          style={{
            position: "absolute",
            right: 48,
            top: 120,
            width: 320,
            padding: 16,
            borderRadius: 16,
            background: "rgba(255,255,255,.88)",
            border: "1px solid rgba(15,23,42,.08)",
            boxShadow: "0 18px 44px rgba(15,23,42,.10)",
            opacity: interpolate(frame, [200, 280], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            }),
          }}
        >
          <div style={{ fontSize: 13, fontWeight: 900, color: ACCENT2, marginBottom: 8 }}>
            侧栏智能体
          </div>
          <div style={{ fontSize: 16, color: TEXT, lineHeight: 1.5, fontWeight: 600 }}>
            多轮对话、附件卡片与任务列表同屏；子流程与编排状态可回放。
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
