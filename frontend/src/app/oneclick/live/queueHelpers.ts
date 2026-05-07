import type { OneClickQueueItem, OneClickTask } from "@/lib/api";

export const DEFAULT_QUEUE_CHANNELS = [1, 2, 3, 4] as const;

export const DEFAULT_QUEUE_CHANNEL_TIMES: Record<string, string | null> = Object.fromEntries(
  DEFAULT_QUEUE_CHANNELS.map((ch) => [String(ch), null]),
);

export function normalizeQueueChannelTimes(times?: Record<string, string | null | undefined> | null) {
  const out: Record<string, string | null> = { ...DEFAULT_QUEUE_CHANNEL_TIMES };
  for (const [key, value] of Object.entries(times || {})) {
    const ch = Number(key);
    if (Number.isFinite(ch) && ch > 0) out[String(ch)] = value || null;
  }
  return out;
}

export function queueChannelTimeLabel(value: string | null | undefined) {
  return value || "수동";
}

export function collectQueueChannels(
  channelTimes: Record<string, string | null | undefined>,
  queueItems: OneClickQueueItem[],
  tasks: OneClickTask[],
) {
  const channels = new Set<number>();
  for (const ch of DEFAULT_QUEUE_CHANNELS) channels.add(ch);
  for (const key of Object.keys(channelTimes || {})) {
    const ch = Number(key);
    if (Number.isFinite(ch) && ch > 0) channels.add(ch);
  }
  for (const item of queueItems || []) {
    const ch = Number(item.channel || 0);
    if (Number.isFinite(ch) && ch > 0) channels.add(ch);
  }
  for (const task of tasks || []) {
    const ch = Number(task.channel || 0);
    if (Number.isFinite(ch) && ch > 0) channels.add(ch);
  }
  return Array.from(channels).sort((a, b) => a - b);
}

export function formatQueueWaitingMeta(
  item: OneClickQueueItem,
  channelTimes: Record<string, string | null | undefined>,
) {
  const source = String(item.queued_source || "manual").toLowerCase();
  const sourceLabel =
    source === "import"
      ? "엑셀 등록"
      : source === "requeue"
        ? "실패 재시도"
        : source === "orphan"
          ? "미완성 복구"
          : source === "schedule" || source === "system"
            ? "자동 등록"
            : "수동 등록";
  const sourceClass =
    source === "requeue" || source === "orphan"
      ? "border-amber-400/30 bg-amber-400/10 text-amber-200"
      : source === "import"
        ? "border-sky-400/30 bg-sky-400/10 text-sky-200"
        : "border-gray-500/30 bg-gray-500/10 text-gray-300";
  const ch = String(item.channel || 1);
  const scheduledTime = channelTimes[ch] || null;
  const scheduleLabel = scheduledTime
    ? `자동 실행 · 매일 ${scheduledTime}`
    : "수동 실행 대기";
  const queuedAt = item.queued_at
    ? new Date(item.queued_at).toLocaleString("ko-KR", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "등록 시각 미상";
  return {
    sourceLabel,
    sourceClass,
    scheduleLabel,
    queuedAt,
    note: item.queued_note || "",
  };
}

export function formatEpisodeBadge(item: OneClickQueueItem) {
  const ep = item.episode_number;
  return typeof ep === "number" && ep > 0 ? `EP.${String(ep).padStart(2, "0")}` : "EP.--";
}

export function episodePrefix(ep?: number | null) {
  return typeof ep === "number" && ep > 0 ? `EP.${String(ep).padStart(2, "0")}` : "";
}

export function withEpisodeTitle(title: string | null | undefined, ep?: number | null) {
  const text = String(title || "").trim();
  const prefix = episodePrefix(ep);
  if (!prefix) return text;
  if (/^EP\.\s*\d+/i.test(text)) return text;
  return `${prefix} ${text}`;
}

export function queueTitle(item: OneClickQueueItem) {
  return withEpisodeTitle(item.topic, item.episode_number);
}

export function queueEpisodeSortValue(item: OneClickQueueItem) {
  const ep = Number(item.episode_number);
  return Number.isFinite(ep) && ep > 0 ? ep : Number.POSITIVE_INFINITY;
}

export function compareQueueByEpisodeWithinChannel(
  a: { item: OneClickQueueItem; index: number },
  b: { item: OneClickQueueItem; index: number },
) {
  const episodeDiff = queueEpisodeSortValue(a.item) - queueEpisodeSortValue(b.item);
  if (episodeDiff !== 0) return episodeDiff;
  return a.index - b.index;
}

export function scheduledDelayMinutes(value: string | null | undefined, nowMinutes: number) {
  if (!value) return Number.POSITIVE_INFINITY;
  const [hh, mm] = value.split(":").map((part) => Number(part));
  if (!Number.isFinite(hh) || !Number.isFinite(mm)) return Number.POSITIVE_INFINITY;
  const scheduled = hh * 60 + mm;
  return (scheduled - nowMinutes + 1440) % 1440;
}

export function channelBadgeClass(channel?: number | null, active = true) {
  if (!active) return "border-border/60 bg-bg-primary/40 text-gray-600";
  switch (Number(channel || 1)) {
    case 1:
      return "border-emerald-300/60 bg-emerald-400/20 text-emerald-100 shadow-[0_0_0_1px_rgba(52,211,153,0.18)]";
    case 2:
      return "border-sky-300/60 bg-sky-400/20 text-sky-100 shadow-[0_0_0_1px_rgba(56,189,248,0.18)]";
    case 3:
      return "border-amber-300/70 bg-amber-400/20 text-amber-100 shadow-[0_0_0_1px_rgba(251,191,36,0.18)]";
    case 4:
      return "border-fuchsia-300/60 bg-fuchsia-400/20 text-fuchsia-100 shadow-[0_0_0_1px_rgba(217,70,239,0.18)]";
    default:
      return "border-blue-300/60 bg-blue-400/20 text-blue-100";
  }
}

export function isLiveNextQueueItem(item: OneClickQueueItem) {
  const note = String(item.queued_note || "");
  return (
    String(item.queued_source || "").toLowerCase() === "manual" &&
    (note.includes("\uc791\uc5c5\ub300") ||
      note.includes("\uc2e4\uc2dc\uac04 \ud604\ud669") ||
      note.includes("\uc218\ub3d9 \uc2e4\ud589"))
  );
}

export function queueItemKey(item: OneClickQueueItem, index: number) {
  return item.id || `${index}:${item.channel || 1}:${item.topic}`;
}
