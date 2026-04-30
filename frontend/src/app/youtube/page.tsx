"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  ChevronDown,
  Eye,
  ExternalLink,
  FileVideo,
  FolderOpen,
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

export default function StudioDashboardPage() {
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

      const [videoRes, playlistRes] = await Promise.all([
        youtubeStudioApi.listVideos({
          maxResults: 12,
          projectId: targetPreset.id,
          channelId: targetChannelId,
        }),
        youtubeStudioApi.listPlaylists(targetPreset.id, targetChannelId),
      ]);
      setVideos(videoRes.items || []);
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

  return (
    <div className="p-8 max-w-7xl space-y-8">
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
        <section>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-300">최근 업로드</h3>
            <Link
              href={studioHref("/youtube/videos", selectedProjectId)}
              className="text-xs text-accent-primary hover:underline"
            >
              전체 보기
            </Link>
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
          ) : (
            <div className="grid grid-cols-2 xl:grid-cols-3 gap-4">
              {videos.map((v) => (
                <Link
                  key={v.video_id}
                  href={studioHref(`/youtube/videos/${v.video_id}`, selectedProjectId)}
                  className="bg-bg-secondary border border-border rounded-lg overflow-hidden hover:border-accent-primary/50 transition-colors"
                >
                  <div className="aspect-video bg-black relative">
                    {v.thumbnail ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={v.thumbnail} alt={v.title} className="w-full h-full object-cover" />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-gray-600 text-xs">
                        썸네일 없음
                      </div>
                    )}
                    <span className="absolute bottom-1 right-1 bg-black/80 text-white text-[10px] px-1 rounded">
                      {parseDuration(v.duration)}
                    </span>
                  </div>
                  <div className="p-3">
                    <div className="text-sm font-semibold line-clamp-2">{v.title}</div>
                    <div className="text-[11px] text-gray-500 mt-1 flex items-center gap-2">
                      <span>{fmtNum(v.view_count)} 조회</span>
                      <span>{v.privacy_status || "-"}</span>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </section>

        <section className="space-y-4">
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
    </div>
  );
}
