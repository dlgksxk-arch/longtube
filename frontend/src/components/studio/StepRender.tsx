"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { Film, Download, CheckCircle2, AlertCircle, Play, Trash2, Upload, Headphones } from "lucide-react";
import LoadingButton from "@/components/common/LoadingButton";
import GenerationTimer from "@/components/common/GenerationTimer";
import { subtitleApi, scriptApi, projectsApi, downloadUrls, resolveAssetUrl, assetUrl, type Project, type Cut, type ProjectConfig } from "@/lib/api";

interface Props {
  project: Project;
  cuts: Cut[];
  onUpdate: () => void;
}

interface RenderResult {
  status: string;
  path?: string;
  size?: number;
  elapsed_seconds?: number;
  download_url?: string;
  shorts?: {
    index: number;
    download_url: string;
    duration_seconds?: number;
    start_cut?: number;
    end_cut?: number;
  }[];
}

/**
 * Step 6: 최종 렌더링 스텝 (v1.1.32 이후)
 */
export default function StepRender({ project, cuts, onUpdate }: Props) {
  const [rendering, setRendering] = useState(false);
  const [result, setResult] = useState<RenderResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [previewBust, setPreviewBust] = useState(0);
  const [clearing, setClearing] = useState(false);
  const [clearError, setClearError] = useState<string | null>(null);
  const [availableShorts, setAvailableShorts] = useState<number[]>([1, 2]);
  const [bgmConfig, setBgmConfig] = useState<Partial<ProjectConfig>>(project.config || {});
  const [uploadingBgm, setUploadingBgm] = useState(false);
  const [generatingBgm, setGeneratingBgm] = useState(false);
  const [savingBgm, setSavingBgm] = useState(false);
  const bgmInputRef = useRef<HTMLInputElement>(null);

  const existingAssetUrl = assetUrl(project.id, "output/final_with_subtitles.mp4");
  const [showExisting, setShowExisting] = useState(true);

  useEffect(() => {
    setAvailableShorts([1, 2]);
  }, [project.id, previewBust]);

  useEffect(() => {
    setBgmConfig(project.config || {});
  }, [project.id, project.config]);

  const patchBgmConfig = (patch: Partial<ProjectConfig>) => {
    setBgmConfig((prev) => ({ ...prev, ...patch }));
  };

  const saveBgmConfig = async (patch: Partial<ProjectConfig> = {}) => {
    const next = { ...bgmConfig, ...patch };
    setSavingBgm(true);
    try {
      await projectsApi.update(project.id, {
        config: {
          bgm_enabled: Boolean(next.bgm_enabled),
          bgm_style_prompt: next.bgm_style_prompt || "",
          bgm_volume: Number(next.bgm_volume ?? 0.24),
        },
      });
      setBgmConfig(next);
      onUpdate();
    } finally {
      setSavingBgm(false);
    }
  };

  const handleBgmUpload = async (file: File | null) => {
    if (!file) return;
    setUploadingBgm(true);
    setError(null);
    try {
      await saveBgmConfig({ bgm_enabled: true });
      const res = await subtitleApi.uploadBgm(project.id, file);
      patchBgmConfig({ bgm_enabled: true, bgm_path: res.path, bgm_volume: bgmConfig.bgm_volume ?? res.volume ?? 0.24 });
      onUpdate();
    } catch (err: any) {
      setError(err?.message || "BGM 업로드 실패");
    } finally {
      setUploadingBgm(false);
    }
  };

  const handleBgmGenerate = async () => {
    setGeneratingBgm(true);
    setError(null);
    try {
      await saveBgmConfig({ bgm_enabled: true });
      const res = await subtitleApi.generateBgm(project.id);
      patchBgmConfig({
        bgm_enabled: true,
        bgm_path: res.path,
        bgm_prompt_used: res.prompt,
        bgm_volume: bgmConfig.bgm_volume ?? res.volume ?? 0.24,
      });
      onUpdate();
    } catch (err: any) {
      setError(err?.message || "BGM 생성 실패");
    } finally {
      setGeneratingBgm(false);
    }
  };

  const handleBgmDelete = async () => {
    if (!window.confirm("BGM 파일을 삭제할까요?")) return;
    setError(null);
    try {
      await subtitleApi.deleteBgm(project.id);
      patchBgmConfig({ bgm_enabled: false, bgm_path: "" });
      onUpdate();
    } catch (err: any) {
      setError(err?.message || "BGM 삭제 실패");
    }
  };

  // ★ 마운트 시 step_states["6"] === "running" 이면 rendering 상태 복원
  // 다른 스텝 갔다가 돌아와도 렌더링 중 UI 유지
  useEffect(() => {
    const ss = project.step_states as Record<string, string> | null;
    if (ss?.["6"] === "running") {
      setRendering(true);
      setShowExisting(false);
    } else if (ss?.["6"] === "completed" && !result) {
      // 다른 탭에 있는 동안 완료된 경우 결과 복원
      setResult({ status: "rendered", download_url: `/assets/${project.id}/output/final_with_subtitles.mp4` });
      setPreviewBust(Date.now());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // project prop 이 업데이트될 때도 상태 동기화
  useEffect(() => {
    const ss = project.step_states as Record<string, string> | null;
    const dbState = ss?.["6"];
    if (dbState === "running" && !rendering) {
      setRendering(true);
      setShowExisting(false);
    } else if (rendering && dbState && dbState !== "running") {
      // 서버 재시작 등으로 "failed"가 된 경우 렌더링 상태 해제
      setRendering(false);
      if (dbState === "failed") {
        setError("렌더링이 중단되었습니다 (서버 재시작 등). 다시 시도해 주세요.");
      } else if (dbState === "completed" && !result) {
        setResult({ status: "rendered", download_url: `/assets/${project.id}/output/final_with_subtitles.mp4` });
        setPreviewBust(Date.now());
      }
    }
  }, [project.step_states, rendering, result, project.id]);

  const renderFinal = async () => {
    setRendering(true);
    setResult(null);
    setError(null);
    setClearError(null);
    setShowExisting(false);
    try {
      await subtitleApi.renderAsync(project.id);
      onUpdate();
    } catch (err: any) {
      setError(err?.message || "렌더링 실패");
      setRendering(false);
    }
  };

  const handleRenderComplete = useCallback(() => {
    setRendering(false);
    setPreviewBust(Date.now());
    setResult({ status: "rendered", download_url: `/assets/${project.id}/output/final_with_subtitles.mp4` });
    onUpdate();
  }, [project.id, onUpdate]);

  const handleClear = async () => {
    const ok = window.confirm("렌더링 결과를 삭제하시겠습니까?\n(최종 영상 파일이 삭제됩니다)");
    if (!ok) return;
    setClearing(true);
    setClearError(null);
    try {
      await scriptApi.clearStep(project.id, "subtitle");
      setResult(null);
      setShowExisting(false);
      setAvailableShorts([1, 2]);
      setError(null);
      setPreviewBust(0);
      onUpdate();
    } catch (err: any) {
      setClearError(err?.message || "삭제 실패");
    } finally {
      setClearing(false);
    }
  };

  const finalVideoUrl = result?.download_url
    ? `${resolveAssetUrl(result.download_url)}?t=${previewBust}`
    : showExisting
    ? existingAssetUrl
    : null;

  const previewTitle = rendering
    ? "렌더링 진행 중"
    : result
    ? "최종 결과 영상"
    : showExisting
    ? "이전 렌더링 결과 (있는 경우)"
    : "미리보기 없음";

  const hasAudio = cuts.length > 0 && cuts.every((c) => c.audio_path);
  const hasVideo = cuts.length > 0 && cuts.every((c) => c.video_path);
  const ready = hasAudio && hasVideo;
  const hasResult = !!(result || showExisting);
  const shortsFromResult = result?.shorts?.length
    ? result.shorts.map((item) => ({
        index: item.index,
        url: `${resolveAssetUrl(item.download_url)}?t=${previewBust}`,
        duration: item.duration_seconds,
        startCut: item.start_cut,
        endCut: item.end_cut,
      }))
    : availableShorts.map((index) => ({
        index,
        url: `${assetUrl(project.id, `output/shorts/short_${index}.mp4`)}?t=${previewBust}`,
        duration: undefined,
        startCut: undefined,
        endCut: undefined,
      }));

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {/* 고정 헤더 */}
      <div className="flex-shrink-0 pb-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-accent-secondary">
            <Film size={20} />
            <h2 className="text-lg font-semibold">최종 렌더링</h2>
          </div>
          <div className="flex items-center gap-2">
            {hasResult && !rendering && (
              <LoadingButton
                onClick={handleClear}
                loading={clearing}
                icon={<Trash2 size={14} />}
                variant="danger"
                disabled={rendering || clearing}
              >
                삭제
              </LoadingButton>
            )}
            <LoadingButton
              onClick={renderFinal}
              loading={rendering}
              icon={<Play size={14} />}
              variant="primary"
              disabled={!ready || rendering}
            >
              {result && !rendering ? "다시 렌더링" : "최종 렌더링"}
            </LoadingButton>
          </div>
        </div>
      </div>

      {/* 스크롤 영역 */}
      <div className="flex-1 overflow-y-auto space-y-4">

      {!ready && (
        <div className="bg-accent-warning/10 border border-accent-warning/40 rounded-lg p-3 text-xs text-accent-warning flex items-center gap-2">
          <AlertCircle size={14} />
          먼저 음성과 영상 단계를 끝내야 최종 렌더링을 할 수 있습니다.
          {!hasAudio && <span>· 음성 누락</span>}
          {!hasVideo && <span>· 영상 누락</span>}
        </div>
      )}

      <div className="bg-bg-secondary border border-border rounded-lg p-5 space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-medium text-gray-300 flex items-center gap-2">
              <Headphones size={14} className="text-accent-secondary" />
              렌더링 BGM
            </h3>
            <p className="text-[11px] text-gray-500 mt-1">
              최종 렌더 직전에 생성/믹스됩니다. 숏츠는 BGM이 들어간 최종본에서 잘립니다.
            </p>
          </div>
          <label className="flex items-center gap-2 text-xs text-gray-300">
            <input
              type="checkbox"
              checked={Boolean(bgmConfig.bgm_enabled)}
              onChange={(e) => {
                patchBgmConfig({ bgm_enabled: e.target.checked });
                void saveBgmConfig({ bgm_enabled: e.target.checked });
              }}
              disabled={savingBgm || rendering}
            />
            사용
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <input
            ref={bgmInputRef}
            type="file"
            accept="audio/*,.mp3,.wav,.m4a,.aac,.ogg,.flac"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0] || null;
              handleBgmUpload(f);
              e.target.value = "";
            }}
          />
          <button
            type="button"
            onClick={() => bgmInputRef.current?.click()}
            disabled={uploadingBgm || generatingBgm || rendering}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded border border-border text-sm text-gray-300 hover:border-gray-500 disabled:opacity-50"
          >
            <Upload size={13} />
            {uploadingBgm ? "업로드 중..." : "오디오 업로드"}
          </button>
          <button
            type="button"
            onClick={handleBgmGenerate}
            disabled={uploadingBgm || generatingBgm || rendering}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded border border-accent-primary/40 text-sm text-accent-primary hover:bg-accent-primary/10 disabled:opacity-50"
          >
            <Headphones size={13} />
            {generatingBgm ? "생성 중..." : "AI 생성"}
          </button>
          {bgmConfig.bgm_path && (
            <>
              <span
                className="text-xs text-gray-500 truncate max-w-[360px]"
                title={bgmConfig.bgm_path}
              >
                {bgmConfig.bgm_path}
              </span>
              <button
                type="button"
                onClick={handleBgmDelete}
                disabled={rendering}
                className="inline-flex items-center gap-1 px-2 py-1 rounded border border-red-500/30 text-xs text-red-400 hover:bg-red-500/10 disabled:opacity-50"
              >
                <Trash2 size={12} />
                삭제
              </button>
            </>
          )}
        </div>

        <div>
          <label className="text-xs text-gray-500">생성 프롬프트</label>
          <input
            type="text"
            value={bgmConfig.bgm_style_prompt || ""}
            onChange={(e) => patchBgmConfig({ bgm_style_prompt: e.target.value })}
            onBlur={() => saveBgmConfig()}
            placeholder="예: calm historical documentary, orchestral, no vocals"
            className="mt-1 w-full bg-bg-primary border border-border rounded px-3 py-2 text-sm text-gray-200 outline-none focus:border-accent-primary/50"
            disabled={rendering}
          />
          {bgmConfig.bgm_prompt_used && (
            <p className="mt-1 text-[11px] text-gray-600 truncate" title={bgmConfig.bgm_prompt_used}>
              마지막 생성: {bgmConfig.bgm_prompt_used}
            </p>
          )}
        </div>

        <div className="grid grid-cols-[120px_1fr_56px] items-center gap-3">
          <span className="text-xs text-gray-500">볼륨</span>
          <input
            type="range"
            min={0}
            max={0.4}
            step={0.01}
            value={Number(bgmConfig.bgm_volume ?? 0.24)}
            onChange={(e) => patchBgmConfig({ bgm_volume: Number(e.target.value) })}
            onMouseUp={() => saveBgmConfig()}
            onTouchEnd={() => saveBgmConfig()}
            className="w-full"
            disabled={rendering}
          />
          <span className="text-xs font-mono text-gray-400 text-right">
            {Math.round(Number(bgmConfig.bgm_volume ?? 0.24) * 100)}%
          </span>
        </div>
      </div>

      {/* 백그라운드 렌더링 진행 게이지 */}
      <GenerationTimer
        projectId={project.id}
        step="render"
        label="최종 렌더링 중..."
        onComplete={handleRenderComplete}
      />

      {/* 미리보기 / 진행 / 결과 패널 */}
      <div className="bg-bg-secondary border border-border rounded-lg p-5">
        <h3 className="text-sm font-medium text-gray-300 mb-3">{previewTitle}</h3>

        <div className="bg-black rounded-lg aspect-video max-w-2xl mx-auto relative overflow-hidden flex items-center justify-center">
          {!rendering && finalVideoUrl && (
            <video
              key={finalVideoUrl}
              src={finalVideoUrl}
              controls
              className="w-full h-full object-contain bg-black"
              onError={() => {
                if (showExisting && !result) setShowExisting(false);
              }}
            />
          )}
          {rendering && (
            <div className="flex flex-col items-center gap-3 text-gray-200">
              <div className="w-10 h-10 border-4 border-accent-secondary border-t-transparent rounded-full animate-spin" />
              <p className="text-sm font-medium">렌더링 중...</p>
            </div>
          )}
          {!rendering && !finalVideoUrl && (
            <div className="text-xs text-gray-600">
              아직 렌더링된 영상이 없습니다. 상단 "최종 렌더링" 버튼을 눌러 시작하세요.
            </div>
          )}
        </div>

        {result && !rendering && (
          <div className="mt-4 flex flex-wrap items-center justify-center gap-4">
            <div className="flex items-center gap-2 text-green-300 text-sm">
              <CheckCircle2 size={16} />
              <span>렌더링 완료</span>
            </div>
            {typeof result.elapsed_seconds === "number" && (
              <span className="text-xs text-gray-400">소요 시간: {result.elapsed_seconds}초</span>
            )}
            {typeof result.size === "number" && (
              <span className="text-xs text-gray-400">
                파일 크기: {(result.size / (1024 * 1024)).toFixed(1)} MB
              </span>
            )}
            {finalVideoUrl && (
              <a
                href={finalVideoUrl}
                download="final_with_subtitles.mp4"
                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md text-xs bg-green-700/30 hover:bg-green-700/50 border border-green-600/50 text-green-200 transition-colors"
              >
                <Download size={12} /> 최종 영상 다운로드
              </a>
            )}
          </div>
        )}

        {error && (
          <div className="mt-3 text-xs text-accent-danger flex items-center gap-1 justify-center">
            <AlertCircle size={12} /> {error}
          </div>
        )}
        {clearError && (
          <div className="mt-3 text-xs text-accent-danger flex items-center gap-1 justify-center">
            <AlertCircle size={12} /> {clearError}
          </div>
        )}
      </div>

      {hasResult && !rendering && shortsFromResult.length > 0 && (
        <div className="bg-bg-secondary border border-border rounded-lg p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-medium text-gray-300">숏츠 결과</h3>
            <span className="text-xs text-gray-500">자동 추출 9:16</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {shortsFromResult.map((short) => (
              <div
                key={`${short.index}-${short.url}`}
                className="rounded-lg border border-border bg-bg-primary/60 p-3"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="text-sm text-gray-200 font-medium">
                    숏츠 {short.index}
                    {short.startCut && short.endCut && (
                      <span className="ml-2 text-xs text-gray-500">
                        컷 {short.startCut}-{short.endCut}
                      </span>
                    )}
                  </div>
                  {short.duration && (
                    <span className="text-xs text-gray-500">{Math.round(short.duration)}초</span>
                  )}
                </div>
                <div className="bg-black rounded-md aspect-[9/16] max-h-[360px] mx-auto overflow-hidden">
                  <video
                    src={short.url}
                    controls
                    className="w-full h-full object-contain bg-black"
                    onError={() => {
                      setAvailableShorts((prev) => prev.filter((idx) => idx !== short.index));
                    }}
                  />
                </div>
                <div className="mt-3 flex justify-center">
                  <a
                    href={short.url}
                    download={`short_${short.index}.mp4`}
                    className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md text-xs bg-green-700/30 hover:bg-green-700/50 border border-green-600/50 text-green-200 transition-colors"
                  >
                    <Download size={12} /> 숏츠 다운로드
                  </a>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 전체 다운로드 */}
      <div className="flex justify-end">
        <a
          href={downloadUrls.all(project.id)}
          className="px-4 py-2 rounded-lg text-sm bg-bg-secondary border border-border hover:bg-bg-tertiary text-white flex items-center gap-2 transition-colors"
        >
          <Download size={14} /> 전체 다운로드
        </a>
      </div>

      </div>{/* 스크롤 영역 끝 */}
    </div>
  );
}
