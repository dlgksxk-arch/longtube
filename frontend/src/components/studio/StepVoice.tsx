"use client";

/**
 * StepVoice — 음성(TTS) 생성 단계.
 *
 * v1.1.46 이후: TTS 모델 선택 / 목소리 선택 UI 는 프로젝트 설정(StepSettings)
 * 으로 이관되었다. 이 화면은 이제 **생성/재생성/미리듣기/진행률** 에만
 * 집중한다. 모델·보이스를 바꾸고 싶으면 설정 화면으로 돌아가서 바꾸고 저장한다.
 */

import { useState, useEffect, useRef } from "react";
import { Mic, Volume2, RefreshCw, Wand2, Headphones, Trash2, StopCircle, PlayCircle, Loader2 } from "lucide-react";
import LoadingButton from "@/components/common/LoadingButton";
import CostEstimate from "@/components/common/CostEstimate";
import { voiceApi, modelsApi, scriptApi, taskApi, type Project, type Cut, type ModelInfo } from "@/lib/api";
import GenerationTimer from "@/components/common/GenerationTimer";

interface Props {
  project: Project;
  cuts: Cut[];
  onUpdate: () => void;
}

export default function StepVoice({ project, cuts, onUpdate }: Props) {
  const [generating, setGenerating] = useState(false);
  const [regeneratingCut, setRegeneratingCut] = useState<number | null>(null);
  // ttsModels 는 비용 표시에만 필요. 모델 선택 UI 자체는 StepSettings 로 이관됨.
  const [ttsModels, setTtsModels] = useState<ModelInfo[]>([]);
  const [playingCut, setPlayingCut] = useState<number | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewPlaying, setPreviewPlaying] = useState(false);
  const [generatingIndex, setGeneratingIndex] = useState(-1);
  const lastCompletedRef = useRef(0);

  // Poll task status during generation → refresh cuts when a new voice completes
  useEffect(() => {
    if (!generating) {
      lastCompletedRef.current = 0;
      setGeneratingIndex(-1);
      return;
    }
    const poll = setInterval(async () => {
      try {
        const status = await taskApi.status(project.id, "voice");
        if (status.completed > lastCompletedRef.current) {
          lastCompletedRef.current = status.completed;
          onUpdate();
        }
        setGeneratingIndex(status.completed);
        if (status.status !== "running") {
          setGenerating(false);
          setGeneratingIndex(-1);
          onUpdate();
        }
      } catch {}
    }, 2000);
    return () => clearInterval(poll);
  }, [generating, project.id]);

  useEffect(() => {
    modelsApi.listTTS().then((d) => setTtsModels(d.models)).catch(() => {});
  }, [project.id]);

  // On mount — restore generating state if backend task is still running.
  // Allows user to switch tabs mid-generation and return without losing UI state.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const status = await taskApi.status(project.id, "voice");
        if (!cancelled && status.status === "running") {
          setGenerating(true);
          lastCompletedRef.current = status.completed;
          setGeneratingIndex(status.completed);
        }
      } catch {}
    })();
    return () => { cancelled = true; };
  }, [project.id]);

  const previewVoice = async () => {
    setPreviewLoading(true);
    try {
      const result = await voiceApi.preview(project.id);
      if (result.path) {
        setPreviewPlaying(true);
        const audio = new Audio(`http://localhost:8000/assets/${project.id}/${result.path}?t=${Date.now()}`);
        audio.onended = () => setPreviewPlaying(false);
        audio.onerror = () => setPreviewPlaying(false);
        audio.play().catch(() => setPreviewPlaying(false));
      }
    } catch (err: any) {
      alert("미리듣기 실패: " + err.message);
    } finally {
      setPreviewLoading(false);
    }
  };

  const generateAll = async () => {
    setGenerating(true);
    try {
      await voiceApi.generateAsync(project.id);
    } catch (err: any) {
      alert("음성 생성 실패: " + err.message);
      setGenerating(false);
    }
  };

  const stopGeneration = async () => {
    if (!confirm("음성 생성을 중지하시겠습니까?\n이미 완료된 컷은 유지됩니다.")) return;
    try {
      await taskApi.cancel(project.id, "voice");
      setGenerating(false);
      onUpdate();
    } catch {}
  };

  const resumeGeneration = async () => {
    setGenerating(true);
    try {
      const res = await voiceApi.resumeAsync(project.id);
      if (res.status === "nothing_to_resume") {
        alert("이어서 생성할 컷이 없습니다. 모든 컷이 완료되었습니다.");
        setGenerating(false);
      }
    } catch (err: any) {
      alert("이어서 생성 실패: " + err.message);
      setGenerating(false);
    }
  };

  const hasPendingCuts = cuts.some((c) => !c.audio_path && c.narration);

  const regenerate = async (cutNumber: number) => {
    setRegeneratingCut(cutNumber);
    try {
      await voiceApi.regenerate(project.id, cutNumber);
      onUpdate();
    } catch (err: any) {
      alert("재생성 실패: " + err.message);
    } finally {
      setRegeneratingCut(null);
    }
  };

  const playAudio = (cut: Cut) => {
    if (!cut.audio_path) return;
    if (playingCut === cut.cut_number) {
      setPlayingCut(null);
      return;
    }
    setPlayingCut(cut.cut_number);
    const audio = new Audio(`http://localhost:8000/assets/${project.id}/${cut.audio_path}`);
    audio.onended = () => setPlayingCut(null);
    audio.play().catch(() => setPlayingCut(null));
  };

  const cutsWithAudio = cuts.filter((c) => c.audio_path);

  // Cost estimate: avg ~70 chars per cut narration (5sec Korean)
  const selectedTts = ttsModels.find((m) => m.id === project.config.tts_model);
  const costPerKChars = selectedTts?.cost_value ?? 0.30;
  const avgCharsPerCut = 70;
  const totalChars = cuts.length > 0 ? cuts.reduce((sum, c) => sum + c.narration.length, 0) : (Math.floor(project.config.target_duration / 5) * avgCharsPerCut);
  const estimatedVoiceCost = (totalChars / 1000) * costPerKChars;
  const currentModelLabel = selectedTts?.name || project.config.tts_model || "-";

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {/* ── 상단 컨트롤 (틀고정) ── */}
      <div className="flex-shrink-0 space-y-4 pb-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-accent-secondary">
          <Mic size={20} />
          <h2 className="text-lg font-semibold">음성 생성 (TTS)</h2>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-400">
            {cutsWithAudio.length}/{cuts.length}컷 완료
          </span>
          {generating ? (
            <button
              onClick={stopGeneration}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm bg-accent-danger/20 border border-accent-danger/50 text-accent-danger hover:bg-accent-danger/30 transition-colors"
            >
              <StopCircle size={14} />
              중지
            </button>
          ) : (
            <>
              {hasPendingCuts && cutsWithAudio.length > 0 ? (
                <LoadingButton onClick={resumeGeneration} loading={false} icon={<PlayCircle size={14} />} variant="secondary">
                  이어서 생성
                </LoadingButton>
              ) : (
                <LoadingButton onClick={generateAll} loading={false} icon={<Wand2 size={14} />} variant="secondary">
                  전체 생성
                </LoadingButton>
              )}
            </>
          )}
          {!generating && (
            <button
              onClick={async () => {
                const msg = cutsWithAudio.length > 0
                  ? `생성된 음성 ${cutsWithAudio.length}개를 모두 삭제하시겠습니까?\n파일 시스템의 audio 폴더가 전부 제거됩니다.`
                  : "음성 단계를 초기화하시겠습니까?\n남아있는 부분 파일과 태스크 상태가 정리됩니다.";
                if (!confirm(msg)) return;
                try {
                  await scriptApi.clearStep(project.id, "voice");
                  await taskApi.cancel(project.id, "voice").catch(() => {});
                  onUpdate();
                } catch (err: any) {
                  alert("정리 실패: " + err.message);
                }
              }}
              className="p-2 rounded-lg border border-border text-gray-500 hover:text-accent-danger hover:border-accent-danger/50 transition-colors"
              title={cutsWithAudio.length > 0 ? "음성 모두 지우기" : "음성 단계 정리"}
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </div>

      {/* v1.1.46: 모델·목소리 선택 UI 는 StepSettings 로 이관되었다.
          이 섹션은 현재 설정의 요약 + 미리듣기 + 예상 비용만 보여준다. */}
      <div className="bg-bg-secondary border border-border rounded-lg px-4 py-3 flex items-center justify-between gap-4">
        <div className="flex items-center gap-4 text-xs text-gray-400 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-gray-500">TTS 모델</span>
            <span className="text-gray-200 truncate">{currentModelLabel}</span>
          </div>
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="text-gray-500">목소리</span>
            <span className="text-gray-200 truncate">
              {project.config.tts_voice_id || "미선택"}
            </span>
          </div>
          <span className="text-[10px] text-gray-600">
            · 모델/목소리는 프로젝트 설정에서 변경합니다
          </span>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            onClick={previewVoice}
            disabled={previewLoading || previewPlaying}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm border transition-colors ${
              previewPlaying
                ? "bg-accent-primary/20 border-accent-primary text-accent-primary"
                : "bg-bg-primary border-border text-gray-300 hover:border-accent-primary/50"
            } disabled:opacity-50`}
          >
            <Headphones size={14} className={previewPlaying ? "animate-pulse" : ""} />
            {previewLoading ? "생성 중..." : previewPlaying ? "재생 중..." : "미리듣기"}
          </button>
          <CostEstimate
            label="음성 예상 비용"
            amount={estimatedVoiceCost}
            detail={`${totalChars.toLocaleString()}자`}
          />
        </div>
      </div>

      {/* Generation timer */}
      <GenerationTimer
        projectId={project.id}
        step="voice"
        running={generating}
        totalItems={cuts.length}
        secsPerItem={4}
        label="음성 생성 중..."
        onComplete={() => {
          setGenerating(false);
          onUpdate();
        }}
      />
      </div>{/* 상단 컨트롤 끝 */}

      {/* ── 스크롤 영역 ── */}
      <div className="flex-1 overflow-y-auto min-h-0">
      {/* Cut list */}
      {cuts.length === 0 ? (
        <div className="bg-bg-secondary border border-border rounded-lg p-12 text-center">
          <Mic size={48} className="mx-auto mb-4 text-gray-600" />
          <p className="text-gray-400">대본을 먼저 생성하세요.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {cuts.map((cut, idx) => {
            const isCurrentlyGenerating = generating && !cut.audio_path && cut.narration && idx === generatingIndex;
            const isWaiting = generating && !cut.audio_path && cut.narration && idx > generatingIndex;
            return (
              <div key={cut.cut_number} className={`bg-bg-secondary border rounded-lg px-4 py-3 flex items-center gap-4 ${isCurrentlyGenerating ? "border-accent-primary/60 ring-1 ring-accent-primary/30" : "border-border"}`}>
                <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${isCurrentlyGenerating ? "bg-accent-primary text-white" : "bg-accent-primary/20 text-accent-primary"}`}>
                  {isCurrentlyGenerating ? <Loader2 size={14} className="animate-spin" /> : cut.cut_number}
                </div>
                <p className="flex-1 text-sm text-gray-300 truncate">{cut.narration}</p>
                <div className="flex items-center gap-2 flex-shrink-0">
                  {cut.audio_duration && (
                    <span className="text-xs text-gray-500">{cut.audio_duration.toFixed(1)}s</span>
                  )}
                  {cut.audio_path ? (
                    <>
                      {generating && (
                        <span className="text-[10px] text-emerald-400 font-medium">완료</span>
                      )}
                      <button
                        onClick={() => playAudio(cut)}
                        className={`p-1.5 rounded transition-colors ${
                          playingCut === cut.cut_number
                            ? "bg-accent-primary/20 text-accent-primary"
                            : "hover:bg-bg-tertiary text-gray-400 hover:text-white"
                        }`}
                      >
                        <Volume2 size={14} />
                      </button>
                      <button
                        onClick={() => regenerate(cut.cut_number)}
                        disabled={regeneratingCut === cut.cut_number}
                        className="p-1.5 rounded hover:bg-bg-tertiary text-gray-400 hover:text-accent-warning transition-colors disabled:opacity-50"
                      >
                        <RefreshCw size={14} className={regeneratingCut === cut.cut_number ? "animate-spin" : ""} />
                      </button>
                    </>
                  ) : isCurrentlyGenerating ? (
                    <span className="text-xs text-accent-primary font-medium">생성 중...</span>
                  ) : isWaiting ? (
                    <span className="text-xs text-gray-600">대기 중</span>
                  ) : (
                    <span className="text-xs text-gray-600">미생성</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
      </div>{/* 스크롤 영역 끝 */}
    </div>
  );
}
