/**
 * 채널별 색상 헬퍼 (v2.1.0).
 *
 * 규약(기획 §6.3): 인라인 삼항 연산자로 채널 색을 분기하지 않고,
 * 반드시 이 헬퍼를 통해 Tailwind 클래스를 받는다.
 *
 * 채널 매핑:
 *   CH1 → blue-400
 *   CH2 → green-400
 *   CH3 → amber-400
 *   CH4 → pink-400
 */

export type ChannelId = 1 | 2 | 3 | 4;

/** 팔레트 (Tailwind 4xx 기준). */
export const CHANNEL_PALETTE: Record<ChannelId, {
  text: string;
  bg: string;
  bgSoft: string;
  border: string;
  dot: string;
  name: string;
}> = {
  1: {
    text: "text-blue-400",
    bg: "bg-blue-500",
    bgSoft: "bg-blue-500/10",
    border: "border-blue-500/40",
    dot: "bg-blue-400",
    name: "blue",
  },
  2: {
    text: "text-green-400",
    bg: "bg-green-500",
    bgSoft: "bg-green-500/10",
    border: "border-green-500/40",
    dot: "bg-green-400",
    name: "green",
  },
  3: {
    text: "text-amber-400",
    bg: "bg-amber-500",
    bgSoft: "bg-amber-500/10",
    border: "border-amber-500/40",
    dot: "bg-amber-400",
    name: "amber",
  },
  4: {
    text: "text-pink-400",
    bg: "bg-pink-500",
    bgSoft: "bg-pink-500/10",
    border: "border-pink-500/40",
    dot: "bg-pink-400",
    name: "pink",
  },
};

/** 값이 1~4 범위 밖이면 가장 가까운 값으로 보정한다. */
function normalize(ch: number | string | null | undefined): ChannelId {
  const n = Number(ch);
  if (!Number.isFinite(n)) return 1;
  const v = Math.min(4, Math.max(1, Math.trunc(n)));
  return v as ChannelId;
}

export function channelColor(ch: number | string | null | undefined) {
  return CHANNEL_PALETTE[normalize(ch)];
}

export function channelName(ch: number | string | null | undefined): string {
  return `CH${normalize(ch)}`;
}
