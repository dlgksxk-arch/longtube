"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  BarChart3,
  ChevronDown,
  Eye,
  FileVideo,
  FolderOpen,
  Loader2,
  TrendingUp,
  ThumbsUp,
  MessageSquare,
  RefreshCw,
  Trash2,
  Upload as UploadIcon,
} from "lucide-react";
import {
  assetUrl,
  projectsApi,
  youtubeStudioApi,
  type GeneratedVideoArtifact,
  type Project,
  type StudioAuthStatus,
  type StudioCommentThread,
  type StudioPlaylist,
  type StudioVideoListItem,
} from "@/lib/api";

function fmtNum(n?: number | null): string {
  if (n == null) return "-";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function parseDuration(iso?: string | null): string {
  if (!iso) return "-";
  const m = /PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/.exec(iso);
  if (!m) return iso;
  const h = Number(m[1] || 0);
  const mi = Number(m[2] || 0);
  const s = Number(m[3] || 0);
  const parts: string[] = [];
  if (h) parts.push(String(h));
  parts.push(h ? String(mi).padStart(2, "0") : String(mi));
  parts.push(String(s).padStart(2, "0"));
  return parts.join(":");
}

function durationSeconds(iso?: string | null): number | null {
  if (!iso) return null;
  const m = /PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/.exec(iso);
  if (!m) return null;
  return Number(m[1] || 0) * 3600 + Number(m[2] || 0) * 60 + Number(m[3] || 0);
}

function isShortsUpload(video: StudioVideoListItem): boolean {
  const seconds = durationSeconds(video.duration);
  return video.title.toLowerCase().includes("#shorts") || (seconds != null && seconds <= 75);
}

function fmtBytes(bytes?: number | null): string {
  if (bytes == null) return "-";
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)}GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)}MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${bytes}B`;
}

function fmtDateFromSeconds(seconds?: number | null): string {
  if (!seconds) return "-";
  return new Date(seconds * 1000).toLocaleString("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtDate(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleDateString("ko-KR", { month: "2-digit", day: "2-digit" });
}

function studioHref(path: string, projectId?: string | null): string {
  const pid = (projectId || "").trim();
  return pid ? `${path}?project=${encodeURIComponent(pid)}` : path;
}

function getPresetChannelId(preset?: Project | null): number | undefined {
  const raw = preset?.config?.youtube_channel ?? preset?.config?.channel;
  const channelId =
    typeof raw === "number" ? raw : typeof raw === "string" ? Number.parseInt(raw, 10) : NaN;
  return Number.isFinite(channelId) && channelId >= 1 && channelId <= 4 ? channelId : undefined;
}

function engagementScore(video: StudioVideoListItem): number {
  return (video.view_count || 0) + (video.like_count || 0) * 10 + (video.comment_count || 0) * 25;
}

async function listAllStudioVideos(projectId: string, channelId?: number): Promise<StudioVideoListItem[]> {
  const all: StudioVideoListItem[] = [];
  let pageToken: string | undefined;
  const seenTokens = new Set<string>();

  for (let page = 0; page < 20; page += 1) {
    const res = await youtubeStudioApi.listVideos({
      maxResults: 50,
      pageToken,
      projectId,
      channelId,
    });
    all.push(...(res.items || []));

    const nextToken = res.next_page_token || undefined;
    if (!nextToken || seenTokens.has(nextToken)) break;
    seenTokens.add(nextToken);
    pageToken = nextToken;
  }

  return all;
}

function StudioDashboardPageInner() {
  const searchParams = useSearchParams();
  const requestedProjectId = (searchParams.get("project") || "").trim();

  const [presets, setPresets] = useState<Project[]>([]);
  const [authMap, setAuthMap] = useState<Record<string, StudioAuthStatus>>({});
  const [videos, setVideos] = useState<StudioVideoListItem[]>([]);
  const [generatedVideos, setGeneratedVideos] = useState<GeneratedVideoArtifact[]>([]);
  const [playlists, setPlaylists] = useState<StudioPlaylist[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploadingArtifactId, setUploadingArtifactId] = useState<string | null>(null);
  const [mutatingArtifactId, setMutatingArtifactId] = useState<string | null>(null);
  const [generatedOpen, setGeneratedOpen] = useState(true);
  const [selectedGeneratedId, setSelectedGeneratedId] = useState<string | null>(null);
  const [videoFilter, setVideoFilter] = useState<"main" | "shorts" | "all">("main");
  const [analysisTab, setAnalysisTab] = useState<"week" | "top" | "next">("week");
  const [commentVideo, setCommentVideo] = useState<StudioVideoListItem | null>(null);
  const [commentThreads, setCommentThreads] = useState<StudioCommentThread[]>([]);
  const [commentsLoading, setCommentsLoading] = useState(false);
  const [commentsError, setCommentsError] = useState<string | null>(null);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const selectedPreset = useMemo(
    () => presets.find((preset) => preset.id === requestedProjectId) || presets[0] || null,
    [presets, requestedProjectId],
  );
  const selectedProjectId = selectedPreset?.id || null;
  const selectedChannelId = getPresetChannelId(selectedPreset);
  const selectedAuth = selectedProjectId ? authMap[selectedProjectId] : null;
  const selectedGenerated =
    generatedVideos.find((item) => item.id === selectedGeneratedId) || generatedVideos[0] || null;
  const generatedStats = useMemo(
    () => ({
      uploaded: generatedVideos.filter((item) => item.uploaded).length,
      local: generatedVideos.filter((item) => !item.uploaded).length,
      projects: new Set(generatedVideos.map((item) => item.project_id)).size,
    }),
    [generatedVideos],
  );
  const groupedVideos = useMemo(() => {
    const shorts = videos.filter(isShortsUpload);
    const main = videos.filter((video) => !isShortsUpload(video));
    const visible = videoFilter === "shorts" ? shorts : videoFilter === "all" ? videos : main;
    return { main, shorts, visible };
  }, [videoFilter, videos]);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const presetRows = await projectsApi.list();
      setPresets(presetRows);
      const targetPreset =
        presetRows.find((preset) => preset.id === requestedProjectId) || presetRows[0] || null;

      const authEntries = await Promise.all(
        presetRows.map(async (preset) => {
          const presetChannelId = getPresetChannelId(preset);
          try {
            const data = await youtubeStudioApi.authStatus(preset.id, presetChannelId);
            return [preset.id, data] as const;
          } catch {
            return [preset.id, { authenticated: false, project_id: preset.id }] as const;
          }
        }),
      );
      const nextAuthMap = Object.fromEntries(authEntries) as Record<string, StudioAuthStatus>;
      setAuthMap(nextAuthMap);

      if (!targetPreset) {
        setGeneratedVideos([]);
        setVideos([]);
        setPlaylists([]);
        return;
      }

      const targetChannelId = getPresetChannelId(targetPreset);
      const generatedRes = await youtubeStudioApi.listGeneratedVideos({
        projectId: targetPreset.id,
        channelId: targetChannelId,
      });
      setGeneratedVideos(generatedRes.items || []);

      if (!nextAuthMap[targetPreset.id]?.authenticated) {
        setVideos([]);
        setPlaylists([]);
        return;
      }

      const [videoRows, playlistRes] = await Promise.all([
        listAllStudioVideos(targetPreset.id, targetChannelId),
        youtubeStudioApi.listPlaylists(targetPreset.id, targetChannelId),
      ]);
      setVideos(videoRows);
      setPlaylists(playlistRes.items || []);
    } catch (e) {
      setErr((e as Error).message);
      setVideos([]);
      setPlaylists([]);
      setGeneratedVideos([]);
    } finally {
      setLastRefreshedAt(new Date());
      setLoading(false);
    }
  }, [requestedProjectId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const id = window.setInterval(() => {
      void load();
    }, 30 * 60 * 1000);
    return () => window.clearInterval(id);
  }, [load]);

  useEffect(() => {
    if (generatedVideos.length === 0) {
      setSelectedGeneratedId(null);
      return;
    }
    if (!selectedGeneratedId || !generatedVideos.some((item) => item.id === selectedGeneratedId)) {
      setSelectedGeneratedId(generatedVideos[0].id);
    }
  }, [generatedVideos, selectedGeneratedId]);

  const totals = useMemo(
    () =>
      videos.reduce(
        (acc, v) => {
          acc.views += v.view_count || 0;
          acc.likes += v.like_count || 0;
          acc.comments += v.comment_count || 0;
          return acc;
        },
        { views: 0, likes: 0, comments: 0 },
      ),
    [videos],
  );
  const analytics = useMemo(() => {
    const now = new Date();
    const weekStart = new Date(now);
    weekStart.setDate(now.getDate() - 7);

    const publishedThisWeek = videos.filter((video) => {
      if (!video.published_at) return false;
      const date = new Date(video.published_at);
      return !Number.isNaN(date.getTime()) && date >= weekStart;
    });
    const topByViews = [...videos].sort((a, b) => (b.view_count || 0) - (a.view_count || 0)).slice(0, 5);
    const topByComments = [...videos].sort((a, b) => (b.comment_count || 0) - (a.comment_count || 0)).slice(0, 5);
    const topByScore = [...videos].sort((a, b) => engagementScore(b) - engagementScore(a)).slice(0, 5);
    const weekViews = publishedThisWeek.reduce((sum, video) => sum + (video.view_count || 0), 0);
    const weekComments = publishedThisWeek.reduce((sum, video) => sum + (video.comment_count || 0), 0);
    const weekLikes = publishedThisWeek.reduce((sum, video) => sum + (video.like_count || 0), 0);
    const weekShorts = publishedThisWeek.filter(isShortsUpload);
    const weekMain = publishedThisWeek.filter((video) => !isShortsUpload(video));
    const avgViews = videos.length ? Math.round(totals.views / videos.length) : 0;
    const weekAvgViews = publishedThisWeek.length ? Math.round(weekViews / publishedThisWeek.length) : 0;
    const strongest = topByScore[0] || null;
    const strongestIsShorts = strongest ? isShortsUpload(strongest) : false;
    const shortsViews = groupedVideos.shorts.reduce((sum, video) => sum + (video.view_count || 0), 0);
    const mainViews = groupedVideos.main.reduce((sum, video) => sum + (video.view_count || 0), 0);

    const recommendations: string[] = [];
    if (strongest) {
      recommendations.push(
        `${strongestIsShorts ? "Shorts" : "본영상"}에서 "${strongest.title}" 반응이 가장 좋습니다. 같은 소재를 후속편/반대 관점/비하인드로 2~3개 더 뽑는 게 좋습니다.`,
      );
    }
    if (weekAvgViews < avgViews && videos.length > 0) {
      recommendations.push("이번 주 평균 조회수가 전체 평균보다 낮습니다. 제목 첫 20자와 썸네일 문구를 더 직접적인 갈등/비밀/반전 중심으로 조정하세요.");
    } else if (publishedThisWeek.length > 0) {
      recommendations.push("이번 주 평균 반응은 나쁘지 않습니다. 지금은 새 포맷을 크게 흔들기보다 잘 나온 제목 구조를 반복 실험하는 쪽이 좋습니다.");
    }
    if (weekComments === 0 && publishedThisWeek.length > 0) {
      recommendations.push("댓글이 거의 없습니다. 설명 첫 줄이나 고정 댓글에 질문형 문장을 넣어서 선택지를 던지는 방식으로 반응을 유도하세요.");
    } else if (weekComments > 0) {
      recommendations.push("댓글이 붙은 영상은 다음 영상 주제 후보로 따로 빼두세요. 댓글은 조회수보다 후속 기획 신호가 더 강합니다.");
    }
    if (shortsViews > mainViews && groupedVideos.shorts.length > 0) {
      recommendations.push("Shorts 조회 기여가 큽니다. Shorts는 본영상 유입용으로 제목/설명에 본편 키워드를 더 선명하게 연결하세요.");
    }

    return {
      publishedThisWeek,
      topByViews,
      topByComments,
      topByScore,
      weekViews,
      weekComments,
      weekLikes,
      weekShorts,
      weekMain,
      avgViews,
      weekAvgViews,
      recommendations,
    };
  }, [groupedVideos.main, groupedVideos.shorts, totals.views, videos]);

  const handleUploadGenerated = useCallback(
    async (artifact: GeneratedVideoArtifact) => {
      if (!selectedProjectId || !selectedAuth?.authenticated) return;
      setUploadingArtifactId(artifact.id);
      setErr(null);
      try {
        await youtubeStudioApi.uploadGeneratedVideo(
          {
            project_id: artifact.project_id,
            relative_path: artifact.relative_path,
            title: artifact.project_title || artifact.topic || artifact.filename,
            description: artifact.topic || "",
            tags: artifact.kind === "shorts" ? ["Shorts"] : [],
            privacy_status: "private",
          },
          { projectId: selectedProjectId, channelId: selectedChannelId },
        );
        await load();
      } catch (e) {
        setErr((e as Error).message);
      } finally {
        setUploadingArtifactId(null);
      }
    },
    [load, selectedAuth?.authenticated, selectedChannelId, selectedProjectId],
  );

  const handleOpenGeneratedFolder = useCallback(async (artifact: GeneratedVideoArtifact) => {
    setMutatingArtifactId(artifact.id);
    setErr(null);
    try {
      await youtubeStudioApi.openGeneratedVideoFolder({
        project_id: artifact.project_id,
        relative_path: artifact.relative_path,
      });
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setMutatingArtifactId(null);
    }
  }, []);

  const handleDeleteGenerated = useCallback(
    async (artifact: GeneratedVideoArtifact, deleteProject = false) => {
      const message = deleteProject
        ? `프로젝트 폴더 전체를 삭제합니다.\n\n${artifact.project_title || artifact.topic || artifact.project_id}`
        : `이 결과물 파일을 삭제합니다.\n\n${artifact.filename}`;
      if (!window.confirm(message)) return;
      setMutatingArtifactId(artifact.id);
      setErr(null);
      try {
        await youtubeStudioApi.deleteGeneratedVideo({
          project_id: artifact.project_id,
          relative_path: artifact.relative_path,
          delete_project: deleteProject,
        });
        if (selectedGeneratedId === artifact.id) setSelectedGeneratedId(null);
        await load();
      } catch (e) {
        setErr((e as Error).message);
      } finally {
        setMutatingArtifactId(null);
      }
    },
    [load, selectedGeneratedId],
  );

  const handleLoadComments = useCallback(
    async (video: StudioVideoListItem) => {
      if (!selectedProjectId || !selectedAuth?.authenticated) return;
      setCommentVideo(video);
      setCommentsLoading(true);
      setCommentsError(null);
      try {
        const res = await youtubeStudioApi.listComments(video.video_id, {
          order: "time",
          maxResults: 30,
          projectId: selectedProjectId,
          channelId: selectedChannelId,
        });
        setCommentThreads(res.items || []);
      } catch (e) {
        setCommentsError((e as Error).message);
        setCommentThreads([]);
      } finally {
        setCommentsLoading(false);
      }
    },
    [selectedAuth?.authenticated, selectedChannelId, selectedProjectId],
  );

  return (
    <div className="p-8 max-w-[1500px] space-y-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-3xl font-bold">대시보드</h2>
          <p className="text-gray-400 text-sm mt-1">프리셋별 YouTube 채널을 분리해서 관리합니다.</p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          {lastRefreshedAt && (
            <span className="text-[11px] text-gray-500">
              마지막 갱신{" "}
              {lastRefreshedAt.toLocaleTimeString("ko-KR", {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          )}
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-lg border border-border bg-bg-secondary px-3 py-2 text-sm text-gray-300 hover:border-accent-primary/50 hover:text-white disabled:opacity-50"
            title="YouTube와 로컬 생성 결과물을 다시 불러옵니다"
          >
            <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
            새로고침
          </button>
          <Link
            href={studioHref("/youtube/upload", selectedProjectId)}
            className="bg-red-600 hover:bg-red-500 text-white px-4 py-2 rounded-lg flex items-center gap-2 text-sm"
          >
            <UploadIcon size={16} /> 새 영상 업로드
          </Link>
        </div>
      </div>

      <section className="bg-bg-secondary border border-border rounded-xl p-5">
        <div className="grid grid-cols-[minmax(0,1fr)_220px] gap-4 items-start">
          <div>
            <div className="text-xs text-gray-400 mb-1">현재 프리셋</div>
            <div className="text-lg font-semibold truncate" title={selectedPreset?.title || ""}>
              {selectedPreset?.title || "프리셋 없음"}
            </div>
            {selectedPreset && (
              <div className="mt-1 text-[11px] text-gray-500 font-mono">{selectedPreset.id}</div>
            )}
            <div className="mt-3 text-sm text-gray-300">
              {selectedAuth?.authenticated
                ? `연결 채널: ${selectedAuth.channel_title || "연결됨"}`
                : "현재 프리셋에 YouTube OAuth 가 연결되어 있지 않습니다."}
            </div>
          </div>

          <div
            className={`rounded-lg border px-4 py-3 text-sm ${
              selectedAuth?.authenticated
                ? "border-green-500/30 bg-green-500/10 text-green-300"
                : "border-gray-600 bg-gray-700/30 text-gray-300"
            }`}
          >
            <div className="text-xs mb-1">연결 상태</div>
            <div className="font-semibold">{selectedAuth?.authenticated ? "연결됨" : "미연결"}</div>
          </div>
        </div>
      </section>

      {err && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-300 text-sm rounded p-3">
          {err}
        </div>
      )}

      <div className="grid grid-cols-4 gap-4">
        <div className="bg-bg-secondary border border-border rounded-lg p-4">
          <div className="text-xs text-gray-400 mb-1">최근 영상</div>
          <div className="text-2xl font-bold">{videos.length}</div>
        </div>
        <div className="bg-bg-secondary border border-border rounded-lg p-4">
          <div className="text-xs text-gray-400 mb-1 flex items-center gap-1">
            <Eye size={12} /> 합계 조회
          </div>
          <div className="text-2xl font-bold">{fmtNum(totals.views)}</div>
        </div>
        <div className="bg-bg-secondary border border-border rounded-lg p-4">
          <div className="text-xs text-gray-400 mb-1 flex items-center gap-1">
            <ThumbsUp size={12} /> 합계 좋아요
          </div>
          <div className="text-2xl font-bold">{fmtNum(totals.likes)}</div>
        </div>
        <div className="bg-bg-secondary border border-border rounded-lg p-4">
          <div className="text-xs text-gray-400 mb-1 flex items-center gap-1">
            <MessageSquare size={12} /> 합계 댓글
          </div>
          <div className="text-2xl font-bold">{fmtNum(totals.comments)}</div>
        </div>
      </div>

      <div className="grid grid-cols-[minmax(0,1fr)_320px] gap-6">
        <section className="min-w-0">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-sm font-semibold text-gray-300">최근 업로드</h3>
              {[
                ["main", "본영상", groupedVideos.main.length],
                ["shorts", "Shorts", groupedVideos.shorts.length],
                ["all", "전체", videos.length],
              ].map(([key, label, count]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setVideoFilter(key as "main" | "shorts" | "all")}
                  className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors ${
                    videoFilter === key
                      ? "border-accent-primary bg-accent-primary/20 text-white"
                      : "border-border bg-bg-secondary text-gray-400 hover:border-accent-primary/50 hover:text-gray-200"
                  }`}
                >
                  {label} <span className="text-gray-500">{count}</span>
                </button>
              ))}
            </div>
            <div className="flex items-center gap-3">
              <Link
                href={studioHref("/youtube/comments", selectedProjectId)}
                className="inline-flex items-center gap-1 rounded-lg border border-border bg-bg-secondary px-3 py-1.5 text-xs font-semibold text-gray-300 hover:border-accent-primary/50 hover:text-white"
              >
                <MessageSquare size={13} />
                댓글 관리
              </Link>
              <Link
                href={studioHref("/youtube/videos", selectedProjectId)}
                className="text-xs text-accent-primary hover:underline"
              >
                전체 보기
              </Link>
            </div>
          </div>
          {loading ? (
            <div className="text-gray-500 text-sm">불러오는 중...</div>
          ) : !selectedAuth?.authenticated ? (
            <div className="bg-bg-secondary border border-border rounded-lg p-6 text-sm text-gray-500">
              현재 프리셋이 연결되지 않아 영상 목록을 불러오지 않았습니다.
            </div>
          ) : videos.length === 0 ? (
            <div className="bg-bg-secondary border border-border rounded-lg p-6 text-sm text-gray-500">
              영상이 없습니다.
            </div>
          ) : groupedVideos.visible.length === 0 ? (
            <div className="bg-bg-secondary border border-border rounded-lg p-6 text-sm text-gray-500">
              이 분류에 표시할 영상이 없습니다.
            </div>
          ) : (
            <div className="grid grid-cols-2 xl:grid-cols-3 gap-4">
              {groupedVideos.visible.map((v) => {
                const shorts = isShortsUpload(v);
                return (
                  <div
                    key={v.video_id}
                    className="bg-bg-secondary border border-border rounded-lg overflow-hidden hover:border-accent-primary/50 transition-colors"
                  >
                    <Link href={studioHref(`/youtube/videos/${v.video_id}`, selectedProjectId)} className="block">
                      <div className="aspect-video bg-black relative">
                        {v.thumbnail ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={v.thumbnail} alt={v.title} className="w-full h-full object-cover" />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center text-gray-600 text-xs">
                            썸네일 없음
                          </div>
                        )}
                        <span className="absolute left-1 top-1 rounded bg-black/80 px-1.5 py-0.5 text-[10px] font-semibold text-white">
                          {shorts ? "Shorts" : "본영상"}
                        </span>
                        <span className="absolute bottom-1 right-1 bg-black/80 text-white text-[10px] px-1 rounded">
                          {parseDuration(v.duration)}
                        </span>
                      </div>
                      <div className="p-3 pb-2">
                        <div className="text-sm font-semibold line-clamp-2">{v.title}</div>
                        <div className="text-[11px] text-gray-500 mt-1 flex items-center gap-2">
                          <span>{fmtNum(v.view_count)} 조회</span>
                          <span>{v.privacy_status || "-"}</span>
                        </div>
                      </div>
                    </Link>
                    <div className="flex items-center justify-between gap-2 border-t border-border px-3 py-2">
                      <span className="text-[11px] text-gray-500">
                        댓글 {fmtNum(v.comment_count)}
                      </span>
                      <button
                        type="button"
                        onClick={() => void handleLoadComments(v)}
                        className="inline-flex items-center gap-1 rounded border border-border bg-bg-primary px-2 py-1 text-[11px] font-semibold text-gray-300 hover:border-accent-primary/50 hover:text-white"
                      >
                        <MessageSquare size={12} />
                        확인
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        <section className="space-y-4">
          <div className="bg-bg-secondary border border-border rounded-lg overflow-hidden">
            <div className="flex items-center justify-between gap-3 border-b border-border px-3 py-3">
              <div className="min-w-0">
                <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-300">
                  <MessageSquare size={14} />
                  댓글 확인
                </h3>
                <p className="mt-1 truncate text-xs text-gray-500">
                  {commentVideo ? commentVideo.title : "영상 카드의 댓글 확인을 누르세요"}
                </p>
              </div>
              {commentVideo && (
                <button
                  type="button"
                  onClick={() => void handleLoadComments(commentVideo)}
                  disabled={commentsLoading}
                  className="shrink-0 rounded border border-border bg-bg-primary px-2 py-1 text-[11px] text-gray-300 hover:border-accent-primary/50 disabled:opacity-50"
                  title="댓글 새로고침"
                >
                  <RefreshCw size={13} className={commentsLoading ? "animate-spin" : ""} />
                </button>
              )}
            </div>

            <div className="max-h-80 overflow-y-auto p-3">
              {!commentVideo ? (
                <div className="py-8 text-center text-sm text-gray-500">
                  본영상이나 Shorts 카드에서 바로 댓글을 열 수 있습니다.
                </div>
              ) : commentsLoading ? (
                <div className="flex items-center justify-center gap-2 py-8 text-sm text-gray-500">
                  <Loader2 size={15} className="animate-spin" />
                  댓글 불러오는 중...
                </div>
              ) : commentsError ? (
                <div className="rounded border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">
                  {commentsError}
                </div>
              ) : commentThreads.length === 0 ? (
                <div className="py-8 text-center text-sm text-gray-500">댓글이 없습니다.</div>
              ) : (
                <div className="space-y-3">
                  {commentThreads.map((thread) => (
                    <div key={thread.thread_id} className="rounded-lg border border-border bg-bg-primary/40 p-3">
                      <div className="flex items-center justify-between gap-2 text-[11px] text-gray-500">
                        <span className="min-w-0 truncate font-semibold text-gray-300">
                          {thread.author || "익명"}
                        </span>
                        <span className="shrink-0">
                          {thread.published_at
                            ? new Date(thread.published_at).toLocaleString("ko-KR", {
                                month: "2-digit",
                                day: "2-digit",
                                hour: "2-digit",
                                minute: "2-digit",
                              })
                            : ""}
                        </span>
                      </div>
                      <p className="mt-2 line-clamp-4 whitespace-pre-wrap break-words text-sm text-gray-200">
                        {thread.text}
                      </p>
                      <div className="mt-2 flex items-center gap-3 text-[11px] text-gray-500">
                        <span>좋아요 {thread.like_count ?? 0}</span>
                        <span>답글 {thread.total_reply_count ?? 0}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="bg-bg-secondary border border-border rounded-lg overflow-hidden">
            <button
              type="button"
              onClick={() => setGeneratedOpen((open) => !open)}
              className="w-full flex items-center justify-between gap-3 px-3 py-3 text-left hover:bg-bg-primary/30"
            >
              <span className="min-w-0">
                <span className="block text-sm font-semibold text-gray-300">생성 결과물</span>
                <span className="block text-xs text-gray-500">
                  실제 파일 {generatedVideos.length}개 · 프로젝트 {generatedStats.projects}개 · 미업로드 {generatedStats.local}개
                </span>
              </span>
              <ChevronDown
                size={16}
                className={`shrink-0 text-gray-400 transition-transform ${generatedOpen ? "rotate-180" : ""}`}
              />
            </button>

            {generatedOpen && (
              <div className="border-t border-border p-3 space-y-3">
                {loading ? (
                  <div className="text-sm text-gray-500 py-4">불러오는 중...</div>
                ) : generatedVideos.length === 0 ? (
                  <div className="text-sm text-gray-500 py-4">실제 영상 파일이 없습니다.</div>
                ) : (
                  <>
                    <div className="rounded-lg border border-border bg-black overflow-hidden">
                      {selectedGenerated ? (
                        <video
                          key={selectedGenerated.id}
                          src={assetUrl(selectedGenerated.project_id, selectedGenerated.relative_path)}
                          controls
                          preload="metadata"
                          className="w-full aspect-video bg-black"
                        />
                      ) : (
                        <div className="aspect-video flex items-center justify-center text-sm text-gray-600">
                          선택된 파일 없음
                        </div>
                      )}
                    </div>

                    {selectedGenerated && (
                      <div className="rounded-lg border border-border bg-bg-primary/40 p-2">
                        <div className="flex items-center gap-2">
                          <span className="rounded bg-gray-700 px-2 py-0.5 text-xs text-gray-300">
                            {selectedGenerated.kind === "shorts" ? "Shorts" : "Main"}
                          </span>
                          <span className="min-w-0 flex-1 truncate text-sm font-semibold text-gray-200" title={selectedGenerated.project_title || selectedGenerated.topic}>
                            {selectedGenerated.project_title || selectedGenerated.topic}
                          </span>
                        </div>
                        <div className="mt-1 truncate text-[11px] text-gray-500" title={selectedGenerated.relative_path}>
                          {selectedGenerated.label} · {selectedGenerated.filename} · {fmtBytes(selectedGenerated.size)} · {fmtDateFromSeconds(selectedGenerated.updated_at)}
                        </div>
                        <div className="mt-2 flex flex-wrap items-center gap-2">
                          <button
                            type="button"
                            onClick={() => void handleOpenGeneratedFolder(selectedGenerated)}
                            disabled={mutatingArtifactId === selectedGenerated.id}
                            className="inline-flex items-center gap-1 rounded border border-border bg-bg-secondary px-2 py-1 text-[11px] font-semibold text-gray-300 hover:border-accent-primary/50 disabled:opacity-50"
                          >
                            <FolderOpen size={12} />
                            폴더 열기
                          </button>
                          <button
                            type="button"
                            onClick={() => void handleDeleteGenerated(selectedGenerated, false)}
                            disabled={mutatingArtifactId === selectedGenerated.id}
                            className="inline-flex items-center gap-1 rounded border border-red-500/30 bg-red-500/10 px-2 py-1 text-[11px] font-semibold text-red-300 hover:bg-red-500/15 disabled:opacity-50"
                          >
                            <Trash2 size={12} />
                            파일 삭제
                          </button>
                          <button
                            type="button"
                            onClick={() => void handleDeleteGenerated(selectedGenerated, true)}
                            disabled={mutatingArtifactId === selectedGenerated.id}
                            className="inline-flex items-center gap-1 rounded border border-red-500/40 bg-red-500/15 px-2 py-1 text-[11px] font-semibold text-red-200 hover:bg-red-500/20 disabled:opacity-50"
                          >
                            <Trash2 size={12} />
                            프로젝트 삭제
                          </button>
                        </div>
                      </div>
                    )}

                    <div className="max-h-64 space-y-2 overflow-y-auto pr-1">
                      {generatedVideos.map((item) => {
                        const isUploading = uploadingArtifactId === item.id;
                        const isMutating = mutatingArtifactId === item.id;
                        const selected = selectedGenerated?.id === item.id;
                        return (
                          <div
                            key={item.id}
                            role="button"
                            tabIndex={0}
                            onClick={() => setSelectedGeneratedId(item.id)}
                            onKeyDown={(event) => {
                              if (event.key === "Enter" || event.key === " ") {
                                event.preventDefault();
                                setSelectedGeneratedId(item.id);
                              }
                            }}
                            className={`w-full rounded-lg border px-2 py-2 text-left transition-colors ${
                              selected
                                ? "border-accent-primary/70 bg-accent-primary/10"
                                : "border-border bg-bg-primary/40 hover:border-accent-primary/40"
                            }`}
                          >
                            <div className="flex items-center gap-2">
                              <FileVideo size={15} className="shrink-0 text-purple-300" />
                              <span className="rounded bg-gray-700 px-1.5 py-0.5 text-[10px] text-gray-300">
                                {item.kind === "shorts" ? "Shorts" : "Main"}
                              </span>
                              <span className="min-w-0 flex-1 truncate text-xs font-semibold text-gray-200">
                                {item.project_title || item.topic}
                              </span>
                              <span
                                className={`shrink-0 rounded border px-1.5 py-0.5 text-[10px] ${
                                  item.uploaded
                                    ? "border-green-500/30 bg-green-500/10 text-green-300"
                                    : "border-yellow-500/30 bg-yellow-500/10 text-yellow-300"
                                }`}
                              >
                                {item.uploaded ? "업로드됨" : "미업로드"}
                              </span>
                            </div>
                            <div className="mt-1 flex items-center gap-2 pl-6 text-[11px] text-gray-500">
                              <span className="min-w-0 flex-1 truncate">
                                {item.label} · {item.filename} · {fmtBytes(item.size)} · {fmtDateFromSeconds(item.updated_at)}
                              </span>
                              <button
                                type="button"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  void handleOpenGeneratedFolder(item);
                                }}
                                disabled={isMutating}
                                className="shrink-0 text-gray-400 hover:text-gray-200 disabled:opacity-40"
                                title="폴더 열기"
                              >
                                <FolderOpen size={13} />
                              </button>
                              {item.youtube_url && (
                                <a
                                  href={item.youtube_url}
                                  target="_blank"
                                  rel="noreferrer"
                                  onClick={(event) => event.stopPropagation()}
                                  className="shrink-0 text-accent-primary hover:underline"
                                >
                                  열기
                                </a>
                              )}
                              <button
                                type="button"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  void handleDeleteGenerated(item, false);
                                }}
                                disabled={isMutating}
                                className="shrink-0 text-red-300 hover:text-red-200 disabled:opacity-40"
                                title="파일 삭제"
                              >
                                <Trash2 size={13} />
                              </button>
                              {!item.uploaded && (
                                <button
                                  type="button"
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    if (!selectedAuth?.authenticated || isUploading) return;
                                    void handleUploadGenerated(item);
                                  }}
                                  disabled={!selectedAuth?.authenticated || isUploading}
                                  className={`shrink-0 rounded px-2 py-0.5 text-[11px] font-semibold ${
                                    !selectedAuth?.authenticated || isUploading
                                      ? "bg-gray-700 text-gray-500"
                                      : "bg-red-600 text-white hover:bg-red-500"
                                  }`}
                                >
                                  {isUploading ? "업로드 중..." : "업로드"}
                                </button>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </>
                )}
              </div>
            )}
          </div>

          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-gray-300">재생목록</h3>
              <Link
                href={studioHref("/youtube/playlists", selectedProjectId)}
                className="text-xs text-accent-primary hover:underline"
              >
                관리
              </Link>
            </div>
            <div className="bg-bg-secondary border border-border rounded-lg p-3 space-y-3">
              {!selectedAuth?.authenticated ? (
                <div className="text-sm text-gray-500 py-4">프리셋 연결 후 확인할 수 있습니다.</div>
              ) : loading ? (
                <div className="text-sm text-gray-500 py-4">불러오는 중...</div>
              ) : playlists.length === 0 ? (
                <div className="text-sm text-gray-500 py-4">재생목록이 없습니다.</div>
              ) : (
                playlists.slice(0, 8).map((p) => (
                  <Link
                    key={p.playlist_id}
                    href={studioHref(`/youtube/playlists/${p.playlist_id}`, selectedProjectId)}
                    className="block rounded-lg border border-border bg-bg-primary/40 px-3 py-3 hover:border-accent-primary/50 transition-colors"
                  >
                    <div className="text-sm font-semibold truncate" title={p.title}>
                      {p.title}
                    </div>
                    <div className="text-[11px] text-gray-500 mt-1">
                      {p.item_count ?? 0}개 · {p.privacy_status || "-"}
                    </div>
                  </Link>
                ))
              )}
            </div>
          </div>
        </section>
      </div>

      <section className="rounded-xl border border-border bg-bg-secondary p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="flex items-center gap-2 text-lg font-bold">
              <BarChart3 size={18} className="text-accent-primary" />
              분석
            </h3>
            <p className="mt-1 text-xs text-gray-500">
              실제 업로드 영상 {videos.length}개 기준 · 반응 점수는 조회수/좋아요/댓글을 합산합니다.
            </p>
          </div>
          <div className="flex rounded-lg border border-border bg-bg-primary p-1">
            {[
              ["week", "이번주 현황"],
              ["top", "반응 좋은 콘텐츠"],
              ["next", "앞으로 나갈 점"],
            ].map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setAnalysisTab(key as "week" | "top" | "next")}
                className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
                  analysisTab === key
                    ? "bg-accent-primary text-white"
                    : "text-gray-400 hover:bg-bg-secondary hover:text-gray-200"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {!selectedAuth?.authenticated ? (
          <div className="rounded-lg border border-border bg-bg-primary/40 p-6 text-sm text-gray-500">
            YouTube 연결 후 분석을 볼 수 있습니다.
          </div>
        ) : videos.length === 0 ? (
          <div className="rounded-lg border border-border bg-bg-primary/40 p-6 text-sm text-gray-500">
            분석할 업로드 영상이 없습니다.
          </div>
        ) : analysisTab === "week" ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 xl:grid-cols-5">
              <div className="rounded-lg border border-border bg-bg-primary/40 p-4">
                <div className="text-xs text-gray-500">이번 주 업로드</div>
                <div className="mt-1 text-2xl font-bold">{analytics.publishedThisWeek.length}</div>
              </div>
              <div className="rounded-lg border border-border bg-bg-primary/40 p-4">
                <div className="text-xs text-gray-500">본영상 / Shorts</div>
                <div className="mt-1 text-2xl font-bold">
                  {analytics.weekMain.length} / {analytics.weekShorts.length}
                </div>
              </div>
              <div className="rounded-lg border border-border bg-bg-primary/40 p-4">
                <div className="text-xs text-gray-500">이번 주 조회수</div>
                <div className="mt-1 text-2xl font-bold">{fmtNum(analytics.weekViews)}</div>
              </div>
              <div className="rounded-lg border border-border bg-bg-primary/40 p-4">
                <div className="text-xs text-gray-500">좋아요 / 댓글</div>
                <div className="mt-1 text-2xl font-bold">
                  {fmtNum(analytics.weekLikes)} / {fmtNum(analytics.weekComments)}
                </div>
              </div>
              <div className="rounded-lg border border-border bg-bg-primary/40 p-4">
                <div className="text-xs text-gray-500">평균 조회수</div>
                <div className="mt-1 text-2xl font-bold">{fmtNum(analytics.weekAvgViews)}</div>
              </div>
            </div>

            <div className="rounded-lg border border-border bg-bg-primary/40 p-4">
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-gray-300">
                <TrendingUp size={14} />
                이번 주 업로드
              </div>
              {analytics.publishedThisWeek.length === 0 ? (
                <div className="text-sm text-gray-500">이번 주에 공개된 영상이 없습니다.</div>
              ) : (
                <div className="divide-y divide-border">
                  {analytics.publishedThisWeek.slice(0, 8).map((video) => (
                    <div key={video.video_id} className="flex items-center gap-3 py-2 text-sm">
                      <span className="w-14 shrink-0 text-xs text-gray-500">{fmtDate(video.published_at)}</span>
                      <span className="shrink-0 rounded bg-gray-700 px-2 py-0.5 text-[11px] text-gray-300">
                        {isShortsUpload(video) ? "Shorts" : "본영상"}
                      </span>
                      <span className="min-w-0 flex-1 truncate font-semibold">{video.title}</span>
                      <span className="shrink-0 text-xs text-gray-500">
                        {fmtNum(video.view_count)} 조회 · 댓글 {fmtNum(video.comment_count)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ) : analysisTab === "top" ? (
          <div className="grid gap-4 xl:grid-cols-3">
            {[
              ["조회수 TOP", analytics.topByViews],
              ["댓글 TOP", analytics.topByComments],
              ["종합 반응 TOP", analytics.topByScore],
            ].map(([title, rows]) => (
              <div key={title as string} className="rounded-lg border border-border bg-bg-primary/40 p-4">
                <h4 className="mb-3 text-sm font-semibold text-gray-300">{title as string}</h4>
                <div className="space-y-2">
                  {(rows as StudioVideoListItem[]).map((video, index) => (
                    <Link
                      key={video.video_id}
                      href={studioHref(`/youtube/videos/${video.video_id}`, selectedProjectId)}
                      className="block rounded-lg border border-border bg-bg-secondary px-3 py-2 hover:border-accent-primary/50"
                    >
                      <div className="flex items-center gap-2">
                        <span className="rounded bg-accent-primary/20 px-2 py-0.5 text-[11px] font-bold text-accent-primary">
                          #{index + 1}
                        </span>
                        <span className="min-w-0 flex-1 truncate text-sm font-semibold">{video.title}</span>
                      </div>
                      <div className="mt-1 text-[11px] text-gray-500">
                        {isShortsUpload(video) ? "Shorts" : "본영상"} · {fmtNum(video.view_count)} 조회 · 좋아요{" "}
                        {fmtNum(video.like_count)} · 댓글 {fmtNum(video.comment_count)}
                      </div>
                    </Link>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
            <div className="rounded-lg border border-border bg-bg-primary/40 p-4">
              <h4 className="mb-3 text-sm font-semibold text-gray-300">다음 제작 방향</h4>
              <div className="space-y-3">
                {analytics.recommendations.map((item) => (
                  <div key={item} className="rounded-lg border border-border bg-bg-secondary p-3 text-sm text-gray-200">
                    {item}
                  </div>
                ))}
              </div>
            </div>
            <div className="rounded-lg border border-border bg-bg-primary/40 p-4">
              <h4 className="mb-3 text-sm font-semibold text-gray-300">운영 체크</h4>
              <div className="space-y-2 text-sm text-gray-300">
                <div className="flex justify-between gap-3">
                  <span className="text-gray-500">전체 평균 조회수</span>
                  <span className="font-semibold">{fmtNum(analytics.avgViews)}</span>
                </div>
                <div className="flex justify-between gap-3">
                  <span className="text-gray-500">이번 주 평균 조회수</span>
                  <span className="font-semibold">{fmtNum(analytics.weekAvgViews)}</span>
                </div>
                <div className="flex justify-between gap-3">
                  <span className="text-gray-500">본영상 수</span>
                  <span className="font-semibold">{groupedVideos.main.length}</span>
                </div>
                <div className="flex justify-between gap-3">
                  <span className="text-gray-500">Shorts 수</span>
                  <span className="font-semibold">{groupedVideos.shorts.length}</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

export default function StudioDashboardPage() {
  return (
    <Suspense fallback={<div className="p-8 text-sm text-gray-500">불러오는 중...</div>}>
      <StudioDashboardPageInner />
    </Suspense>
  );
}
