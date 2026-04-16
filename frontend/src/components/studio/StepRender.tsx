"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { Film, Download, CheckCircle2, AlertCircle, Play, Trash2 } from "lucide-react";
import LoadingButton from "@/components/common/LoadingButton";
import GenerationTimer from "@/components/common/GenerationTimer";
import { subtitleApi, scriptApi, downloadUrls, resolveAssetUrl, ASSET_BASE, type Project, type Cut } from "@/lib/api";

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

  const existingAssetUrl = `${ASSET_BASE}/assets/${project.id}/output/final_with_subtitles.mp4`;
  const [showExisting, setShowExisting] = useState(true);

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
