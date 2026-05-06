"use client";

import { useEffect, useRef, useState } from "react";
import { Clock, Loader2, RefreshCw } from "lucide-react";
import { assetUrl, modelsApi, oneclickApi, type ModelInfo, type OneClickTask } from "@/lib/api";

/** v1.1.53: 썸네일 패널 — 실시간 3단계 표시 */
export function ThumbnailPanel({ task }: { task: OneClickTask }) {
  const pid = task.project_id;
  const [imageModels, setImageModels] = useState<ModelInfo[]>([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [regenerating, setRegenerating] = useState(false);
  const [thumbKey, setThumbKey] = useState(0);

  const thumbStatus = task.thumbnail_status || "waiting";
  const thumbUrl = pid ? `${assetUrl(pid, "output/thumbnail.png")}?v=${thumbKey}` : "";

  const prevStatusRef = useRef(thumbStatus);
  useEffect(() => {
    if (prevStatusRef.current !== "done" && thumbStatus === "done") {
      setThumbKey((k) => k + 1);
    }
    prevStatusRef.current = thumbStatus;
  }, [thumbStatus]);

  useEffect(() => {
    modelsApi.listImage().then((r) => setImageModels(r.models || []));
  }, []);

  useEffect(() => {
    setSelectedModel(task.models?.thumbnail || task.models?.image || "");
  }, [task.models?.thumbnail, task.models?.image]);

  const [regenError, setRegenError] = useState<string | null>(null);

  const handleRegenerate = async () => {
    setRegenerating(true);
    setRegenError(null);
    try {
      await oneclickApi.regenerateThumbnail(task.task_id, selectedModel || undefined);
      setThumbKey((k) => k + 1);
    } catch (e: any) {
      const detail = e?.message || String(e) || "알 수 없는 오류";
      console.error("썸네일 재생성 실패:", detail);
      setRegenError(detail);
    } finally {
      setRegenerating(false);
    }
  };

  return (
    <div className="bg-bg-secondary border border-border rounded-xl p-5 flex-shrink-0">
      <h3 className="text-base font-bold text-gray-100 mb-4">썸네일</h3>

      <div className="relative w-full aspect-video bg-black/30 rounded-lg overflow-hidden mb-4">
        {regenerating ? (
          <div className="flex flex-col items-center justify-center h-full gap-3">
            <Loader2 size={28} className="animate-spin text-accent-primary" />
            <span className="text-sm text-gray-400">썸네일 재생성 중...</span>
          </div>
        ) : regenError ? (
          <div className="flex flex-col items-center justify-center h-full gap-2 px-4">
            <span className="text-sm text-red-400 font-semibold">썸네일 재생성 실패</span>
            <span className="text-sm text-red-300/70 text-center leading-relaxed max-h-20 overflow-y-auto">
              {regenError}
            </span>
          </div>
        ) : thumbStatus === "done" || prevStatusRef.current === "done" ? (
          <img
            key={thumbKey}
            src={thumbUrl}
            alt="thumbnail"
            className="w-full h-full object-cover"
            onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
          />
        ) : thumbStatus === "generating" ? (
          <div className="flex flex-col items-center justify-center h-full gap-3">
            <Loader2 size={28} className="animate-spin text-accent-primary" />
            <span className="text-sm text-gray-400">썸네일 생성 중...</span>
          </div>
        ) : thumbStatus === "failed" ? (
          <div className="flex flex-col items-center justify-center h-full gap-2 px-4">
            <span className="text-sm text-red-400 font-semibold">썸네일 생성 실패</span>
            {task.thumbnail_error && (
              <span className="text-sm text-red-300/70 text-center leading-relaxed max-h-20 overflow-y-auto">
                {task.thumbnail_error}
              </span>
            )}
            <button
              onClick={handleRegenerate}
              className="text-sm text-accent-primary hover:underline mt-1"
            >
              다시 시도
            </button>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full gap-3">
            <Clock size={20} className="text-gray-600" />
            <span className="text-sm text-gray-600">대본 생성 완료 후 자동 생성</span>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        <select
          value={selectedModel}
          onChange={(e) => setSelectedModel(e.target.value)}
          className="flex-1 text-sm bg-bg-primary text-gray-300 border border-border rounded-lg px-3 py-2 outline-none"
        >
          {imageModels.map((m) => (
            <option key={m.id} value={m.id}>{m.name || m.id}</option>
          ))}
        </select>
        <button
          onClick={handleRegenerate}
          disabled={regenerating || !pid || thumbStatus === "generating"}
          className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-lg bg-accent-primary/15 text-accent-primary border border-accent-primary/30 hover:bg-accent-primary/25 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <RefreshCw size={13} className={regenerating ? "animate-spin" : ""} />
          {regenerating ? "생성 중..." : "재생성"}
        </button>
      </div>
    </div>
  );
}
