import { Composition } from "remotion";
import { SiteIntro } from "./compositions/SiteIntro";
import { TOTAL_SITE_INTRO_FRAMES } from "./compositions/siteIntro/constants";

export const RemotionRoot = () => {
  return (
    <Composition
      id="SiteIntro"
      component={SiteIntro}
      durationInFrames={TOTAL_SITE_INTRO_FRAMES}
      fps={30}
      width={1920}
      height={1080}
    />
  );
};
