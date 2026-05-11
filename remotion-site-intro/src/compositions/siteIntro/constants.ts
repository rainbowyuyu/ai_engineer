/** 章节时长（帧），合计 9000 @30fps ≈ 5 分钟 */
import { Easing, interpolate } from "remotion";

export const CHAPTER_DURATIONS = [
  300, 1500, 1200, 1800, 1500, 2100, 600,
] as const;

/** 章节间叠化（上层整屏淡入盖住下层） */
export const CROSSFADE_FRAMES = 200;

export const BG0 = "#f7f8fb";
export const ACCENT = "#2563eb";
export const ACCENT2 = "#10b981";
export const TEXT = "#0f172a";
export const MUTED = "#64748b";

export type ChapterIndex = 0 | 1 | 2 | 3 | 4 | 5 | 6;

export function chapterStarts(): number[] {
  const starts: number[] = [];
  let acc = 0;
  for (const d of CHAPTER_DURATIONS) {
    starts.push(acc);
    acc += d;
  }
  return starts;
}

/** 与 `CHAPTER_DURATIONS` 对齐的 Sequence.from / durationInFrames（叠化重叠） */
export function computeSequenceLayout(): {
  starts: number[];
  from: number[];
  durationInFrames: number[];
  totalDuration: number;
} {
  const starts = chapterStarts();
  const from = CHAPTER_DURATIONS.map((_, i) =>
    i === 0 ? 0 : starts[i] - CROSSFADE_FRAMES,
  );
  const durationInFrames = CHAPTER_DURATIONS.map(
    (d, i) => starts[i] + d - from[i],
  );
  const totalDuration =
    from[from.length - 1] +
    durationInFrames[durationInFrames.length - 1];
  return { starts, from, durationInFrames, totalDuration };
}

const _layout = computeSequenceLayout();

export const TOTAL_SITE_INTRO_FRAMES = _layout.totalDuration;

export const SEQUENCE_FROM = _layout.from;

export const SEQUENCE_DURATION = _layout.durationInFrames;

/** 叠化栈：首段淡入、末段淡出；中间段仅淡入（由上层盖住） */
export function stackLayerOpacity(
  localFrame: number,
  sequenceDuration: number,
  chapterIndex: number,
): number {
  const n = CHAPTER_DURATIONS.length;
  const isFirst = chapterIndex === 0;
  const isLast = chapterIndex === n - 1;
  const F = CROSSFADE_FRAMES;
  let op = 1;
  if (isFirst) {
    op *= interpolate(localFrame, [0, F], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.out(Easing.cubic),
    });
  } else {
    op *= interpolate(localFrame, [0, F], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.out(Easing.cubic),
    });
  }
  if (isLast) {
    op *= interpolate(
      localFrame,
      [Math.max(0, sequenceDuration - F), sequenceDuration],
      [1, 0],
      {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
        easing: Easing.in(Easing.cubic),
      },
    );
  }
  return op;
}
