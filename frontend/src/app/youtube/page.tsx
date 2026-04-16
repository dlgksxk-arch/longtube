"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Film, ListMusic, Eye, ThumbsUp, MessageSquare, Upload as UploadIcon } from "lucide-react";
import {
  youtubeStudioApi,
  type StudioVideoListItem,
  type StudioPlaylist,
} from "@/lib/api";

// v1.1.31: Studio 대시보드 — 최근 업로드 + 재생목록 요약.

function fmtNum(n?: number | null): string {
  if (n == null) return "-";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
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

export default function StudioDashboardPage() {
  const [videos, setVideos] = useState<StudioVideoListItem[]>([]);
  const [playlists, setPlaylists] = useState<StudioPlaylist[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setErr(null);
      try {
        const [v, p] = await Promise.all([
          youtubeStudioApi.listVideos({ maxResults: 6 }),
          youtubeStudioApi.listPlaylists(),
        ]);
        setVideos(v.items || []);
        setPlaylists(p.items || []);
      } catch (e) {
        setErr((e as Error).message);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const totals = videos.reduce(
    (acc, v) => {
      acc.views += v.view_count || 0;
      acc.likes += v.like_count || 0;
      acc.comments += v.comment_count || 0;
      return acc;
    },
    { views: 0, likes: 0, comments: 0 },
  );

  return (
    <div className="p-8 max-w-6xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold">대시보드</h2>
          <p className="text-gray-400 text-sm mt-1">최근 영상과 재생목록을 한눈에 봅니다.</p>
        </div>
        <Link
          href="/youtube/upload"
          className="bg-red-600 hover:bg-red-500 text-white px-4 py-2 rounded-lg flex items-center gap-2 text-sm"
        >
          <UploadIcon size={16} /> 새 영상 업로드
        </Link>
      </div>

      {err && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-300 text-sm rounded p-3 mb-4">
          {err}
        </div>
      )}

      {/* 요약 카드 (최근 6편 기준) */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        <div className="bg-bg-secondary border border-border rounded-lg p-4">
          <div className="text-xs text-gray-400 mb-1 flex items-center gap-1"><Film size={12} /> 최근 영상</div>
          <div className="text-2xl font-bold">{videos.length}</div>
        </div>
        <div className="bg-bg-secondary border border-border rounded-lg p-4">
          <div className="text-xs text-gray-400 mb-1 flex items-center gap-1"><Eye size={12} /> 합계 조회</div>
          <div className="text-2xl font-bold">{fmtNum(totals.views)}</div>
        </div>
        <div className="bg-bg-secondary border border-border rounded-lg p-4">
          <div className="text-xs text-gray-400 mb-1 flex items-center gap-1"><ThumbsUp size={12} /> 합계 좋아요</div>
          <div className="text-2xl font-bold">{fmtNum(totals.likes)}</div>
        </div>
        <div className="bg-bg-secondary border border-border rounded-lg p-4">
          <div className="text-xs text-gray-400 mb-1 flex items-center gap-1"><MessageSquare size={12} /> 합계 댓글</div>
          <div className="text-2xl font-bold">{fmtNum(totals.comments)}</div>
        </div>
      </div>

      {/* 최근 영상 */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-300">최근 업로드</h3>
          <Link href="/youtube/videos" className="text-xs text-accent-primary hover:underline">전체 보기 →</Link>
        </div>
        {loading ? (
          <div className="text-gray-500 text-sm">불러오는 중...</div>
        ) : videos.length === 0 ? (
          <div className="text-gray-500 text-sm">영상이 없습니다.</div>
        ) : (
          <div className="grid grid-cols-3 gap-4">
            {videos.map((v) => (
              <Link
                key={v.video_id}
                href={`/youtube/videos/${v.video_id}`}
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
                    <span>· {v.privacy_status || "-"}</span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* 재생목록 */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-300">재생목록</h3>
          <Link href="/youtube/playlists" className="text-xs text-accent-primary hover:underline">관리 →</Link>
        </div>
        {loading ? (
          <div className="text-gray-500 text-sm">불러오는 중...</div>
        ) : playlists.length === 0 ? (
          <div className="text-gray-500 text-sm">재생목록이 없습니다.</div>
        ) : (
          <div className="grid grid-cols-4 gap-3">
            {playlists.slice(0, 8).map((p) => (
              <Link
                key={p.playlist_id}
                href={`/youtube/playlists/${p.playlist_id}`}
                className="bg-bg-secondary border border-border rounded-lg p-3 hover:border-accent-primary/50 transition-colors"
              >
                <div className="flex items-center gap-2 mb-1">
                  <ListMusic size={14} className="text-accent-secondary" />
                  <span className="text-sm font-semibold truncate" title={p.title}>{p.title}</span>
                </div>
                <div className="text-[11px] text-gray-500">
                  {p.item_count ?? 0} 항목 · {p.privacy_status || "-"}
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
