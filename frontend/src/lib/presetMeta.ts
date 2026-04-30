/**
 * v2.3.0 — 프리셋 config 에서 카드 meta 를 안전하게 추출.
 *
 * v2.2.0 단계에서 config JSON 스키마가 확정되지 않아, 값이 빈
 * 객체일 수도 있고 부분 채워져 있을 수도 있다. UI 가 죽지 않게
 * 전부 optional 로 꺼내고, 표기 단위까지 여기서 결정한다.
 *
 * 기대 스키마(느슨):
 *   config = {
 *     content: {
 *       duration_sec?: number,           // 목표 영상 길이
 *       target_language?: "ko"|"en"|"ja",
 *       constraints?: string,
 *     },
 *     models: {
 *       script?: string,                 // 예: "gpt-4o"
 *       image?: string,                  // 예: "flux.1-dev"
 *       video?: string,                  // 예: "wan-2.2"
 *       tts?: string,
 *     },
 *     economics?: {
 *       cost_per_episode_krw?: number,
 *       monthly_estimate_krw?: number,
 *     },
 *     upload?: {
 *       schedule_cron?: string,
 *     },
 *   }
 */

export interface PresetCardMeta {
  durationLabel: string | null;   // 예: "10분 30초"
  language: string | null;        // 예: "KO"
  modelChain: string | null;      // 예: "gpt-4o → flux → wan"
  perEpisodeKrw: number | null;
  monthlyKrw: number | null;
  schedule: string | null;        // cron 그대로
}

function asStr(v: unknown): string | null {
  if (typeof v !== "string") return null;
  const t = v.trim();
  return t.length > 0 ? t : null;
}

function asNum(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string") {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function fmtDuration(sec: number | null): string | null {
  if (sec == null || sec <= 0) return null;
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  if (m === 0) return `${s}초`;
  if (s === 0) return `${m}분`;
  return `${m}분 ${s}초`;
}

function fmtLang(v: string | null): string | null {
  if (!v) return null;
  const up = v.toUpperCase();
  if (up === "KO" || up === "EN" || up === "JA") return up;
  return null;
}

function fmtModelChain(models: unknown): string | null {
  if (!models || typeof models !== "object") return null;
  const m = models as Record<string, unknown>;
  const parts = [asStr(m.script), asStr(m.image), asStr(m.video)].filter(
    (x): x is string => !!x,
  );
  if (parts.length === 0) return null;
  // 긴 모델명이 섞여도 카드에서 줄바꿈 없이 보이도록 축약.
  return parts.map((p) => (p.length > 14 ? p.slice(0, 13) + "…" : p)).join(" → ");
}

export function parsePresetMeta(config: unknown): PresetCardMeta {
  const c = (config && typeof config === "object" ? config : {}) as Record<
    string,
    unknown
  >;
  const content = (c.content as Record<string, unknown>) ?? {};
  const econ = (c.economics as Record<string, unknown>) ?? {};
  const upload = (c.upload as Record<string, unknown>) ?? {};

  return {
    durationLabel: fmtDuration(asNum(content.duration_sec)),
    language: fmtLang(asStr(content.target_language)),
    modelChain: fmtModelChain(c.models),
    perEpisodeKrw: asNum(econ.cost_per_episode_krw),
    monthlyKrw: asNum(econ.monthly_estimate_krw),
    schedule: asStr(upload.schedule_cron),
  };
}

/** 천 단위 ₩ 포맷. null 이면 대시. */
export function fmtKrw(v: number | null): string {
  if (v == null) return "—";
  return `₩${Math.round(v).toLocaleString("ko-KR")}`;
}

/** ISO 날짜 → "04-21 14:03". null safe. */
export function fmtUpdatedAt(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(
    d.getMinutes(),
  )}`;
}
