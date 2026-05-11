import React from "react";
import { MUTED } from "../constants";

export const ChromeBrowser: React.FC<{
  url: string;
  children?: React.ReactNode;
  height?: number;
}> = ({ url, children, height = 52 }) => {
  return (
    <div
      style={{
        borderBottom: "1px solid rgba(15,23,42,.08)",
        background: "linear-gradient(180deg, #f8fafc, #f1f5f9)",
      }}
    >
      <div
        style={{
          height,
          display: "flex",
          alignItems: "center",
          padding: "0 18px",
          gap: 10,
        }}
      >
        <div style={{ display: "flex", gap: 7 }}>
          {["#ff5f57", "#febc2e", "#28c840"].map((c) => (
            <div
              key={c}
              style={{
                width: 12,
                height: 12,
                borderRadius: 999,
                background: c,
                opacity: 0.95,
              }}
            />
          ))}
        </div>
        <div
          style={{
            flex: 1,
            marginLeft: 8,
            height: 30,
            borderRadius: 10,
            background: "rgba(255,255,255,.9)",
            border: "1px solid rgba(15,23,42,.08)",
            display: "flex",
            alignItems: "center",
            padding: "0 14px",
            fontSize: 14,
            color: MUTED,
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
          }}
        >
          {url}
        </div>
      </div>
      {children ?? null}
    </div>
  );
};
