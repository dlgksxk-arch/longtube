export type AccentRange = [number, number];
export type KeepSegment = {start: number; end: number};
export type CaptionCue = {text: string; startFrame: number; endFrame: number};

export type LongTubeShortsProps = {
  pipelineId: string;
  videoUrl: string;
  audioUrl: string;
  avatarUrl: string | null;
  titleLines: string[];
  accentRanges: AccentRange[][];
  channel: string;
  durationInFrames: number;
  playbackRate: number;
  keepSegments: KeepSegment[];
  captionCues: CaptionCue[];
};

export const defaultShortsProps: LongTubeShortsProps = {
  pipelineId: "shared-all-channels-3word-captions-v2",
  videoUrl: "",
  audioUrl: "",
  avatarUrl: null,
  titleLines: ["", "", ""],
  accentRanges: [[], [], []],
  channel: "",
  durationInFrames: 30,
  playbackRate: 1.2,
  keepSegments: [],
  captionCues: [],
};
