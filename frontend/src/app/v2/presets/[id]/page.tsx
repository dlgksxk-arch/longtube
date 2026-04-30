/**
 * /v2/presets/[id] — 프리셋 편집 (기획 §10).
 *
 * v2.3.1: 섹션 2(내용 방향), 3(AI 모델), 7(업로드 템플릿) 실필드 구현.
 *   - 섹션 1 식별: 이름만 수정, 채널/폼타입 잠금.
 *   - 섹션 2 내용: 주제(테스트폼만) / 톤 / 스타일 / 시청자 / 시그니처.
 *   - 섹션 3 모델: /api/models/llm, /image, /tts 3개 드롭다운.
 *       썸네일(Nano Banana) · BGM(ElevenLabs Music) 은 고정 — 표시만.
 *   - 섹션 7 업로드: 제목/설명 템플릿 + placeholder 안내, 공개 설정, 재생목록.
 *
 * config 스키마는 아직 확정이 아니므로 관대한 partial 병합:
 *   PATCH 시 `{ config: { ...prev, ...next } }` 로 보낸다. 필드 삭제는 UI 에서
 *   빈 문자열 → 서버에서 optional 로 해석되게 그대로 둔다.
 */
"use client";

import { useEffect, useId, useMemo, useRef, useState, useCallback } from "react";
import Link from "next/link";
import { useRouter, useParams } from "next/navigation";
import { channelColor } from "@/lib/channelColor";
import {
  v2Url,
  V2_API_BASE,
  assetUrl,
  presetInterludeApi,
  type InterludeKind,
  type InterludeState,
  type InterludeEntry,
} from "@/lib/v2Api";
import {
  LoadingState,
  ErrorState,
  ConfirmDialog,
  V2Button,
} from "@/components/v2";

// ---------------------------------------------------------------------------
// 타입 & 상수

interface PresetDetail {
  id: number;
  channel_id: number;
  form_type: "딸깍폼" | "테스트폼";
  name: string;
  full_name: string;
  is_modified: boolean;
  config: Record<string, unknown>;
}

type SectionKey =
  | "identity"
  | "content"
  | "models"
  | "structure"
  | "subtitles"
  | "references"
  | "upload"
  | "automation"
  | "audio";

const SECTIONS: { key: SectionKey; label: string; num: number }[] = [
  { key: "identity", label: "식별", num: 1 },
  { key: "content", label: "내용 방향", num: 2 },
  { key: "models", label: "AI 모델", num: 3 },
  { key: "structure", label: "영상 구조", num: 4 },
  { key: "subtitles", label: "자막", num: 5 },
  { key: "references", label: "레퍼런스", num: 6 },
  { key: "upload", label: "업로드 템플릿", num: 7 },
  { key: "automation", label: "자동화", num: 8 },
  { key: "audio", label: "음향 (BGM)", num: 9 },
];

// §10.3 섹션 1~9 전부 구현 — UPCOMING 자리에 남길 항목 없음.
// 빈 배열이지만 JSX 에서 조건부로 렌더링하므로 타입 유지 위해 유지.
const UPCOMING: { num: number; label: string; when: string }[] = [];

/** 기획 §10.3 섹션 2 톤 권장값. 드롭다운 + 자유 입력 혼용. */
const TONE_SUGGESTIONS = [
  "차분한 다큐",
  "드라마틱",
  "미스터리",
  "교양",
  "친근한 해설",
  "긴박감",
  "유쾌",
] as const;

const STYLE_SUGGESTIONS = [
  "역사",
  "미스터리",
  "인물",
  "과학",
  "사건·사고",
  "문화",
  "지리",
  "전쟁",
] as const;

const VISIBILITY_OPTIONS = [
  { value: "public", label: "공개" },
  { value: "unlisted", label: "링크 공유" },
  { value: "private", label: "비공개" },
] as const;
type Visibility = (typeof VISIBILITY_OPTIONS)[number]["value"];

const SUBTITLE_LANG_OPTIONS = [
  { value: "ko", label: "한국어" },
  { value: "en", label: "English" },
  { value: "ja", label: "日本語" },
] as const;
type SubtitleLang = (typeof SUBTITLE_LANG_OPTIONS)[number]["value"];

const SUBTITLE_POSITION_OPTIONS = [
  { value: "top", label: "상단" },
  { value: "middle", label: "가운데" },
  { value: "bottom", label: "하단" },
] as const;
type SubtitlePosition = (typeof SUBTITLE_POSITION_OPTIONS)[number]["value"];

const REFERENCE_MODE_OPTIONS = [
  { value: "off", label: "사용 안 함" },
  { value: "style", label: "스타일" },
  { value: "composition", label: "구도" },
] as const;
type ReferenceMode = (typeof REFERENCE_MODE_OPTIONS)[number]["value"];

// 섹션 8 — 자동화. pause_during_studio 는 강제 true (§10.3) — 토글 없이 표시만.
const RESOLUTION_OPTIONS = [
  { value: "720p", label: "720p" },
  { value: "1080p", label: "1080p" },
  { value: "1440p", label: "1440p" },
  { value: "2160p", label: "2160p (4K)" },
] as const;
type Resolution = (typeof RESOLUTION_OPTIONS)[number]["value"];

// 섹션 9 — 음향. §10.3 명시 3단계.
const DUCKING_OPTIONS = [
  { value: "low", label: "낮음" },
  { value: "normal", label: "보통" },
  { value: "strong", label: "강함" },
] as const;
type DuckingStrength = (typeof DUCKING_OPTIONS)[number]["value"];

/** config 안전 파싱용 헬퍼. */
function pickObj(o: Record<string, unknown>, key: string): Record<string, unknown> {
  const v = o[key];
  if (v && typeof v === "object" && !Array.isArray(v)) {
    return v as Record<string, unknown>;
  }
  return {};
}
function pickStr(o: Record<string, unknown>, key: string): string {
  const v = o[key];
  return typeof v === "string" ? v : "";
}
function pickBool(o: Record<string, unknown>, key: string): boolean {
  const v = o[key];
  return typeof v === "boolean" ? v : false;
}
function pickNum(o: Record<string, unknown>, key: string): number | null {
  const v = o[key];
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string" && v.trim() !== "") {
    const n = Number(v);
    if (Number.isFinite(n)) return n;
  }
  return null;
}
function pickStrArray(o: Record<string, unknown>, key: string): string[] {
  const v = o[key];
  if (Array.isArray(v)) return v.filter((x): x is string => typeof x === "string");
  return [];
}
/** number | null → input value. null 이면 빈 문자열. */
function numToInput(n: number | null): string {
  return n === null ? "" : String(n);
}
/** input value → number | null. 빈/잘못된 값은 null. */
function inputToNum(s: string): number | null {
  const t = s.trim();
  if (t === "") return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

// ---------------------------------------------------------------------------

interface ModelInfo {
  id: string;
  name?: string;
  provider?: string;
  available?: boolean;
}

async function fetchModelList(kind: "llm" | "image" | "tts"): Promise<ModelInfo[]> {
  const res = await fetch(`${V2_API_BASE}/models/${kind}`);
  if (!res.ok) throw new Error(`/${kind} HTTP ${res.status}`);
  const j = (await res.json()) as { models?: ModelInfo[] };
  return j.models ?? [];
}

// ---------------------------------------------------------------------------

export default function V2PresetEditPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const idNum = Number(params?.id);
  const idp = useId();

  const [detail, setDetail] = useState<PresetDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // 편집 상태 — 섹션별.
  const [name, setName] = useState("");
  const [content, setContent] = useState({
    topic: "",
    tone: "",
    style: "",
    target_audience: "",
    signature_phrase: "",
  });
  const [models, setModels] = useState({
    script_model: "",
    image_model: "",
    tts_model: "",
    tts_voice_id: "",
  });
  const [upload, setUpload] = useState<{
    title_template: string;
    description_template: string;
    playlist_id: string;
    visibility: Visibility;
    scheduled: boolean;
  }>({
    title_template: "",
    description_template: "",
    playlist_id: "",
    visibility: "public",
    scheduled: false,
  });

  // 섹션 4 — 영상 구조 (v2.4.0 기획 §10.3 재정렬).
  //   - 목표 길이는 분 단위(정수) 로 입력받고, 저장은 초(target_duration_*_sec) 로도
  //     함께 써서 기존 파이프라인 하위호환.
  //   - 인트로/본문/아웃트로는 자유 textarea + 드롭다운 추천값.
  //   - 인터미션은 N분마다 / 총 N회 둘 다 입력. 파이프라인은 둘 중 있는 값을 우선.
  //   - 업로드 슬롯은 별도 state (interlude). 여기는 숫자/텍스트만 관리.
  const [structure, setStructure] = useState<{
    target_duration_min_min: string;   // 최소 목표 길이 (분)
    target_duration_max_min: string;   // 최대 목표 길이 (분)
    intro_template: string;
    body_template: string;
    outro_template: string;
    intermission_every_min: string;    // N분마다
    intermission_total_count: string;  // 총 N회 (선택)
  }>({
    target_duration_min_min: "",
    target_duration_max_min: "",
    intro_template: "",
    body_template: "",
    outro_template: "",
    intermission_every_min: "",
    intermission_total_count: "",
  });

  // 섹션 4 — 인터루드 영상 상태. 별도 엔드포인트에서 fetch.
  const [interludes, setInterludes] = useState<InterludeState | null>(null);
  const [interludeBusy, setInterludeBusy] = useState<
    Partial<Record<InterludeKind, boolean>>
  >({});
  const [interludeErr, setInterludeErr] = useState<string | null>(null);

  // 섹션 5 — 자막.
  const [subtitles, setSubtitles] = useState<{
    enabled: boolean;
    burn_in: boolean;
    language: SubtitleLang;
    position: SubtitlePosition;
    max_chars_per_line: string;
  }>({
    enabled: false,
    burn_in: false,
    language: "ko",
    position: "bottom",
    max_chars_per_line: "",
  });

  // 섹션 6 — 레퍼런스. URL 은 multiline textarea (한 줄당 1 URL).
  const [references, setReferences] = useState<{
    mode: ReferenceMode;
    strength: string;
    image_urls_text: string;
  }>({
    mode: "off",
    strength: "",
    image_urls_text: "",
  });

  // 섹션 8 — 자동화. pause_during_studio 는 서버가 강제 true — state 없음.
  const [automation, setAutomation] = useState<{
    retry_on_fail: string;
    min_duration_sec: string;
    max_duration_sec: string;
    min_loudness_lufs: string;
    max_loudness_lufs: string;
    min_resolution: Resolution;
  }>({
    retry_on_fail: "",
    min_duration_sec: "",
    max_duration_sec: "",
    min_loudness_lufs: "",
    max_loudness_lufs: "",
    min_resolution: "1080p",
  });

  // 섹션 9 — 음향 / BGM.
  const [audio, setAudio] = useState<{
    bgm_enabled: boolean;
    bgm_style_prompt: string;
    bgm_volume_db: string;
    ducking_strength: DuckingStrength;
    fade_in_sec: string;
    fade_out_sec: string;
  }>({
    bgm_enabled: true,
    bgm_style_prompt: "",
    bgm_volume_db: "",
    ducking_strength: "normal",
    fade_in_sec: "",
    fade_out_sec: "",
  });

  const [saving, setSaving] = useState(false);
  const [saveErr, setSaveErr] = useState<string | null>(null);
  const [active, setActive] = useState<SectionKey>("identity");
  const [confirmDel, setConfirmDel] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const res = await fetch(v2Url(`/v2/presets/${idNum}`));
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const j: PresetDetail = await res.json();
      setDetail(j);
      setName(j.name);
      const cfg = j.config ?? {};
      const cObj = pickObj(cfg, "content");
      setContent({
        topic: pickStr(cObj, "topic"),
        tone: pickStr(cObj, "tone"),
        style: pickStr(cObj, "style"),
        target_audience: pickStr(cObj, "target_audience"),
        signature_phrase: pickStr(cObj, "signature_phrase"),
      });
      const mObj = pickObj(cfg, "models");
      const mScript = pickObj(mObj, "script");
      const mImage = pickObj(mObj, "image");
      const mTts = pickObj(mObj, "tts");
      setModels({
        script_model: pickStr(mScript, "model_id"),
        image_model: pickStr(mImage, "model_id"),
        tts_model: pickStr(mTts, "model_id"),
        tts_voice_id: pickStr(mTts, "voice_id"),
      });
      const uObj = pickObj(cfg, "upload");
      const visRaw = pickStr(uObj, "visibility");
      const vis: Visibility =
        visRaw === "unlisted" || visRaw === "private" ? visRaw : "public";
      setUpload({
        title_template: pickStr(uObj, "title_template"),
        description_template: pickStr(uObj, "description_template"),
        playlist_id: pickStr(uObj, "playlist_id"),
        visibility: vis,
        scheduled: pickBool(uObj, "scheduled"),
      });

      // 섹션 4 — 영상 구조. 초 단위로 저장된 구버전 값도 분으로 끌어올려
      // 표시한다 (600s → 10분). 기본 키는 분(..._min_min / ..._max_min) 으로 통일.
      const stObj = pickObj(cfg, "structure");
      const minSecLegacy = pickNum(stObj, "target_duration_min_sec");
      const maxSecLegacy = pickNum(stObj, "target_duration_max_sec");
      const minMin = pickNum(stObj, "target_duration_min_min");
      const maxMin = pickNum(stObj, "target_duration_max_min");
      setStructure({
        target_duration_min_min: numToInput(
          minMin ?? (minSecLegacy != null ? Math.round(minSecLegacy / 60) : null),
        ),
        target_duration_max_min: numToInput(
          maxMin ?? (maxSecLegacy != null ? Math.round(maxSecLegacy / 60) : null),
        ),
        intro_template: pickStr(stObj, "intro_template"),
        body_template: pickStr(stObj, "body_template"),
        outro_template: pickStr(stObj, "outro_template"),
        intermission_every_min: numToInput(
          pickNum(stObj, "intermission_every_min"),
        ),
        intermission_total_count: numToInput(
          pickNum(stObj, "intermission_total_count"),
        ),
      });

      // 섹션 5 — 자막.
      const sbObj = pickObj(cfg, "subtitles");
      const lang = pickStr(sbObj, "language");
      const pos = pickStr(sbObj, "position");
      setSubtitles({
        enabled: pickBool(sbObj, "enabled"),
        burn_in: pickBool(sbObj, "burn_in"),
        language: (lang === "en" || lang === "ja" ? lang : "ko") as SubtitleLang,
        position: (pos === "top" || pos === "middle"
          ? pos
          : "bottom") as SubtitlePosition,
        max_chars_per_line: numToInput(pickNum(sbObj, "max_chars_per_line")),
      });

      // 섹션 6 — 레퍼런스.
      const rfObj = pickObj(cfg, "references");
      const rMode = pickStr(rfObj, "mode");
      setReferences({
        mode: (rMode === "style" || rMode === "composition"
          ? rMode
          : "off") as ReferenceMode,
        strength: numToInput(pickNum(rfObj, "strength")),
        image_urls_text: pickStrArray(rfObj, "image_urls").join("\n"),
      });

      // 섹션 8 — 자동화. pause_during_studio 는 읽기만 — 서버 강제 true.
      const atObj = pickObj(cfg, "automation");
      const qgObj = pickObj(atObj, "quality_gates");
      const resRaw = pickStr(qgObj, "min_resolution");
      const resVal: Resolution =
        resRaw === "720p" ||
        resRaw === "1440p" ||
        resRaw === "2160p"
          ? (resRaw as Resolution)
          : "1080p";
      setAutomation({
        retry_on_fail: numToInput(pickNum(atObj, "retry_on_fail")),
        min_duration_sec: numToInput(pickNum(qgObj, "min_duration_sec")),
        max_duration_sec: numToInput(pickNum(qgObj, "max_duration_sec")),
        min_loudness_lufs: numToInput(pickNum(qgObj, "min_loudness_lufs")),
        max_loudness_lufs: numToInput(pickNum(qgObj, "max_loudness_lufs")),
        min_resolution: resVal,
      });

      // 섹션 9 — 음향.
      const auObj = pickObj(cfg, "audio");
      const duRaw = pickStr(auObj, "ducking_strength");
      const duVal: DuckingStrength =
        duRaw === "low" || duRaw === "strong"
          ? (duRaw as DuckingStrength)
          : "normal";
      // bgm_enabled 는 키가 없으면 true (기본 on — §10.3). pickBool 은 없으면 false 라 예외 처리.
      const bgmKey = "bgm_enabled" in auObj ? pickBool(auObj, "bgm_enabled") : true;
      setAudio({
        bgm_enabled: bgmKey,
        bgm_style_prompt: pickStr(auObj, "bgm_style_prompt"),
        bgm_volume_db: numToInput(pickNum(auObj, "bgm_volume_db")),
        ducking_strength: duVal,
        fade_in_sec: numToInput(pickNum(auObj, "fade_in_sec")),
        fade_out_sec: numToInput(pickNum(auObj, "fade_out_sec")),
      });
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [idNum]);

  useEffect(() => {
    if (!Number.isFinite(idNum)) return;
    load();
  }, [idNum, load]);

  const originals = useMemo(() => {
    if (!detail) return null;
    const cfg = detail.config ?? {};
    const cObj = pickObj(cfg, "content");
    const mObj = pickObj(cfg, "models");
    const mScript = pickObj(mObj, "script");
    const mImage = pickObj(mObj, "image");
    const mTts = pickObj(mObj, "tts");
    const uObj = pickObj(cfg, "upload");
    const visRaw = pickStr(uObj, "visibility");
    const stObj = pickObj(cfg, "structure");
    const sbObj = pickObj(cfg, "subtitles");
    const sbLang = pickStr(sbObj, "language");
    const sbPos = pickStr(sbObj, "position");
    const rfObj = pickObj(cfg, "references");
    const rMode = pickStr(rfObj, "mode");
    return {
      name: detail.name,
      content: {
        topic: pickStr(cObj, "topic"),
        tone: pickStr(cObj, "tone"),
        style: pickStr(cObj, "style"),
        target_audience: pickStr(cObj, "target_audience"),
        signature_phrase: pickStr(cObj, "signature_phrase"),
      },
      models: {
        script_model: pickStr(mScript, "model_id"),
        image_model: pickStr(mImage, "model_id"),
        tts_model: pickStr(mTts, "model_id"),
        tts_voice_id: pickStr(mTts, "voice_id"),
      },
      upload: {
        title_template: pickStr(uObj, "title_template"),
        description_template: pickStr(uObj, "description_template"),
        playlist_id: pickStr(uObj, "playlist_id"),
        visibility: (visRaw === "unlisted" || visRaw === "private"
          ? visRaw
          : "public") as Visibility,
        scheduled: pickBool(uObj, "scheduled"),
      },
      structure: (() => {
        const minSecLegacy = pickNum(stObj, "target_duration_min_sec");
        const maxSecLegacy = pickNum(stObj, "target_duration_max_sec");
        const minMin = pickNum(stObj, "target_duration_min_min");
        const maxMin = pickNum(stObj, "target_duration_max_min");
        return {
          target_duration_min_min: numToInput(
            minMin ?? (minSecLegacy != null ? Math.round(minSecLegacy / 60) : null),
          ),
          target_duration_max_min: numToInput(
            maxMin ?? (maxSecLegacy != null ? Math.round(maxSecLegacy / 60) : null),
          ),
          intro_template: pickStr(stObj, "intro_template"),
          body_template: pickStr(stObj, "body_template"),
          outro_template: pickStr(stObj, "outro_template"),
          intermission_every_min: numToInput(
            pickNum(stObj, "intermission_every_min"),
          ),
          intermission_total_count: numToInput(
            pickNum(stObj, "intermission_total_count"),
          ),
        };
      })(),
      subtitles: {
        enabled: pickBool(sbObj, "enabled"),
        burn_in: pickBool(sbObj, "burn_in"),
        language: (sbLang === "en" || sbLang === "ja" ? sbLang : "ko") as SubtitleLang,
        position: (sbPos === "top" || sbPos === "middle"
          ? sbPos
          : "bottom") as SubtitlePosition,
        max_chars_per_line: numToInput(pickNum(sbObj, "max_chars_per_line")),
      },
      references: {
        mode: (rMode === "style" || rMode === "composition"
          ? rMode
          : "off") as ReferenceMode,
        strength: numToInput(pickNum(rfObj, "strength")),
        image_urls_text: pickStrArray(rfObj, "image_urls").join("\n"),
      },
      automation: (() => {
        const atObj = pickObj(cfg, "automation");
        const qgObj = pickObj(atObj, "quality_gates");
        const resRaw = pickStr(qgObj, "min_resolution");
        const resVal: Resolution =
          resRaw === "720p" || resRaw === "1440p" || resRaw === "2160p"
            ? (resRaw as Resolution)
            : "1080p";
        return {
          retry_on_fail: numToInput(pickNum(atObj, "retry_on_fail")),
          min_duration_sec: numToInput(pickNum(qgObj, "min_duration_sec")),
          max_duration_sec: numToInput(pickNum(qgObj, "max_duration_sec")),
          min_loudness_lufs: numToInput(pickNum(qgObj, "min_loudness_lufs")),
          max_loudness_lufs: numToInput(pickNum(qgObj, "max_loudness_lufs")),
          min_resolution: resVal,
        };
      })(),
      audio: (() => {
        const auObj = pickObj(cfg, "audio");
        const duRaw = pickStr(auObj, "ducking_strength");
        const duVal: DuckingStrength =
          duRaw === "low" || duRaw === "strong"
            ? (duRaw as DuckingStrength)
            : "normal";
        const bgmKey =
          "bgm_enabled" in auObj ? pickBool(auObj, "bgm_enabled") : true;
        return {
          bgm_enabled: bgmKey,
          bgm_style_prompt: pickStr(auObj, "bgm_style_prompt"),
          bgm_volume_db: numToInput(pickNum(auObj, "bgm_volume_db")),
          ducking_strength: duVal,
          fade_in_sec: numToInput(pickNum(auObj, "fade_in_sec")),
          fade_out_sec: numToInput(pickNum(auObj, "fade_out_sec")),
        };
      })(),
    };
  }, [detail]);

  const modified = useMemo(() => {
    if (!originals) return false;
    if (name.trim() !== originals.name) return true;
    if (JSON.stringify(content) !== JSON.stringify(originals.content)) return true;
    if (JSON.stringify(models) !== JSON.stringify(originals.models)) return true;
    if (JSON.stringify(upload) !== JSON.stringify(originals.upload)) return true;
    if (JSON.stringify(structure) !== JSON.stringify(originals.structure)) return true;
    if (JSON.stringify(subtitles) !== JSON.stringify(originals.subtitles)) return true;
    if (JSON.stringify(references) !== JSON.stringify(originals.references)) return true;
    if (JSON.stringify(automation) !== JSON.stringify(originals.automation)) return true;
    if (JSON.stringify(audio) !== JSON.stringify(originals.audio)) return true;
    return false;
  }, [name, content, models, upload, structure, subtitles, references, automation, audio, originals]);

  // 섹션 4 — 인터루드 fetch. 프리셋 로드 직후 한 번, 업로드/삭제 후 재조회.
  const loadInterludes = useCallback(async () => {
    if (!Number.isFinite(idNum)) return;
    try {
      const j = await presetInterludeApi.get(idNum);
      setInterludes(j);
    } catch (e) {
      setInterludeErr(e instanceof Error ? e.message : String(e));
    }
  }, [idNum]);

  useEffect(() => {
    if (detail) {
      loadInterludes();
    }
  }, [detail, loadInterludes]);

  const uploadInterlude = useCallback(
    async (kind: InterludeKind, file: File) => {
      if (!detail) return;
      setInterludeBusy((b) => ({ ...b, [kind]: true }));
      setInterludeErr(null);
      try {
        await presetInterludeApi.upload(detail.id, kind, file);
        await loadInterludes();
      } catch (e) {
        setInterludeErr(e instanceof Error ? e.message : String(e));
      } finally {
        setInterludeBusy((b) => ({ ...b, [kind]: false }));
      }
    },
    [detail, loadInterludes],
  );

  const deleteInterlude = useCallback(
    async (kind: InterludeKind) => {
      if (!detail) return;
      setInterludeBusy((b) => ({ ...b, [kind]: true }));
      setInterludeErr(null);
      try {
        await presetInterludeApi.remove(detail.id, kind);
        await loadInterludes();
      } catch (e) {
        setInterludeErr(e instanceof Error ? e.message : String(e));
      } finally {
        setInterludeBusy((b) => ({ ...b, [kind]: false }));
      }
    },
    [detail, loadInterludes],
  );

  const changeIntermissionEvery = useCallback(
    async (sec: number) => {
      if (!detail) return;
      if (!Number.isFinite(sec) || sec < 30 || sec > 1800) return;
      try {
        const j = await presetInterludeApi.updateConfig(detail.id, sec);
        setInterludes(j);
      } catch (e) {
        // 입력 중 노이즈 에러는 UI 에 덮어쓰지 않는다.
        console.warn("intermission_every_sec update failed", e);
      }
    },
    [detail],
  );

  const save = async () => {
    if (!detail) return;
    setSaving(true);
    setSaveErr(null);
    try {
      // 기존 config 를 베이스로 섹션별 partial 병합.
      const nextConfig: Record<string, unknown> = { ...(detail.config ?? {}) };
      nextConfig.content = {
        ...(pickObj(detail.config ?? {}, "content")),
        topic: content.topic,
        tone: content.tone,
        style: content.style,
        target_audience: content.target_audience,
        signature_phrase: content.signature_phrase,
      };
      nextConfig.models = {
        ...(pickObj(detail.config ?? {}, "models")),
        script: { model_id: models.script_model },
        image: { model_id: models.image_model },
        tts: { model_id: models.tts_model, voice_id: models.tts_voice_id },
      };
      nextConfig.upload = {
        ...(pickObj(detail.config ?? {}, "upload")),
        title_template: upload.title_template,
        description_template: upload.description_template,
        playlist_id: upload.playlist_id,
        visibility: upload.visibility,
        scheduled: upload.scheduled,
      };

      // 섹션 4 — 영상 구조.
      //   - 분 단위로 입력받고, 초 단위 레거시 키도 동시 저장해 기존 파이프라인 호환.
      //   - 의미 없는 opening_sec/closing_sec/segment_count_* 키는 명시적 삭제.
      const minMin = inputToNum(structure.target_duration_min_min);
      const maxMin = inputToNum(structure.target_duration_max_min);
      const prevStruct = pickObj(detail.config ?? {}, "structure");
      nextConfig.structure = {
        ...prevStruct,
        target_duration_min_min: minMin,
        target_duration_max_min: maxMin,
        target_duration_min_sec: minMin != null ? minMin * 60 : null,
        target_duration_max_sec: maxMin != null ? maxMin * 60 : null,
        intro_template: structure.intro_template,
        body_template: structure.body_template,
        outro_template: structure.outro_template,
        intermission_every_min: inputToNum(structure.intermission_every_min),
        intermission_total_count: inputToNum(structure.intermission_total_count),
      };
      // 구 키 제거 (JSON 에서 빼버린다).
      delete (nextConfig.structure as Record<string, unknown>).opening_sec;
      delete (nextConfig.structure as Record<string, unknown>).closing_sec;
      delete (nextConfig.structure as Record<string, unknown>).segment_count_min;
      delete (nextConfig.structure as Record<string, unknown>).segment_count_max;

      // 섹션 5 — 자막.
      nextConfig.subtitles = {
        ...(pickObj(detail.config ?? {}, "subtitles")),
        enabled: subtitles.enabled,
        burn_in: subtitles.burn_in,
        language: subtitles.language,
        position: subtitles.position,
        max_chars_per_line: inputToNum(subtitles.max_chars_per_line),
      };

      // 섹션 6 — 레퍼런스.
      const refUrls = references.image_urls_text
        .split("\n")
        .map((l) => l.trim())
        .filter((l) => l.length > 0);
      nextConfig.references = {
        ...(pickObj(detail.config ?? {}, "references")),
        mode: references.mode,
        strength: inputToNum(references.strength),
        image_urls: refUrls,
      };

      // 섹션 8 — 자동화. pause_during_studio 는 UI 토글 없이 서버가 강제 true.
      // 프런트가 먼저 true 로 박아서 저장 → 서버 Pydantic 모델 붙을 때도 일관.
      const prevAt = pickObj(detail.config ?? {}, "automation");
      const prevQg = pickObj(prevAt, "quality_gates");
      nextConfig.automation = {
        ...prevAt,
        retry_on_fail: inputToNum(automation.retry_on_fail),
        pause_during_studio: true,
        quality_gates: {
          ...prevQg,
          min_duration_sec: inputToNum(automation.min_duration_sec),
          max_duration_sec: inputToNum(automation.max_duration_sec),
          min_loudness_lufs: inputToNum(automation.min_loudness_lufs),
          max_loudness_lufs: inputToNum(automation.max_loudness_lufs),
          min_resolution: automation.min_resolution,
        },
      };

      // 섹션 9 — 음향.
      nextConfig.audio = {
        ...(pickObj(detail.config ?? {}, "audio")),
        bgm_enabled: audio.bgm_enabled,
        bgm_style_prompt: audio.bgm_style_prompt,
        bgm_volume_db: inputToNum(audio.bgm_volume_db),
        ducking_strength: audio.ducking_strength,
        fade_in_sec: inputToNum(audio.fade_in_sec),
        fade_out_sec: inputToNum(audio.fade_out_sec),
      };

      const body: Record<string, unknown> = { config: nextConfig };
      if (name.trim() !== detail.name) body.name = name.trim();

      const res = await fetch(v2Url(`/v2/presets/${detail.id}`), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const txt = await res.text();
        throw new Error(`HTTP ${res.status} ${txt}`);
      }
      const j: PresetDetail = await res.json();
      setDetail(j);
      setName(j.name);
    } catch (e) {
      setSaveErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!detail) return;
    try {
      const res = await fetch(v2Url(`/v2/presets/${detail.id}`), {
        method: "DELETE",
      });
      if (!res.ok && res.status !== 204) {
        const txt = await res.text();
        throw new Error(`HTTP ${res.status} ${txt}`);
      }
      router.push("/v2/presets");
    } catch (e) {
      setSaveErr(e instanceof Error ? e.message : String(e));
      setConfirmDel(false);
    }
  };

  if (!Number.isFinite(idNum)) {
    return (
      <div className="p-6">
        <ErrorState message="올바르지 않은 프리셋 ID입니다." />
      </div>
    );
  }
  if (loading) {
    return (
      <div className="p-6">
        <LoadingState />
      </div>
    );
  }
  if (err) {
    return (
      <div className="p-6">
        <ErrorState message={err} onRetry={load} />
      </div>
    );
  }
  if (!detail) return null;

  const c = channelColor(detail.channel_id);
  const isDdalkkak = detail.form_type === "딸깍폼";
  const activeMeta = SECTIONS.find((s) => s.key === active)!;

  return (
    <div className="flex flex-col h-full">
      {/* 상단 고정 바 --------------------------------------------------- */}
      <header className="sticky top-0 z-10 bg-bg-primary border-b border-border px-5 py-3 flex items-center gap-3">
        <Link
          href="/v2/presets"
          className="text-xs text-gray-400 hover:text-gray-100 underline-offset-2 hover:underline"
        >
          ← 목록
        </Link>
        <div className="flex items-center gap-2 min-w-0">
          <span
            className={`px-2 py-0.5 rounded-md text-xs font-semibold ${c.bgSoft} ${c.text} border ${c.border}`}
          >
            CH{detail.channel_id}
          </span>
          <span className="px-2 py-0.5 rounded-md text-xs bg-bg-tertiary text-gray-300 border border-border">
            {detail.form_type}
          </span>
          <h1 className="text-base font-semibold text-gray-100 truncate">
            {detail.full_name}
          </h1>
          {modified && (
            <span className="px-2 py-0.5 rounded-md text-xs bg-amber-500/15 text-amber-300 border border-amber-500/30">
              modified
            </span>
          )}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <V2Button variant="ghost" size="sm" onClick={() => setConfirmDel(true)}>
            삭제
          </V2Button>
          <V2Button
            variant="primary"
            size="sm"
            onClick={save}
            disabled={!modified || saving}
            loading={saving}
          >
            저장
          </V2Button>
        </div>
      </header>

      <div className="flex-1 flex min-h-0">
        {/* 좌측 섹션 탭 ------------------------------------------------ */}
        <nav
          className="w-[220px] shrink-0 border-r border-border bg-bg-secondary p-3 space-y-1 overflow-y-auto"
          aria-label="프리셋 섹션"
        >
          {SECTIONS.map((s) => {
            const isActive = active === s.key;
            return (
              <button
                key={s.key}
                type="button"
                onClick={() => setActive(s.key)}
                aria-current={isActive ? "page" : undefined}
                className={`w-full text-left px-3 py-2 rounded-md text-sm flex items-center gap-2 transition-colors ${
                  isActive
                    ? "bg-sky-500/15 text-sky-200 border border-sky-500/30"
                    : "text-gray-300 hover:bg-bg-tertiary hover:text-gray-100 border border-transparent"
                }`}
              >
                <span className="text-xs text-gray-500 w-4 text-right">
                  {s.num}.
                </span>
                <span className="truncate">{s.label}</span>
              </button>
            );
          })}

          {UPCOMING.length > 0 && (
            <>
              <p className="mt-4 px-3 text-xs text-gray-500 uppercase tracking-wide">
                다음 릴리즈
              </p>
              <ul className="px-3 pt-1 space-y-1">
                {UPCOMING.map((u) => (
                  <li
                    key={u.num}
                    className="text-xs text-gray-500 flex items-center gap-2"
                  >
                    <span className="w-4 text-right">{u.num}.</span>
                    <span className="truncate">{u.label}</span>
                    <span className="ml-auto text-[11px] text-gray-600">
                      {u.when}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </nav>

        {/* 우측 섹션 본문 ---------------------------------------------- */}
        <div className="flex-1 overflow-y-auto p-6">
          <section className="max-w-[780px]">
            <h2 className="text-gray-100 mb-4">
              <span className="text-gray-500 mr-2">{activeMeta.num}.</span>
              {activeMeta.label}
            </h2>

            {active === "identity" && (
              <IdentitySection
                detail={detail}
                name={name}
                setName={setName}
                isDdalkkak={isDdalkkak}
                c={c}
                idp={idp}
                saveErr={saveErr}
              />
            )}
            {active === "content" && (
              <ContentSection
                value={content}
                onChange={setContent}
                isDdalkkak={isDdalkkak}
                idp={idp}
              />
            )}
            {active === "models" && (
              <ModelsSection
                value={models}
                onChange={setModels}
                idp={idp}
              />
            )}
            {active === "structure" && (
              <StructureSection
                value={structure}
                onChange={setStructure}
                idp={idp}
                interludes={interludes}
                interludeBusy={interludeBusy}
                interludeErr={interludeErr}
                onUploadInterlude={uploadInterlude}
                onDeleteInterlude={deleteInterlude}
                onChangeIntermissionEvery={changeIntermissionEvery}
              />
            )}
            {active === "subtitles" && (
              <SubtitlesSection
                value={subtitles}
                onChange={setSubtitles}
                idp={idp}
              />
            )}
            {active === "references" && (
              <ReferencesSection
                value={references}
                onChange={setReferences}
                idp={idp}
              />
            )}
            {active === "upload" && (
              <UploadSection
                value={upload}
                onChange={setUpload}
                idp={idp}
              />
            )}
            {active === "automation" && (
              <AutomationSection
                value={automation}
                onChange={setAutomation}
                idp={idp}
              />
            )}
            {active === "audio" && (
              <AudioSection
                value={audio}
                onChange={setAudio}
                idp={idp}
              />
            )}

            {saveErr && active !== "identity" && (
              <p
                role="alert"
                className="mt-4 text-xs text-red-300 bg-red-500/10 border border-red-500/40 rounded-md px-3 py-2"
              >
                {saveErr}
              </p>
            )}
          </section>
        </div>
      </div>

      <ConfirmDialog
        open={confirmDel}
        title="프리셋을 삭제할까요?"
        description={`"${detail.full_name}" 을 삭제합니다. 큐/태스크에서 이 프리셋을 참조하면 삭제가 차단될 수 있습니다.`}
        confirmLabel="삭제"
        cancelLabel="취소"
        danger
        onConfirm={remove}
        onCancel={() => setConfirmDel(false)}
      />
    </div>
  );
}

/* ========================================================================= */
/* 섹션 1 — 식별 (기존 유지)                                                   */
/* ========================================================================= */

function IdentitySection({
  detail,
  name,
  setName,
  isDdalkkak,
  c,
  idp,
  saveErr,
}: {
  detail: PresetDetail;
  name: string;
  setName: (v: string) => void;
  isDdalkkak: boolean;
  c: ReturnType<typeof channelColor>;
  idp: string;
  saveErr: string | null;
}) {
  return (
    <div className="space-y-5">
      <div>
        <label
          htmlFor={`${idp}-full`}
          className="block text-xs text-gray-400 mb-1"
        >
          풀네임 (자동)
        </label>
        <input
          id={`${idp}-full`}
          type="text"
          value={`CH${detail.channel_id}-${detail.form_type}-${
            name.trim() || "…"
          }`}
          readOnly
          className="w-full bg-bg-primary border border-border rounded-md px-3 py-2 text-sm text-gray-400 cursor-default"
        />
        <p className="mt-1 text-xs text-gray-500">
          이름 규칙: {"{채널}-{폼타입}-{name}"}. name 만 수정 가능합니다.
        </p>
      </div>

      <div>
        <label
          htmlFor={`${idp}-name`}
          className="block text-xs text-gray-400 mb-1"
        >
          이름 (사용자 부분)
        </label>
        <input
          id={`${idp}-name`}
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={64}
          className="w-full bg-bg-tertiary border border-border rounded-md px-3 py-2 text-sm text-gray-100"
        />
      </div>

      <div>
        <p className="block text-xs text-gray-400 mb-1">채널</p>
        <div className="flex items-center gap-2">
          <span
            className={`px-2 py-0.5 rounded-md text-xs font-semibold ${c.bgSoft} ${c.text} border ${c.border}`}
          >
            CH{detail.channel_id}
          </span>
          {isDdalkkak && (
            <span className="text-xs text-gray-500">
              딸깍폼은 채널 변경이 잠겨 있습니다 (승격/강등으로만 변경).
            </span>
          )}
        </div>
      </div>

      <div>
        <p className="block text-xs text-gray-400 mb-1">폼 타입</p>
        <span className="px-2 py-0.5 rounded-md text-xs font-semibold bg-bg-tertiary text-gray-300 border border-border">
          {detail.form_type}
        </span>
      </div>

      {saveErr && (
        <p
          role="alert"
          className="text-xs text-red-300 bg-red-500/10 border border-red-500/40 rounded-md px-3 py-2"
        >
          {saveErr}
        </p>
      )}
    </div>
  );
}

/* ========================================================================= */
/* 섹션 2 — 내용 방향                                                          */
/* ========================================================================= */

interface ContentState {
  topic: string;
  tone: string;
  style: string;
  target_audience: string;
  signature_phrase: string;
}

function ContentSection({
  value,
  onChange,
  isDdalkkak,
  idp,
}: {
  value: ContentState;
  onChange: (v: ContentState) => void;
  isDdalkkak: boolean;
  idp: string;
}) {
  const patch = (k: keyof ContentState, v: string) =>
    onChange({ ...value, [k]: v });

  return (
    <div className="space-y-5">
      {/* 주제 ------------------------------------------------------- */}
      <div>
        <label
          htmlFor={`${idp}-topic`}
          className="block text-xs text-gray-400 mb-1"
        >
          주제
        </label>
        {isDdalkkak ? (
          <div className="rounded-md border border-dashed border-border bg-bg-secondary/50 px-3 py-2 text-xs text-gray-400">
            딸깍폼은 큐에서 주입됩니다. 주제는 `/v2/queue` 큐 추가 모달에서
            한 건씩 입력하세요.
          </div>
        ) : (
          <textarea
            id={`${idp}-topic`}
            value={value.topic}
            onChange={(e) => patch("topic", e.target.value)}
            rows={4}
            placeholder="이 테스트폼이 다룰 고정 주제를 자유롭게 입력합니다."
            className="w-full bg-bg-tertiary border border-border rounded-md px-3 py-2 text-sm text-gray-100 resize-y"
          />
        )}
      </div>

      {/* 톤/분위기 -------------------------------------------------- */}
      <SuggestField
        idp={`${idp}-tone`}
        label="톤/분위기"
        value={value.tone}
        onChange={(v) => patch("tone", v)}
        suggestions={TONE_SUGGESTIONS}
        placeholder="예: 차분한 다큐"
      />

      {/* 스타일 ----------------------------------------------------- */}
      <SuggestField
        idp={`${idp}-style`}
        label="스타일"
        value={value.style}
        onChange={(v) => patch("style", v)}
        suggestions={STYLE_SUGGESTIONS}
        placeholder="예: 역사"
      />

      {/* 시청자 타깃 ------------------------------------------------ */}
      <div>
        <label
          htmlFor={`${idp}-audience`}
          className="block text-xs text-gray-400 mb-1"
        >
          시청자 타깃 메모
        </label>
        <input
          id={`${idp}-audience`}
          type="text"
          value={value.target_audience}
          onChange={(e) => patch("target_audience", e.target.value)}
          maxLength={200}
          placeholder="예: 30~50대 한국사 입문자"
          className="w-full bg-bg-tertiary border border-border rounded-md px-3 py-2 text-sm text-gray-100"
        />
      </div>

      {/* 시그니처 문구 ---------------------------------------------- */}
      <div>
        <label
          htmlFor={`${idp}-sig`}
          className="block text-xs text-gray-400 mb-1"
        >
          시그니처 문구 (인트로/아웃트로용)
        </label>
        <input
          id={`${idp}-sig`}
          type="text"
          value={value.signature_phrase}
          onChange={(e) => patch("signature_phrase", e.target.value)}
          maxLength={200}
          placeholder="예: 오늘도 끝까지 가봅시다"
          className="w-full bg-bg-tertiary border border-border rounded-md px-3 py-2 text-sm text-gray-100"
        />
      </div>
    </div>
  );
}

/** 드롭다운(권장) + 자유 입력 겸용 필드. */
function SuggestField({
  idp,
  label,
  value,
  onChange,
  suggestions,
  placeholder,
}: {
  idp: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  suggestions: readonly string[];
  placeholder?: string;
}) {
  const listId = `${idp}-list`;
  return (
    <div>
      <label htmlFor={idp} className="block text-xs text-gray-400 mb-1">
        {label}
      </label>
      <input
        id={idp}
        list={listId}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full bg-bg-tertiary border border-border rounded-md px-3 py-2 text-sm text-gray-100"
      />
      <datalist id={listId}>
        {suggestions.map((s) => (
          <option key={s} value={s} />
        ))}
      </datalist>
      <p className="mt-1 text-[11px] text-gray-500">
        권장값 중 선택하거나 자유 입력할 수 있습니다.
      </p>
    </div>
  );
}

/* ========================================================================= */
/* 섹션 3 — AI 모델                                                            */
/* ========================================================================= */

interface ModelsState {
  script_model: string;
  image_model: string;
  tts_model: string;
  tts_voice_id: string;
}

function ModelsSection({
  value,
  onChange,
  idp,
}: {
  value: ModelsState;
  onChange: (v: ModelsState) => void;
  idp: string;
}) {
  const [llm, setLlm] = useState<ModelInfo[] | null>(null);
  const [image, setImage] = useState<ModelInfo[] | null>(null);
  const [tts, setTts] = useState<ModelInfo[] | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [a, b, c] = await Promise.all([
          fetchModelList("llm"),
          fetchModelList("image"),
          fetchModelList("tts"),
        ]);
        if (cancelled) return;
        setLlm(a);
        setImage(b);
        setTts(c);
      } catch (e) {
        if (cancelled) return;
        setLoadErr(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const patch = (k: keyof ModelsState, v: string) =>
    onChange({ ...value, [k]: v });

  return (
    <div className="space-y-5">
      {loadErr && (
        <p className="text-xs text-red-300 bg-red-500/10 border border-red-500/40 rounded-md px-3 py-2">
          모델 목록 조회 실패: {loadErr}
        </p>
      )}

      <ModelSelect
        idp={`${idp}-script`}
        label="대본 모델"
        value={value.script_model}
        onChange={(v) => patch("script_model", v)}
        models={llm}
      />
      <ModelSelect
        idp={`${idp}-image`}
        label="이미지 모델"
        value={value.image_model}
        onChange={(v) => patch("image_model", v)}
        models={image}
      />
      <div className="grid grid-cols-1 sm:grid-cols-[1fr_180px] gap-3">
        <ModelSelect
          idp={`${idp}-tts`}
          label="TTS 모델"
          value={value.tts_model}
          onChange={(v) => patch("tts_model", v)}
          models={tts}
        />
        <div>
          <label
            htmlFor={`${idp}-voice`}
            className="block text-xs text-gray-400 mb-1"
          >
            TTS 음성 ID
          </label>
          <input
            id={`${idp}-voice`}
            type="text"
            value={value.tts_voice_id}
            onChange={(e) => patch("tts_voice_id", e.target.value)}
            placeholder="ElevenLabs voice_id"
            className="w-full bg-bg-tertiary border border-border rounded-md px-3 py-2 text-sm text-gray-100"
          />
        </div>
      </div>

      {/* 고정 모델들 -------------------------------------------------- */}
      <div className="rounded-xl border border-border bg-bg-secondary/40 p-4 space-y-2">
        <p className="text-xs text-gray-400">
          프리셋 단위로 바꿀 수 없는 모델 (§10.3 섹션 3):
        </p>
        <div className="flex items-center gap-2 text-xs">
          <span className="text-gray-500 w-20 shrink-0">썸네일</span>
          <span className="text-gray-100">
            Nano Banana (Gemini 2.5 Flash Image) — 고정
          </span>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className="text-gray-500 w-20 shrink-0">BGM</span>
          <span className="text-gray-100">ElevenLabs Music — 고정</span>
        </div>
      </div>

      <p className="text-[11px] text-gray-500">
        모델별 고급 옵션(temperature 등)과 시스템 프롬프트는 전역 설정에서
        관리합니다. 프리셋에는 선택한 model id 만 저장됩니다.
      </p>
    </div>
  );
}

function ModelSelect({
  idp,
  label,
  value,
  onChange,
  models,
}: {
  idp: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  models: ModelInfo[] | null;
}) {
  const isLoading = models === null;
  return (
    <div>
      <label htmlFor={idp} className="block text-xs text-gray-400 mb-1">
        {label}
      </label>
      <select
        id={idp}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={isLoading}
        className="w-full bg-bg-tertiary border border-border rounded-md px-3 py-2 text-sm text-gray-100 disabled:opacity-60"
      >
        <option value="">— 선택 —</option>
        {value && !isLoading && !models?.some((m) => m.id === value) && (
          <option value={value}>(레지스트리에 없음) {value}</option>
        )}
        {(models ?? []).map((m) => (
          <option key={m.id} value={m.id}>
            {m.name ?? m.id} {m.provider ? `· ${m.provider}` : ""}
            {m.available === false ? " · (키 미설정)" : ""}
          </option>
        ))}
      </select>
      {isLoading && (
        <p className="mt-1 text-[11px] text-gray-500">모델 목록 불러오는 중…</p>
      )}
    </div>
  );
}

/* ========================================================================= */
/* 섹션 7 — 업로드 템플릿                                                      */
/* ========================================================================= */

interface UploadState {
  title_template: string;
  description_template: string;
  playlist_id: string;
  visibility: Visibility;
  scheduled: boolean;
}

function UploadSection({
  value,
  onChange,
  idp,
}: {
  value: UploadState;
  onChange: (v: UploadState) => void;
  idp: string;
}) {
  const patch = <K extends keyof UploadState>(k: K, v: UploadState[K]) =>
    onChange({ ...value, [k]: v });

  return (
    <div className="space-y-5">
      {/* 제목 템플릿 ------------------------------------------------- */}
      <div>
        <label
          htmlFor={`${idp}-title`}
          className="block text-xs text-gray-400 mb-1"
        >
          제목 템플릿
        </label>
        <input
          id={`${idp}-title`}
          type="text"
          value={value.title_template}
          onChange={(e) => patch("title_template", e.target.value)}
          placeholder="예: [{채널이름}] {주제}"
          className="w-full bg-bg-tertiary border border-border rounded-md px-3 py-2 text-sm text-gray-100 font-mono"
        />
        <PlaceholderHints />
      </div>

      {/* 설명 템플릿 ------------------------------------------------- */}
      <div>
        <label
          htmlFor={`${idp}-desc`}
          className="block text-xs text-gray-400 mb-1"
        >
          설명 템플릿
        </label>
        <textarea
          id={`${idp}-desc`}
          value={value.description_template}
          onChange={(e) => patch("description_template", e.target.value)}
          rows={6}
          placeholder={"예: {요약}\n\n#{해시태그}\n\n{채널이름} · {날짜}"}
          className="w-full bg-bg-tertiary border border-border rounded-md px-3 py-2 text-sm text-gray-100 font-mono resize-y"
        />
      </div>

      {/* 태그 안내 --------------------------------------------------- */}
      <div className="rounded-md border border-border bg-bg-secondary/40 px-3 py-2 text-xs text-gray-400">
        태그는 대본 생성 단계에서
        <code className="mx-1 text-gray-200">generate_script_with_meta</code>
        가 title·tags·summary 를 동시 산출합니다. 이 프리셋에서 따로 입력하지
        않습니다.
      </div>

      {/* 재생목록 ---------------------------------------------------- */}
      <div>
        <label
          htmlFor={`${idp}-playlist`}
          className="block text-xs text-gray-400 mb-1"
        >
          재생목록 ID
        </label>
        <input
          id={`${idp}-playlist`}
          type="text"
          value={value.playlist_id}
          onChange={(e) => patch("playlist_id", e.target.value)}
          placeholder="YouTube playlist id (옵션)"
          className="w-full bg-bg-tertiary border border-border rounded-md px-3 py-2 text-sm text-gray-100 font-mono"
        />
        <p className="mt-1 text-[11px] text-gray-500">
          신규 재생목록 생성은 `/v2/youtube/playlists` 연결 후 지원 예정 (v2.4.0).
        </p>
      </div>

      {/* 공개 설정 --------------------------------------------------- */}
      <div>
        <p className="block text-xs text-gray-400 mb-1">공개 설정</p>
        <div className="flex items-center gap-2">
          {VISIBILITY_OPTIONS.map((o) => {
            const sel = value.visibility === o.value;
            return (
              <button
                key={o.value}
                type="button"
                onClick={() => patch("visibility", o.value)}
                className={`h-9 px-3.5 rounded-md text-sm border transition-colors ${
                  sel
                    ? "bg-sky-500/15 text-sky-200 border-sky-500/40"
                    : "bg-bg-tertiary text-gray-300 border-border hover:bg-gray-700"
                }`}
                aria-pressed={sel}
              >
                {o.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* 예약 업로드 ------------------------------------------------- */}
      <div>
        <label className="inline-flex items-center gap-2 text-sm text-gray-200">
          <input
            type="checkbox"
            checked={value.scheduled}
            onChange={(e) => patch("scheduled", e.target.checked)}
            className="h-4 w-4 rounded border-border bg-bg-tertiary"
          />
          예약 업로드 사용
        </label>
        <p className="mt-1 text-[11px] text-gray-500">
          구체 예약 시간은 `/v2/schedule` 의 스케줄 규칙을 따릅니다.
        </p>
      </div>
    </div>
  );
}

function PlaceholderHints() {
  const keys = ["{주제}", "{요약}", "{채널이름}", "{길이}", "{날짜}"] as const;
  return (
    <p className="mt-1 text-[11px] text-gray-500">
      쓸 수 있는 placeholder:{" "}
      {keys.map((k, i) => (
        <span key={k}>
          <code className="text-gray-300">{k}</code>
          {i < keys.length - 1 ? ", " : ""}
        </span>
      ))}
    </p>
  );
}

// ---------------------------------------------------------------------------
// 섹션 4 — 영상 구조 (v2.4.0 재구성, 기획 §10.3)
//   - 길이: 분 단위. 초 단위 레거시는 저장 단계에서 자동 동기화.
//   - 인트로/본문/아웃트로 템플릿: 자유 textarea + 추천값 드롭다운.
//   - 인터미션 주기: N분마다 / 총 N회 중 한쪽 (또는 둘 다) 설정.
//   - 오프닝/인터미션/엔딩 실제 영상은 InterludeUploadBlock 에서 별도 처리.

interface StructureValue {
  target_duration_min_min: string;
  target_duration_max_min: string;
  intro_template: string;
  body_template: string;
  outro_template: string;
  intermission_every_min: string;
  intermission_total_count: string;
}

/** 템플릿 드롭다운 추천값 — 대본 생성기 프롬프트에 그대로 꽂힌다. */
const INTRO_TEMPLATES = [
  "강한 훅 (질문으로 시작)",
  "사건 현장 묘사부터",
  "결론 선공개 (teaser)",
  "시청자 공감 멘트",
  "통계/숫자로 주의 환기",
] as const;
const BODY_TEMPLATES = [
  "시간순 서술 (연대기)",
  "사건 → 원인 → 결과",
  "주제 → 근거 3개 → 반론",
  "인물 중심 스토리텔링",
  "Q&A 문답식 전개",
] as const;
const OUTRO_TEMPLATES = [
  "요약 + 다음 편 예고",
  "질문 던지기 (댓글 유도)",
  "감정적 마무리 (여운)",
  "채널 구독 유도",
  "관련 영상 추천",
] as const;

function StructureSection({
  value,
  onChange,
  idp,
  interludes,
  interludeBusy,
  interludeErr,
  onUploadInterlude,
  onDeleteInterlude,
  onChangeIntermissionEvery,
}: {
  value: StructureValue;
  onChange: (v: StructureValue) => void;
  idp: string;
  interludes: InterludeState | null;
  interludeBusy: Partial<Record<InterludeKind, boolean>>;
  interludeErr: string | null;
  onUploadInterlude: (kind: InterludeKind, file: File) => void;
  onDeleteInterlude: (kind: InterludeKind) => void;
  onChangeIntermissionEvery: (sec: number) => void;
}) {
  const patch = <K extends keyof StructureValue>(k: K, v: StructureValue[K]) =>
    onChange({ ...value, [k]: v });

  return (
    <div className="space-y-6 text-sm">
      <p className="text-xs text-gray-500">
        길이는 분 단위, 템플릿은 자유 입력 또는 권장값 선택입니다. 비워 두면
        파이프라인 기본값이 쓰입니다.
      </p>

      {/* 1. 목표 길이 (분) ------------------------------------------- */}
      <div>
        <p className="block text-xs text-gray-400 mb-1">목표 영상 길이 (분)</p>
        <div className="grid grid-cols-2 gap-3">
          <NumField
            id={`${idp}-dur-min-min`}
            label="최소"
            value={value.target_duration_min_min}
            onChange={(v) => patch("target_duration_min_min", v)}
            placeholder="예: 8"
            min={1}
            max={180}
          />
          <NumField
            id={`${idp}-dur-max-min`}
            label="최대"
            value={value.target_duration_max_min}
            onChange={(v) => patch("target_duration_max_min", v)}
            placeholder="예: 12"
            min={1}
            max={180}
          />
        </div>
        <p className="mt-1 text-[11px] text-gray-500">
          대본 생성기는 이 구간을 목표로 문장 밀도 · 컷 수를 정합니다.
        </p>
      </div>

      {/* 2. 템플릿 3종 ------------------------------------------------ */}
      <TemplateField
        idp={`${idp}-intro`}
        label="인트로 템플릿"
        value={value.intro_template}
        onChange={(v) => patch("intro_template", v)}
        suggestions={INTRO_TEMPLATES}
        placeholder="예: 강한 훅 (질문으로 시작)"
        hint="대본 첫 30초의 구성을 지시합니다. 빈 값이면 LLM 이 자유 구성."
      />
      <TemplateField
        idp={`${idp}-body`}
        label="본문 템플릿"
        value={value.body_template}
        onChange={(v) => patch("body_template", v)}
        suggestions={BODY_TEMPLATES}
        placeholder="예: 시간순 서술 (연대기)"
        hint="본문 전개 방식. 채널 정체성을 가장 많이 결정하는 필드입니다."
      />
      <TemplateField
        idp={`${idp}-outro`}
        label="아웃트로 템플릿"
        value={value.outro_template}
        onChange={(v) => patch("outro_template", v)}
        suggestions={OUTRO_TEMPLATES}
        placeholder="예: 요약 + 다음 편 예고"
        hint="마지막 30초의 구성. 구독/다음 편 유도 여부를 포함합니다."
      />

      {/* 3. 인터미션 주기 --------------------------------------------- */}
      <div>
        <p className="block text-xs text-gray-400 mb-1">
          인터미션 삽입 규칙 (선택)
        </p>
        <div className="grid grid-cols-2 gap-3">
          <NumField
            id={`${idp}-inter-every`}
            label="N분마다"
            value={value.intermission_every_min}
            onChange={(v) => {
              patch("intermission_every_min", v);
              // 백엔드의 intermission_every_sec 도 즉시 맞춤(초 환산).
              const n = Number(v);
              if (Number.isFinite(n) && n >= 1) {
                onChangeIntermissionEvery(Math.round(n * 60));
              }
            }}
            placeholder="예: 3"
            min={1}
            max={30}
          />
          <NumField
            id={`${idp}-inter-total`}
            label="총 N회"
            value={value.intermission_total_count}
            onChange={(v) => patch("intermission_total_count", v)}
            placeholder="예: 2"
            min={0}
            max={20}
          />
        </div>
        <p className="mt-1 text-[11px] text-gray-500">
          두 값 모두 있으면 &quot;N분마다&quot; 가 우선이고 최대 &quot;총 N회&quot; 만큼만 삽입합니다.
          기본 주기는 3분(180초) 입니다.
        </p>
      </div>

      {/* 4. 인터루드 영상 업로드 -------------------------------------- */}
      <InterludeUploadBlock
        interludes={interludes}
        busy={interludeBusy}
        error={interludeErr}
        onUpload={onUploadInterlude}
        onDelete={onDeleteInterlude}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// 템플릿 textarea + datalist 추천값 겸용 필드.
function TemplateField({
  idp,
  label,
  value,
  onChange,
  suggestions,
  placeholder,
  hint,
}: {
  idp: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  suggestions: readonly string[];
  placeholder?: string;
  hint?: string;
}) {
  const listId = `${idp}-list`;
  return (
    <div>
      <label htmlFor={idp} className="block text-xs text-gray-400 mb-1">
        {label}
      </label>
      <input
        id={idp}
        list={listId}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full bg-bg-tertiary border border-border rounded-md px-3 py-2 text-sm text-gray-100"
      />
      <datalist id={listId}>
        {suggestions.map((s) => (
          <option key={s} value={s} />
        ))}
      </datalist>
      {hint && (
        <p className="mt-1 text-[11px] text-gray-500">{hint}</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 오프닝/인터미션/엔딩 영상 업로드 블록. 파일 슬롯 3개.
function InterludeUploadBlock({
  interludes,
  busy,
  error,
  onUpload,
  onDelete,
}: {
  interludes: InterludeState | null;
  busy: Partial<Record<InterludeKind, boolean>>;
  error: string | null;
  onUpload: (kind: InterludeKind, file: File) => void;
  onDelete: (kind: InterludeKind) => void;
}) {
  const KINDS: { key: InterludeKind; label: string; hint: string }[] = [
    {
      key: "opening",
      label: "오프닝 영상",
      hint: "본편 맨 앞에 붙습니다. 업로드가 없으면 넘어갑니다.",
    },
    {
      key: "intermission",
      label: "인터미션 영상",
      hint: "본편 중간에 위 규칙대로 끼워 넣습니다.",
    },
    {
      key: "ending",
      label: "엔딩 영상",
      hint: "본편 맨 뒤에 붙습니다. 업로드가 없으면 넘어갑니다.",
    },
  ];

  return (
    <div>
      <p className="block text-xs text-gray-400 mb-2">
        오프닝 · 인터미션 · 엔딩 영상 (선택)
      </p>
      <p className="text-[11px] text-gray-500 mb-3">
        각 슬롯에 mp4/mov/mkv/webm/m4v/avi 파일 1 개씩 업로드할 수 있습니다
        (최대 500MB). 없는 kind 는 그냥 넘어갑니다.
      </p>

      <div className="grid grid-cols-1 gap-3">
        {KINDS.map((k) => {
          const entry: InterludeEntry | undefined = interludes
            ? (interludes[k.key] as InterludeEntry)
            : undefined;
          return (
            <InterludeSlot
              key={k.key}
              label={k.label}
              hint={k.hint}
              entry={entry ?? null}
              busy={busy[k.key] === true}
              disabled={interludes === null}
              onUpload={(f) => onUpload(k.key, f)}
              onDelete={() => onDelete(k.key)}
            />
          );
        })}
      </div>

      {error && (
        <p
          role="alert"
          className="mt-3 text-xs text-red-300 bg-red-500/10 border border-red-500/40 rounded-md px-3 py-2"
        >
          {error}
        </p>
      )}
    </div>
  );
}

function InterludeSlot({
  label,
  hint,
  entry,
  busy,
  disabled,
  onUpload,
  onDelete,
}: {
  label: string;
  hint: string;
  entry: InterludeEntry | null;
  busy: boolean;
  disabled: boolean;
  onUpload: (file: File) => void;
  onDelete: () => void;
}) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const hasFile = Boolean(entry?.video_path);
  const src = hasFile && entry?.video_path ? assetUrl(entry.video_path) : null;

  const formatSize = (b: number | null | undefined) => {
    if (!b || b < 1024) return `${b ?? 0} B`;
    if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
    if (b < 1024 * 1024 * 1024) return `${(b / 1024 / 1024).toFixed(1)} MB`;
    return `${(b / 1024 / 1024 / 1024).toFixed(2)} GB`;
  };

  const formatDur = (s: number | null | undefined) => {
    if (!s || s <= 0) return "—";
    const mm = Math.floor(s / 60);
    const ss = Math.round(s % 60);
    return `${mm}:${String(ss).padStart(2, "0")}`;
  };

  return (
    <div className="rounded-md border border-border bg-bg-secondary p-3">
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm text-gray-100 font-medium">{label}</p>
          <p className="text-[11px] text-gray-500 mt-0.5">{hint}</p>

          {hasFile && entry ? (
            <div className="mt-2 text-[12px] text-gray-400 space-y-0.5">
              <p className="truncate">
                <span className="text-gray-500">파일: </span>
                <span className="text-gray-200">{entry.filename || "—"}</span>
              </p>
              <p className="tabular-nums">
                <span className="text-gray-500">길이: </span>
                <span className="text-gray-200">
                  {formatDur(entry.duration)}
                </span>
                <span className="text-gray-500 ml-3">크기: </span>
                <span className="text-gray-200">
                  {formatSize(entry.size_bytes)}
                </span>
              </p>
            </div>
          ) : (
            <p className="mt-2 text-[12px] text-gray-500 italic">
              업로드된 영상이 없습니다.
            </p>
          )}
        </div>

        {src && (
          <video
            src={src}
            className="w-[120px] h-[68px] rounded border border-border bg-black object-contain shrink-0"
            muted
            preload="metadata"
            controls={false}
          />
        )}
      </div>

      <div className="mt-3 flex items-center gap-2">
        <input
          ref={inputRef}
          type="file"
          accept=".mp4,.mov,.mkv,.webm,.m4v,.avi,video/*"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onUpload(f);
            e.target.value = "";
          }}
        />
        <V2Button
          variant="secondary"
          size="sm"
          onClick={() => inputRef.current?.click()}
          disabled={disabled || busy}
          loading={busy}
        >
          {hasFile ? "다시 올리기" : "영상 업로드"}
        </V2Button>
        {hasFile && (
          <V2Button
            variant="ghost"
            size="sm"
            onClick={onDelete}
            disabled={disabled || busy}
          >
            삭제
          </V2Button>
        )}
      </div>
    </div>
  );
}

function NumField({
  id,
  label,
  value,
  onChange,
  placeholder,
  min,
  max,
  step,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  min?: number;
  max?: number;
  step?: number;
}) {
  return (
    <div>
      <label htmlFor={id} className="block text-[11px] text-gray-500 mb-1">
        {label}
      </label>
      <input
        id={id}
        type="number"
        inputMode="numeric"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        min={min}
        max={max}
        step={step}
        className="w-full bg-bg-tertiary border border-border rounded-md px-3 py-2 text-sm text-gray-100 tabular-nums"
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// 섹션 5 — 자막

interface SubtitlesValue {
  enabled: boolean;
  burn_in: boolean;
  language: SubtitleLang;
  position: SubtitlePosition;
  max_chars_per_line: string;
}

function SubtitlesSection({
  value,
  onChange,
  idp,
}: {
  value: SubtitlesValue;
  onChange: (v: SubtitlesValue) => void;
  idp: string;
}) {
  const patch = <K extends keyof SubtitlesValue>(k: K, v: SubtitlesValue[K]) =>
    onChange({ ...value, [k]: v });
  const disabled = !value.enabled;

  return (
    <div className="space-y-5 text-sm">
      <div>
        <label className="inline-flex items-center gap-2 text-sm text-gray-200">
          <input
            type="checkbox"
            checked={value.enabled}
            onChange={(e) => patch("enabled", e.target.checked)}
            className="h-4 w-4 rounded border-border bg-bg-tertiary"
          />
          자막 사용
        </label>
        <p className="mt-1 text-[11px] text-gray-500">
          꺼짐 상태면 이 섹션의 나머지 필드는 파이프라인에서 무시됩니다.
        </p>
      </div>

      <div className={disabled ? "opacity-50 pointer-events-none" : ""}>
        <div className="space-y-5">
          {/* 구워넣기 ----------------------------------------------- */}
          <div>
            <label className="inline-flex items-center gap-2 text-sm text-gray-200">
              <input
                type="checkbox"
                checked={value.burn_in}
                onChange={(e) => patch("burn_in", e.target.checked)}
                className="h-4 w-4 rounded border-border bg-bg-tertiary"
              />
              영상에 구워넣기 (burn-in)
            </label>
            <p className="mt-1 text-[11px] text-gray-500">
              체크 시 최종 영상에 자막이 영구 합성됩니다. 체크 해제 시 별도
              자막 파일(.srt) 만 생성합니다.
            </p>
          </div>

          {/* 언어 ---------------------------------------------------- */}
          <div>
            <label
              htmlFor={`${idp}-sub-lang`}
              className="block text-xs text-gray-400 mb-1"
            >
              자막 언어
            </label>
            <select
              id={`${idp}-sub-lang`}
              value={value.language}
              onChange={(e) => patch("language", e.target.value as SubtitleLang)}
              className="w-full bg-bg-tertiary border border-border rounded-md px-3 py-2 text-sm text-gray-100"
            >
              {SUBTITLE_LANG_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>

          {/* 위치 ---------------------------------------------------- */}
          <div>
            <p className="block text-xs text-gray-400 mb-1">표시 위치</p>
            <div className="flex items-center gap-2">
              {SUBTITLE_POSITION_OPTIONS.map((o) => {
                const sel = value.position === o.value;
                return (
                  <button
                    key={o.value}
                    type="button"
                    onClick={() => patch("position", o.value)}
                    className={`h-9 px-3.5 rounded-md text-sm border transition-colors ${
                      sel
                        ? "bg-sky-500/15 text-sky-200 border-sky-500/40"
                        : "bg-bg-tertiary text-gray-300 border-border hover:bg-gray-700"
                    }`}
                    aria-pressed={sel}
                  >
                    {o.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* 줄당 글자 수 -------------------------------------------- */}
          <div>
            <NumField
              id={`${idp}-sub-chars`}
              label="줄당 최대 글자 수 (비워두면 자동)"
              value={value.max_chars_per_line}
              onChange={(v) => patch("max_chars_per_line", v)}
              placeholder="예: 20"
              min={5}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 섹션 6 — 레퍼런스

interface ReferencesValue {
  mode: ReferenceMode;
  strength: string;
  image_urls_text: string;
}

function ReferencesSection({
  value,
  onChange,
  idp,
}: {
  value: ReferencesValue;
  onChange: (v: ReferencesValue) => void;
  idp: string;
}) {
  const patch = <K extends keyof ReferencesValue>(k: K, v: ReferencesValue[K]) =>
    onChange({ ...value, [k]: v });
  const off = value.mode === "off";

  const urlLines = value.image_urls_text
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.length > 0);

  return (
    <div className="space-y-5 text-sm">
      {/* 모드 --------------------------------------------------------- */}
      <div>
        <p className="block text-xs text-gray-400 mb-1">참조 모드</p>
        <div className="flex items-center gap-2">
          {REFERENCE_MODE_OPTIONS.map((o) => {
            const sel = value.mode === o.value;
            return (
              <button
                key={o.value}
                type="button"
                onClick={() => patch("mode", o.value)}
                className={`h-9 px-3.5 rounded-md text-sm border transition-colors ${
                  sel
                    ? "bg-sky-500/15 text-sky-200 border-sky-500/40"
                    : "bg-bg-tertiary text-gray-300 border-border hover:bg-gray-700"
                }`}
                aria-pressed={sel}
              >
                {o.label}
              </button>
            );
          })}
        </div>
        <p className="mt-1 text-[11px] text-gray-500">
          &quot;사용 안 함&quot; 이면 이미지 생성 단계는 레퍼런스 없이 실행됩니다.
          &quot;스타일&quot; 은 색감/질감, &quot;구도&quot; 는 레이아웃/시점을 우선 반영.
        </p>
      </div>

      <div className={off ? "opacity-50 pointer-events-none" : ""}>
        <div className="space-y-5">
          {/* 강도 ---------------------------------------------------- */}
          <div>
            <NumField
              id={`${idp}-ref-str`}
              label="강도 (0.0 ~ 1.0)"
              value={value.strength}
              onChange={(v) => patch("strength", v)}
              placeholder="예: 0.6"
              min={0}
              step={0.05}
            />
            <p className="mt-1 text-[11px] text-gray-500">
              값이 높을수록 원본에 더 충실하게 복사됩니다. 0 이면 무효.
            </p>
          </div>

          {/* URL 목록 ------------------------------------------------ */}
          <div>
            <label
              htmlFor={`${idp}-ref-urls`}
              className="block text-xs text-gray-400 mb-1"
            >
              레퍼런스 이미지 URL (한 줄에 하나)
            </label>
            <textarea
              id={`${idp}-ref-urls`}
              value={value.image_urls_text}
              onChange={(e) => patch("image_urls_text", e.target.value)}
              rows={6}
              spellCheck={false}
              className="w-full bg-bg-tertiary border border-border rounded-md px-3 py-2 text-sm text-gray-100 font-mono"
              placeholder={"https://example.com/ref1.jpg\nhttps://example.com/ref2.jpg"}
            />
            <p className="mt-1 text-[11px] text-gray-500">
              현재 파싱되는 URL: <span className="text-gray-300 tabular-nums">{urlLines.length}</span> 개. 빈 줄·공백은 무시합니다.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 섹션 8 — 자동화

interface AutomationValue {
  retry_on_fail: string;
  min_duration_sec: string;
  max_duration_sec: string;
  min_loudness_lufs: string;
  max_loudness_lufs: string;
  min_resolution: Resolution;
}

function AutomationSection({
  value,
  onChange,
  idp,
}: {
  value: AutomationValue;
  onChange: (v: AutomationValue) => void;
  idp: string;
}) {
  const patch = <K extends keyof AutomationValue>(
    k: K,
    v: AutomationValue[K]
  ) => onChange({ ...value, [k]: v });

  return (
    <div className="space-y-5 text-sm">
      <p className="text-xs text-gray-500">
        실패 재시도 · 품질 게이트 설정입니다. 모든 값은 선택 입력이며 비우면
        파이프라인 기본값이 쓰입니다.
      </p>

      {/* 재시도 횟수 ---------------------------------------------------- */}
      <div>
        <p className="block text-xs text-gray-400 mb-1">실패 시 재시도 횟수</p>
        <div className="grid grid-cols-2 gap-3">
          <NumField
            id={`${idp}-retry`}
            label="재시도"
            value={value.retry_on_fail}
            onChange={(v) => patch("retry_on_fail", v)}
            placeholder="예: 1 (기본)"
            min={0}
          />
        </div>
        <p className="mt-1 text-[11px] text-gray-500">
          스텝(대본/이미지/영상/TTS) 단위로 각각 적용됩니다. 0 이면 재시도 없음.
        </p>
      </div>

      {/* 스튜디오 동시 실행 — 강제 true, 읽기만 --------------------- */}
      <div className="rounded-md border border-border bg-bg-tertiary/40 px-3 py-2">
        <p className="text-xs text-gray-300">
          스튜디오(테스트폼) 실행 중 딸깍폼 일시정지 —{" "}
          <span className="text-sky-300">항상 ON</span>
        </p>
        <p className="mt-1 text-[11px] text-gray-500">
          §10.3 규칙에 따라 토글 없이 서버가 강제 적용합니다. 테스트폼이
          돌아가는 동안 해당 채널의 딸깍 큐는 절대 실행되지 않습니다.
        </p>
      </div>

      {/* 품질 게이트 — 길이 -------------------------------------------- */}
      <div>
        <p className="block text-xs text-gray-400 mb-1">품질 게이트 · 영상 길이 (초)</p>
        <div className="grid grid-cols-2 gap-3">
          <NumField
            id={`${idp}-qg-dur-min`}
            label="최소"
            value={value.min_duration_sec}
            onChange={(v) => patch("min_duration_sec", v)}
            placeholder="예: 300"
            min={0}
          />
          <NumField
            id={`${idp}-qg-dur-max`}
            label="최대"
            value={value.max_duration_sec}
            onChange={(v) => patch("max_duration_sec", v)}
            placeholder="예: 1800"
            min={0}
          />
        </div>
        <p className="mt-1 text-[11px] text-gray-500">
          최종 영상이 이 범위를 벗어나면 경고 배지를 띄웁니다(업로드는 막지 않음).
        </p>
      </div>

      {/* 품질 게이트 — 음량 -------------------------------------------- */}
      <div>
        <p className="block text-xs text-gray-400 mb-1">품질 게이트 · 음량 (LUFS)</p>
        <div className="grid grid-cols-2 gap-3">
          <NumField
            id={`${idp}-qg-lufs-min`}
            label="최소 (예: -20)"
            value={value.min_loudness_lufs}
            onChange={(v) => patch("min_loudness_lufs", v)}
            placeholder="예: -20"
            step={0.5}
          />
          <NumField
            id={`${idp}-qg-lufs-max`}
            label="최대 (예: -10)"
            value={value.max_loudness_lufs}
            onChange={(v) => patch("max_loudness_lufs", v)}
            placeholder="예: -10"
            step={0.5}
          />
        </div>
        <p className="mt-1 text-[11px] text-gray-500">
          YouTube 권장 구간은 -14 LUFS 내외입니다. 음수 부호 필수.
        </p>
      </div>

      {/* 품질 게이트 — 해상도 ----------------------------------------- */}
      <div>
        <p className="block text-xs text-gray-400 mb-1">품질 게이트 · 최소 해상도</p>
        <div className="flex gap-2 flex-wrap">
          {RESOLUTION_OPTIONS.map((o) => {
            const selected = value.min_resolution === o.value;
            return (
              <button
                key={o.value}
                type="button"
                onClick={() => patch("min_resolution", o.value)}
                className={
                  "px-3 py-1.5 rounded-md text-xs border transition-colors " +
                  (selected
                    ? "bg-sky-500/20 border-sky-400 text-sky-100"
                    : "bg-bg-tertiary border-border text-gray-300 hover:text-gray-100")
                }
                aria-pressed={selected}
              >
                {o.label}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 섹션 9 — 음향 (BGM)

interface AudioValue {
  bgm_enabled: boolean;
  bgm_style_prompt: string;
  bgm_volume_db: string;
  ducking_strength: DuckingStrength;
  fade_in_sec: string;
  fade_out_sec: string;
}

function AudioSection({
  value,
  onChange,
  idp,
}: {
  value: AudioValue;
  onChange: (v: AudioValue) => void;
  idp: string;
}) {
  const patch = <K extends keyof AudioValue>(k: K, v: AudioValue[K]) =>
    onChange({ ...value, [k]: v });

  const dim = !value.bgm_enabled;

  return (
    <div className="space-y-5 text-sm">
      {/* BGM on/off ---------------------------------------------------- */}
      <div>
        <label className="inline-flex items-center gap-2 text-sm text-gray-200">
          <input
            id={`${idp}-bgm-on`}
            type="checkbox"
            checked={value.bgm_enabled}
            onChange={(e) => patch("bgm_enabled", e.target.checked)}
            className="h-4 w-4"
          />
          BGM 사용
        </label>
        <p className="mt-1 text-[11px] text-gray-500">
          끄면 아래 설정은 저장은 되지만 파이프라인이 무시합니다.
        </p>
      </div>

      {/* BGM 스타일 프롬프트 ------------------------------------------- */}
      <div className={dim ? "opacity-50" : ""}>
        <label
          htmlFor={`${idp}-bgm-style`}
          className="block text-xs text-gray-400 mb-1"
        >
          BGM 스타일 프롬프트 (한 줄)
        </label>
        <input
          id={`${idp}-bgm-style`}
          type="text"
          value={value.bgm_style_prompt}
          onChange={(e) => patch("bgm_style_prompt", e.target.value)}
          placeholder="예: calm historical documentary, orchestral, no vocals"
          className="w-full bg-bg-tertiary border border-border rounded-md px-3 py-2 text-sm text-gray-100"
          disabled={dim}
        />
        <p className="mt-1 text-[11px] text-gray-500">
          ElevenLabs Music 에 전달되는 프롬프트입니다. 한국어/영어 혼용 가능.
        </p>
      </div>

      {/* 볼륨 + 덕킹 ---------------------------------------------------- */}
      <div className={dim ? "opacity-50" : ""}>
        <p className="block text-xs text-gray-400 mb-1">볼륨 · 덕킹</p>
        <div className="grid grid-cols-2 gap-3">
          <NumField
            id={`${idp}-bgm-vol`}
            label="BGM 볼륨 (dB, 예: -18)"
            value={value.bgm_volume_db}
            onChange={(v) => patch("bgm_volume_db", v)}
            placeholder="-30 ~ -6"
            step={1}
          />
          <div>
            <p className="block text-[11px] text-gray-500 mb-1">덕킹 강도</p>
            <div className="flex gap-2 flex-wrap">
              {DUCKING_OPTIONS.map((o) => {
                const selected = value.ducking_strength === o.value;
                return (
                  <button
                    key={o.value}
                    type="button"
                    onClick={() => !dim && patch("ducking_strength", o.value)}
                    disabled={dim}
                    className={
                      "px-3 py-1.5 rounded-md text-xs border transition-colors " +
                      (selected
                        ? "bg-sky-500/20 border-sky-400 text-sky-100"
                        : "bg-bg-tertiary border-border text-gray-300 hover:text-gray-100 disabled:hover:text-gray-300")
                    }
                    aria-pressed={selected}
                  >
                    {o.label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
        <p className="mt-1 text-[11px] text-gray-500">
          덕킹은 내레이션 구간에서 BGM 을 눌러주는 강도입니다. "보통" 기본.
        </p>
      </div>

      {/* 페이드 -------------------------------------------------------- */}
      <div className={dim ? "opacity-50" : ""}>
        <p className="block text-xs text-gray-400 mb-1">페이드 (초)</p>
        <div className="grid grid-cols-2 gap-3">
          <NumField
            id={`${idp}-fade-in`}
            label="페이드 인"
            value={value.fade_in_sec}
            onChange={(v) => patch("fade_in_sec", v)}
            placeholder="예: 2"
            min={0}
            step={0.5}
          />
          <NumField
            id={`${idp}-fade-out`}
            label="페이드 아웃"
            value={value.fade_out_sec}
            onChange={(v) => patch("fade_out_sec", v)}
            placeholder="예: 2"
            min={0}
            step={0.5}
          />
        </div>
      </div>
    </div>
  );
}
