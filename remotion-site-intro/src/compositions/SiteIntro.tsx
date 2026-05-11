import React from "react";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  Sequence,
  staticFile,
  useCurrentFrame,
} from "remotion";
import { Audio } from "@remotion/media";
import { Ch00Hook } from "./siteIntro/chapters/Ch00Hook";
import { Ch01Landing } from "./siteIntro/chapters/Ch01Landing";
import { Ch02Agent } from "./siteIntro/chapters/Ch02Agent";
import { Ch03DesignDomain } from "./siteIntro/chapters/Ch03DesignDomain";
import { Ch04Orchestrate } from "./siteIntro/chapters/Ch04Orchestrate";
import { Ch05Tutorial } from "./siteIntro/chapters/Ch05Tutorial";
import { Ch06Outro } from "./siteIntro/chapters/Ch06Outro";
import { BG0, SEQUENCE_DURATION, SEQUENCE_FROM, TOTAL_SITE_INTRO_FRAMES } from "./siteIntro/constants";
import { FontGate } from "./siteIntro/FontGate";

/** 将 `public/onboarding/bgm.mp3` 放入仓库后改为 `true` 即可启用占位音轨。 */
const ENABLE_BGM = false;

export const SiteIntro: React.FC = () => {
  const frame = useCurrentFrame();
  const pulse = interpolate(Math.sin(frame * 0.07), [-1, 1], [0.55, 0.85], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <FontGate>
      <AbsoluteFill
        style={{
          backgroundColor: BG0,
          backgroundImage: [
            `radial-gradient(900px 600px at 15% 10%, rgba(37,99,235,${pulse * 0.14}), transparent 60%)`,
            `radial-gradient(900px 700px at 85% 15%, rgba(16,185,129,${pulse * 0.11}), transparent 55%)`,
            "linear-gradient(180deg, #f7f8fb, #ffffff)",
          ].join(", "),
        }}
      >
        {ENABLE_BGM ? (
          <Sequence from={0} durationInFrames={TOTAL_SITE_INTRO_FRAMES}>
            <Audio
              src={staticFile("onboarding/bgm.mp3")}
              volume={(f) =>
                interpolate(f, [0, 45, TOTAL_SITE_INTRO_FRAMES - 60, TOTAL_SITE_INTRO_FRAMES], [0, 0.12, 0.12, 0], {
                  extrapolateLeft: "clamp",
                  extrapolateRight: "clamp",
                  easing: Easing.inOut(Easing.quad),
                })
              }
            />
          </Sequence>
        ) : null}

        <Sequence from={SEQUENCE_FROM[0]} durationInFrames={SEQUENCE_DURATION[0]}>
          <Ch00Hook />
        </Sequence>
        <Sequence from={SEQUENCE_FROM[1]} durationInFrames={SEQUENCE_DURATION[1]}>
          <Ch01Landing />
        </Sequence>
        <Sequence from={SEQUENCE_FROM[2]} durationInFrames={SEQUENCE_DURATION[2]}>
          <Ch02Agent />
        </Sequence>
        <Sequence from={SEQUENCE_FROM[3]} durationInFrames={SEQUENCE_DURATION[3]}>
          <Ch03DesignDomain />
        </Sequence>
        <Sequence from={SEQUENCE_FROM[4]} durationInFrames={SEQUENCE_DURATION[4]}>
          <Ch04Orchestrate />
        </Sequence>
        <Sequence from={SEQUENCE_FROM[5]} durationInFrames={SEQUENCE_DURATION[5]}>
          <Ch05Tutorial />
        </Sequence>
        <Sequence from={SEQUENCE_FROM[6]} durationInFrames={SEQUENCE_DURATION[6]}>
          <Ch06Outro />
        </Sequence>
      </AbsoluteFill>
    </FontGate>
  );
};
