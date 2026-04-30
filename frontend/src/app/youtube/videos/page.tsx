"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  Search,
  Eye,
  ThumbsUp,
  MessageSquare,
  Trash2,
  Edit3,
  ExternalLink,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  Lock,
  Link2 as LinkIcon,
  Globe,
  Clock,
  Zap,
} from "lucide-react";
import {
  projectsApi,
  youtubeStudioApi,
  type Project,
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

function PrivacyBadge({ status, publishAt }: { status?: string | null; publishAt?: string | null }) {
  if (publishAt) {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] bg-amber-400/20 text-amber-300 px-1.5 py-0.5 rounded">
        <Clock size={10} /> 예약
      </span>
    );
  }
  if (status === "public") {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] bg-green-500/20 text-green-400 px-1.5 py-0.5 rounded">
        <Globe size={10} /> 공개
      </span>
    );
  }
  if (status === "unlisted") {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] bg-blue-500/20 text-blue-400 px-1.5 py-0.5 rounded">
        <LinkIcon size={10} /> 일부 공개
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-[10px] bg-gray-500/20 text-gray-400 px-1.5 py-0.5 rounded">
      <Lock size={10} /> 비공개
    </span>
  );
}

export default function StudioVideosPage() {
  const searchParams = useSearchParams();
  const projectId = (searchParams.get("project") || "").trim();

  const [videos, setVideos] = useState<StudioVideoListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [pageToken, setPageToken] = useState<string | null>(null);
  const [nextToken, setNextToken] = useState<string | null>(null);
  const [pageStack, setPageStack] = useState<(string | null)[]>([null]);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null);
  const [selectedChannelId, setSelectedChannelId] = useState<number | undefined>(undefined);

  const load = useCallback(
    async (token: string | null, q: string) => {
      if (!projectId) return;
      setLoading(true);
      setErr(null);
      try {
        const res = await youtubeStudioApi.listVideos({
          pageToken: token || undefined,
          query: q || undefined,
          maxResults: 25,
          projectId,
          channelId: selectedChannelId,
        });
        setVideos(res.items || []);
        setNextToken(res.next_page_token || null);
        setLastRefreshedAt(new Date());
      } catch (e) {
        setErr((e as Error).message);
      } finally {
        setLoading(false);
      }
    },
    [projectId, selectedChannelId],
  );

  useEffect(() => {
    let cancelled = false;
    setSelectedChannelId(undefined);
    if (!projectId) return;
    projectsApi
      .get(projectId)
      .then((project) => {
        if (!cancelled) setSelectedChannelId(getPresetChannelId(project));
      })
      .catch(() => {
        if (!cancelled) setSelectedChannelId(undefined);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  useEffect(() => {
    setPageStack([null]);
    setPageToken(null);
    if (!projectId) {
      setVideos([]);
      return;
    }
    load(null, "");
  }, [projectId, load]);

  useEffect(() => {
    if (!projectId) return;
    const id = window.setInterval(() => {
      void load(pageToken, query);
    }, 30 * 60 * 1000);
    return () => window.clearInterval(id);
  }, [load, pageToken, projectId, query]);

  const doSearch = () => {
    setPageStack([null]);
    setPageToken(null);
    load(null, query);
  };

  const goNext = () => {
    if (!nextToken) return;
    setPageStack((s) => [...s, nextToken]);
    setPageToken(nextToken);
    load(nextToken, query);
  };

  const goPrev = () => {
    if (pageStack.length <= 1) return;
    const stack = [...pageStack];
    stack.pop();
    const prev = stack[stack.length - 1];
    setPageStack(stack);
    setPageToken(prev);
    load(prev, query);
  };

  const onDelete = async (videoId: string, title: string) => {
    if (!confirm(`정말 삭제하시겠습니까?\n\n"${title}"\n\n복구할 수 없습니다.`)) return;
    try {
      await youtubeStudioApi.deleteVideo(videoId, projectId, selectedChannelId);
      setVideos((items) => items.filter((item) => item.video_id !== videoId));
    } catch (e) {
      alert(`삭제 실패: ${(e as Error).message}`);
    }
  };

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold">영상</h2>
          <p className="text-gray-400 text-sm mt-1">선택된 프리셋의 YouTube 영상만 관리합니다.</p>
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
            onClick={() => load(pageToken, query)}
            disabled={loading || !projectId}
            className="text-xs text-gray-400 hover:text-white flex items-center gap-1 disabled:opacity-50"
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} /> 새로고침
          </button>
        </div>
      </div>

      <div className="flex gap-2 mb-4">
        <div className="flex-1 relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && doSearch()}
            placeholder="제목으로 검색"
            className="w-full bg-bg-secondary border border-border rounded-lg pl-9 pr-3 py-2 text-sm focus:outline-none focus:border-accent-primary"
          />
        </div>
        <button
          onClick={doSearch}
          disabled={!projectId}
          className="bg-accent-primary hover:bg-purple-600 px-4 py-2 rounded-lg text-sm disabled:opacity-50"
        >
          검색
        </button>
      </div>

      {err && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-300 text-sm rounded p-3 mb-4">
          {err}
        </div>
      )}

      {!projectId ? (
        <div className="bg-bg-secondary border border-border rounded-lg p-8 text-sm text-gray-500">
          좌측에서 프리셋을 선택하십시오.
        </div>
      ) : (
        <div className="bg-bg-secondary border border-border rounded-lg overflow-hidden">
          <div className="grid grid-cols-[1fr_90px_90px_100px_100px_80px_120px_140px] text-xs text-gray-400 px-4 py-2 border-b border-border bg-bg-tertiary">
            <div>영상</div>
            <div>업로드일</div>
            <div>출처</div>
            <div className="text-right">조회</div>
            <div className="text-right">좋아요</div>
            <div className="text-right">댓글</div>
            <div>공개 상태</div>
            <div className="text-right">작업</div>
          </div>

          {loading && videos.length === 0 ? (
            <div className="p-10 text-center text-gray-500 text-sm">불러오는 중...</div>
          ) : videos.length === 0 ? (
            <div className="p-10 text-center text-gray-500 text-sm">영상이 없습니다.</div>
          ) : (
            videos.map((video) => {
              const lt = video.longtube;
              const uploadDate = lt?.uploaded_at
                ? new Date(lt.uploaded_at).toLocaleDateString("ko-KR", {
                    month: "short",
                    day: "numeric",
                  })
                : video.published_at
                  ? new Date(video.published_at).toLocaleDateString("ko-KR", {
                      month: "short",
                      day: "numeric",
                    })
                  : "-";

              return (
                <div
                  key={video.video_id}
                  className="grid grid-cols-[1fr_90px_90px_100px_100px_80px_120px_140px] items-center px-4 py-3 border-b border-border last:border-b-0 hover:bg-bg-tertiary/40"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-28 aspect-video bg-black flex-shrink-0 rounded overflow-hidden relative">
                      {video.thumbnail ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={video.thumbnail} alt={video.title} className="w-full h-full object-cover" />
                      ) : null}
                      <span className="absolute bottom-0.5 right-0.5 bg-black/80 text-white text-[10px] px-1 rounded">
                        {parseDuration(video.duration)}
                      </span>
                    </div>
                    <div className="min-w-0">
                      <div className="text-sm font-semibold truncate" title={video.title}>
                        {video.title}
                      </div>
                      <div className="text-[11px] text-gray-500 truncate">
                        {video.published_at
                          ? new Date(video.published_at).toLocaleString("ko-KR")
                          : "-"}
                      </div>
                    </div>
                  </div>

                  <div className="text-xs text-gray-400">{uploadDate}</div>

                  <div>
                    {lt ? (
                      lt.source === "oneclick" ? (
                        <span className="inline-flex items-center gap-1 text-[10px] bg-yellow-500/20 text-yellow-300 px-1.5 py-0.5 rounded">
                          <Zap size={10} /> 딸깍
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[10px] bg-sky-500/20 text-sky-300 px-1.5 py-0.5 rounded">
                          프리셋
                        </span>
                      )
                    ) : (
                      <span className="text-xs text-gray-500">외부</span>
                    )}
                  </div>

                  <div className="text-right text-xs text-gray-300">{fmtNum(video.view_count)}</div>
                  <div className="text-right text-xs text-gray-300">{fmtNum(video.like_count)}</div>
                  <div className="text-right text-xs text-gray-300">{fmtNum(video.comment_count)}</div>

                  <div>
                    <PrivacyBadge status={video.privacy_status} publishAt={video.publish_at} />
                  </div>

                  <div className="flex items-center justify-end gap-1">
                    <Link
                      href={studioHref(`/youtube/videos/${video.video_id}`, projectId)}
                      className="p-2 text-gray-400 hover:text-white"
                      title="편집"
                    >
                      <Edit3 size={14} />
                    </Link>
                    <a
                      href={`https://youtube.com/watch?v=${video.video_id}`}
                      target="_blank"
                      className="p-2 text-gray-400 hover:text-white"
                      title="YouTube에서 보기"
                    >
                      <ExternalLink size={14} />
                    </a>
                    <button
                      onClick={() => onDelete(video.video_id, video.title)}
                      className="p-2 text-gray-400 hover:text-red-400"
                      title="삭제"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}

      <div className="flex items-center justify-end gap-2 mt-4">
        <button
          onClick={goPrev}
          disabled={pageStack.length <= 1 || loading || !projectId}
          className="px-3 py-1.5 rounded border border-border text-sm text-gray-300 hover:bg-bg-secondary disabled:opacity-40 flex items-center gap-1"
        >
          <ChevronLeft size={14} /> 이전
        </button>
        <button
          onClick={goNext}
          disabled={!nextToken || loading || !projectId}
          className="px-3 py-1.5 rounded border border-border text-sm text-gray-300 hover:bg-bg-secondary disabled:opacity-40 flex items-center gap-1"
        >
          다음 <ChevronRight size={14} />
        </button>
      </div>
    </div>
  );
}
