import React from "react";
import { Composition } from "remotion";
import timeline from "./timeline.json";
import { FlashPostVideo } from "./Video";
import { H, W } from "./theme";

export const RemotionRoot: React.FC = () => (
  <Composition
    id="FlashPost"
    component={FlashPostVideo}
    durationInFrames={timeline.durationFrames}
    fps={timeline.fps}
    width={W}
    height={H}
  />
);
