import React from "react";
import {AbsoluteFill, Audio, OffthreadVideo, Series, useCurrentFrame} from "remotion";
import type {AccentRange, LongTubeShortsProps} from "./types";

const WIDTH = 1080;
const HEIGHT = 1920;
const CLIP_TOP = 423;
const CLIP_HEIGHT = 840;
const CAPTION_TOP = CLIP_TOP + CLIP_HEIGHT + 16;
const CHANNEL_AVATAR_TOP = 1490;
const CHANNEL_TEXT_TOP = 1502;
const ACCENT = "#ffd24a";
const BACKGROUND = "#f7f7f4";
const TITLE_TOPS = [64, 184, 304];
const TITLE_BASE_COLORS = ["#ffffff", ACCENT, "#ffffff"];

const normalizeRanges = (text: string, ranges: AccentRange[]) =>
  ranges
    .map(([start, end]) => [Math.max(0, start), Math.min(text.length, end)] as AccentRange)
    .filter(([start, end]) => start < end)
    .sort((a, b) => a[0] - b[0]);

const AccentLine: React.FC<{
  text: string;
  ranges: AccentRange[];
  baseColor: string;
}> = ({text, ranges, baseColor}) => {
  const normalized = normalizeRanges(text, ranges);
  const parts: React.ReactNode[] = [];
  let cursor = 0;

  normalized.forEach(([start, end], index) => {
    if (start > cursor) {
      parts.push(<span key={`plain-${index}`}>{text.slice(cursor, start)}</span>);
    }
    parts.push(
      <span key={`accent-${index}`} style={{color: ACCENT}}>
        {text.slice(start, end)}
      </span>,
    );
    cursor = end;
  });
  if (cursor < text.length) {
    parts.push(<span key="plain-last">{text.slice(cursor)}</span>);
  }

  return <span style={{color: baseColor}}>{parts.length ? parts : text}</span>;
};

export const ShortsComposition: React.FC<LongTubeShortsProps> = ({
  videoUrl,
  audioUrl,
  avatarUrl,
  titleLines,
  accentRanges,
  channel,
  durationInFrames,
  playbackRate,
  keepSegments,
  captionCues,
}) => {
  const frame = useCurrentFrame();
  const lines = [...titleLines, "", ""].slice(0, 3);
  const ranges = [...accentRanges, [], []].slice(0, 3);
  const hasAvatar = Boolean(avatarUrl);
  const sourceSegments = keepSegments.length
    ? keepSegments
    : [{start: 0, end: (durationInFrames / 30) * playbackRate}];
  const timedSegments = sourceSegments.map((segment) => ({
    ...segment,
    frames: Math.max(1, Math.round(((segment.end - segment.start) * 30) / playbackRate)),
  }));
  const assignedFrames = timedSegments.reduce((total, segment) => total + segment.frames, 0);
  if (timedSegments.length > 0 && assignedFrames !== durationInFrames) {
    const last = timedSegments[timedSegments.length - 1];
    last.frames = Math.max(1, last.frames + durationInFrames - assignedFrames);
  }
  const activeCaption = captionCues.find(
    (cue) => frame >= cue.startFrame && frame < cue.endFrame,
  );

  return (
    <AbsoluteFill
      style={{
        width: WIDTH,
        height: HEIGHT,
        backgroundColor: BACKGROUND,
        color: "#111111",
        overflow: "hidden",
        fontFamily:
          '"Malgun Gothic", "Yu Gothic", Meiryo, "Nirmala UI", Mangal, Arial, sans-serif',
      }}
    >
      {lines.map((line, index) => (
        <div
          key={index}
          style={{
            position: "absolute",
            top: TITLE_TOPS[index],
            left: 0,
            width: WIDTH,
            textAlign: "center",
            fontSize: 104,
            fontWeight: 900,
            lineHeight: 1.03,
            letterSpacing: 0,
            WebkitTextStroke: "9px rgba(0,0,0,0.95)",
            paintOrder: "stroke fill",
            textShadow:
              "0 7px 0 rgba(0,0,0,.88), 0 0 22px rgba(0,0,0,.92), 5px 0 0 #050505, -5px 0 0 #050505, 0 5px 0 #050505, 0 -5px 0 #050505",
            whiteSpace: "pre",
          }}
        >
          <AccentLine
            text={line}
            ranges={ranges[index] ?? []}
            baseColor={TITLE_BASE_COLORS[index]}
          />
        </div>
      ))}

      <div
        style={{
          position: "absolute",
          top: CLIP_TOP,
          left: 0,
          width: WIDTH,
          height: CLIP_HEIGHT,
          overflow: "hidden",
          backgroundColor: BACKGROUND,
        }}
      >
        <Series>
          {timedSegments.map((segment, index) => (
            <Series.Sequence key={`video-${index}`} durationInFrames={segment.frames}>
              <OffthreadVideo
                src={videoUrl}
                muted
                startFrom={Math.round(segment.start * 30)}
                playbackRate={playbackRate}
                style={{width: "100%", height: "100%", objectFit: "cover"}}
              />
            </Series.Sequence>
          ))}
        </Series>
      </div>

      {activeCaption ? (
        <div
          style={{
            position: "absolute",
            top: CAPTION_TOP,
            left: 54,
            width: WIDTH - 108,
            minHeight: 190,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            textAlign: "center",
            fontSize: 76,
            fontWeight: 900,
            lineHeight: 1.12,
            color: "#ffffff",
            WebkitTextStroke: "7px rgba(0,0,0,0.96)",
            paintOrder: "stroke fill",
            textShadow: "0 5px 12px rgba(0,0,0,0.9)",
            whiteSpace: "pre-wrap",
          }}
        >
          <span
            style={{
              display: "inline-block",
              padding: "12px 28px 16px",
              borderRadius: 12,
              backgroundColor: "rgba(255,255,255,0.7)",
            }}
          >
            {activeCaption.text}
          </span>
        </div>
      ) : null}

      {hasAvatar ? (
        <img
          src={avatarUrl ?? ""}
          style={{
            position: "absolute",
            left: 318,
            top: CHANNEL_AVATAR_TOP,
            width: 112,
            height: 112,
            borderRadius: "50%",
            objectFit: "cover",
          }}
        />
      ) : null}

      <div
        style={{
          position: "absolute",
          left: hasAvatar ? 426 : 0,
          top: CHANNEL_TEXT_TOP,
          width: hasAvatar ? WIDTH - 426 - 60 : WIDTH,
          textAlign: hasAvatar ? "left" : "center",
          fontSize: 92,
          fontWeight: 900,
          lineHeight: 1.05,
          color: "#111111",
          WebkitTextStroke: "2px rgba(255,255,255,.95)",
          paintOrder: "stroke fill",
          textShadow: "0 3px 8px rgba(0,0,0,.18)",
          whiteSpace: "pre-wrap",
        }}
      >
        {channel}
      </div>

      <Series>
        {timedSegments.map((segment, index) => (
          <Series.Sequence key={`audio-${index}`} durationInFrames={segment.frames}>
            <Audio
              src={audioUrl}
              startFrom={Math.round(segment.start * 30)}
              playbackRate={playbackRate}
            />
          </Series.Sequence>
        ))}
      </Series>
    </AbsoluteFill>
  );
};
