"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Plus, Trash2, Edit3, ListMusic, RefreshCw } from "lucide-react";
import { youtubeStudioApi, type StudioPlaylist } from "@/lib/api";

export default function PlaylistsPage() {
  const [items, setItems] = useState<StudioPlaylist[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newPrivacy, setNewPrivacy] = useState<"private" | "unlisted" | "public">("private");
  const [editing, setEditing] = useState<StudioPlaylist | null>(null);

  const load = async () => {
    setLoading(true);
    setErr(null);
    try {
      const res = await youtubeStudioApi.listPlaylists();
      setItems(res.items || []);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const create = async () => {
    if (!newTitle.trim()) return;
    try {
      await youtubeStudioApi.createPlaylist({
        title: newTitle.trim(),
        description: newDesc,
        privacy_status: newPrivacy,
      });
      setNewTitle("");
      setNewDesc("");
      setNewPrivacy("private");
      setShowCreate(false);
      load();
    } catch (e) {
      alert(`생성 실패: ${(e as Error).message}`);
    }
  };

  const saveEdit = async () => {
    if (!editing) return;
    try {
      await youtubeStudioApi.updatePlaylist(editing.playlist_id, {
        title: editing.title,
        description: editing.description,
        privacy_status: editing.privacy_status as "private" | "unlisted" | "public" | undefined,
      });
      setEditing(null);
      load();
    } catch (e) {
      alert(`수정 실패: ${(e as Error).message}`);
    }
  };

  const del = async (pl: StudioPlaylist) => {
    if (!confirm(`"${pl.title}" 재생목록을 삭제하시겠습니까? 복구할 수 없습니다.`)) return;
    try {
      await youtubeStudioApi.deletePlaylist(pl.playlist_id);
      load();
    } catch (e) {
      alert(`삭제 실패: ${(e as Error).message}`);
    }
  };

  return (
    <div className="p-8 max-w-5xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold">재생목록</h2>
          <p className="text-gray-400 text-sm mt-1">채널의 재생목록을 만들고 삭제합니다.</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={load}
            disabled={loading}
            className="text-xs text-gray-400 hover:text-white flex items-center gap-1 disabled:opacity-50"
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} /> 새로고침
          </button>
          <button
            onClick={() => setShowCreate(true)}
            className="bg-accent-primary hover:bg-purple-600 text-white px-3 py-1.5 rounded text-sm flex items-center gap-1"
          >
            <Plus size={14} /> 새 재생목록
          </button>
        </div>
      </div>

      {err && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-300 text-sm rounded p-3 mb-4">{err}</div>
      )}

      {showCreate && (
        <div className="bg-bg-secondary border border-border rounded-lg p-4 mb-4">
          <h3 className="text-sm font-semibold mb-3">새 재생목록</h3>
          <input
            type="text"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder="제목"
            className="w-full bg-bg-primary border border-border rounded px-3 py-2 text-sm mb-2 focus:outline-none focus:border-accent-primary"
          />
          <textarea
            value={newDesc}
            onChange={(e) => setNewDesc(e.target.value)}
            placeholder="설명 (선택)"
            rows={3}
            className="w-full bg-bg-primary border border-border rounded px-3 py-2 text-sm mb-2 focus:outline-none focus:border-accent-primary"
          />
          <div className="flex items-center gap-2 mb-3">
            <label className="text-xs text-gray-400">공개:</label>
            <select
              value={newPrivacy}
              onChange={(e) => setNewPrivacy(e.target.value as "private" | "unlisted" | "public")}
              className="bg-bg-primary border border-border rounded px-2 py-1 text-xs"
            >
              <option value="private">비공개</option>
              <option value="unlisted">일부공개</option>
              <option value="public">공개</option>
            </select>
          </div>
          <div className="flex items-center gap-2 justify-end">
            <button
              onClick={() => setShowCreate(false)}
              className="text-xs text-gray-400 hover:text-white px-3 py-1.5"
            >
              취소
            </button>
            <button
              onClick={create}
              className="bg-accent-primary hover:bg-purple-600 text-white px-3 py-1.5 rounded text-sm"
            >
              생성
            </button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        {loading && items.length === 0 ? (
          <div className="col-span-2 text-gray-500 text-sm text-center py-6">불러오는 중...</div>
        ) : items.length === 0 ? (
          <div className="col-span-2 text-gray-500 text-sm text-center py-6">재생목록이 없습니다.</div>
        ) : (
          items.map((pl) => (
            <div key={pl.playlist_id} className="bg-bg-secondary border border-border rounded-lg p-4">
              {editing?.playlist_id === pl.playlist_id ? (
                <div>
                  <input
                    type="text"
                    value={editing.title}
                    onChange={(e) => setEditing({ ...editing, title: e.target.value })}
                    className="w-full bg-bg-primary border border-border rounded px-2 py-1 text-sm mb-2"
                  />
                  <textarea
                    value={editing.description || ""}
                    onChange={(e) => setEditing({ ...editing, description: e.target.value })}
                    rows={2}
                    className="w-full bg-bg-primary border border-border rounded px-2 py-1 text-xs mb-2"
                  />
                  <div className="flex items-center gap-2 mb-2">
                    <select
                      value={editing.privacy_status || "private"}
                      onChange={(e) =>
                        setEditing({
                          ...editing,
                          privacy_status: e.target.value as "private" | "unlisted" | "public",
                        })
                      }
                      className="bg-bg-primary border border-border rounded px-2 py-1 text-xs"
                    >
                      <option value="private">비공개</option>
                      <option value="unlisted">일부공개</option>
                      <option value="public">공개</option>
                    </select>
                  </div>
                  <div className="flex items-center gap-2 justify-end">
                    <button
                      onClick={() => setEditing(null)}
                      className="text-xs text-gray-400 px-2 py-1"
                    >
                      취소
                    </button>
                    <button
                      onClick={saveEdit}
                      className="bg-accent-primary text-white px-3 py-1 rounded text-xs"
                    >
                      저장
                    </button>
                  </div>
                </div>
              ) : (
                <div>
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <Link
                      href={`/youtube/playlists/${pl.playlist_id}`}
                      className="flex items-center gap-2 min-w-0 flex-1 hover:text-accent-primary"
                    >
                      <ListMusic size={16} className="text-accent-secondary flex-shrink-0" />
                      <span className="text-base font-semibold truncate" title={pl.title}>
                        {pl.title}
                      </span>
                    </Link>
                    <div className="flex items-center gap-1 flex-shrink-0">
                      <button
                        onClick={() => setEditing(pl)}
                        className="p-1 text-gray-400 hover:text-white"
                        title="수정"
                      >
                        <Edit3 size={13} />
                      </button>
                      <button
                        onClick={() => del(pl)}
                        className="p-1 text-gray-400 hover:text-red-400"
                        title="삭제"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </div>
                  <div className="text-xs text-gray-500 mb-1">
                    {pl.item_count ?? 0} 항목 · {pl.privacy_status || "-"}
                  </div>
                  {pl.description && (
                    <p className="text-xs text-gray-400 line-clamp-2">{pl.description}</p>
                  )}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
