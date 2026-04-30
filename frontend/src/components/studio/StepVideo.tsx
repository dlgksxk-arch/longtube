"use client";

import { useState, useEffect, useRef } from "react";
import { Film, Wand2, Play, Trash2, StopCircle, PlayCircle, Loader2, Users, X } from "lucide-react";
import LoadingButton from "@/components/common/LoadingButton";
import ModelSelector from "@/components/common/ModelSelector";
import CostEstimate from "@/components/common/CostEstimate";
import { videoApi, modelsApi, projectsApi, scriptApi, taskApi, apiStatusApi, assetUrl, cutHasCharacter, type Project, type Cut, type ModelInfo, type TaskStatus, type FalVideoProbeResult } from "@/lib/api";
import { AlertCircle, Stethoscope } from "lucide-react";
import GenerationTimer from "@/components/common/GenerationTimer";

interface Props {
  project: Project;
  cuts: Cut[];
  onUpdate: () => void;
}

export default function StepVideo({ project, cuts, onUpdate }: Props) {
  const [generating, setGenerating] = useState(false);
  const [waiting, setWaiting] = useState(false);  // 이미지 완료 대기 중
  const [playingCut, setPlayingCut] = useState<number | null>(null);
  const [previewCut, setPreviewCut] = useState<Cut | null>(null);
  const [videoError, setVideoError] = useState<string | null>(null);
  const [videoModels, setVideoModels] = useState<ModelInfo[]>([]);
  const [generatingIndex, setGeneratingIndex] = useState(-1);
  const [taskStatus, setTaskStatus] = useState<TaskStatus | null>(null);
  const [probing, setProbing] = useState(false);
  const [probeResult, setProbeResult] = useState<FalVideoProbeResult | null>(null);
  const lastCompletedRef = useRef(0);

  const runFalProbe = async () => {
    const modelId = project.config.video_model || "seedance-lite";
    // Only probe fal models; for local ffmpeg it's meaningless
    const m = videoModels.find((vm) => vm.id === modelId);
    if (m && m.provider && m.provider !== "fal") {
      setProbeResult({
        ok: true,
        model: modelId,
        input_model: modelId,
        http_code: 0,
        status: "key_valid",
        detail: `${m.name}는 fal.ai 공급자가 아니라서 이 진단은 의미가 없습니다.`,
        body: "",
      });
      return;
    }
    setProbing(true);
    setProbeResult(null);
    try {
      const r = await apiStatusApi.probeFalVideo(modelId);
      setProbeResult(r);
    } catch (e: any) {
      setProbeResult({
        ok: false,
        model: modelId,
        input_model: modelId,
        http_code: 0,
        status: "error",
        detail: `요청 실패: ${e?.message || e}`,
        body: "",
      });
    } finally {
      setProbing(false);
    }
  };

  const cutsWithVideo = cuts.filter((c) => c.video_path);

  // Poll task status during generation → refresh cuts when a new video completes
  // Also detect "waiting" → "running" transition via step_states
  useEffect(() => {
    if (!generating) {
      lastCompletedRef.current = 0;
      setGeneratingIndex(-1);
      setWaiting(false);
      return;
    }
    const poll = setInterval(async () => {
      try {
        const status = await taskApi.status(project.id, "video");
        setTaskStatus(status);

        // step_states 에서 대기 상태 감지
        const proj = await projectsApi.get(project.id);
        const videoStepState = proj?.step_states?.["5"] || "";
        setWaiting(videoStepState === "waiting");

        if (status.completed > lastCompletedRef.current) {
          lastCompletedRef.current = status.completed;
          onUpdate();
        }
        setGeneratingIndex(status.completed);
        if (status.status !== "running") {
          setGenerating(false);
          setWaiting(false);
          setGeneratingIndex(-1);
          onUpdate();
        }
      } catch {}
    }, 2000);
    return () => clearInterval(poll);
  }, [generating, project.id]);

  // Also fetch task status once on mount so error cards show even when idle/failed
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const status = await taskApi.status(project.id, "video");
        if (!cancelled) setTaskStatus(status);
      } catch {}
    })();
    return () => { cancelled = true; };
  }, [project.id, cuts.length]);

  useEffect(() => {
    modelsApi.listVideo().then((d) => setVideoModels(d.models)).catch(() => {});
  }, [project.id]);

  // On mount / project change — restore generating state if backend task is still running.
  // This lets the user switch tabs mid-generation and come back without losing the UI state.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const status = await taskApi.status(project.id, "video");
        if (!cancelled && status.status === "running") {
          setGenerating(true);
          lastCompletedRef.current = status.completed;
          setGeneratingIndex(status.completed);
          // step_states["5"] === "waiting" 이면 대기 상태 복원
          const videoStepState = project.step_states?.["5"] || "";
          setWaiting(videoStepState === "waiting");
        }
      } catch {}
    })();
    return () => { cancelled = true; };
  }, [project.id]);

  const changeModel = async (modelId: string) => {
    try {
      await projectsApi.update(project.id, { config: { video_model: modelId } });
      onUpdate();
    } catch {}
  };

  const generateAll = async () => {
    setGenerating(true);
    try {
      await videoApi.generateAsync(project.id);
    } catch (err: any) {
      alert("영상 생성 실패: " + err.message);
      setGenerating(false);
    }
  };

  const stopGeneration = async () => {
    // v1.1.55: confirm 제거 — 바로 중지
    try {
      setGenerating(false);
      await taskApi.cancel(project.id, "video");
      onUpdate();
    } catch {}
  };

  const resumeGeneration = async () => {
    setGenerating(true);
    try {
      const res = await videoApi.resumeAsync(project.id);
      if (res.status === "nothing_to_resume") {
        alert("이어서 생성할 영상이 없습니다. 모든 컷이 완료되었습니다.");
        setGenerating(false);
      }
    } catch (err: any) {
      alert("이어서 생성 실패: " + err.message);
      setGenerating(false);
    }
  };

  const hasPendingCuts = cuts.some((c) => !c.video_path && c.image_path && c.audio_path);

  // Cost estimate
  const selectedModel = videoModels.find((m) => m.id === project.config.video_model);
  const costPerClip = selectedModel?.cost_value || 0;
  const cutCount = cuts.length || Math.floor(project.config.target_duration / 5);
  // v1.1.36: 선택된 AI 컷 수 계산. 규칙은 backend video.py 와 동일.
  const videoTargetSelection = project.config.video_target_selection || "all";
  const countAiCuts = (total: number, selection: string): number => {
    if (total <= 0) return 0;
    if (selection === "all") return total;
    let step = 0;
    if (selection === "every_3" || selection === "character_only") step = 3;
    else if (selection === "every_4") step = 4;
    else if (selection === "every_5") step = 5;
    else return total;
    let n = 0;
    for (let i = 1; i <= total; i++) {
      // v1.1.55: 앞 5컷은 무조건 AI
      if (i <= 5 || (i - 1) % step === 0) n++;
    }
    return n;
  };
  const aiCutCount = countAiCuts(cutCount, videoTargetSelection);
  const estimatedVideoCost = aiCutCount * costPerClip;

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {/* ── 상단 컨트롤 (틀고정) ── */}
      <div className="flex-shrink-0 space-y-4 pb-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-accent-secondary">
          <Film size={20} />
          <h2 className="text-lg font-semibold">영상 생성</h2>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-400">
            {cutsWithVideo.length}/{cuts.length}컷 완료
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
              {hasPendingCuts && cutsWithVideo.length > 0 ? (
                <LoadingButton onClick={resumeGeneration} loading={false} icon={<PlayCircle size={14} />} variant="secondary">
                  이어서 생성
                </LoadingButton>
              ) : (
                <LoadingButton onClick={generateAll} loading={false} icon={<Wand2 size={14} />} variant="secondary">
                  전체 생성 + 병합
                </LoadingButton>
              )}
            </>
          )}
          {!generating && (
            <button
              onClick={async () => {
                const msg = cutsWithVideo.length > 0
                  ? `생성된 영상 ${cutsWithVideo.length}개를 모두 삭제하시겠습니까?\n병합된 최종 영상과 파일 시스템의 video 폴더가 전부 제거됩니다.`
                  : "영상 단계를 초기화하시겠습니까?\n남아있는 부분 파일과 태스크 상태가 정리됩니다.";
                if (!confirm(msg)) return;
                try {
                  await scriptApi.clearStep(project.id, "video");
                  await taskApi.cancel(project.id, "video").catch(() => {});
                  onUpdate();
                } catch (err: any) {
                  alert("정리 실패: " + err.message);
                }
              }}
              className="p-2 rounded-lg border border-border text-gray-500 hover:text-accent-danger hover:border-accent-danger/50 transition-colors"
              title={cutsWithVideo.length > 0 ? "영상 모두 지우기" : "영상 단계 정리"}
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </div>

      {/* 이미지 대기 상태 배너 */}
      {generating && waiting && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/30 text-yellow-400 text-sm">
          <Loader2 size={16} className="animate-spin" />
          <span>이미지 생성 완료 대기 중... 이미지 완료 후 3초 뒤 영상 생성이 시작됩니다.</span>
        </div>
      )}

      {/* Model + Cost */}
      <div className="grid grid-cols-2 gap-3">
        <ModelSelector
          label="영상 생성 모델"
          models={videoModels}
          value={project.config.video_model}
          onChange={changeModel}
        />
        <div className="flex items-end">
          <CostEstimate
            label="영상 예상 비용"
            amount={estimatedVideoCost}
            detail={
              videoTargetSelection === "all"
                ? `${cutCount}클립`
                : `AI ${aiCutCount}컷 / 폴백 ${cutCount - aiCutCount}컷`
            }
          />
        </div>
      </div>

      {/* v1.1.36: 영상 제작 대상 선택은 프로젝트 설정(StepSettings) 으로 이동됨.
          여기서는 현재 선택값에 따라 비용 detail 만 표시. */}
      {videoTargetSelection !== "all" && (
        <div className="rounded-lg border border-border/60 bg-bg-secondary/50 px-3 py-2 text-[11px] text-gray-500">
          총 {cutCount}컷 중 AI 생성{" "}
          <span className="text-accent-secondary font-semibold">{aiCutCount}컷</span>, 나머지{" "}
          {cutCount - aiCutCount}컷은 ffmpeg-kenburns 폴백.
          <span className="ml-1 text-gray-600">(설정에서 변경)</span>
        </div>
      )}

      </div>{/* 상단 컨트롤 끝 */}

      {/* ── 스크롤 영역 ── */}
      <div className="flex-1 overflow-y-auto min-h-0 space-y-4">
      {/* fal.ai key diagnostic */}
      <div className="flex items-center gap-2 flex-wrap">
        <button
          onClick={runFalProbe}
          disabled={probing}
          className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md border border-border bg-bg-secondary hover:border-accent-primary/50 hover:text-accent-primary transition-colors disabled:opacity-50"
          title="선택한 모델의 API 키 상태를 실제 queue 엔드포인트에 질의해서 확인합니다"
        >
          {probing ? <Loader2 size={12} className="animate-spin" /> : <Stethoscope size={12} />}
          <span>영상 API 키 진단</span>
        </button>
        {probeResult && (
          <span className="text-[11px] text-gray-500">
            모델: <span className="font-mono">{probeResult.model}</span>
          </span>
        )}
      </div>

      {probeResult && (
        <div
          className={`rounded-lg p-3 border text-xs ${
            probeResult.status === "key_valid"
              ? "bg-accent-primary/5 border-accent-primary/40"
              : probeResult.status === "auth_failed"
              ? "bg-accent-danger/5 border-accent-danger/50"
              : "bg-bg-secondary border-border"
          }`}
        >
          <div className="flex items-start gap-2">
            <AlertCircle
              size={14}
              className={`mt-0.5 flex-shrink-0 ${
                probeResult.status === "key_valid"
                  ? "text-accent-primary"
                  : probeResult.status === "auth_failed"
                  ? "text-accent-danger"
                  : "text-gray-400"
              }`}
            />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-semibold">
                  {probeResult.status === "key_valid" && "키 유효"}
                  {probeResult.status === "auth_failed" && "키 거부됨"}
                  {probeResult.status === "not_configured" && "키 미설정"}
                  {probeResult.status === "timeout" && "응답 시간 초과"}
                  {probeResult.status === "error" && "네트워크 오류"}
                  {probeResult.status === "unknown_ok" && "예상 밖 응답"}
                </span>
                {probeResult.http_code > 0 && (
                  <span className="font-mono text-[10px] text-gray-500">HTTP {probeResult.http_code}</span>
                )}
              </div>
              <p className="text-gray-300 mt-1">{probeResult.detail}</p>
              {probeResult.body && (
                <pre className="mt-2 p-2 bg-bg-primary/70 border border-border rounded text-[10px] font-mono text-gray-400 whitespace-pre-wrap break-all max-h-32 overflow-auto">
                  {probeResult.body}
                </pre>
              )}
              {probeResult.status === "auth_failed" && (
                <div className="mt-2 text-[11px] text-gray-400">
                  확인할 곳:{" "}
                  <a
                    href="https://fal.ai/dashboard/keys"
                    target="_blank"
                    rel="noreferrer"
                    className="text-accent-primary hover:underline"
                  >
                    fal.ai 대시보드 → Keys
                  </a>
                  {" · "}
                  <a
                    href="https://fal.ai/dashboard/billing"
                    target="_blank"
                    rel="noreferrer"
                    className="text-accent-primary hover:underline"
                  >
                    Billing
                  </a>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Task error card — shown when backend recorded any per-cut failure or task-level error */}
      {taskStatus && (taskStatus.status === "failed" || (taskStatus.item_errors && taskStatus.item_errors.length > 0)) && (
        <div className="bg-accent-danger/5 border border-accent-danger/50 rounded-lg p-4">
          <div className="flex items-start gap-2 mb-2">
            <AlertCircle size={16} className="text-accent-danger mt-0.5 flex-shrink-0" />
            <div className="flex-1">
              <h3 className="text-sm font-semibold text-accent-danger">
                영상 생성 실패 {taskStatus.item_errors && taskStatus.item_errors.length > 0 && `(${taskStatus.item_errors.length}개 컷)`}
              </h3>
              {taskStatus.error && (
                <p className="text-xs text-gray-400 mt-1">{taskStatus.error}</p>
              )}
            </div>
          </div>
          {taskStatus.item_errors && taskStatus.item_errors.length > 0 && (
            <div className="mt-2 space-y-1 max-h-60 overflow-auto">
              {taskStatus.item_errors.map((ie, i) => (
                <div key={i} className="text-xs bg-bg-primary/50 border border-accent-danger/20 rounded px-2 py-1.5">
                  <span className="text-accent-danger font-semibold">컷 {ie.cut_number}:</span>{" "}
                  <span className="text-gray-300 font-mono break-all">{ie.error}</span>
                </div>
              ))}
            </div>
          )}
          <p className="text-[10px] text-gray-500 mt-2">
            백엔드 콘솔의 <span className="font-mono">[video-async]</span> 로그에 전체 traceback 이 찍힙니다.
            이 카드는 백엔드 재시작 시 사라집니다 (메모리 저장).
          </p>
        </div>
      )}

      {cuts.length === 0 ? (
        <div className="bg-bg-secondary border border-border rounded-lg p-12 text-center">
          <Film size={48} className="mx-auto mb-4 text-gray-600" />
          <p className="text-gray-400">이미지와 음성을 먼저 생성하세요.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {/* Individual clips */}
          <div className="grid grid-cols-4 gap-2">
            {(() => {
              // v1.1.49: 병렬 생성 — 영상 없는 컷 중 앞 4개만 "생성 중", 나머지 "대기"
              const CONCURRENT = 4;
              const _genSet = new Set<number>();
              const _waitSet = new Set<number>();
              if (generating && !waiting) {
                let count = 0;
                for (const c of cuts) {
                  if (!c.video_path && c.image_path && c.audio_path) {
                    if (count < CONCURRENT) _genSet.add(c.cut_number);
                    else _waitSet.add(c.cut_number);
                    count++;
                  }
                }
              } else if (generating && waiting) {
                for (const c of cuts) {
                  if (!c.video_path && c.image_path && c.audio_path) {
                    _waitSet.add(c.cut_number);
                  }
                }
              }
              return cuts.map((cut) => ({ cut, _genSet, _waitSet }));
            })().map(({ cut, _genSet, _waitSet }) => {
              const isCurrentlyGenerating = _genSet.has(cut.cut_number);
              const isWaiting = _waitSet.has(cut.cut_number);
              return (
                <div key={cut.cut_number} className={`bg-bg-secondary border rounded-lg overflow-hidden ${isCurrentlyGenerating ? "border-accent-primary/60 ring-1 ring-accent-primary/30" : "border-border"}`}>
                  <div className="aspect-video bg-bg-primary relative">
                    {cut.video_path ? (
                      <>
                        <video
                          src={assetUrl(project.id, cut.video_path)}
                          className="w-full h-full object-cover"
                          preload="metadata"
                          muted
                          poster={cut.image_path ? assetUrl(project.id, cut.image_path) : undefined}
                          onPlay={() => setPlayingCut(cut.cut_number)}
                          onPause={() => setPlayingCut(null)}
                          onEnded={() => setPlayingCut(null)}
                        />
                        {playingCut !== cut.cut_number && (
                          <button
                            type="button"
                            className="absolute inset-0 flex items-center justify-center cursor-pointer"
                            aria-label={`컷 ${cut.cut_number} 영상 재생`}
                            onClick={() => {
                              setVideoError(null);
                              setPlayingCut(cut.cut_number);
                              setPreviewCut(cut);
                            }}
                          >
                            <div className="w-12 h-12 rounded-full bg-black/60 flex items-center justify-center">
                              <Play size={20} className="text-white ml-0.5" />
                            </div>
                          </button>
                        )}
                      </>
                    ) : isCurrentlyGenerating ? (
                      <div className="w-full h-full flex flex-col items-center justify-center gap-2">
                        {cut.image_path && (
                          <img src={assetUrl(project.id, cut.image_path)} className="absolute inset-0 w-full h-full object-cover opacity-30" alt="" />
                        )}
                        <Loader2 size={24} className="text-accent-primary animate-spin relative z-10" />
                        <span className="text-[10px] text-accent-primary font-medium relative z-10">생성 중...</span>
                      </div>
                    ) : isWaiting ? (
                      <div className="w-full h-full flex flex-col items-center justify-center gap-1 relative">
                        {cut.image_path && (
                          <img src={assetUrl(project.id, cut.image_path)} className="absolute inset-0 w-full h-full object-cover opacity-20" alt="" />
                        )}
                        <Film size={20} className="text-gray-600 relative z-10" />
                        <span className="text-[10px] text-gray-600 relative z-10">대기 중</span>
                      </div>
                    ) : cut.image_path ? (
                      <div className="w-full h-full relative">
                        <img src={assetUrl(project.id, cut.image_path)} className="absolute inset-0 w-full h-full object-cover opacity-60" alt="" />
                        <div className="absolute inset-0 bg-black/30 flex flex-col items-center justify-center gap-1">
                          <Film size={22} className="text-gray-300" />
                          <span className="text-[10px] text-gray-300 font-medium">영상 대기</span>
                        </div>
                      </div>
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-gray-600">
                        <Film size={24} />
                      </div>
                    )}
                    <div className={`absolute top-2 left-2 w-6 h-6 rounded-full text-white text-xs flex items-center justify-center font-bold ${isCurrentlyGenerating ? "bg-accent-primary" : "bg-black/70"}`}>
                      {cut.cut_number}
                    </div>
                    {cutHasCharacter(cut.cut_number) && (
                      <div
                        className="absolute bottom-2 left-2 px-1.5 py-0.5 rounded text-[10px] bg-accent-secondary/80 text-white font-bold flex items-center gap-1"
                        title="캐릭터가 자연스럽게 움직이는 프롬프트가 자동으로 적용됩니다."
                      >
                        <Users size={10} /> 캐릭터 모션
                      </div>
                    )}
                    {cut.cut_number === 1 && (
                      <div className="absolute bottom-2 right-2 px-1.5 py-0.5 rounded text-[10px] bg-accent-primary/80 text-white font-bold">
                        오프닝
                      </div>
                    )}
                    {cuts.length > 1 && cut.cut_number === cuts.length && (
                      <div className="absolute bottom-2 right-2 px-1.5 py-0.5 rounded text-[10px] bg-accent-warning/80 text-black font-bold">
                        엔딩
                      </div>
                    )}
                    {cut.video_path && generating && (
                      <div className="absolute top-2 right-2 px-1.5 py-0.5 rounded text-[10px] bg-emerald-500/80 text-white font-bold">완료</div>
                    )}
                  </div>
                  <div className="px-3 py-2 flex items-center justify-between">
                    <p className="text-xs text-gray-400 truncate flex-1">{cut.narration}</p>
                    {cut.audio_duration && (
                      <span className="text-xs text-gray-500 ml-2">{cut.audio_duration.toFixed(1)}s</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
      </div>{/* 스크롤 영역 끝 */}
      {previewCut?.video_path && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-6"
          onClick={() => {
            setPreviewCut(null);
            setPlayingCut(null);
            setVideoError(null);
          }}
        >
          <div
            className="w-full max-w-5xl rounded-2xl border border-border bg-bg-secondary shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <div>
                <p className="text-sm font-semibold text-white">컷 {previewCut.cut_number} 영상 미리보기</p>
                <p className="mt-0.5 text-[11px] text-gray-500">{previewCut.video_model || project.config.video_model}</p>
              </div>
              <button
                type="button"
                className="rounded-lg p-2 text-gray-400 hover:bg-white/10 hover:text-white"
                onClick={() => {
                  setPreviewCut(null);
                  setPlayingCut(null);
                  setVideoError(null);
                }}
                aria-label="미리보기 닫기"
              >
                <X size={18} />
              </button>
            </div>
            <div className="p-4">
              <video
                key={`${previewCut.cut_number}-${previewCut.video_path}`}
                src={`${assetUrl(project.id, previewCut.video_path)}?v=${encodeURIComponent(project.updated_at || "")}`}
                poster={previewCut.image_path ? assetUrl(project.id, previewCut.image_path) : undefined}
                className="max-h-[72vh] w-full rounded-xl bg-black object-contain"
                controls
                autoPlay
                playsInline
                onCanPlay={() => setVideoError(null)}
                onError={(e) => {
                  const code = e.currentTarget.error?.code ?? "unknown";
                  setVideoError(`브라우저가 이 영상 파일을 열지 못했습니다. media error=${code}`);
                }}
              />
              {videoError && (
                <div className="mt-3 rounded-lg border border-accent-danger/50 bg-accent-danger/10 px-3 py-2 text-xs text-accent-danger">
                  {videoError}
                </div>
              )}
              <p className="mt-3 text-sm text-gray-300">{previewCut.narration}</p>
              <a
                href={assetUrl(project.id, previewCut.video_path)}
                target="_blank"
                rel="noreferrer"
                className="mt-2 inline-block text-xs text-accent-primary hover:underline"
              >
                새 탭에서 영상 파일 직접 열기
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
