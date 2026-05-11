import React, { useEffect, useMemo } from "react";
import { AbsoluteFill, continueRender, delayRender } from "remotion";
import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadNotoSansSC } from "@remotion/google-fonts/NotoSansSC";

const inter = loadInter("normal", {
  subsets: ["latin"],
  weights: ["400", "500", "600", "700", "800"],
});

const noto = loadNotoSansSC("normal", {
  subsets: ["latin", "chinese-simplified"],
  weights: ["400", "500", "700"],
});

export const FontGate: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const fontFamily = useMemo(
    () => `${noto.fontFamily}, ${inter.fontFamily}, sans-serif`,
    [],
  );

  useEffect(() => {
    const h = delayRender();
    void Promise.all([inter.waitUntilDone(), noto.waitUntilDone()])
      .then(() => {
        continueRender(h);
      })
      .catch(() => {
        continueRender(h);
      });
  }, []);

  return (
    <AbsoluteFill
      style={{
        fontFamily,
      }}
    >
      {children}
    </AbsoluteFill>
  );
};
