"use client";

import { useEffect, useState, useRef } from "react";
import { Settings, Save, ArrowRight, Upload, Trash2, Image as ImageIcon, User, BadgeCheck, Film, Play, StopCircle, Clock, Headphones } from "lucide-react";
import ModelSelector from "@/components/common/ModelSelector";
import LoadingButton from "@/components/common/LoadingButton";
import YouTubeAuthPanel from "@/components/studio/YouTubeAuthPanel";
import VoiceSelector, { type VoiceChangePatch } from "@/components/studio/VoiceSelector";
import {
  imageApi,
  interludeApi,
  modelsApi,
  projectsApi,
  voiceApi,
  ASSET_BASE,
  type AssetRef,
  type InterludeEntry,
  type InterludeKind,
  type InterludeState,
  type ModelInfo,
  type Project,
  type ProjectAssets,
  type ProjectConfig,
} from "@/lib/api";

interface Props {
  project: Project;
  onUpdate: () => void;
  onNextStep?: () => void;
  /** v1.1.55: 부모에게 dirty 상태를 알려줌 — 스텝 전환 시 미저장 경고용 */
  onDirtyChange?: (dirty: boolean) => void;
}

type AssetKind = "reference" | "character" | "logo";

const INTERLUDE_KINDS: { kind: InterludeKind; label: string; desc: string; icon: React.ReactNode }[] = [
  { kind: "opening",      label: "오프닝",    desc: "본편 맨 앞에 삽입되는 영상", icon: <Play size={14} className="text-accent-secondary" /> },
  { kind: "intermission", label: "인터미션",  desc: "본편 중간에 지정된 간격으로 삽입", icon: <Film size={14} className="text-accent-secondary" /> },
  { kind: "ending",       label: "엔딩",      desc: "본편 맨 끝에 삽입되는 영상", icon: <StopCircle size={14} className="text-accent-secondary" /> },
];

function _fmtBytes(n?: number): string {
  if (!n || n <= 0) return "-";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function _fmtDuration(sec?: number): string {
  if (!sec || sec <= 0) return "-";
  if (sec < 60) return `${sec.toFixed(1)}초`;
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}분 ${s}초`;
}

export default function StepSettings({ project, onUpdate, onNextStep, onDirtyChange }: Props) {
  const [llmModels, setLlmModels] = useState<ModelInfo[]>([]);
  const [imageModels, setImageModels] = useState<ModelInfo[]>([]);
  const [videoModels, setVideoModels] = useState<ModelInfo[]>([]);
  const [ttsModels, setTtsModels] = useState<ModelInfo[]>([]);
  const [config, setConfig] = useState<ProjectConfig>(project.config);
  const [saving, setSaving] = useState(false);
  const [title, setTitle] = useState(project.title);
  const [topic, setTopic] = useState(project.topic || "");
  const [assets, setAssets] = useState<ProjectAssets | null>(null);
  const [uploadingKind, setUploadingKind] = useState<AssetKind | null>(null);
  const refInputRef = useRef<HTMLInputElement>(null);
  const charInputRef = useRef<HTMLInputElement>(null);
  const logoInputRef = useRef<HTMLInputElement>(null);

  // v1.1.47: TTS 미리듣기 상태. local config (아직 저장 안 된) 로 서버에 override 를 보내
  // 즉시 들어볼 수 있도록 한다.
  const [ttsPreviewLoading, setTtsPreviewLoading] = useState(false);
  const [ttsPreviewPlaying, setTtsPreviewPlaying] = useState(false);

  // 간지영상(오프닝/인터미션/엔딩) 상태 — project.config["interlude"] 에 저장됨
  const [interlude, setInterlude] = useState<InterludeState | null>(null);
  const [uploadingInterlude, setUploadingInterlude] = useState<InterludeKind | null>(null);
  const [intermissionEvery, setIntermissionEvery] = useState<number>(180);
  const openingInputRef = useRef<HTMLInputElement>(null);
  const intermissionInputRef = useRef<HTMLInputElement>(null);
  const endingInputRef = useRef<HTMLInputElement>(null);
  const interludeInputRefs: Record<InterludeKind, React.RefObject<HTMLInputElement>> = {
    opening: openingInputRef,
    intermission: intermissionInputRef,
    ending: endingInputRef,
  };

  useEffect(() => {
    Promise.all([
      modelsApi.listLLM(),
      modelsApi.listImage(),
      modelsApi.listVideo(),
      modelsApi.listTTS(),
    ]).then(([llm, img, vid, tts]) => {
      setLlmModels(llm.models || []);
      setImageModels(img.models || []);
      setVideoModels(vid.models || []);
      setTtsModels(tts.models || []);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    setConfig(project.config);
    setTitle(project.title);
    setTopic(project.topic || "");
  }, [project]);

  const loadAssets = async () => {
    try {
      const data = await imageApi.getAssets(project.id);
      setAssets(data);
    } catch {
      // 최초 로드 시 config 에 아무 레퍼런스도 없으면 빈 목록으로 유지
      setAssets({
        project_id: project.id,
        reference_images: [],
        character_images: [],
        logo_images: [],
      });
    }
  };

  useEffect(() => {
    loadAssets();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.id]);

  const loadInterlude = async () => {
    try {
      const data = await interludeApi.get(project.id);
      setInterlude(data);
      setIntermissionEvery(data.intermission_every_sec || 180);
    } catch {
      setInterlude({
        project_id: project.id,
        opening: null,
        intermission: null,
        ending: null,
        intermission_every_sec: 180,
      });
    }
  };

  useEffect(() => {
    loadInterlude();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.id]);

  const handleInterludeUpload = async (kind: InterludeKind, file: File | null) => {
    if (!file) return;
    setUploadingInterlude(kind);
    try {
      await interludeApi.upload(project.id, kind, file);
      await loadInterlude();
      onUpdate();
    } catch (e) {
      console.error("[settings] interlude upload failed", e);
      alert(`업로드 실패: ${(e as Error).message || e}`);
    } finally {
      setUploadingInterlude(null);
    }
  };

  const handleInterludeDelete = async (kind: InterludeKind) => {
    if (!confirm(`${kind} 영상을 삭제할까요?`)) return;
    try {
      await interludeApi.remove(project.id, kind);
      await loadInterlude();
      onUpdate();
    } catch (e) {
      console.error("[settings] interlude delete failed", e);
      alert(`삭제 실패: ${(e as Error).message || e}`);
    }
  };

  // v1.1.55: 변경 추적 — 저장 전 이탈 시 경고 + 필수값 검증
  const [isDirty, setIsDirty] = useState(false);
  const markDirty = () => { if (!isDirty) { setIsDirty(true); onDirtyChange?.(true); } };

  const updateConfig = (key: keyof ProjectConfig, value: any) => {
    setConfig((prev) => ({ ...prev, [key]: value }));
    markDirty();
  };

  // v1.1.46: VoiceSelector 가 돌려주는 patch 를 local config 에 병합.
  // 저장은 기존 "저장" 버튼이 한 번에 처리한다.
  const applyVoicePatch = (patch: VoiceChangePatch) => {
    setConfig((prev) => ({
      ...prev,
      tts_voice_id: patch.tts_voice_id,
      ...(patch.tts_voice_preset !== undefined ? { tts_voice_preset: patch.tts_voice_preset } : {}),
      ...(patch.tts_voice_lang !== undefined ? { tts_voice_lang: patch.tts_voice_lang } : {}),
    }));
  };

  // v1.1.46: TTS 모델을 바꾸면 기존에 선택돼 있던 voice_id / preset 은 무효가 되므로 비운다.
  // VoiceSelector 가 fetch 후 첫 번째 보이스로 자동 채운다(ElevenLabs) 혹은
  // OpenAI TTS 기본 preset 으로 표시만 된다(저장 시 patch 필요).
  const changeTtsModel = (modelId: string) => {
    setConfig((prev) => ({
      ...prev,
      tts_model: modelId,
      tts_voice_id: "",
      tts_voice_preset: "",
    }));
  };

  // v1.1.47: 미리듣기. 저장 없이 local config 값들을 override 로 서버에 넘겨
  // 현재 드롭다운 선택대로 짧은 샘플을 생성·재생한다.
  const previewTts = async () => {
    if (!config.tts_voice_id) {
      alert("목소리를 먼저 선택하세요.");
      return;
    }
    setTtsPreviewLoading(true);
    try {
      const result = await voiceApi.preview(project.id, {
        tts_model: config.tts_model,
        tts_voice_id: config.tts_voice_id,
        tts_voice_preset: config.tts_voice_preset,
        tts_voice_lang: config.tts_voice_lang,
        tts_speed: config.tts_speed,
      });
      if (result?.path) {
        setTtsPreviewPlaying(true);
        const audio = new Audio(
          `${ASSET_BASE}/assets/${project.id}/${result.path}?t=${Date.now()}`,
        );
        audio.onended = () => setTtsPreviewPlaying(false);
        audio.onerror = () => setTtsPreviewPlaying(false);
        audio.play().catch(() => setTtsPreviewPlaying(false));
      }
    } catch (err: any) {
      alert("미리듣기 실패: " + (err?.message || err));
    } finally {
      setTtsPreviewLoading(false);
    }
  };

  // v1.1.55: 필수값 목록. 빨간 * 가 붙은 필드와 동기화.
  const missingFields: string[] = [];
  if (!title.trim()) missingFields.push("프로젝트 제목");
  // 주제는 필수가 아님 — 대본 생성 시 제목에서 유추 가능
  if (!config.target_duration || config.target_duration <= 0) missingFields.push("목표 길이");
  const hasRequiredFields = missingFields.length === 0;

  const save = async () => {
    if (!hasRequiredFields) {
      alert(`필수 항목을 입력해 주세요:\n${missingFields.map(f => `• ${f}`).join("\n")}`);
      return;
    }
    setSaving(true);
    try {
      await projectsApi.update(project.id, { title, topic, config });
      // 인터미션 주기도 같이 저장 (config 와 별도 엔드포인트)
      try {
        await interludeApi.updateConfig(project.id, {
          intermission_every_sec: intermissionEvery,
        });
      } catch (e) {
        console.warn("[settings] intermission_every_sec save failed", e);
      }
      setIsDirty(false);
      onDirtyChange?.(false);
      onUpdate();
    } finally {
      setSaving(false);
    }
  };

  const saveAndNext = async () => {
    await save();
    onNextStep?.();
  };

  // 5초 단위 컷 수 계산 — 설정 저장 시 각 스텝의 총 필요한 칸 수 근거가 됨
  const expectedCuts = Math.max(1, Math.ceil((config.target_duration || 0) / 5));

  const handleAssetUpload = async (kind: AssetKind, file: File | null) => {
    console.log("[settings] handleAssetUpload called", { kind, file });
    if (!file) {
      console.warn("[settings] handleAssetUpload: file is null, aborting");
      return;
    }
    console.log("[settings] uploading", {
      kind,
      name: file.name,
      size: file.size,
      type: file.type,
      projectId: project.id,
    });
    setUploadingKind(kind);
    try {
      let result: any;
      if (kind === "reference") result = await imageApi.uploadReference(project.id, file);
      else if (kind === "character") result = await imageApi.uploadCharacter(project.id, file);
      else result = await imageApi.uploadLogo(project.id, file);
      console.log("[settings] upload success", result);
      await loadAssets();
      onUpdate();
    } catch (e) {
      console.error("[settings] asset upload failed", e);
      alert(`업로드 실패 (${kind}): ${(e as Error).message || e}`);
    } finally {
      setUploadingKind(null);
    }
  };

  const handleAssetDelete = async (kind: AssetKind, filename: string) => {
    console.log("[settings] handleAssetDelete called", { kind, filename });
    try {
      if (kind === "reference") await imageApi.deleteReference(project.id, filename);
      else if (kind === "character") await imageApi.deleteCharacter(project.id, filename);
      else await imageApi.deleteLogo(project.id, filename);
      await loadAssets();
      onUpdate();
    } catch (e) {
      console.error("[settings] asset delete failed", e);
      alert(`삭제 실패 (${kind}): ${(e as Error).message || e}`);
    }
  };

  // Subtitle preview helpers
  const subFont = config.subtitle_style?.font || "Pretendard Bold";
  const subSize = config.subtitle_style?.size || 48;
  const subColor = config.subtitle_style?.color || "#FFFFFF";
  const subOutline = config.subtitle_style?.outline_color || "#000000";
  const subPosition = config.subtitle_style?.position || "bottom";
  const subBgEnabled = Boolean(config.subtitle_style?.bg_enabled);
  const subBgColor = config.subtitle_style?.bg_color || "#000000";
  const subBgOpacity =
    typeof config.subtitle_style?.bg_opacity === "number"
      ? config.subtitle_style!.bg_opacity!
      : 0.6;

  return (<div className="flex flex-col flex-1 min-h-0">
      <div className="flex-shrink-0 flex items-center gap-2 text-accent-secondary pb-4">
        <Settings size={20} />
        <h2 className="text-lg font-semibold">프로젝트 설정</h2>
      </div>
      <div className="flex-1 overflow-y-auto space-y-6">
      {/* 기본 정보 */}
      <div className="bg-bg-secondary border border-border rounded-lg p-5 space-y-4">
        <h3 className="text-sm font-medium text-gray-300">기본 정보</h3>
        <div>
          <label className="block text-xs text-gray-400 mb-1">
            프로젝트 제목 <span className="text-red-500">*</span>
          </label>
          <input
            value={title}
            onChange={(e) => { setTitle(e.target.value); markDirty(); }}
            className={`w-full bg-bg-primary border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-accent-primary ${
              !title.trim() ? "border-red-500/60" : "border-border"
            }`}
          />
          {!title.trim() && <p className="text-[10px] text-red-400 mt-1">제목을 입력해 주세요</p>}
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1">
            주제
          </label>
          <input
            value={topic}
            onChange={(e) => { setTopic(e.target.value); markDirty(); }}
            placeholder="영상 주제를 입력하세요 (예: 호르무즈 해협의 역사)"
            className={`w-full bg-bg-primary border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-accent-primary placeholder:text-gray-600 ${
              "border-border"
            }`}
          />
          {/* 주제는 선택 사항 */}
        </div>
        {/* v1.1.73: 대본 생성 시 LLM 에 "최우선 제약" 으로 주입되는 규칙. 주제 필드에
            뭉쳐 넣으면 모델이 설명으로 해석하고 무시할 위험이 있어 전용 필드로 분리. */}
        <div>
          <label className="block text-xs text-gray-400 mb-1">
            금칙사항 / 필수사항{" "}
            <span className="text-[10px] text-gray-500">(대본 생성 시 최우선 규칙으로 주입)</span>
          </label>
          <textarea
            value={config.content_constraints || ""}
            onChange={(e) => updateConfig("content_constraints", e.target.value)}
            placeholder={"예:\n환단고기 등 위서 인용 금지\n사료 부족 시 '설이 있다' 로 열어둘 것\n청동기 부족국가 연합의 기억이라는 관점 유지"}
            rows={4}
            className="w-full bg-bg-primary border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-accent-primary placeholder:text-gray-600 resize-y"
          />
          <p className="text-[10px] text-gray-500 mt-1">
            한 줄에 하나씩 또는 &quot; / &quot; 로 구분. 비워 두면 기존 동작 그대로입니다.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-gray-400 mb-1">
              목표 길이 (초) <span className="text-red-500">*</span>{" "}
              <span className="text-accent-secondary">· 예상 컷 수: {expectedCuts}개 (5초 단위)</span>
            </label>
            <input
              type="number"
              value={config.target_duration}
              onChange={(e) => updateConfig("target_duration", Number(e.target.value))}
              className={`w-full bg-bg-primary border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-accent-primary ${
                !config.target_duration || config.target_duration <= 0 ? "border-red-500/60" : "border-border"
              }`}
            />
            {(!config.target_duration || config.target_duration <= 0) && (
              <p className="text-[10px] text-red-400 mt-1">목표 길이를 입력해 주세요</p>
            )}
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">화면 비율</label>
            <select
              value={config.aspect_ratio}
              onChange={(e) => updateConfig("aspect_ratio", e.target.value)}
              className="w-full bg-bg-primary border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-accent-primary"
            >
              <option value="16:9">16:9 (가로)</option>
              <option value="9:16">9:16 (세로 · Shorts)</option>
              <option value="1:1">1:1 (정사각형)</option>
            </select>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-gray-400 mb-1">스타일</label>
            <select
              value={config.style}
              onChange={(e) => updateConfig("style", e.target.value)}
              className="w-full bg-bg-primary border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-accent-primary"
            >
              <option value="news_explainer">뉴스 해설</option>
              <option value="documentary">다큐멘터리</option>
              <option value="storytelling">스토리텔링</option>
              <option value="educational">교육</option>
              <option value="entertainment">엔터테인먼트</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">언어</label>
            <select
              value={config.language}
              onChange={(e) => updateConfig("language", e.target.value)}
              className="w-full bg-bg-primary border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-accent-primary"
            >
              <option value="ko">한국어</option>
              <option value="en">English</option>
              <option value="ja">日本語</option>
            </select>
          </div>
        </div>
      </div>

      {/* AI 모델 선택 */}
      <div className="bg-bg-secondary border border-border rounded-lg p-5 space-y-4">
        <h3 className="text-sm font-medium text-gray-300">AI 모델 선택</h3>
        <div className="grid grid-cols-2 gap-4">
          <ModelSelector label="대본 모델 (LLM)" models={llmModels} value={config.script_model} onChange={(v) => updateConfig("script_model", v)} />
          <ModelSelector label="이미지 모델" models={imageModels} value={config.image_model} onChange={(v) => updateConfig("image_model", v)} />
          <ModelSelector label="썸네일 모델" models={imageModels} value={config.thumbnail_model || config.image_model} onChange={(v) => updateConfig("thumbnail_model", v)} />
          <ModelSelector label="영상 모델" models={videoModels} value={config.video_model} onChange={(v) => updateConfig("video_model", v)} />
          <ModelSelector label="TTS 모델" models={ttsModels} value={config.tts_model} onChange={changeTtsModel} />
          {/* v1.1.46: 목소리 선택을 프로젝트 설정으로 이관.
              이전에는 StepVoice 에만 있어서 설정을 다시 거슬러 올라가 바꿔야 했다.
              StepSettings 의 로컬 config 에 직접 반영되고, "저장" 버튼이 한 번에 영속화한다. */}
          <VoiceSelector
            projectId={project.id}
            ttsModel={config.tts_model}
            voiceId={config.tts_voice_id || ""}
            voicePreset={config.tts_voice_preset}
            onChange={applyVoicePatch}
            compact
          />
        </div>

        {/* v1.1.47: TTS 미리듣기 — 저장 없이 local config 로 바로 재생 */}
        <div className="flex items-center justify-end gap-2 pt-1">
          <span className="text-[10px] text-gray-500">
            저장 없이 현재 선택된 모델·목소리·속도로 짧은 샘플을 생성합니다
          </span>
          <button
            type="button"
            onClick={previewTts}
            disabled={ttsPreviewLoading || ttsPreviewPlaying || !config.tts_voice_id}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm border transition-colors ${
              ttsPreviewPlaying
                ? "bg-accent-primary/20 border-accent-primary text-accent-primary"
                : "bg-bg-primary border-border text-gray-300 hover:border-accent-primary/50"
            } disabled:opacity-50`}
          >
            <Headphones size={14} className={ttsPreviewPlaying ? "animate-pulse" : ""} />
            {ttsPreviewLoading ? "생성 중..." : ttsPreviewPlaying ? "재생 중..." : "TTS 미리듣기"}
          </button>
        </div>

        {/* v2.1.1: AI 영상 생성 활성화 토글 */}
        <div className="pt-3 border-t border-border/60">
          <div className="flex items-center justify-between mb-3">
            <label className="text-xs text-gray-400">
              AI 영상 생성
              <span className="text-gray-500 ml-1">(비활성 시 모든 컷 이미지+줌 효과)</span>
            </label>
            <button
              type="button"
              onClick={() => updateConfig("enable_ai_video", !config.enable_ai_video)}
              className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                config.enable_ai_video !== false
                  ? "bg-accent-secondary"
                  : "bg-gray-600"
              }`}
            >
              <span
                className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                  config.enable_ai_video !== false ? "translate-x-4" : "translate-x-0.5"
                }`}
              />
            </button>
          </div>
        </div>

        {/* v1.1.36: 영상 제작 대상 — 선택되지 않은 컷은 비용 0 의 ffmpeg-kenburns
            폴백으로 생성. 영상 단계가 전체 비용의 80~90% 를 차지하는 구간이라
            여기서 필터만 걸어도 1/3~1/5 로 감축이 가능. */}
        {config.enable_ai_video !== false && <div className="pt-3 border-t border-border/60">
          <div className="flex items-center justify-between mb-2">
            <label className="text-xs text-gray-400">
              영상 제작 대상{" "}
              <span className="text-gray-500">(선택되지 않은 컷은 Ken Burns 폴백)</span>
            </label>
            <div className="text-[10px] text-gray-500">
              총 {expectedCuts}컷 중 AI 생성 {(() => {
                const sel = config.video_target_selection || "all";
                if (sel === "all") return expectedCuts;
                let step = 0;
                if (sel === "every_3" || sel === "character_only") step = 3;
                else if (sel === "every_4") step = 4;
                else if (sel === "every_5") step = 5;
                else return expectedCuts;
                let n = 0;
                for (let i = 1; i <= expectedCuts; i++) {
                  // v1.1.55: 앞 5컷은 무조건 AI
                  if (i <= 5 || (i - 1) % step === 0) n++;
                }
                return n;
              })()}컷
            </div>
          </div>
          <div className="grid grid-cols-5 gap-2">
            {[
              { value: "all",            label: "전체",       hint: "모든 컷 AI 생성" },
              { value: "every_3",        label: "3컷당 1장",   hint: "1,4,7... 컷만 AI, 나머지는 Ken Burns" },
              { value: "every_4",        label: "4컷당 1장",   hint: "1,5,9... 컷만 AI" },
              { value: "every_5",        label: "5컷당 1장",   hint: "1,6,11... 컷만 AI" },
              { value: "character_only", label: "캐릭터만",    hint: "캐릭터 등장 컷(3컷당) 만 AI" },
            ].map((opt) => {
              const selected = (config.video_target_selection || "all") === opt.value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => updateConfig("video_target_selection", opt.value)}
                  title={opt.hint}
                  className={`px-2 py-2 rounded-md border text-xs transition-colors ${
                    selected
                      ? "bg-accent-secondary/20 border-accent-secondary text-accent-secondary"
                      : "bg-bg-primary border-border text-gray-400 hover:border-accent-secondary/50"
                  }`}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
        </div>}

        {/* 음성 속도 — OpenAI: 0.25~4.0, ElevenLabs: 0.7~1.2 에서 clamp 됨.
            기본 0.9 로 살짝 느리게. 슬라이더 범위는 공통으로 0.7~1.2. */}
        <div className="pt-2 border-t border-border/60">
          <label className="block text-xs text-gray-400 mb-2">
            음성 속도{" "}
            <span className="text-gray-500">
              ({(config.tts_speed ?? 0.9).toFixed(2)}x
              {(config.tts_speed ?? 0.9) < 1 ? " · 느긋하게" : (config.tts_speed ?? 0.9) > 1 ? " · 빠르게" : " · 기본"})
            </span>
          </label>
          <input
            type="range"
            min={0.7}
            max={1.2}
            step={0.05}
            value={config.tts_speed ?? 0.9}
            onChange={(e) => updateConfig("tts_speed", Number(e.target.value))}
            className="w-full accent-accent-primary"
          />
          <div className="flex justify-between text-[10px] text-gray-500 mt-1">
            <span>느긋 0.70x</span>
            <span>기본 1.00x</span>
            <span>빠름 1.20x</span>
          </div>
        </div>
      </div>

      {/* 자막 스타일 */}
      <div className="bg-bg-secondary border border-border rounded-lg p-5 space-y-4">
        <h3 className="text-sm font-medium text-gray-300">자막 스타일</h3>
        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className="block text-xs text-gray-400 mb-1">폰트</label>
            <input
              value={config.subtitle_style?.font || "Pretendard Bold"}
              onChange={(e) => setConfig((prev) => ({
                ...prev,
                subtitle_style: { ...prev.subtitle_style, font: e.target.value },
              }))}
              className="w-full bg-bg-primary border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-accent-primary"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">크기</label>
            <input
              type="number"
              value={config.subtitle_style?.size || 48}
              onChange={(e) => setConfig((prev) => ({
                ...prev,
                subtitle_style: { ...prev.subtitle_style, size: Number(e.target.value) },
              }))}
              className="w-full bg-bg-primary border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-accent-primary"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">위치</label>
            <select
              value={config.subtitle_style?.position || "bottom"}
              onChange={(e) => setConfig((prev) => ({
                ...prev,
                subtitle_style: { ...prev.subtitle_style, position: e.target.value },
              }))}
              className="w-full bg-bg-primary border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-accent-primary"
            >
              <option value="bottom">하단</option>
              <option value="center">중앙</option>
              <option value="top">상단</option>
            </select>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-gray-400 mb-1">글자 색상</label>
            <div className="flex items-center gap-2">
              <input
                type="color"
                value={subColor}
                onChange={(e) => setConfig((prev) => ({
                  ...prev,
                  subtitle_style: { ...prev.subtitle_style, color: e.target.value },
                }))}
                className="w-8 h-8 rounded border border-border cursor-pointer"
              />
              <span className="text-sm text-gray-400">{subColor}</span>
            </div>
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">외곽선 색상</label>
            <div className="flex items-center gap-2">
              <input
                type="color"
                value={subOutline}
                onChange={(e) => setConfig((prev) => ({
                  ...prev,
                  subtitle_style: { ...prev.subtitle_style, outline_color: e.target.value },
                }))}
                className="w-8 h-8 rounded border border-border cursor-pointer"
              />
              <span className="text-sm text-gray-400">{subOutline}</span>
            </div>
          </div>
        </div>

        {/* 자막 배경 박스 */}
        <div className="pt-2 border-t border-border/60">
          <label className="flex items-center gap-2 text-xs text-gray-300 mb-3 cursor-pointer">
            <input
              type="checkbox"
              checked={subBgEnabled}
              onChange={(e) => setConfig((prev) => ({
                ...prev,
                subtitle_style: { ...prev.subtitle_style, bg_enabled: e.target.checked },
              }))}
              className="w-4 h-4 accent-accent-primary"
            />
            <span>자막 배경 박스 사용</span>
            <span className="text-[10px] text-gray-500">
              (켜면 외곽선 대신 반투명 박스로 렌더됨)
            </span>
          </label>
          <div className={`grid grid-cols-2 gap-4 ${subBgEnabled ? "" : "opacity-40 pointer-events-none"}`}>
            <div>
              <label className="block text-xs text-gray-400 mb-1">배경 색상</label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={subBgColor}
                  onChange={(e) => setConfig((prev) => ({
                    ...prev,
                    subtitle_style: { ...prev.subtitle_style, bg_color: e.target.value },
                  }))}
                  className="w-8 h-8 rounded border border-border cursor-pointer"
                />
                <span className="text-sm text-gray-400">{subBgColor}</span>
              </div>
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">
                불투명 농도 <span className="text-gray-500">({Math.round(subBgOpacity * 100)}%)</span>
              </label>
              <input
                type="range"
                min={0}
                max={100}
                step={1}
                value={Math.round(subBgOpacity * 100)}
                onChange={(e) => setConfig((prev) => ({
                  ...prev,
                  subtitle_style: {
                    ...prev.subtitle_style,
                    bg_opacity: Number(e.target.value) / 100,
                  },
                }))}
                className="w-full accent-accent-primary"
              />
            </div>
          </div>
        </div>

        {/* 자막 미리보기 (축소된 컴팩트 버전) */}
        <div>
          <label className="block text-xs text-gray-400 mb-2">미리보기</label>
          <div className="flex justify-center">
          <div className="relative rounded-lg overflow-hidden border border-border"
               style={{
                 width: config.aspect_ratio === "9:16" ? 80 : config.aspect_ratio === "1:1" ? 140 : 260,
                 height: 140,
               }}>
            {/* Dark background simulating video */}
            <div className="absolute inset-0 bg-gradient-to-b from-gray-800 to-gray-900" />
            {/* Subtitle text */}
            <div className={`absolute left-0 right-0 flex justify-center px-4 ${
              subPosition === "top" ? "top-4" : subPosition === "center" ? "top-1/2 -translate-y-1/2" : "bottom-4"
            }`}>
              <span
                style={{
                  fontFamily: subFont,
                  fontSize: Math.min(subSize * 0.3, 18),
                  color: subColor,
                  padding: subBgEnabled ? "2px 6px" : undefined,
                  backgroundColor: subBgEnabled
                    ? `${subBgColor}${Math.round(subBgOpacity * 255).toString(16).padStart(2, "0")}`
                    : undefined,
                  borderRadius: subBgEnabled ? 2 : undefined,
                  textShadow: subBgEnabled
                    ? undefined
                    : `
                        -2px -2px 0 ${subOutline},
                         2px -2px 0 ${subOutline},
                        -2px  2px 0 ${subOutline},
                         2px  2px 0 ${subOutline},
                         0   -2px 0 ${subOutline},
                         0    2px 0 ${subOutline},
                        -2px  0   0 ${subOutline},
                         2px  0   0 ${subOutline}
                      `,
                  lineHeight: 1.4,
                  textAlign: "center" as const,
                }}
              >
                {topic || project.topic || "자막 미리보기 텍스트입니다"}
              </span>
            </div>
          </div>
          </div>
        </div>
      </div>

      {/* v1.1.60: 프리셋 → YouTube 채널 바인딩
            이 프리셋으로 만든 영상이 어떤 채널 계정에 업로드될지 결정한다.
            딸깍 위젯의 "채널별 YouTube 계정" 에서 각 CH 에 미리 로그인해 두면,
            여기서 고른 채널의 토큰으로 자동 업로드된다. */}
      <div className="bg-bg-secondary border border-border rounded-lg p-5 space-y-3">
        <h3 className="text-sm font-medium text-gray-300">YouTube 채널 바인딩</h3>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
          {([
            { value: 0, label: "자동", color: "text-gray-400" },
            { value: 1, label: "CH1",  color: "text-blue-400" },
            { value: 2, label: "CH2",  color: "text-green-400" },
            { value: 3, label: "CH3",  color: "text-amber-400" },
            { value: 4, label: "CH4",  color: "text-purple-400" },
          ] as const).map((opt) => {
            const current = Number(config.youtube_channel || 0);
            const selected = current === opt.value;
            return (
              <button
                key={opt.value}
                type="button"
                onClick={() =>
                  updateConfig("youtube_channel", opt.value || null)
                }
                className={`px-2 py-2 text-xs font-semibold rounded border transition-colors ${
                  selected
                    ? "border-accent-primary bg-accent-primary/10 text-white"
                    : `border-border ${opt.color} hover:border-gray-500`
                }`}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
        <p className="text-[11px] text-gray-500">
          이 프리셋으로 만든 영상은 선택한 채널의 YouTube 계정으로 업로드됩니다.
          "자동" 이면 큐 항목에서 직접 고른 채널, 또는 전역 토큰을 사용합니다.
          채널별 계정 로그인은 딸깍 위젯의 "채널별 YouTube 계정" 섹션에서 합니다.
        </p>
      </div>

      {/* v1.1.55: YouTube 공개 범위 — 기존 StepYouTube 에서 프리셋 설정으로 이관 */}
      <div className="bg-bg-secondary border border-border rounded-lg p-5 space-y-3">
        <h3 className="text-sm font-medium text-gray-300">YouTube 공개 범위</h3>
        <div className="space-y-2">
          {([
            { value: "private",  label: "비공개 (private)",     desc: "본인만 볼 수 있음. 안전하게 테스트할 때 권장." },
            { value: "unlisted", label: "일부 공개 (unlisted)", desc: "링크가 있는 사람만 볼 수 있음. 검색 노출 안 됨." },
            { value: "public",   label: "전체 공개 (public)",   desc: "모든 사람이 볼 수 있음. 되돌리려면 YouTube Studio 에서 직접 변경해야 함." },
          ] as const).map((opt) => {
            const selected = (config.youtube_privacy || "private") === opt.value;
            return (
              <label
                key={opt.value}
                className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                  selected
                    ? "border-accent-primary bg-accent-primary/10"
                    : "border-border hover:border-gray-600"
                }`}
              >
                <input
                  type="radio"
                  name="youtube_privacy"
                  value={opt.value}
                  checked={selected}
                  onChange={() => updateConfig("youtube_privacy", opt.value)}
                  className="mt-1"
                />
                <div className="flex-1">
                  <div className="text-sm font-medium text-gray-200">{opt.label}</div>
                  <div className="text-[11px] text-gray-500">{opt.desc}</div>
                </div>
              </label>
            );
          })}
        </div>
      </div>

      {/* 레퍼런스 자산 */}
      <div className="bg-bg-secondary border border-border rounded-lg p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium text-gray-300">레퍼런스</h3>
          <p className="text-[11px] text-gray-500">
            이미지 생성 시 스타일/캐릭터/로고를 강제로 반영합니다. 캐릭터는 3컷마다 1장씩 배치됩니다.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* 이미지 생성 레퍼런스 */}
          <AssetSlot
            title="이미지 생성 레퍼런스"
            description="전체 영상의 아트 스타일/톤"
            icon={<ImageIcon size={14} className="text-accent-secondary" />}
            items={assets?.reference_images || []}
            uploading={uploadingKind === "reference"}
            onPick={() => {
              console.log("[settings] reference onPick, ref=", refInputRef.current);
              if (!refInputRef.current) {
                alert("내부 오류: reference file input ref 가 null 입니다.");
                return;
              }
              refInputRef.current.click();
            }}
            onDelete={(f) => handleAssetDelete("reference", f)}
            projectId={project.id}
          />
          <input
            ref={refInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0] || null;
              handleAssetUpload("reference", f);
              e.target.value = "";
            }}
          />

          {/* 캐릭터 */}
          <AssetSlot
            title="캐릭터"
            description="3컷마다 1장씩 자동 배치"
            icon={<User size={14} className="text-accent-secondary" />}
            items={assets?.character_images || []}
            uploading={uploadingKind === "character"}
            onPick={() => {
              console.log("[settings] character onPick, ref=", charInputRef.current);
              if (!charInputRef.current) {
                alert("내부 오류: character file input ref 가 null 입니다.");
                return;
              }
              charInputRef.current.click();
            }}
            onDelete={(f) => handleAssetDelete("character", f)}
            projectId={project.id}
          />
          <input
            ref={charInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0] || null;
              handleAssetUpload("character", f);
              e.target.value = "";
            }}
          />

          {/* 로고 */}
          <AssetSlot
            title="로고"
            description="간지영상/썸네일에 자연스럽게 삽입"
            icon={<BadgeCheck size={14} className="text-accent-secondary" />}
            items={assets?.logo_images || []}
            uploading={uploadingKind === "logo"}
            onPick={() => {
              console.log("[settings] logo onPick, ref=", logoInputRef.current);
              if (!logoInputRef.current) {
                alert("내부 오류: logo file input ref 가 null 입니다.");
                return;
              }
              logoInputRef.current.click();
            }}
            onDelete={(f) => handleAssetDelete("logo", f)}
            projectId={project.id}
          />
          <input
            ref={logoInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0] || null;
              handleAssetUpload("logo", f);
              e.target.value = "";
            }}
          />
        </div>

        <div>
          <label className="block text-xs text-gray-400 mb-1">이미지 전체 분위기 프롬프트</label>
          <textarea
            value={config.image_global_prompt || ""}
            onChange={(e) => updateConfig("image_global_prompt", e.target.value)}
            placeholder="예: cinematic, moody lighting, warm color grading, film grain"
            rows={2}
            className="w-full bg-bg-primary border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-accent-primary placeholder:text-gray-600 resize-none"
          />
        </div>

        <div>
          <label className="block text-xs text-gray-400 mb-1">
            이미지 네거티브 프롬프트{" "}
            <span className="text-[10px] text-gray-500">(ComfyUI 로컬 모델만 적용)</span>
          </label>
          <textarea
            value={config.image_negative_prompt || ""}
            onChange={(e) => updateConfig("image_negative_prompt", e.target.value)}
            placeholder="예: monochrome, black and white, grayscale, sketch, line art, blurry, low quality, watermark, text, deformed"
            rows={2}
            className="w-full bg-bg-primary border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-accent-primary placeholder:text-gray-600 resize-none"
          />
          <p className="text-[10px] text-gray-500 mt-1">
            비워두면 기본값(blurry, low quality 등) 사용. 흑백 스케치로 나올 때는{" "}
            <code className="text-accent-secondary">monochrome, black and white, grayscale, sketch, line art</code>{" "}
            를 넣으세요.
          </p>
        </div>

        <div>
          <label className="block text-xs text-gray-400 mb-1">캐릭터 설명</label>
          <textarea
            value={config.character_description || ""}
            onChange={(e) => updateConfig("character_description", e.target.value)}
            placeholder="예: 20대 한국 여성, 긴 검은 머리, 회색 니트, 온화한 표정"
            rows={2}
            className="w-full bg-bg-primary border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-accent-primary placeholder:text-gray-600 resize-none"
          />
        </div>
      </div>

      {/* 오프닝 / 인터미션 / 엔딩 영상 업로드 */}
      <div className="bg-bg-secondary border border-border rounded-lg p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Film size={16} className="text-accent-secondary" />
            <h3 className="text-sm font-medium text-gray-300">오프닝 · 인터미션 · 엔딩 영상</h3>
          </div>
          <p className="text-[11px] text-gray-500">
            업로드해 두면 최종 병합 시 자동으로 끼워 넣습니다.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {INTERLUDE_KINDS.map(({ kind, label, desc, icon }) => {
            const entry: InterludeEntry | null = interlude ? interlude[kind] : null;
            const uploading = uploadingInterlude === kind;
            const hasVideo = !!entry && !!entry.video_path;
            return (
              <div key={kind} className="bg-bg-primary border border-border rounded-lg p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    {icon}
                    <span className="text-xs font-medium text-gray-200">{label}</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => interludeInputRefs[kind].current?.click()}
                    disabled={uploading}
                    className="text-[11px] bg-accent-primary hover:bg-purple-600 disabled:opacity-50 text-white px-2 py-1 rounded flex items-center gap-1"
                  >
                    <Upload size={11} />
                    {uploading ? "업로드중…" : hasVideo ? "교체" : "업로드"}
                  </button>
                </div>
                <p className="text-[10px] text-gray-500 leading-tight">{desc}</p>

                <input
                  ref={interludeInputRefs[kind]}
                  type="file"
                  accept="video/mp4,video/quicktime,video/x-matroska,video/webm,video/x-msvideo,.mp4,.mov,.mkv,.webm,.m4v,.avi"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0] || null;
                    handleInterludeUpload(kind, f);
                    e.target.value = "";
                  }}
                />

                {hasVideo ? (
                  <div className="rounded border border-border bg-bg-secondary/40 p-2 space-y-1.5">
                    <div className="text-[11px] text-gray-200 truncate" title={entry?.filename}>
                      {entry?.filename || "(파일명 없음)"}
                    </div>
                    <div className="flex items-center gap-2 text-[10px] text-gray-500">
                      <span>{_fmtDuration(entry?.duration)}</span>
                      <span>·</span>
                      <span>{_fmtBytes(entry?.size_bytes)}</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleInterludeDelete(kind)}
                      className="w-full text-[11px] text-gray-400 hover:text-accent-danger hover:bg-accent-danger/10 rounded px-2 py-1 flex items-center justify-center gap-1 transition-colors"
                    >
                      <Trash2 size={11} /> 삭제
                    </button>
                  </div>
                ) : (
                  <div className="text-[11px] text-gray-600 italic border border-dashed border-border rounded p-2 text-center">
                    업로드된 영상 없음
                  </div>
                )}
              </div>
            );
          })}
        </div>

        <div>
          <label className="block text-xs text-gray-400 mb-1 flex items-center gap-1.5">
            <Clock size={12} />
            인터미션 간격 (초)
            <span className="text-gray-600">· 본편 길이가 이 값보다 길어지면 한 번씩 인터미션 영상을 끼워넣습니다.</span>
          </label>
          <input
            type="number"
            min={30}
            max={1800}
            value={intermissionEvery}
            onChange={(e) => setIntermissionEvery(Math.max(30, Math.min(1800, Number(e.target.value) || 180)))}
            className="w-full bg-bg-primary border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-accent-primary"
          />
        </div>
      </div>

      {/* YouTube 계정 인증 */}
      <YouTubeAuthPanel projectId={project.id} />

      {/* 파이프라인 옵션 */}
      <div className="bg-bg-secondary border border-border rounded-lg p-5 space-y-4">
        <h3 className="text-sm font-medium text-gray-300">파이프라인 옵션</h3>
        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={config.auto_pause_after_step}
            onChange={(e) => updateConfig("auto_pause_after_step", e.target.checked)}
            className="w-4 h-4 rounded border-border accent-accent-primary"
          />
          <span className="text-sm">각 단계 완료 후 자동 일시중지</span>
        </label>
        <div>
          <label className="block text-xs text-gray-400 mb-1">컷 전환 효과</label>
          <select
            value={config.cut_transition}
            onChange={(e) => updateConfig("cut_transition", e.target.value)}
            className="w-full bg-bg-primary border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-accent-primary"
          >
            <option value="slow">느린 전환</option>
            <option value="fast">빠른 전환</option>
            <option value="cut">직접 컷</option>
            <option value="crossfade">크로스페이드</option>
          </select>
        </div>
      </div>

      {/* v1.1.55: 미저장 경고 + 필수값 안내 + 저장 버튼 */}
      <div className="space-y-2">
        {isDirty && (
          <div className="flex items-center gap-2 text-xs text-amber-400 bg-amber-400/10 border border-amber-400/30 rounded-lg px-3 py-2">
            <span>변경사항이 저장되지 않았습니다.</span>
          </div>
        )}
        {!hasRequiredFields && (
          <div className="flex items-center gap-2 text-xs text-red-400 bg-red-400/10 border border-red-400/30 rounded-lg px-3 py-2">
            <span>필수 항목을 입력해 주세요: {missingFields.join(", ")}</span>
          </div>
        )}
        <div className="flex justify-end gap-3">
          <LoadingButton onClick={save} loading={saving} icon={<Save size={14} />} variant="secondary">
            설정 저장{isDirty ? " *" : ""}
          </LoadingButton>
          <button
            onClick={saveAndNext}
            disabled={!hasRequiredFields}
            className="bg-accent-primary hover:bg-purple-600 text-white font-semibold px-5 py-2 rounded-lg flex items-center gap-2 text-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            저장 후 다음 단계 <ArrowRight size={14} />
          </button>
        </div>
      </div>
      </div>{/* 스크롤 영역 끝 */}
    </div>
  );
}


// ─── AssetSlot: 레퍼런스/캐릭터/로고 공용 업로드 위젯 ───
interface AssetSlotProps {
  title: string;
  description: string;
  icon: React.ReactNode;
  items: AssetRef[];
  uploading: boolean;
  onPick: () => void;
  onDelete: (filename: string) => void;
  projectId: string;
}

function AssetSlot({
  title,
  description,
  icon,
  items,
  uploading,
  onPick,
  onDelete,
  projectId,
}: AssetSlotProps) {
  return (
    <div className="bg-bg-primary border border-border rounded-lg p-3 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {icon}
          <span className="text-xs font-medium text-gray-200">{title}</span>
        </div>
        <button
          type="button"
          onClick={onPick}
          disabled={uploading}
          className="text-[11px] bg-accent-primary hover:bg-purple-600 disabled:opacity-50 text-white px-2 py-1 rounded flex items-center gap-1"
        >
          <Upload size={11} />
          {uploading ? "업로드중…" : "추가"}
        </button>
      </div>
      <p className="text-[10px] text-gray-500 leading-tight">{description}</p>

      {items.length === 0 ? (
        <div className="text-[11px] text-gray-600 italic border border-dashed border-border rounded p-2 text-center">
          등록된 이미지 없음
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-2">
          {items.map((it) => (
            <div
              key={it.path}
              className="relative group rounded overflow-hidden border border-border"
              title={it.filename}
            >
              {it.exists ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={`${ASSET_BASE}/assets/${projectId}/${it.path}`}
                  alt={it.filename}
                  className="w-full h-14 object-cover"
                />
              ) : (
                <div className="w-full h-14 bg-bg-secondary flex items-center justify-center text-[10px] text-gray-500">
                  missing
                </div>
              )}
              <button
                type="button"
                onClick={() => onDelete(it.filename)}
                className="absolute top-0 right-0 bg-black/70 hover:bg-red-600 p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
                title="삭제"
              >
                <Trash2 size={10} className="text-white" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
