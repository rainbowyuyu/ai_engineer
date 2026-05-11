import React from "react";
import { ACCENT, ACCENT2, MUTED, TEXT } from "../constants";

export const ChatBubble: React.FC<{
  role: "user" | "assistant";
  text: string;
  opacity: number;
  y: number;
}> = ({ role, text, opacity, y }) => {
  const isUser = role === "user";
  return (
    <div
      style={{
        display: "flex",
        justifyContent: isUser ? "flex-end" : "flex-start",
        marginBottom: 14,
        opacity,
        transform: `translateY(${y}px)`,
      }}
    >
      <div
        style={{
          maxWidth: "min(920px, 86%)",
          borderRadius: 16,
          padding: "16px 18px",
          background: isUser
            ? "linear-gradient(135deg, rgba(37,99,235,.12), rgba(37,99,235,.06))"
            : "rgba(255,255,255,.95)",
          border: `1px solid ${
            isUser ? "rgba(37,99,235,.22)" : "rgba(15,23,42,.08)"
          }`,
          boxShadow: isUser
            ? "0 10px 28px rgba(37,99,235,.12)"
            : "0 10px 28px rgba(15,23,42,.08)",
        }}
      >
        <div
          style={{
            fontSize: 12,
            fontWeight: 800,
            letterSpacing: 1.2,
            color: isUser ? ACCENT : ACCENT2,
            marginBottom: 8,
          }}
        >
          {isUser ? "用户" : "助手"}
        </div>
        <div
          style={{
            fontSize: 22,
            lineHeight: 1.55,
            color: TEXT,
            fontWeight: 500,
          }}
        >
          {text}
        </div>
        <div style={{ marginTop: 10, fontSize: 14, color: MUTED }}>
          {isUser ? "附件：IGES · 上下文已带入任务" : "可继续在侧栏追问或切换工具模式"}
        </div>
      </div>
    </div>
  );
};
