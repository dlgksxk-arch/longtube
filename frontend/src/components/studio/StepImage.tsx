"use client";

import { useState, useEffect, useRef } from "react";
import { Image as ImageIcon, Wand2, RefreshCw, Upload, Eye, Palette, Users, Trash2, StopCircle, PlayCircle, Loader2 } from "lucide-react";
import LoadingButton from "@/components/common/LoadingButton";
import ModelSelector from "@/components/common/ModelSelector";
import CostEstimate from "@/components/common/CostEstimate";
import { imageApi, modelsApi, projectsApi, scriptApi, taskApi, assetUrl, type Project, type Cut, type ModelInfo } from "@/lib/api";
import GenerationTimer from "@/components/common/GenerationTimer";

interface Props {
  project: Project;
  cuts: Cut[];
  onUpdate: () => void;
}

export default function StepImage({ project, cuts, onUpdate }: Props) {
  const [generating, setGenerating] = useState(false);
  const [regeneratingCut, setRegeneratingCut] = useState<number | null>(null);
  const [previewCut, setPreviewCut] = useState<Cut | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadCut, setUploadCut] = useState<number | null>(null);
  const [imageModels, setImageModels] = useState<ModelInfo[]>([]);
  const [globalPrompt, setGlobalPrompt] = useState("");
  const [savingPrompt, setSavingPrompt] = useState(false);
  const [generatingIndex, setGeneratingIndex] = useState(-1); // which cut index is currently generating
  const lastCompletedRef = useRef(0);

  const cutsWithImage = cuts.filter((c) => c.image_path);
  // v1.1.27: 레퍼런스/캐릭터 이미지는 Step 1 설정에서만 관리.
  // 여기서는 설정에 저장된 값을 그대로 사용하기 때문에 업로드 UI 를 제거한다.
  const referenceImages: string[] = (project.config as any).reference_images || [];
  const characterImages: string[] = (project.config as any).character_images || [];
  const hasCharacterAnchor = characterImages.length > 0 || Boolean((project.config as any).character_description?.trim?.());

  // Poll task status during generation → refresh cuts when a new image completes
  useEffect(() => {
    if (!generating) {
      lastCompletedRef.current = 0;
      setGeneratingIndex(-1);
      return;
    }
    const poll = setInterval(async () => {
      try {
        const status = await taskApi.status(project.id, "image");
        // Detect new completion → refresh UI
        if (status.completed > lastCompletedRef.current) {
          lastCompletedRef.current = status.completed;
          onUpdate(); // re-fetch cuts to show new images
        }
        // Track which cut is currently generating (next after completed)
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
    modelsApi.listImage().then((d) => setImageModels(d.models)).catch(() => {});
    setGlobalPrompt((project.config as any).image_global_prompt || "");
  }, [project.id]);

  // On mount — restore generating state if backend task is still running.
  // Allows user to switch tabs mid-generation and return without losing UI state.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const status = await taskApi.status(project.id, "image");
        if (!cancelled && status.status === "running") {
          setGenerating(true);
          lastCompletedRef.current = status.completed;
          setGeneratingIndex(status.completed);
        }
      } catch {}
    })();
    return () => { cancelled = true; };
  }, [project.id]);

  const changeModel = async (modelId: string) => {
    try {
      await projectsApi.update(project.id, { config: { image_model: modelId } });
      onUpdate();
    } catch {}
  };

  const saveGlobalPrompt = async () => {
    setSavingPrompt(true);
    try {
      await projectsApi.update(project.id, { config: { image_global_prompt: globalPrompt } });
      onUpdate();
    } catch {}
    setSavingPrompt(false);
  };

  const generateAll = async () => {
    setGenerating(true);
    try {
      await imageApi.generateAsync(project.id);
    } catch (err: any) {
      alert("이미지 생성 실패: " + err.message);
      setGenerating(false);
    }
  };

  const stopGeneration = async () => {
    if (!confirm("이미지 생성을 중지하시겠습니까?\n이미 완료된 이미지는 유지됩니다.")) return;
    try {
      await taskApi.cancel(project.id, "image");
      setGenerating(false);
      onUpdate();
    } catch {}
  };

  const resumeGeneration = async () => {
    setGenerating(true);
    try {
      const res = await imageApi.resumeAsync(project.id);
      if (res.status === "nothing_to_resume") {
        alert("이어서 생성할 이미지가 없습니다. 모든 컷이 완료되었습니다.");
        setGenerating(false);
      }
    } catch (err: any) {
      alert("이어서 생성 실패: " + err.message);
      setGenerating(false);
    }
  };

  const hasPendingCuts = cuts.some((c) => !c.image_path && c.image_prompt);

  const regenerate = async (cutNumber: number) => {
    setRegeneratingCut(cutNumber);
    try {
      await imageApi.regenerate(project.id, cutNumber);
      onUpdate();
    } catch (err: any) {
      alert("재생성 실패: " + err.message);
    } finally {
      setRegeneratingCut(null);
    }
  };

  const triggerUpload = (cutNumber: number) => {
    setUploadCut(cutNumber);
    fileInputRef.current?.click();
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || uploadCut === null) return;
    try {
      await imageApi.upload(project.id, uploadCut, file);
      onUpdate();
    } catch (err: any) {
      alert("업로드 실패: " + err.message);
    } finally {
      setUploadCut(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  // Cost estimate
  const selectedModel = imageModels.find((m) => m.id === project.config.image_model);
  // v1.1.56: `||` 대신 `??` — `cost_value: 0` (ComfyUI 로컬 무료 모델) 이
  // falsy 로 간주돼 0.03 폴백에 덮여 실제는 $0 인데 UI 는 ~$0.18 로 표시되던 버그 수정.
  const costPerImage = selectedModel?.cost_value ?? 0.03;
  const cutCount = cuts.length || Math.floor(project.config.target_duration / 5);
  const estimatedImageCost = cutCount * costPerImage;

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {/* ── 상단 컨트롤 (틀고정) ── */}
      <div className="flex-shrink-0 space-y-4 pb-4">
      <input type="file" ref={fileInputRef} onChange={handleUpload} accept="image/*" className="hidden" />

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-accent-secondary">
          <ImageIcon size={20} />
          <h2 className="text-lg font-semibold">이미지 생성</h2>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-400">
            {cutsWithImage.length}/{cuts.length}컷 완료
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
              {hasPendingCuts && cutsWithImage.length > 0 ? (
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
                const msg = cutsWithImage.length > 0
                  ? `생성된 이미지 ${cutsWithImage.length}개를 모두 삭제하시겠습니까?\n파일 시스템의 images 폴더가 전부 제거됩니다.`
                  : "이미지 단계를 초기화하시겠습니까?\n남아있는 부분 파일과 태스크 상태가 정리됩니다.";
                if (!confirm(msg)) return;
                try {
                  await scriptApi.clearStep(project.id, "image");
                  await taskApi.cancel(project.id, "image").catch(() => {});
                  onUpdate();
                } catch (err: any) {
                  alert("정리 실패: " + err.message);
                }
              }}
              className="p-2 rounded-lg border border-border text-gray-500 hover:text-accent-danger hover:border-accent-danger/50 transition-colors"
              title={cutsWithImage.length > 0 ? "이미지 모두 지우기" : "이미지 단계 정리"}
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </div>

      {/* Model + Cost */}
      <div className="grid grid-cols-2 gap-3">
        <ModelSelector
          label="이미지 생성 모델"
          models={imageModels}
          value={project.config.image_model}
          onChange={changeModel}
        />
        <div className="flex items-end">
          <CostEstimate label="이미지 예상 비용" amount={estimatedImageCost} detail={`${cutCount}장`} />
        </div>
      </div>

      </div>{/* 상단 컨트롤 끝 */}

      {/* ── 스크롤 영역 ── */}
      <div className="flex-1 overflow-y-auto min-h-0">
      {cuts.length === 0 ? (
        <div className="bg-bg-secondary border border-border rounded-lg p-12 text-center">
          <ImageIcon size={48} className="mx-auto mb-4 text-gray-600" />
          <p className="text-gray-400">대본을 먼저 생성하세요.</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-6 gap-2">
            {(() => {
              // v1.1.49: 병렬 생성 — 이미지 없는 컷 중 앞 4개만 "생성 중", 나머지 "대기"
              const CONCURRENT_IMAGES = 4;
              const _genSet = new Set<number>();
              const _waitSet = new Set<number>();
              if (generating) {
                let count = 0;
                for (const c of cuts) {
                  if (!c.image_path && c.image_prompt) {
                    if (count < CONCURRENT_IMAGES) _genSet.add(c.cut_number);
                    else _waitSet.add(c.cut_number);
                    count++;
                  }
                }
              }
              return cuts.map((cut) => ({ cut, _genSet, _waitSet }));
            })().map(({ cut, _genSet, _waitSet }) => {
              const isCurrentlyGenerating = _genSet.has(cut.cut_number);
              const isWaiting = _waitSet.has(cut.cut_number);
              return (
                <div key={cut.cut_number} className={`bg-bg-secondary border rounded-lg overflow-hidden group ${isCurrentlyGenerating ? "border-accent-primary/60 ring-1 ring-accent-primary/30" : "border-border"}`}>
                  <div className="aspect-video bg-bg-primary relative">
                    {cut.image_path ? (
                      <>
                        <img
                          src={`${assetUrl(project.id, cut.image_path)}?t=${Date.now()}`}
                          alt={`컷 ${cut.cut_number}`}
                          className="w-full h-full object-cover"
                          onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                        />
                        <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                          <button onClick={() => setPreviewCut(cut)} className="p-2 rounded-full bg-white/20 hover:bg-white/30 text-white">
                            <Eye size={16} />
                          </button>
                          <button
                            onClick={() => regenerate(cut.cut_number)}
                            disabled={regeneratingCut === cut.cut_number}
                            className="p-2 rounded-full bg-white/20 hover:bg-white/30 text-white disabled:opacity-50"
                          >
                            <RefreshCw size={16} className={regeneratingCut === cut.cut_number ? "animate-spin" : ""} />
                          </button>
                          <button onClick={() => triggerUpload(cut.cut_number)} className="p-2 rounded-full bg-white/20 hover:bg-white/30 text-white">
                            <Upload size={16} />
                          </button>
                        </div>
                      </>
                    ) : isCurrentlyGenerating ? (
                      <div className="w-full h-full flex flex-col items-center justify-center gap-2">
                        <Loader2 size={24} className="text-accent-primary animate-spin" />
                        <span className="text-[10px] text-accent-primary font-medium">생성 중...</span>
                      </div>
                    ) : isWaiting ? (
                      <div className="w-full h-full flex flex-col items-center justify-center gap-1">
                        <ImageIcon size={20} className="text-gray-600" />
                        <span className="text-[10px] text-gray-600">대기 중</span>
                      </div>
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-gray-600">
                        <ImageIcon size={24} />
                      </div>
                    )}
                    <div className={`absolute top-2 left-2 w-6 h-6 rounded-full text-white text-xs flex items-center justify-center font-bold ${isCurrentlyGenerating ? "bg-accent-primary" : "bg-black/70"}`}>
                      {cut.cut_number}
                    </div>
                    {hasCharacterAnchor && (
                      <div
                        className="absolute bottom-2 left-2 px-1.5 py-0.5 rounded text-[10px] bg-accent-secondary/80 text-white font-bold flex items-center gap-1"
                        title="이 컷에는 캐릭터 프롬프트가 적용됩니다"
                      >
                        <Users size={10} /> 캐릭터
                      </div>
                    )}
                    {cut.image_path && generating && (
                      <div className="absolute top-2 right-2 px-1.5 py-0.5 rounded text-[10px] bg-emerald-500/80 text-white font-bold">완료</div>
                    )}
                    {cut.is_custom_image && !generating && (
                      <div className="absolute top-2 right-2 px-1.5 py-0.5 rounded text-[10px] bg-accent-warning/80 text-black font-bold">커스텀</div>
                    )}
                  </div>
                  <div className="px-3 py-2">
                    <p className="text-xs text-gray-400 truncate">{cut.image_prompt}</p>
                    {cut.image_model && <p className="text-[10px] text-gray-600 mt-1">{cut.image_model}</p>}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
      </div>{/* 스크롤 영역 끝 */}

      {/* Preview Modal */}
      {previewCut && previewCut.image_path && (
        <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-8" onClick={() => setPreviewCut(null)}>
          <div className="max-w-4xl max-h-full" onClick={(e) => e.stopPropagation()}>
            <img
              src={assetUrl(project.id, previewCut.image_path)}
              alt={`컷 ${previewCut.cut_number} 미리보기`}
              className="max-w-full max-h-[80vh] object-contain rounded-lg"
            />
            <div className="mt-3 text-center">
              <p className="text-sm text-gray-300">컷 {previewCut.cut_number} — {previewCut.image_model}</p>
              <p className="text-xs text-gray-500 mt-1">{previewCut.image_prompt}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
