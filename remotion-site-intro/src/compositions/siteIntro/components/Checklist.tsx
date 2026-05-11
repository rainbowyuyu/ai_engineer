import React from "react";
import { Easing, interpolate } from "remotion";
import { ACCENT2, MUTED, TEXT } from "../constants";

export const Checklist: React.FC<{
  frame: number;
  items: string[];
  /** 每条开始显现的全局偏移（相对章节起点） */
  staggerFrom?: number;
}> = ({ frame, items, staggerFrom = 0 }) => {
  return (
    <div
      style={{
        borderRadius: 18,
        padding: "22px 22px",
        background: "rgba(255,255,255,.92)",
        border: "1px solid rgba(15,23,42,.10)",
        boxShadow: "0 18px 46px rgba(15,23,42,.10)",
      }}
    >
      <div
        style={{
          fontSize: 14,
          fontWeight: 900,
          letterSpacing: 2,
          color: MUTED,
          marginBottom: 14,
        }}
      >
        第一次使用 · 成功路径
      </div>
      {items.map((it, i) => {
        const start = staggerFrom + i * 36;
        const check = interpolate(frame, [start + 8, start + 34], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: Easing.out(Easing.cubic),
        });
        const rowOp = interpolate(frame, [start, start + 22], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
        return (
          <div
            key={it}
            style={{
              display: "flex",
              gap: 14,
              alignItems: "flex-start",
              padding: "12px 6px",
              borderRadius: 14,
              opacity: rowOp,
              background: "rgba(248,250,252,.9)",
              border: "1px solid rgba(15,23,42,.06)",
              marginBottom: 10,
            }}
          >
            <div
              style={{
                width: 26,
                height: 26,
                borderRadius: 8,
                border: `2px solid ${ACCENT2}`,
                display: "grid",
                placeItems: "center",
                color: "#fff",
                background: `rgba(16,185,129,${0.15 + 0.85 * check})`,
                fontWeight: 900,
                fontSize: 14,
                flexShrink: 0,
              }}
            >
              {check > 0.85 ? "✓" : ""}
            </div>
            <div
              style={{
                fontSize: 20,
                lineHeight: 1.45,
                color: TEXT,
                fontWeight: 600,
              }}
            >
              {it}
            </div>
          </div>
        );
      })}
    </div>
  );
};
