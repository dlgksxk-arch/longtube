"use client";

/**
 * VoiceSelector — TTS 목소리 선택 드롭다운.
 *
 * v1.1.46: 기존에는 StepVoice 안에만 있던 목소리 선택 UI 를 추출해
 * StepSettings 에서도 재사용할 수 있도록 분리했다.
 *
 * 모드:
 * - ElevenLabs: 백엔드 /voice/{id}/voices 에서 whitelist 된 실제 보이스를
 *   그대로 그룹핑(ko/en/ja/other) 해 드롭다운으로 보여준다. 선택하면
 *   tts_voice_id 만 저장.
 * - OpenAI TTS: ElevenLabs 와 달리 언어별로 고정된 프리셋(ko-child-boy 등)을
 *   내부 VOICE_PRESETS 목록으로 보여주고 OPENAI_VOICE_MAP 으로 실제
 *   voice_id(alloy / nova / ...) 로 변환해 저장한다.
 *
 * 이 컴포넌트는 저장을 직접 수행하지 않는다. 선택 결과는 `onChange(patch)` 로
 * 부모에게 전달되고, 부모가 local config state 를 업데이트 하거나
 * projectsApi.update 를 즉시 호출하거나 결정한다. (StepSettings 는 전자,
 * StepVoice 는 후자였다. v1.1.46 이후로는 StepSettings 만 사용.)
 */

import { useState, useEffect, useRef } from "react";
import { ChevronDown, Loader2 } from "lucide-react";
import { voiceApi } from "@/lib/api";

interface ApiVoice {
  id: string;
  name: string;
  description?: string | null;
  preview_url?: string | null;
  category?: string | null;
  gender?: string | null;
  accent?: string | null;
  age?: string | null;
  use_case?: string | null;
  language?: string | null;
}

interface VoicePreset {
  id: string;
  name: string;
  description: string;
  icon: string;
  lang: "ko" | "en" | "ja";
  isChild?: boolean;
}

const VOICE_PRESETS: VoicePreset[] = [
  // 한국어
  { id: "ko-child-boy",     name: "4세 남자아이",  description: "밝고 귀여운 어린 남자아이 (ElevenLabs 권장)",  icon: "👦", lang: "ko", isChild: true },
  { id: "ko-child-girl",    name: "4세 여자아이",  description: "발랄한 어린 여자아이 (ElevenLabs 권장)",       icon: "👧", lang: "ko", isChild: true },
  { id: "ko-male-young",    name: "청년 남성",     description: "활기찬 20대 남성",             icon: "🧑", lang: "ko" },
  { id: "ko-female-young",  name: "청년 여성",     description: "밝은 20대 여성",               icon: "👩", lang: "ko" },
  { id: "ko-male-mature",   name: "성인 남성",     description: "차분한 성인 남성",             icon: "👨", lang: "ko" },
  { id: "ko-female-mature", name: "성인 여성",     description: "안정감 있는 성인 여성",         icon: "👩‍💼", lang: "ko" },
  { id: "ko-narrator",      name: "내레이터",      description: "전문 나레이션 목소리",          icon: "🎙️", lang: "ko" },
  // English
  { id: "en-child-boy",     name: "Boy (4yr)",     description: "Young boy voice (ElevenLabs recommended)", icon: "👦", lang: "en", isChild: true },
  { id: "en-child-girl",    name: "Girl (4yr)",    description: "Young girl voice (ElevenLabs recommended)", icon: "👧", lang: "en", isChild: true },
  { id: "en-male-young",    name: "Young Male",    description: "Energetic young adult male",     icon: "🧑", lang: "en" },
  { id: "en-female-young",  name: "Young Female",  description: "Bright young adult female",      icon: "👩", lang: "en" },
  { id: "en-male-mature",   name: "Mature Male",   description: "Calm, authoritative male",       icon: "👨", lang: "en" },
  { id: "en-female-mature", name: "Mature Female",  description: "Warm, professional female",     icon: "👩‍💼", lang: "en" },
  { id: "en-narrator",      name: "Narrator",      description: "Professional narration voice",   icon: "🎙️", lang: "en" },
  // 日本語
  { id: "ja-child-boy",     name: "4歳 男の子",    description: "明るくかわいい男の子 (ElevenLabs推奨)",  icon: "👦", lang: "ja", isChild: true },
  { id: "ja-child-girl",    name: "4歳 女の子",    description: "元気な女の子 (ElevenLabs推奨)",          icon: "👧", lang: "ja", isChild: true },
  { id: "ja-male-young",    name: "青年 男性",     description: "活発な20代男性",                icon: "🧑", lang: "ja" },
  { id: "ja-female-young",  name: "青年 女性",     description: "明るい20代女性",                icon: "👩", lang: "ja" },
  { id: "ja-male-mature",   name: "成人 男性",     description: "落ち着いた男性",                icon: "👨", lang: "ja" },
  { id: "ja-female-mature", name: "成人 女性",     description: "安定感のある女性",              icon: "👩‍💼", lang: "ja" },
  { id: "ja-narrator",      name: "ナレーター",    description: "プロのナレーション",             icon: "🎙️", lang: "ja" },
];

const LANG_LABELS: Record<string, string> = { ko: "🇰🇷 한국어", en: "🇺🇸 English", ja: "🇯🇵 日本語", other: "🌐 기타" };

// OpenAI TTS 용 preset → voice_id 맵
const OPENAI_VOICE_MAP: Record<string, string> = {
  "ko-child-boy":     "echo",
  "ko-child-girl":    "shimmer",
  "ko-male-young":    "alloy",
  "ko-female-young":  "nova",
  "ko-male-mature":   "onyx",
  "ko-female-mature": "shimmer",
  "ko-narrator":      "fable",
  "en-child-boy":     "echo",
  "en-child-girl":    "shimmer",
  "en-male-young":    "alloy",
  "en-female-young":  "nova",
  "en-male-mature":   "onyx",
  "en-female-mature": "shimmer",
  "en-narrator":      "fable",
  "ja-child-boy":     "echo",
  "ja-child-girl":    "shimmer",
  "ja-male-young":    "alloy",
  "ja-female-young":  "nova",
  "ja-male-mature":   "onyx",
  "ja-female-mature": "shimmer",
  "ja-narrator":      "fable",
};

function inferVoiceLangCode(v: { language?: string | null; accent?: string | null; name?: string | null }): "ko" | "en" | "ja" | "other" {
  const hay = `${v.language || ""} ${v.accent || ""} ${v.name || ""}`.toLowerCase();
  if (!hay.trim()) return "other";
  if (/\b(ko|kor|korean|한국)\b|korea/.test(hay)) return "ko";
  if (/\b(ja|jp|jpn|japanese|日本)\b|japan/.test(hay)) return "ja";
  if (/\b(en|eng|english|american|british|australian)\b/.test(hay)) return "en";
  return "other";
}

/**
 * VoiceChangePatch — onChange 로 부모에게 내려보내는 변경 결과.
 * tts_voice_preset 는 OpenAI TTS 에서만 값이 차고, ElevenLabs 직접 선택 시
 * 빈 문자열로 리셋된다.
 */
export interface VoiceChangePatch {
  tts_voice_id: string;
  tts_voice_preset?: string;
  tts_voice_lang?: string;
}

interface Props {
  projectId: string;
  /** 현재 편집 중인 TTS 모델. fetch 대상을 결정한다. */
  ttsModel: string;
  voiceId: string;
  voicePreset?: string;
  onChange: (patch: VoiceChangePatch) => void;
  /** true 면 select 박스 높이를 ModelSelector 와 동일하게 맞춘다. (StepSettings 용) */
  compact?: boolean;
}

export default function VoiceSelector({
  projectId,
  ttsModel,
  voiceId,
  voicePreset,
  onChange,
  compact = false,
}: Props) {
  const [open, setOpen] = useState(false);
  const [apiVoices, setApiVoices] = useState<ApiVoice[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  const isElevenLabs = (ttsModel || "elevenlabs") === "elevenlabs";

  // ElevenLabs 모드에서만 API 호출. OpenAI TTS 는 고정 프리셋 사용.
  const fetchVoices = async () => {
    if (!isElevenLabs) {
      setApiVoices([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await voiceApi.listVoices(projectId, ttsModel);
      const voices: ApiVoice[] = Array.isArray(data?.voices) ? data.voices : [];
      setApiVoices(voices);
      // 저장된 voice_id 가 없고 목록이 있으면 첫 번째를 자동 선택.
      if (!voiceId && voices.length > 0) {
        onChange({ tts_voice_id: voices[0].id, tts_voice_preset: "" });
      }
    } catch (e: any) {
      setError(e?.message || "voice list 로드 실패");
      setApiVoices([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchVoices();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, ttsModel]);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const changeOpenAiPreset = (presetId: string) => {
    setOpen(false);
    const vId = OPENAI_VOICE_MAP[presetId] || Object.values(OPENAI_VOICE_MAP)[0];
    const lang = VOICE_PRESETS.find((v) => v.id === presetId)?.lang || "ko";
    onChange({ tts_voice_id: vId, tts_voice_preset: presetId, tts_voice_lang: lang });
  };

  const changeElevenDirect = (vId: string) => {
    setOpen(false);
    onChange({ tts_voice_id: vId, tts_voice_preset: "" });
  };

  const previewApiVoice = (v: ApiVoice, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!v.preview_url) return;
    try {
      const audio = new Audio(v.preview_url);
      audio.play().catch(() => {});
    } catch {}
  };

  // 표시 상태 계산
  // OpenAI TTS 의 경우, 저장된 preset 값이 없으면 voice_id 를 역조회해서 가장 가까운 preset 추정.
  let currentPreset: VoicePreset | undefined;
  if (!isElevenLabs) {
    if (voicePreset) {
      currentPreset = VOICE_PRESETS.find((v) => v.id === voicePreset);
    }
    if (!currentPreset && voiceId) {
      const guessedId = Object.entries(OPENAI_VOICE_MAP).find(
        ([, vid]) => vid === voiceId,
      )?.[0];
      if (guessedId) currentPreset = VOICE_PRESETS.find((v) => v.id === guessedId);
    }
    if (!currentPreset) currentPreset = VOICE_PRESETS[0];
  }
  const currentApiVoice = apiVoices.find((v) => v.id === voiceId);

  const btnClass = compact
    ? "w-full bg-bg-primary border border-border rounded-lg px-3 py-2 text-sm text-left flex items-center justify-between hover:border-accent-primary/50 transition-colors"
    : "w-full bg-bg-primary border border-border rounded-lg px-3 py-2 text-sm text-left flex items-center justify-between hover:border-accent-primary/50 transition-colors";

  return (
    <div ref={ref} className="relative">
      <label className="block text-xs text-gray-400 mb-1">
        목소리 선택
        {isElevenLabs && apiVoices.length > 0 && (
          <span className="ml-2 text-[10px] text-gray-600">
            ({apiVoices.length}개 사용 가능)
          </span>
        )}
      </label>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={btnClass}
      >
        <div className="flex items-center gap-2 min-w-0">
          {isElevenLabs ? (
            loading ? (
              <span className="text-gray-500 flex items-center gap-1">
                <Loader2 size={12} className="animate-spin" /> 불러오는 중…
              </span>
            ) : currentApiVoice ? (
              <>
                <span>🎙️</span>
                <span className="truncate">{currentApiVoice.name}</span>
                {currentApiVoice.gender && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-bg-tertiary text-gray-500">
                    {currentApiVoice.gender}
                  </span>
                )}
              </>
            ) : (
              <span className="text-gray-500">보이스를 선택하세요</span>
            )
          ) : currentPreset ? (
            <>
              <span>{currentPreset.icon}</span>
              <span>{currentPreset.name}</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-bg-tertiary text-gray-500">
                {currentPreset.lang === "ko" ? "한국어" : currentPreset.lang === "ja" ? "日本語" : "English"}
              </span>
            </>
          ) : null}
        </div>
        <ChevronDown size={14} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="absolute z-50 mt-1 w-full bg-bg-secondary border border-border rounded-lg shadow-xl max-h-80 overflow-y-auto">
          {isElevenLabs ? (
            loading ? (
              <div className="px-3 py-4 text-center text-gray-500 text-xs flex items-center justify-center gap-2">
                <Loader2 size={12} className="animate-spin" /> ElevenLabs 에서 목록 가져오는 중…
              </div>
            ) : error ? (
              <div className="px-3 py-4 text-center text-accent-danger text-xs">
                {error}
                <button
                  onClick={fetchVoices}
                  className="ml-2 underline hover:text-accent-primary"
                >
                  재시도
                </button>
              </div>
            ) : apiVoices.length === 0 ? (
              <div className="px-3 py-4 text-center text-gray-500 text-xs">
                사용 가능한 보이스가 없습니다. ElevenLabs 계정에 Blondie /
                Larry Flicker / Emmaline / Northern Terry 가 추가되어 있는지
                확인하세요.
              </div>
            ) : (
              (["ko", "en", "ja", "other"] as const).map((lang) => {
                const group = apiVoices.filter((v) => inferVoiceLangCode(v) === lang);
                if (group.length === 0) return null;
                return (
                  <div key={lang}>
                    <div className="sticky top-0 px-3 py-1.5 text-[10px] font-bold text-gray-500 bg-bg-tertiary border-b border-border uppercase tracking-wider">
                      {LANG_LABELS[lang]}
                    </div>
                    {group.map((v) => (
                      <button
                        key={v.id}
                        onClick={() => changeElevenDirect(v.id)}
                        className={`w-full text-left px-3 py-2 text-sm hover:bg-accent-primary/10 transition-colors ${
                          v.id === voiceId
                            ? "bg-accent-primary/20 text-accent-primary"
                            : "text-gray-300"
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <span>🎙️</span>
                          <span className="font-medium flex-1 truncate">{v.name}</span>
                          {v.preview_url && (
                            <span
                              onClick={(e) => previewApiVoice(v, e)}
                              className="text-[10px] text-gray-500 hover:text-accent-primary px-1 cursor-pointer"
                              title="미리듣기"
                            >
                              ▶
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-1.5 ml-6 mt-0.5 text-[10px] text-gray-500">
                          {v.gender && <span>{v.gender}</span>}
                          {v.accent && <span>· {v.accent}</span>}
                          {v.age && <span>· {v.age}</span>}
                          {v.use_case && <span>· {v.use_case}</span>}
                        </div>
                        {v.description && (
                          <p className="text-[10px] text-gray-600 mt-0.5 ml-6 truncate">
                            {v.description}
                          </p>
                        )}
                      </button>
                    ))}
                  </div>
                );
              })
            )
          ) : (
            (["ko", "en", "ja"] as const).map((lang) => (
              <div key={lang}>
                <div className="sticky top-0 px-3 py-1.5 text-[10px] font-bold text-gray-500 bg-bg-tertiary border-b border-border uppercase tracking-wider">
                  {LANG_LABELS[lang]}
                </div>
                {VOICE_PRESETS.filter((v) => v.lang === lang).map((v) => (
                  <button
                    key={v.id}
                    onClick={() => changeOpenAiPreset(v.id)}
                    className={`w-full text-left px-3 py-2 text-sm hover:bg-accent-primary/10 transition-colors ${
                      currentPreset && v.id === currentPreset.id
                        ? "bg-accent-primary/20 text-accent-primary"
                        : "text-gray-300"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span>{v.icon}</span>
                      <span className="font-medium">{v.name}</span>
                      {v.isChild && (
                        <span className="text-[9px] px-1 py-0.5 rounded bg-amber-400/20 text-amber-400">유사음</span>
                      )}
                    </div>
                    <p className="text-xs text-gray-500 mt-0.5 ml-6">{v.description}</p>
                  </button>
                ))}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
