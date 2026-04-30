"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import {
  LayoutDashboard, Play, Pause, Download,
  Check, Loader2, AlertCircle, RotateCcw, Timer
} from "lucide-react";
import { projectsApi, pipelineApi, scriptApi, downloadUrls, type Project, type Cut, type StepProgress } from "@/lib/api";
import { APP_VERSION } from "@/lib/version";
import { formatDurationKo, formatKrw, costTierClasses } from "@/lib/format";
import StepSettings from "@/components/studio/StepSettings";
import StepScript from "@/components/studio/StepScript";
import StepVoice from "@/components/studio/StepVoice";
import StepImage from "@/components/studio/StepImage";
import StepVideo from "@/components/studio/StepVideo";
import StepRender from "@/components/studio/StepRender";
import StepYouTube from "@/components/studio/StepYouTube";
import GenerationTimer from "@/components/common/GenerationTimer";
import LocalServiceStatus from "@/components/common/LocalServiceStatus";

// v1.1.32 이후: 자막 스텝 제거. 자막 스타일은 설정(Step 1)에서 관리하고,
// 번인은 Step 6(렌더링) 에서 한 번에 처리한다.
const STEPS = [
  { num: 1, name: "설정" },
  { num: 2, name: "대본" },
  { num: 3, name: "음성" },
  { num: 4, name: "이미지" },
  { num: 5, name: "영상" },
  { num: 6, name: "렌더링" },
  { num: 7, name: "유튜브" },
];

function formatETA(seconds: number): string {
  if (seconds <= 0) return "";
  if (seconds < 60) return `${seconds}초`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m < 60) return `${m}분 ${s}초`;
  const h = Math.floor(m / 60);
  return `${h}시간 ${m % 60}분`;
}

// 사이드바용: 원형 스텝 인디케이터 (스크린샷의 세로 동그라미 형태)
const stepCircle = (state: string, num: number, isActive: boolean) => {
  const base = "w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 border-2 transition-colors";
  if (state === "completed") {
    return (
      <div className={`${base} bg-accent-success/15 border-accent-success text-accent-success`}>
        <Check size={16} />
      </div>
    );
  }
  if (state === "running") {
    return (
      <div className={`${base} bg-accent-primary/15 border-accent-primary text-accent-primary`}>
        <Loader2 size={16} className="animate-spin" />
      </div>
    );
  }
  if (state === "waiting") {
    return (
      <div className={`${base} bg-yellow-500/15 border-yellow-500 text-yellow-400`}>
        <Timer size={14} />
      </div>
    );
  }
  if (state === "paused") {
    return (
      <div className={`${base} bg-accent-warning/15 border-accent-warning text-accent-warning`}>
        <Pause size={14} />
      </div>
    );
  }
  if (state === "failed") {
    return (
      <div className={`${base} bg-accent-danger/15 border-accent-danger text-accent-danger`}>
        <AlertCircle size={16} />
      </div>
    );
  }
  return (
    <div className={`${base} ${
      isActive
        ? "bg-accent-primary/10 border-accent-primary text-accent-primary"
        : "bg-bg-secondary border-gray-700 text-gray-500"
    }`}>
      <span className="text-sm font-semibold">{num}</span>
    </div>
  );
};

export default function StudioPage() {
  const params = useParams();
  const projectId = params.projectId as string;
  const [project, setProject] = useState<Project | null>(null);
  const [cuts, setCuts] = useState<Cut[]>([]);
  const [activeStep, setActiveStep] = useState(1);
  const [isRunning, setIsRunning] = useState(false);
  const [stepProgress, setStepProgress] = useState<Record<string, StepProgress>>({});
  // v1.1.55: 설정 탭 미저장 경고
  const [settingsDirty, setSettingsDirty] = useState(false);

  const loadProject = useCallback(async () => {
    try {
      const data = await projectsApi.get(projectId);
      setProject(data);
      const running = Object.values(data.step_states || {}).some((s) => s === "running" || s === "waiting");
      setIsRunning(running);
      try {
        const cutsData = await scriptApi.listCuts(projectId);
        setCuts(cutsData.cuts || []);
      } catch {}
    } catch {}
  }, [projectId]);

  const loadProgress = useCallback(async () => {
    try {
      const status = await pipelineApi.status(projectId);
      setStepProgress(status.step_progress || {});
      const running = Object.values(status.step_progress || {}).some((s) => s.state === "running");
      setIsRunning(running);
    } catch {}
  }, [projectId]);

  useEffect(() => {
    loadProject();
    loadProgress();
  }, [loadProject, loadProgress]);

  useEffect(() => {
    if (!isRunning) return;
    const interval = setInterval(() => {
      loadProject();
      loadProgress();
    }, 2000);
    return () => clearInterval(interval);
  }, [isRunning, loadProject, loadProgress]);

  const runAll = async () => {
    try {
      await pipelineApi.runAll(projectId);
      setIsRunning(true);
      loadProject();
      loadProgress();
    } catch (err: any) {
      alert("실행 실패: " + err.message);
    }
  };

  const runStep = async (step: number) => {
    try {
      await pipelineApi.runStep(projectId, step);
      setIsRunning(true);
      loadProject();
      loadProgress();
    } catch (err: any) {
      alert("단계 실행 실패: " + err.message);
    }
  };

  const pauseStep = async (step: number) => {
    try {
      await pipelineApi.pauseStep(projectId, step);
      loadProject();
      loadProgress();
    } catch {}
  };

  const resumeStep = async (step: number) => {
    try {
      await pipelineApi.resumeStep(projectId, step);
      setIsRunning(true);
      loadProject();
      loadProgress();
    } catch {}
  };

  const resetStep = async (step: number) => {
    const name = STEPS.find((s) => s.num === step)?.name || "";
    if (!confirm(`"${name}" 단계를 초기화하시겠습니까?\n생성된 데이터가 삭제됩니다.`)) return;
    try {
      await pipelineApi.resetStep(projectId, step);
      loadProject();
      loadProgress();
    } catch (err: any) {
      alert("초기화 실패: " + err.message);
    }
  };

  const cancelPipeline = async () => {
    try {
      await pipelineApi.cancel(projectId);
      setIsRunning(false);
      loadProject();
      loadProgress();
    } catch {}
  };

  const handleUpdate = useCallback(() => {
    loadProject();
    loadProgress();
  }, [loadProject, loadProgress]);

  // v1.1.55: 설정 미저장 시 브라우저 이탈 경고 (새로고침/뒤로가기/탭 닫기)
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (settingsDirty) { e.preventDefault(); }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [settingsDirty]);

  if (!project) return <div className="p-8 text-gray-400">로딩 중...</div>;

  // Step states: backend step_states + auto-detect from validated cut data
  // listCuts API validates file existence on disk, so cut paths are reliable
  const rawStepStates = project.step_states || {};
  const stepStates: Record<string, string> = { ...rawStepStates };
  // 설정 단계(1)는 항상 완료 상태
  stepStates["1"] = "completed";

  if (cuts.length > 0 && (!stepStates["2"] || stepStates["2"] === "pending")) {
    stepStates["2"] = "completed";
  }
  if (cuts.length > 0 && cuts.every(c => c.audio_path) && stepStates["3"] !== "running") {
    stepStates["3"] = "completed";
  }
  if (cuts.length > 0 && cuts.every(c => c.image_path) && stepStates["4"] !== "running") {
    stepStates["4"] = "completed";
  }
  if (cuts.length > 0 && cuts.every(c => c.video_path) && stepStates["5"] !== "running" && stepStates["5"] !== "waiting") {
    stepStates["5"] = "completed";
  }
  // YouTube 업로드 완료 자동 감지 — v1.1.32 이후 Step 7
  if (project.youtube_url && stepStates["7"] !== "running") {
    stepStates["7"] = "completed";
  }

  const renderStepContent = () => {
    switch (activeStep) {
      case 1: return <StepSettings project={project} onUpdate={handleUpdate} onNextStep={() => setActiveStep(2)} onDirtyChange={setSettingsDirty} />;
      case 2: return <StepScript project={project} onUpdate={handleUpdate} onCutsChange={(c) => setCuts(c)} />;
      case 3: return <StepVoice project={project} cuts={cuts} onUpdate={handleUpdate} />;
      case 4: return <StepImage project={project} cuts={cuts} onUpdate={handleUpdate} />;
      case 5: return <StepVideo project={project} cuts={cuts} onUpdate={handleUpdate} />;
      case 6: return <StepRender project={project} cuts={cuts} onUpdate={handleUpdate} />;
      case 7: return <StepYouTube project={project} cuts={cuts} onUpdate={handleUpdate} />;
      default: return null;
    }
  };

  return (
    <div className="h-screen bg-bg-primary flex flex-col overflow-hidden">
      {/* Top bar — 항상 상단 고정 */}
      <div className="border-b border-border px-6 py-3 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-4">
          <a
            href="/"
            onClick={(e) => {
              if (settingsDirty) {
                if (!confirm("설정에 저장되지 않은 변경사항이 있습니다.\n저장하지 않고 이동하시겠습니까?")) {
                  e.preventDefault();
                }
              }
            }}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border bg-bg-secondary hover:bg-bg-tertiary text-gray-300 hover:text-white transition-colors text-sm font-medium"
          >
            <LayoutDashboard size={16} />
            <span>대시보드</span>
          </a>
          <div className="h-6 w-px bg-border" />
          <div className="min-w-0 max-w-[500px]">
            <h1 className="text-lg font-semibold truncate">{project.title}</h1>
            {/* ★ 안전망: project.topic 이 과거 버그로 긴 YouTube 설명 전문으로
                덮어써져 있을 수 있으므로, 헤더에선 항상 1 줄로 truncate. */}
            <p className="text-xs text-gray-500 truncate" title={project.topic}>
              {project.topic}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-xs text-gray-500">{project.total_cuts || project.estimate?.estimated_cuts || 0}컷</span>
          {/* v1.1.33 → v1.1.35: 예상 소요시간 / 예상비용 (원화 + 월 + tier) */}
          {project.estimate && (() => {
            const est = project.estimate!;
            const tier = costTierClasses(est.cost_tier);
            const krw = est.estimated_cost_krw ?? est.estimated_cost_usd * 1360;
            const monthKrw = est.monthly_cost_krw ?? krw * 30;
            return (
              <>
                <span
                  className="text-xs text-sky-300 bg-sky-400/10 px-2 py-0.5 rounded"
                  title={`LLM ${est.time_breakdown.llm_script}s · 이미지 ${est.time_breakdown.image_generation}s · TTS ${est.time_breakdown.tts}s · 비디오 ${est.time_breakdown.video}s · 합성 ${est.time_breakdown.post_process}s`}
                >
                  예상 {formatDurationKo(est.estimated_seconds)}
                </span>
                <span
                  className={`text-xs ${tier.text} ${tier.bg} border ${tier.border} px-2 py-0.5 rounded font-medium`}
                  title={`1편 $${est.estimated_cost_usd.toFixed(2)} ≈ ${formatKrw(krw)}\n월 30편 예상: ${formatKrw(monthKrw)}\n환율 가정 1 USD ≈ 1,360 KRW\n\nLLM $${est.cost_breakdown.llm_script.toFixed(3)} · 이미지 $${est.cost_breakdown.image_generation.toFixed(3)} · TTS $${est.cost_breakdown.tts.toFixed(3)} · 비디오 $${est.cost_breakdown.video.toFixed(3)}`}
                >
                  {formatKrw(krw)}/편
                </span>
                <span
                  className={`text-xs ${tier.text} opacity-80`}
                  title="일 1편 × 30일 기준"
                >
                  월 {formatKrw(monthKrw)}
                </span>
                {est.cost_tier === "expensive" && (
                  <span className="text-xs text-accent-danger font-semibold">
                    ⚠ 비용 과다
                  </span>
                )}
              </>
            );
          })()}
          <span className="text-sm text-gray-400">실사용: ${project.api_cost?.toFixed(2) || "0.00"}</span>
          {isRunning && (
            <span className="text-xs text-accent-primary animate-pulse flex items-center gap-1">
              <Loader2 size={12} className="animate-spin" /> 처리 중...
            </span>
          )}
          {/* v1.1.42: 자동화 스케줄 기능 제거 — 스튜디오 상단의 "/schedule"
              링크 삭제. 대시보드 상단 "딸깍 제작" 버튼이 대체한다. */}
          <a
            href={downloadUrls.all(projectId)}
            className="bg-bg-secondary hover:bg-bg-tertiary text-white px-3 py-1.5 rounded-lg flex items-center gap-2 text-sm border border-border"
          >
            <Download size={14} /> 다운로드
          </a>
          <span className="text-[10px] text-gray-600 border border-gray-700 rounded px-1.5 py-0.5 font-mono">v{APP_VERSION}</span>
        </div>
      </div>

      {/* v1.1.41: 현재 실행 중인 백그라운드 작업(음성/이미지/영상)을 최상단에
          노출. 사용자가 다른 스텝 탭으로 이동해도 진행 상태가 보이고, 여기서
          직접 중지 버튼도 누를 수 있다. 각 GenerationTimer 는 해당 step 이
          실제로 running 일 때만 렌더링되므로 평시에는 보이지 않는다.
          요청: "한번 시작하면 페이지 변경 되도 계속 진행 되게 해". */}
      <div className="empty:hidden px-6 pt-3 flex flex-col gap-2 flex-shrink-0">
        <GenerationTimer
          projectId={projectId}
          step="script"
          label="대본 생성 중"
          onComplete={handleUpdate}
        />
        <GenerationTimer
          projectId={projectId}
          step="voice"
          label="음성 생성 중"
          onComplete={handleUpdate}
        />
        <GenerationTimer
          projectId={projectId}
          step="image"
          label="이미지 생성 중"
          onComplete={handleUpdate}
        />
        <GenerationTimer
          projectId={projectId}
          step="video"
          label="영상 생성 중"
          onComplete={handleUpdate}
        />
        <GenerationTimer
          projectId={projectId}
          step="render"
          label="최종 렌더링 중"
          onComplete={handleUpdate}
        />
      </div>

      {/* Body: vertical step sidebar + main content */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Left Sidebar — 항상 고정, 내부만 스크롤 */}
        <aside className="w-72 border-r border-border bg-bg-primary flex-shrink-0 overflow-y-auto">
          <LocalServiceStatus />
          <div className="p-4">
            <h2 className="text-[11px] uppercase tracking-wider text-gray-500 font-semibold mb-3 px-2">
              파이프라인
            </h2>
            <div className="relative">
              {STEPS.map((step, i) => {
                const state = stepStates[String(step.num)] || "pending";
                const progress = stepProgress[String(step.num)];
                const pct = progress?.progress_pct || 0;
                const eta = progress?.eta_seconds || 0;
                const isActive = activeStep === step.num;
                const isLast = i === STEPS.length - 1;
                // 파이프라인 스텝(2~5)만 일시정지/진행률/ETA UI 표시.
                // 1(설정), 6(렌더링), 7(유튜브)은 수동 단계라 컨트롤 UI 가 필요 없음.
                // v1.1.32 이후 자막 스텝 제거. 자막은 설정에서 관리하고 렌더링에서 번인.
                // v1.1.49: 렌더링(6)도 백그라운드 실행 지원 — 일시정지/진행률 UI 표시
                const isPipelineStep = step.num >= 2 && step.num <= 6;

                return (
                  <div key={step.num} className="relative">
                    {/* Connector line between circles */}
                    {!isLast && (
                      <div
                        className={`absolute left-[22px] top-[44px] w-0.5 h-[calc(100%-28px)] ${
                          state === "completed" ? "bg-accent-success" : "bg-gray-700"
                        }`}
                      />
                    )}

                    <button
                      onClick={() => {
                        if (activeStep === 1 && settingsDirty && step.num !== 1) {
                          if (!confirm("설정에 저장되지 않은 변경사항이 있습니다.\n저장하지 않고 이동하시겠습니까?")) return;
                          setSettingsDirty(false);
                        }
                        setActiveStep(step.num);
                      }}
                      className={`w-full text-left rounded-lg transition-colors mb-2 relative z-10 ${
                        isActive
                          ? "bg-accent-primary/10 ring-1 ring-accent-primary"
                          : "hover:bg-bg-secondary"
                      }`}
                    >
                      <div className="flex items-start gap-3 p-2">
                        {/* Circle */}
                        {stepCircle(state, step.num, isActive)}

                        {/* Label + info */}
                        <div className="flex-1 min-w-0 pt-1">
                          <div className="flex items-center justify-between">
                            <span className={`text-sm font-medium ${
                              isActive ? "text-accent-primary" : "text-gray-300"
                            }`}>
                              {step.name}
                            </span>
                            {/* Per-step controls (pipeline steps only) */}
                            {isPipelineStep && (
                              <div
                                className="flex items-center gap-0.5"
                                onClick={(e) => e.stopPropagation()}
                              >
                                {state === "running" && (
                                  <button
                                    onClick={() => pauseStep(step.num)}
                                    className="p-1 rounded hover:bg-accent-warning/20 text-gray-500 hover:text-accent-warning"
                                    title="일시정지"
                                  >
                                    <Pause size={11} />
                                  </button>
                                )}
                                {state === "paused" && (
                                  <button
                                    onClick={() => resumeStep(step.num)}
                                    className="p-1 rounded hover:bg-accent-primary/20 text-gray-500 hover:text-accent-primary"
                                    title="이어하기"
                                  >
                                    <Play size={11} />
                                  </button>
                                )}
                                {(state === "completed" || state === "failed" || state === "paused") && (
                                  <button
                                    onClick={() => resetStep(step.num)}
                                    className="p-1 rounded hover:bg-accent-danger/20 text-gray-500 hover:text-accent-danger"
                                    title="초기화"
                                  >
                                    <RotateCcw size={11} />
                                  </button>
                                )}
                              </div>
                            )}
                          </div>

                          {/* Progress bar (pipeline steps only) */}
                          {isPipelineStep && (
                            <div className="w-full h-1 bg-gray-700/50 rounded-full overflow-hidden mt-1.5">
                              <div
                                className={`h-full rounded-full transition-all duration-500 ${
                                  state === "completed" ? "bg-accent-success" :
                                  state === "waiting" ? "bg-yellow-500" :
                                  state === "running" ? "bg-accent-primary" :
                                  state === "paused" ? "bg-accent-warning" :
                                  state === "failed" ? "bg-accent-danger" :
                                  "bg-gray-600"
                                }`}
                                style={{ width: `${state === "completed" ? 100 : pct}%` }}
                              />
                            </div>
                          )}

                          {/* Bottom: status + ETA (pipeline steps only) */}
                          {isPipelineStep && (
                            <div className="flex items-center justify-between mt-1">
                              <span className="text-[10px] text-gray-500">
                                {state === "completed" ? "완료" :
                                 state === "waiting" ? "이미지 대기 중" :
                                 state === "running" ? `${progress?.completed_cuts || 0}/${progress?.total_cuts || 0}` :
                                 state === "paused" ? "일시정지" :
                                 state === "failed" ? "실패" : "대기"}
                              </span>
                              {eta > 0 && state !== "completed" && (
                                <span className="text-[10px] text-gray-500 flex items-center gap-0.5">
                                  <Timer size={8} />
                                  {formatETA(eta)}
                                </span>
                              )}
                            </div>
                          )}

                          {/* 렌더링 단계 보조 라벨 (progress bar 아래) */}
                          {step.num === 6 && stepStates["6"] !== "running" && stepStates["6"] !== "completed" && stepStates["6"] !== "failed" && (
                            <div className="mt-1 text-[10px] text-gray-500">
                              자막 + 오프닝/엔딩 합성
                            </div>
                          )}

                          {/* YouTube 수동 단계 상태 라벨 */}
                          {step.num === 7 && (
                            <div className="mt-1 text-[10px] text-gray-500">
                              {state === "completed" ? "업로드 완료" : "수동 업로드"}
                            </div>
                          )}
                        </div>
                      </div>
                    </button>
                  </div>
                );
              })}
            </div>

            {/* v1.1.42: 자동화 스케줄 카드 삭제. 사용자 요구로 자동 스케줄
                기능 자체가 제거됐다. 딸깍 제작은 대시보드 상단 버튼이 전담. */}
            {/* v1.1.37: 딸깍 제작 위젯은 대시보드(/)로 이동. Studio 는 프리셋/수동 작업 전용 */}
          </div>
        </aside>

        {/* Main content */}
        <main className="flex-1 flex flex-col overflow-hidden">
          <div className="flex-1 flex flex-col min-h-0 p-6 max-w-5xl mx-auto w-full">
            {renderStepContent()}
          </div>
        </main>
      </div>
    </div>
  );
}
