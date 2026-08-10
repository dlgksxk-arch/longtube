import React from "react";
import {AbsoluteFill, OffthreadVideo, Series} from "remotion";

export type LongformClip = {
  url: string;
  durationInFrames: number;
  segments: Array<{
    startFrom: number;
    endAt: number;
    playbackRate: number;
    durationInFrames: number;
  }>;
};

export type LongTubeLongformProps = {
  pipelineId: string;
  width: number;
  height: number;
  fps: number;
  durationInFrames: number;
  clips: LongformClip[];
  title: string;
  channelName: string;
};

export const defaultLongformProps: LongTubeLongformProps = {
  pipelineId: "shared-all-channels-remotion-longform-v1",
  width: 1920,
  height: 1080,
  fps: 30,
  durationInFrames: 30,
  clips: [],
  title: "",
  channelName: "",
};

export const LongformComposition: React.FC<LongTubeLongformProps> = ({
  width,
  clips,
  title,
  channelName,
}) => {
  const scale = Math.max(0.55, Math.min(2, width / 1920));
  const marginX = Math.max(20, Math.round(48 * scale));
  const marginY = Math.max(16, Math.round(30 * scale));
  const channelFontSize = Math.max(48, Math.round(84 * scale));
  const titleFontSize = Math.max(34, Math.round(channelFontSize * 0.7));

  return (
    <AbsoluteFill style={{backgroundColor: "#000", overflow: "hidden"}}>
      <Series>
        {clips.flatMap((clip, clipIndex) =>
          clip.segments.map((segment, segmentIndex) => (
            <Series.Sequence
              key={`${clipIndex}-${segmentIndex}`}
              durationInFrames={Math.max(1, segment.durationInFrames)}
            >
              <OffthreadVideo
                src={clip.url}
                startFrom={segment.startFrom}
                endAt={segment.endAt}
                playbackRate={segment.playbackRate}
                style={{width: "100%", height: "100%", objectFit: "contain"}}
              />
            </Series.Sequence>
          )),
        )}
      </Series>

      {title ? (
        <div
          style={{
            position: "absolute",
            top: marginY,
            left: marginX,
            maxWidth: "74%",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            color: "rgba(255,255,255,0.4)",
            fontFamily: '"Malgun Gothic", "Yu Gothic", Meiryo, Arial, sans-serif',
            fontSize: titleFontSize,
            fontWeight: 900,
            lineHeight: 1.05,
            WebkitTextStroke: `${Math.max(3, Math.round(6 * scale))}px rgba(0,0,0,0.4)`,
            paintOrder: "stroke fill",
          }}
        >
          {title}
        </div>
      ) : null}

      {channelName ? (
        <div
          style={{
            position: "absolute",
            top: marginY,
            right: marginX,
            maxWidth: "22%",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            textAlign: "right",
            color: "rgba(255,210,74,0.4)",
            fontFamily: '"Malgun Gothic", "Yu Gothic", Meiryo, Arial, sans-serif',
            fontSize: channelFontSize,
            fontWeight: 900,
            lineHeight: 1.05,
            WebkitTextStroke: `${Math.max(4, Math.round(8 * scale))}px rgba(0,0,0,0.4)`,
            paintOrder: "stroke fill",
          }}
        >
          {channelName}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
