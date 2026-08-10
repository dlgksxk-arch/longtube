import React from "react";
import {Composition} from "remotion";
import {ShortsComposition} from "./ShortsComposition";
import {defaultShortsProps, type LongTubeShortsProps} from "./types";
import {
  defaultLongformProps,
  LongformComposition,
  type LongTubeLongformProps,
} from "./LongformComposition";

export const RemotionRoot: React.FC = () => (
  <>
    <Composition
      id="LongTubeShorts"
      component={ShortsComposition}
      width={1080}
      height={1920}
      fps={30}
      durationInFrames={30}
      defaultProps={defaultShortsProps}
      calculateMetadata={({props}) => ({
        durationInFrames: Math.max(1, Math.round((props as LongTubeShortsProps).durationInFrames)),
      })}
    />
    <Composition
      id="LongTubeLongform"
      component={LongformComposition}
      width={1920}
      height={1080}
      fps={30}
      durationInFrames={30}
      defaultProps={defaultLongformProps}
      calculateMetadata={({props}) => {
        const longform = props as LongTubeLongformProps;
        return {
          width: Math.max(1, Math.round(longform.width)),
          height: Math.max(1, Math.round(longform.height)),
          fps: Math.max(1, Math.round(longform.fps)),
          durationInFrames: Math.max(1, Math.round(longform.durationInFrames)),
        };
      }}
    />
  </>
);
