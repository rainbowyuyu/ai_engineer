import React from "react";
import { Easing, interpolate } from "remotion";
import { ACCENT, ACCENT2, MUTED, TEXT } from "../constants";

export const StepRail: React.FC<{
  frame: number;
  labels: string[];
  activeIndex: number;
}> = ({ frame, labels, activeIndex }) => {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {labels.map((label, i) => {
        const done = i < activeIndex;
        const active = i === activeIndex;
        const pulse = active
          ? interpolate(Math.sin(frame * 0.12), [-1, 1], [0.92, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            })
          : 1;
        const bar = interpolate(
          frame - i * 10,
          [0, 26],
          [0, 1],
          {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.out(Easing.cubic),
          },
        );
        return (
          <div
            key={label}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 14,
              opacity: bar,
            }}
          >
            <div
              style={{
                width: 36,
                height: 36,
                borderRadius: 12,
                display: "grid",
                placeItems: "center",
                fontWeight: 900,
                fontSize: 15,
                color: done || active ? "#fff" : MUTED,
                background: done
                  ? ACCENT2
                  : active
                    ? ACCENT
                    : "rgba(15,23,42,.06)",
                transform: `scale(${pulse})`,
                border: active ? "1px solid rgba(255,255,255,.35)" : "1px solid transparent",
              }}
            >
              {i + 1}
            </div>
            <div style={{ flex: 1 }}>
              <div
                style={{
                  fontSize: 20,
                  fontWeight: 800,
                  color: active || done ? TEXT : MUTED,
                }}
              >
                {label}
              </div>
              <div style={{ fontSize: 14, color: MUTED, marginTop: 4 }}>
                {done ? "已完成" : active ? "进行中…" : "待开始"}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};
