"use client";

/**
 * v1.1.54 — 딸깍 대시보드 > 완성작 관리
 *
 * 기능:
 * - 카드 그리드 (썸네일, 제목, 업로드 상태, 날짜, 용량)
 * - 영상 미리보기 모달 (final.mp4 재생 + 컷 이미지 슬라이드)
 * - 개별/일괄 삭제 (디스크 정리)
 * - 수동 YouTube 업로드
 * - 상세 정보 패널 (비용, 소요시간, 모델, 컷 수)
 * - 필터 (전체/업로드/미업로드/실패)
 * - 전체 통계 (디스크 용량)
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Film,
  Loader2,
  ExternalLink,
  Play,
  CheckCircle2,
  XCircle,
  Upload,
  Clock,
  Filter,
  Trash2,
  X,
  ChevronLeft,
  ChevronRight,
  HardDrive,
  Zap,
  Info,
  Check,
  AlertTriangle,
} from "lucide-react";
import {
  oneclickApi,
  projectsApi,
  assetUrl,
  type OneClickTask,
  type Project,
  type TaskDetail,
  type LibraryStats,
} from "@/lib/api";

type FilterType = "all" | "uploaded" | "not_uploaded" | "failed";
type ChannelFilter = "all" | "1" | "2" | "3" | "4" | "manual";

const CH_COLORS: Record<string, string> = {
  "1": "text-blue-400 bg-blue-400/15",
  "2": "text-green-400 bg-green-400/15",
  "3": "text-amber-400 bg-amber-400/15",
  "4": "text-purple-400 bg-purple-400/15",
};

export default function LibraryPage() {
  const [tasks, setTasks] = useState<OneClickTask[]>([]);
  const [projects, setProjects] = useState<Map<string, Project>>(new Map());
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<FilterType>("all");
  const [channelFilter, setChannelFilter] = useState<ChannelFilter>("all");
  const [stats, setStats] = useState<LibraryStats | null>(null);

  // 선택 모드 (일괄 삭제)
  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // 모달
  const [detailTask, setDetailTask] = useState<OneClickTask | null>(null);
  const [detail, setDetail] = useState<TaskDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // 업로드 상태
  const [uploading, setUploading] = useState<string | null>(null);
  // 삭제 상태
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [{ tasks: t }, pList] = await Promise.all([
        oneclickApi.list(),
        projectsApi.list(),
      ]);
      const relevant = (t || []).filter(
        (tk) => tk.status === "completed" || tk.status === "failed",
      );
      relevant.sort(
        (a, b) =>
          new Date(b.finished_at || b.created_at).getTime() -
          new Date(a.finished_at || a.created_at).getTime(),
      );
      setTasks(relevant);

      const pMap = new Map<string, Project>();
      for (const p of pList || []) pMap.set(p.id, p);
      setProjects(pMap);

      // 통계
      try {
        const s = await oneclickApi.libraryStats();
        setStats(s);
      } catch {}
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
    // v1.1.58: 탭 포커스 복귀 시 자동 최신화
    const onFocus = () => { void load(); };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [load]);

  // 상세 모달 열기
  const openDetail = useCallback(async (task: OneClickTask) => {
    setDetailTask(task);
    setDetailLoading(true);
    setDetail(null);
    try {
      const d = await oneclickApi.getTaskDetail(task.task_id);
      setDetail(d);
    } catch {}
    setDetailLoading(false);
  }, []);

  const closeDetail = () => {
    setDetailTask(null);
    setDetail(null);
  };

  // 수동 업로드
  const handleUpload = useCallback(
    async (taskId: string) => {
      setUploading(taskId);
      try {
        const res = await oneclickApi.manualUpload(taskId);
        if (res.youtube_url) {
          // 로컬 프로젝트 맵 업데이트
          const task = tasks.find((t) => t.task_id === taskId);
          if (task) {
            const p = projects.get(task.project_id);
            if (p) {
              projects.set(task.project_id, { ...p, youtube_url: res.youtube_url });
              setProjects(new Map(projects));
            }
          }
          // 상세 모달 업데이트
          if (detail && detail.task_id === taskId) {
            setDetail({ ...detail, youtube_url: res.youtube_url });
          }
        }
      } catch (e: any) {
        alert(`업로드 실패: ${e?.message || e}`);
      }
      setUploading(null);
    },
    [tasks, projects, detail],
  );

  // 개별 삭제
  const handleDeleteOne = useCallback(
    async (taskId: string) => {
      if (!confirm("이 완성작을 삭제하시겠습니까?\n디스크의 영상/이미지/음성 파일도 모두 삭제됩니다.")) return;
      try {
        await oneclickApi.deleteTask(taskId);
        setTasks((prev) => prev.filter((t) => t.task_id !== taskId));
        closeDetail();
      } catch {}
    },
    [],
  );

  // 일괄 삭제
  const handleBulkDelete = useCallback(async () => {
    if (selected.size === 0) return;
    if (!confirm(`${selected.size}개 완성작을 삭제하시겠습니까?\n디스크 파일도 모두 삭제됩니다.`)) return;
    setDeleting(true);
    try {
      const res = await oneclickApi.bulkDelete(Array.from(selected));
      setTasks((prev) => prev.filter((t) => !selected.has(t.task_id)));
      setSelected(new Set());
      setSelectMode(false);
      alert(`${res.deleted}개 삭제, ${res.freed_mb}MB 확보`);
    } catch {}
    setDeleting(false);
  }, [selected]);

  // 선택 토글
  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // 필터 적용
  const filtered = tasks.filter((t) => {
    // 상태 필터
    if (filter === "failed" && t.status !== "failed") return false;
    if (filter === "uploaded") {
      const p = projects.get(t.project_id);
      if (!p?.youtube_url) return false;
    }
    if (filter === "not_uploaded") {
      const p = projects.get(t.project_id);
      if (t.status !== "completed" || !!p?.youtube_url) return false;
    }
    // v1.1.58: 채널 필터
    if (channelFilter !== "all") {
      const ch = t.channel;
      if (channelFilter === "manual") {
        if (ch) return false; // 채널 있으면 스케줄 실행
      } else {
        if ((ch || 0) !== parseInt(channelFilter, 10)) return false;
      }
    }
    return true;
  });

  const completed = tasks.filter((t) => t.status === "completed");
  const uploaded = completed.filter((t) => projects.get(t.project_id)?.youtube_url);
  const failed = tasks.filter((t) => t.status === "failed");

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 size={20} className="animate-spin text-gray-500" />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-5">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">완성작 관리</h1>
          <p className="text-xs text-gray-500 mt-1">
            {completed.length}편 완성 · {uploaded.length}편 업로드
            {stats ? ` · ${stats.total_disk_mb}MB 사용 중` : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {selectMode ? (
            <>
              <span className="text-xs text-gray-400">{selected.size}개 선택</span>
              <button
                onClick={handleBulkDelete}
                disabled={selected.size === 0 || deleting}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-accent-danger/20 text-accent-danger hover:bg-accent-danger/30 disabled:opacity-40 transition-colors"
              >
                {deleting ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
                일괄 삭제
              </button>
              <button
                onClick={() => { setSelectMode(false); setSelected(new Set()); }}
                className="px-3 py-1.5 rounded-lg text-xs font-medium bg-bg-secondary text-gray-400 border border-border hover:text-gray-200"
              >
                취소
              </button>
            </>
          ) : (
            <button
              onClick={() => setSelectMode(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-bg-secondary text-gray-400 border border-border hover:text-gray-200 transition-colors"
            >
              <Trash2 size={12} />
              선택 삭제
            </button>
          )}
        </div>
      </div>

      {/* 필터 바 */}
      <div className="flex items-center gap-4">
        <div className="flex gap-2">
          {([
            { key: "all" as FilterType, label: "전체", count: tasks.length },
            { key: "uploaded" as FilterType, label: "업로드됨", count: uploaded.length },
            { key: "not_uploaded" as FilterType, label: "미업로드", count: completed.length - uploaded.length },
            { key: "failed" as FilterType, label: "실패", count: failed.length },
          ]).map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`px-4 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                filter === f.key
                  ? "bg-accent-primary text-white"
                  : "bg-bg-secondary text-gray-400 border border-border hover:text-gray-200"
              }`}
            >
              {f.label} ({f.count})
            </button>
          ))}
        </div>
        {/* v1.1.58: 채널 필터 */}
        <div className="h-5 w-px bg-border" />
        <div className="flex gap-1.5">
          {([
            { key: "all" as ChannelFilter, label: "전체 채널", color: "text-gray-400" },
            { key: "1" as ChannelFilter, label: "CH1", color: "text-blue-400" },
            { key: "2" as ChannelFilter, label: "CH2", color: "text-green-400" },
            { key: "3" as ChannelFilter, label: "CH3", color: "text-amber-400" },
            { key: "4" as ChannelFilter, label: "CH4", color: "text-purple-400" },
            { key: "manual" as ChannelFilter, label: "수동", color: "text-gray-400" },
          ]).map((f) => (
            <button
              key={f.key}
              onClick={() => setChannelFilter(f.key)}
              className={`px-2.5 py-1 rounded text-[10px] font-bold transition-colors ${
                channelFilter === f.key
                  ? `${f.color} bg-white/10 ring-1 ring-white/20`
                  : "text-gray-600 hover:text-gray-400"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* 비어있을 때 */}
      {filtered.length === 0 ? (
        <div className="text-center text-sm text-gray-500 py-20">
          {filter === "all"
            ? "아직 완성된 작업이 없습니다."
            : "해당 조건에 맞는 항목이 없습니다."}
        </div>
      ) : (
        /* 카드 그리드 */
        <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filtered.map((task) => {
            const project = projects.get(task.project_id);
            const hasYT = !!project?.youtube_url;
            const isFailed = task.status === "failed";
            const finDate = task.finished_at ? new Date(task.finished_at) : null;
            const dateLabel = finDate
              ? `${finDate.getMonth() + 1}/${finDate.getDate()} ${String(finDate.getHours()).padStart(2, "0")}:${String(finDate.getMinutes()).padStart(2, "0")}`
              : "-";
            const isSelected = selected.has(task.task_id);

            // 썸네일 — png 우선, jpg 폴백
            const thumbPng = project ? assetUrl(project.id, "output/thumbnail.png") : null;
            const thumbJpg = project ? assetUrl(project.id, "output/thumbnail.jpg") : null;

            return (
              <div
                key={task.task_id}
                onClick={() => selectMode ? toggleSelect(task.task_id) : openDetail(task)}
                className={`bg-bg-secondary border rounded-xl overflow-hidden hover:border-white/10 transition-all group cursor-pointer relative ${
                  isSelected ? "border-accent-primary ring-1 ring-accent-primary/40" : "border-border"
                }`}
              >
                {/* 선택 체크박스 */}
                {selectMode && (
                  <div className={`absolute top-2 left-2 z-10 w-5 h-5 rounded border-2 flex items-center justify-center transition-colors ${
                    isSelected ? "bg-accent-primary border-accent-primary" : "bg-black/50 border-white/30"
                  }`}>
                    {isSelected && <Check size={12} className="text-white" />}
                  </div>
                )}

                {/* 썸네일 */}
                <div className="aspect-video bg-bg-tertiary relative flex items-center justify-center overflow-hidden">
                  {!isFailed && thumbPng ? (
                    <img
                      src={thumbPng}
                      alt=""
                      className="w-full h-full object-cover"
                      onError={(e) => {
                        const img = e.target as HTMLImageElement;
                        if (thumbJpg && img.src !== thumbJpg) {
                          img.src = thumbJpg;
                        } else {
                          img.style.display = "none";
                        }
                      }}
                    />
                  ) : null}

                  {!selectMode && (
                    <div className="absolute inset-0 flex items-center justify-center">
                      {isFailed ? (
                        <XCircle size={24} className="text-accent-danger/60" />
                      ) : (
                        <div className="w-10 h-10 rounded-full bg-white/10 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity backdrop-blur-sm">
                          <Play size={16} className="text-white/80 ml-0.5" />
                        </div>
                      )}
                    </div>
                  )}

                  {/* 컷 수 뱃지 */}
                  {task.total_cuts > 0 && (
                    <span className="absolute bottom-2 right-2 bg-black/70 text-white text-[10px] font-medium px-1.5 py-0.5 rounded">
                      {task.total_cuts}컷
                    </span>
                  )}
                </div>

                {/* 정보 */}
                <div className="p-3">
                  <h4 className="text-sm font-semibold text-gray-200 mb-1.5 line-clamp-2 leading-snug">
                    {task.title || task.topic}
                  </h4>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-[10px] text-gray-600">{dateLabel}</span>
                    {/* v1.1.58: 채널 배지 */}
                    {task.channel ? (
                      <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${CH_COLORS[String(task.channel)] || "text-gray-400 bg-gray-400/15"}`}>
                        CH{task.channel}
                      </span>
                    ) : null}
                    {isFailed ? (
                      <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-accent-danger/15 text-accent-danger">
                        실패
                      </span>
                    ) : hasYT ? (
                      <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-accent-success/15 text-accent-success">
                        업로드됨
                      </span>
                    ) : (
                      <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-amber-400/15 text-amber-400">
                        미업로드
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ───── 상세 모달 ───── */}
      {detailTask && (
        <DetailModal
          task={detailTask}
          detail={detail}
          loading={detailLoading}
          project={projects.get(detailTask.project_id) || null}
          uploading={uploading === detailTask.task_id}
          onClose={closeDetail}
          onUpload={() => handleUpload(detailTask.task_id)}
          onDelete={() => handleDeleteOne(detailTask.task_id)}
        />
      )}
    </div>
  );
}


/* ═══════════════════════════════════════════════════════════════════════
   상세 모달 — 영상 재생 + 컷 슬라이드 + 정보 + 액션
   ═══════════════════════════════════════════════════════════════════════ */

function DetailModal({
  task,
  detail,
  loading,
  project,
  uploading,
  onClose,
  onUpload,
  onDelete,
}: {
  task: OneClickTask;
  detail: TaskDetail | null;
  loading: boolean;
  project: Project | null;
  uploading: boolean;
  onClose: () => void;
  onUpload: () => void;
  onDelete: () => void;
}) {
  const [showVideo, setShowVideo] = useState(true);
  const [cutIdx, setCutIdx] = useState(0);
  const videoRef = useRef<HTMLVideoElement>(null);

  const hasVideo = detail?.has_final_video;
  const videoUrl = detail?.final_video_path && project
    ? assetUrl(project.id, detail.final_video_path)
    : null;
  const cutImages = detail?.cut_images || [];
  const hasYT = !!detail?.youtube_url;

  const formatElapsed = (sec: number | null | undefined) => {
    if (!sec) return "-";
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return m > 0 ? `${m}분 ${s}초` : `${s}초`;
  };

  const formatCost = (est: any) => {
    if (!est?.estimated_cost_krw) return "-";
    return `₩${Math.round(est.estimated_cost_krw).toLocaleString()}`;
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm" onClick={onClose}>
      <div
        className="bg-bg-primary border border-border rounded-2xl w-[900px] max-h-[85vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 헤더 */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-border">
          <h2 className="text-sm font-bold text-white truncate max-w-[600px]">
            {task.title || task.topic}
          </h2>
          <button onClick={onClose} className="p-1 rounded hover:bg-white/5">
            <X size={16} className="text-gray-400" />
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 size={20} className="animate-spin text-gray-500" />
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto">
            {/* 영상 / 이미지 뷰어 */}
            <div className="bg-black aspect-video relative">
              {/* 탭 전환 */}
              {hasVideo && cutImages.length > 0 && (
                <div className="absolute top-3 left-3 z-10 flex gap-1 bg-black/60 rounded-lg p-1 backdrop-blur-sm">
                  <button
                    onClick={() => setShowVideo(true)}
                    className={`px-3 py-1 rounded text-[10px] font-medium transition-colors ${
                      showVideo ? "bg-white/20 text-white" : "text-white/50 hover:text-white/80"
                    }`}
                  >
                    영상
                  </button>
                  <button
                    onClick={() => setShowVideo(false)}
                    className={`px-3 py-1 rounded text-[10px] font-medium transition-colors ${
                      !showVideo ? "bg-white/20 text-white" : "text-white/50 hover:text-white/80"
                    }`}
                  >
                    컷 ({cutImages.length})
                  </button>
                </div>
              )}

              {showVideo && hasVideo && videoUrl ? (
                <video
                  ref={videoRef}
                  src={videoUrl}
                  controls
                  className="w-full h-full object-contain"
                  poster={detail?.thumbnail_path && project
                    ? assetUrl(project.id, detail.thumbnail_path)
                    : undefined}
                />
              ) : cutImages.length > 0 && project ? (
                <div className="w-full h-full flex items-center justify-center relative">
                  <img
                    src={assetUrl(project.id, cutImages[cutIdx])}
                    alt={`컷 ${cutIdx + 1}`}
                    className="max-w-full max-h-full object-contain"
                  />
                  {/* 좌우 화살표 */}
                  {cutIdx > 0 && (
                    <button
                      onClick={() => setCutIdx((i) => i - 1)}
                      className="absolute left-2 top-1/2 -translate-y-1/2 w-8 h-8 rounded-full bg-black/50 flex items-center justify-center hover:bg-black/70"
                    >
                      <ChevronLeft size={16} className="text-white" />
                    </button>
                  )}
                  {cutIdx < cutImages.length - 1 && (
                    <button
                      onClick={() => setCutIdx((i) => i + 1)}
                      className="absolute right-2 top-1/2 -translate-y-1/2 w-8 h-8 rounded-full bg-black/50 flex items-center justify-center hover:bg-black/70"
                    >
                      <ChevronRight size={16} className="text-white" />
                    </button>
                  )}
                  <span className="absolute bottom-3 right-3 bg-black/60 text-white text-[10px] px-2 py-0.5 rounded">
                    {cutIdx + 1} / {cutImages.length}
                  </span>
                </div>
              ) : (
                <div className="w-full h-full flex items-center justify-center">
                  <span className="text-gray-600 text-sm">영상 또는 이미지 없음</span>
                </div>
              )}
            </div>

            {/* 정보 + 액션 */}
            <div className="p-5 space-y-4">
              {/* 상태 뱃지 + 액션 버튼 */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  {/* v1.1.58: 채널 배지 */}
                  {task.channel ? (
                    <span className={`text-[10px] font-bold px-2 py-1 rounded ${CH_COLORS[String(task.channel)] || "text-gray-400 bg-gray-400/15"}`}>
                      CH{task.channel}
                    </span>
                  ) : (
                    <span className="text-[10px] font-bold px-2 py-1 rounded text-gray-500 bg-gray-500/10">
                      수동
                    </span>
                  )}
                  {task.status === "failed" ? (
                    <span className="flex items-center gap-1 text-xs font-medium px-2 py-1 rounded bg-accent-danger/15 text-accent-danger">
                      <XCircle size={12} /> 실패
                    </span>
                  ) : hasYT ? (
                    <span className="flex items-center gap-1 text-xs font-medium px-2 py-1 rounded bg-accent-success/15 text-accent-success">
                      <CheckCircle2 size={12} /> 업로드됨
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-xs font-medium px-2 py-1 rounded bg-amber-400/15 text-amber-400">
                      <Clock size={12} /> 미업로드
                    </span>
                  )}
                  {detail?.error && (
                    <span className="text-[10px] text-accent-danger truncate max-w-[300px]">
                      {detail.error}
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  {/* YouTube 보기 */}
                  {hasYT && (
                    <a
                      href={detail!.youtube_url!}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-blue-500/15 text-blue-400 hover:bg-blue-500/25 transition-colors"
                    >
                      <ExternalLink size={12} /> YouTube
                    </a>
                  )}
                  {/* 수동 업로드 */}
                  {task.status === "completed" && !hasYT && (
                    <button
                      onClick={onUpload}
                      disabled={uploading}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-accent-primary/20 text-accent-primary hover:bg-accent-primary/30 disabled:opacity-40 transition-colors"
                    >
                      {uploading ? (
                        <Loader2 size={12} className="animate-spin" />
                      ) : (
                        <Upload size={12} />
                      )}
                      YouTube 업로드
                    </button>
                  )}
                  {/* 삭제 */}
                  <button
                    onClick={onDelete}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-accent-danger/15 text-accent-danger hover:bg-accent-danger/25 transition-colors"
                  >
                    <Trash2 size={12} /> 삭제
                  </button>
                </div>
              </div>

              {/* 상세 정보 그리드 */}
              {detail && (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <InfoCard icon={<Film size={14} />} label="컷 수" value={`${detail.total_cuts}컷`} />
                  <InfoCard icon={<Clock size={14} />} label="소요 시간" value={formatElapsed(detail.elapsed_sec)} />
                  <InfoCard icon={<Zap size={14} />} label="예상 비용" value={formatCost(detail.estimate)} />
                  <InfoCard icon={<HardDrive size={14} />} label="디스크" value={`${detail.disk_mb}MB`} />
                </div>
              )}

              {/* 모델 정보 */}
              {detail?.models && Object.keys(detail.models).length > 0 && (
                <div className="bg-bg-secondary rounded-lg p-3">
                  <p className="text-[10px] text-gray-500 mb-2 uppercase tracking-wider">사용 모델</p>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(detail.models).map(([key, val]) => (
                      <span key={key} className="text-[10px] bg-bg-tertiary text-gray-300 px-2 py-0.5 rounded">
                        {key}: <span className="text-gray-100">{val}</span>
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* 날짜 */}
              <div className="flex items-center gap-4 text-[10px] text-gray-600">
                {detail?.created_at && (
                  <span>생성: {new Date(detail.created_at).toLocaleString("ko-KR")}</span>
                )}
                {detail?.started_at && (
                  <span>시작: {new Date(detail.started_at).toLocaleString("ko-KR")}</span>
                )}
                {detail?.finished_at && (
                  <span>완료: {new Date(detail.finished_at).toLocaleString("ko-KR")}</span>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


/* ─── 작은 정보 카드 ─── */
function InfoCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="bg-bg-secondary rounded-lg p-3 flex items-center gap-2.5">
      <div className="text-gray-500">{icon}</div>
      <div>
        <p className="text-[10px] text-gray-500">{label}</p>
        <p className="text-xs font-semibold text-gray-200">{value}</p>
      </div>
    </div>
  );
}
