"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, X, Plus } from "lucide-react";
import { youtubeStudioApi, type StudioPlaylistItem } from "@/lib/api";

export default function PlaylistDetailPage() {
  const params = useParams<{ playlistId: string }>();
  const playlistId = params.playlistId;

  const [items, setItems] = useState<StudioPlaylistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [addVideoId, setAddVideoId] = useState("");

  const load = async () => {
    setLoading(true);
    setErr(null);
    try {
      const res = await youtubeStudioApi.listPlaylistItems(playlistId);
      setItems(res.items || []);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (playlistId) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playlistId]);

  const add = async () => {
    const id = addVideoId.trim();
    if (!id) return;
    try {
      await youtubeStudioApi.addPlaylistItem(playlistId, id);
      setAddVideoId("");
      load();
    } catch (e) {
      alert(`추가 실패: ${(e as Error).message}`);
    }
  };

  const remove = async (item: StudioPlaylistItem) => {
    if (!confirm(`"${item.title}" 을 재생목록에서 제거하시겠습니까?`)) return;
    try {
      await youtubeStudioApi.removePlaylistItem(playlistId, item.item_id);
      load();
    } catch (e) {
      alert(`제거 실패: ${(e as Error).message}`);
    }
  };

  return (
    <div className="p-8 max-w-4xl">
      <Link href="/youtube/playlists" className="text-xs text-gray-400 hover:text-white flex items-center gap-1 mb-4">
        <ArrowLeft size={12} /> 재생목록
      </Link>

      <h2 className="text-2xl font-bold mb-1">재생목록 항목</h2>
      <p className="text-gray-500 text-xs font-mono mb-6">{playlistId}</p>

      <div className="bg-bg-secondary border border-border rounded-lg p-4 mb-4">
        <h3 className="text-xs font-semibold text-gray-300 mb-2">영상 추가</h3>
        <div className="flex gap-2">
          <input
            type="text"
            value={addVideoId}
            onChange={(e) => setAddVideoId(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && add()}
            placeholder="YouTube video id (예: dQw4w9WgXcQ)"
            className="flex-1 bg-bg-primary border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-primary"
          />
          <button
            onClick={add}
            className="bg-accent-primary hover:bg-purple-600 text-white px-3 py-2 rounded text-sm flex items-center gap-1"
          >
            <Plus size={14} /> 추가
          </button>
        </div>
      </div>

      {err && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-300 text-sm rounded p-3 mb-4">{err}</div>
      )}

      <div className="bg-bg-secondary border border-border rounded-lg overflow-hidden">
        {loading ? (
          <div className="p-6 text-gray-500 text-sm text-center">불러오는 중...</div>
        ) : items.length === 0 ? (
          <div className="p-6 text-gray-500 text-sm text-center">항목이 없습니다.</div>
        ) : (
          items.map((it) => (
            <div
              key={it.item_id}
              className="flex items-center gap-3 px-4 py-3 border-b border-border last:border-b-0 hover:bg-bg-tertiary/40"
            >
              <div className="text-xs text-gray-500 w-6 text-right">{(it.position ?? 0) + 1}</div>
              <div className="w-24 aspect-video bg-black rounded overflow-hidden flex-shrink-0">
                {it.thumbnail ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={it.thumbnail} alt={it.title} className="w-full h-full object-cover" />
                ) : null}
              </div>
              <div className="flex-1 min-w-0">
                <Link
                  href={`/youtube/videos/${it.video_id}`}
                  className="text-sm font-semibold truncate block hover:text-accent-primary"
                  title={it.title}
                >
                  {it.title}
                </Link>
                <div className="text-[11px] text-gray-500 font-mono">{it.video_id}</div>
              </div>
              <button
                onClick={() => remove(it)}
                className="p-2 text-gray-400 hover:text-red-400"
                title="제거"
              >
                <X size={14} />
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
