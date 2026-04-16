"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Save,
  Trash2,
  ExternalLink,
  Image as ImageIcon,
  Eye,
  ThumbsUp,
  MessageSquare,
  Clock,
} from "lucide-react";
import {
  youtubeStudioApi,
  type StudioVideoDetail,
  type StudioCategory,
} from "@/lib/api";

function toLocalInput(rfc3339?: string | null): string {
  if (!rfc3339) return "";
  try {
    const d = new Date(rfc3339);
    // datetime-local input 은 "YYYY-MM-DDTHH:mm" 포맷을 요구
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch {
    return "";
  }
}

function fromLocalInput(v: string): string {
  if (!v) return "";
  try {
    const d = new Date(v);
    return d.toISOString();
  } catch {
    return v;
  }
}

export default function StudioVideoDetailPage() {
  const params = useParams<{ videoId: string }>();
  const router = useRouter();
  const videoId = params.videoId;

  const [detail, setDetail] = useState<StudioVideoDetail | null>(null);
  const [categories, setCategories] = useState<StudioCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const thumbInputRef = useRef<HTMLInputElement | null>(null);

  // editable fields
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [defaultLanguage, setDefaultLanguage] = useState("");
  const [privacyStatus, setPrivacyStatus] = useState<"private" | "unlisted" | "public">("private");
  const [publishAtLocal, setPublishAtLocal] = useState("");
  const [madeForKids, setMadeForKids] = useState(false);
  const [embeddable, setEmbeddable] = useState(true);
  const [publicStatsViewable, setPublicStatsViewable] = useState(true);

  const reload = async () => {
    setLoading(true);
    setErr(null);
    try {
      const [d, c] = await Promise.all([
        youtubeStudioApi.getVideo(videoId),
        youtubeStudioApi.listCategories("KR").catch(() => ({ items: [], region_code: "KR" })),
      ]);
      setDetail(d);
      setCategories(c.items || []);
      setTitle(d.title || "");
      setDescription(d.description || "");
      setTags((d.tags || []).join(", "));
      setCategoryId(d.category_id || "");
      setDefaultLanguage(d.default_language || "");
      setPrivacyStatus(d.privacy_status || "private");
      setPublishAtLocal(toLocalInput(d.publish_at));
      setMadeForKids(Boolean(d.self_declared_made_for_kids ?? d.made_for_kids));
      setEmbeddable(d.embeddable ?? true);
      setPublicStatsViewable(d.public_stats_viewable ?? true);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (videoId) reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoId]);

  const save = async () => {
    setSaving(true);
    setErr(null);
    setMsg(null);
    try {
      const tagList = tags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      await youtubeStudioApi.updateVideo(videoId, {
        title,
        description,
        tags: tagList,
        category_id: categoryId || undefined,
        default_language: defaultLanguage || undefined,
        privacy_status: privacyStatus,
        publish_at: publishAtLocal ? fromLocalInput(publishAtLocal) : "",
        made_for_kids: madeForKids,
        embeddable,
        public_stats_viewable: publicStatsViewable,
      });
      setMsg("저장되었습니다.");
      await reload();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const onPickThumb = () => thumbInputRef.current?.click();

  const onThumbChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    try {
      await youtubeStudioApi.setThumbnail(videoId, f);
      setMsg("썸네일이 교체되었습니다. 잠시 후 반영됩니다.");
      setTimeout(reload, 1500);
    } catch (err2) {
      setErr((err2 as Error).message);
    } finally {
      if (thumbInputRef.current) thumbInputRef.current.value = "";
    }
  };

  const onDelete = async () => {
    if (!confirm(`정말 삭제하시겠습니까?\n\n"${detail?.title}"\n\n복구할 수 없습니다.`)) return;
    try {
      await youtubeStudioApi.deleteVideo(videoId);
      router.push("/youtube/videos");
    } catch (e) {
      alert(`삭제 실패: ${(e as Error).message}`);
    }
  };

  if (loading && !detail) {
    return <div className="p-8 text-gray-500 text-sm">불러오는 중...</div>;
  }
  if (!detail) {
    return (
      <div className="p-8 text-red-300 text-sm">
        {err || "영상을 찾을 수 없습니다."}
      </div>
    );
  }

  return (
    <div className="p-8 max-w-5xl">
      <Link href="/youtube/videos" className="text-xs text-gray-400 hover:text-white flex items-center gap-1 mb-4">
        <ArrowLeft size={12} /> 영상 목록
      </Link>

      <div className="flex items-start gap-6 mb-6">
        <div className="w-64 aspect-video bg-black rounded overflow-hidden relative flex-shrink-0">
          {detail.thumbnail ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={detail.thumbnail} alt={detail.title} className="w-full h-full object-cover" />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-gray-600 text-xs">썸네일 없음</div>
          )}
          <button
            onClick={onPickThumb}
            className="absolute inset-0 flex items-center justify-center bg-black/60 opacity-0 hover:opacity-100 text-white text-sm transition-opacity"
          >
            <ImageIcon size={16} className="mr-1" /> 썸네일 교체
          </button>
          <input
            ref={thumbInputRef}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            onChange={onThumbChange}
            className="hidden"
          />
        </div>

        <div className="flex-1 min-w-0">
          <div className="text-xs text-gray-500 font-mono mb-1">{detail.video_id}</div>
          <h2 className="text-xl font-bold mb-2 break-words">{detail.title}</h2>
          <div className="flex flex-wrap items-center gap-3 text-xs text-gray-400 mb-4">
            <span className="flex items-center gap-1"><Eye size={12} /> {detail.view_count ?? 0}</span>
            <span className="flex items-center gap-1"><ThumbsUp size={12} /> {detail.like_count ?? 0}</span>
            <span className="flex items-center gap-1"><MessageSquare size={12} /> {detail.comment_count ?? 0}</span>
            {detail.publish_at && (
              <span className="flex items-center gap-1 text-amber-300">
                <Clock size={12} /> 예약: {new Date(detail.publish_at).toLocaleString("ko-KR")}
              </span>
            )}
          </div>
          <a
            href={`https://youtube.com/watch?v=${detail.video_id}`}
            target="_blank"
            className="inline-flex items-center gap-1 text-xs text-accent-primary hover:underline"
          >
            <ExternalLink size={12} /> YouTube 에서 열기
          </a>
        </div>
      </div>

      {err && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-300 text-sm rounded p-3 mb-4">{err}</div>
      )}
      {msg && (
        <div className="bg-green-500/10 border border-green-500/30 text-green-300 text-sm rounded p-3 mb-4">{msg}</div>
      )}

      <div className="grid grid-cols-[1fr_280px] gap-6">
        {/* Main edit panel */}
        <div className="bg-bg-secondary border border-border rounded-lg p-5 space-y-4">
          <div>
            <label className="block text-xs text-gray-400 mb-1">제목</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full bg-bg-primary border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-primary"
              maxLength={100}
            />
            <div className="text-right text-[10px] text-gray-500 mt-0.5">{title.length} / 100</div>
          </div>

          <div>
            <label className="block text-xs text-gray-400 mb-1">설명</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={10}
              className="w-full bg-bg-primary border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-primary font-mono"
              maxLength={5000}
            />
            <div className="text-right text-[10px] text-gray-500 mt-0.5">{description.length} / 5000</div>
          </div>

          <div>
            <label className="block text-xs text-gray-400 mb-1">태그 (콤마로 구분)</label>
            <input
              type="text"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              className="w-full bg-bg-primary border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-primary"
            />
            <div className="text-right text-[10px] text-gray-500 mt-0.5">
              {tags.split(",").filter((t) => t.trim()).length} 개 · 총 {tags.length} 자 / 500
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">카테고리</label>
              <select
                value={categoryId}
                onChange={(e) => setCategoryId(e.target.value)}
                className="w-full bg-bg-primary border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-primary"
              >
                <option value="">-</option>
                {categories.map((c) => (
                  <option key={c.category_id} value={c.category_id}>
                    {c.title}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">기본 언어</label>
              <input
                type="text"
                value={defaultLanguage}
                onChange={(e) => setDefaultLanguage(e.target.value)}
                placeholder="ko"
                className="w-full bg-bg-primary border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-primary"
              />
            </div>
          </div>
        </div>

        {/* Side panel: publish options */}
        <div className="space-y-4">
          <div className="bg-bg-secondary border border-border rounded-lg p-4">
            <h3 className="text-xs font-semibold text-gray-300 mb-3">공개 설정</h3>
            <div className="space-y-2 text-sm">
              {(["private", "unlisted", "public"] as const).map((p) => (
                <label key={p} className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    checked={privacyStatus === p}
                    onChange={() => setPrivacyStatus(p)}
                  />
                  <span>
                    {p === "private" ? "비공개" : p === "unlisted" ? "일부공개" : "공개"}
                  </span>
                </label>
              ))}
            </div>

            <div className="mt-4 pt-4 border-t border-border">
              <label className="block text-xs text-gray-400 mb-1">예약 게시 (선택)</label>
              <input
                type="datetime-local"
                value={publishAtLocal}
                onChange={(e) => setPublishAtLocal(e.target.value)}
                className="w-full bg-bg-primary border border-border rounded px-2 py-1.5 text-xs focus:outline-none focus:border-accent-primary"
              />
              <p className="text-[10px] text-gray-500 mt-1">
                예약 시각을 넣으면 자동으로 비공개로 내려갔다 해당 시각에 공개 전환됩니다. 비우면 예약 해제.
              </p>
            </div>
          </div>

          <div className="bg-bg-secondary border border-border rounded-lg p-4">
            <h3 className="text-xs font-semibold text-gray-300 mb-3">기타</h3>
            <label className="flex items-center gap-2 text-sm mb-2 cursor-pointer">
              <input type="checkbox" checked={madeForKids} onChange={(e) => setMadeForKids(e.target.checked)} />
              아동용 콘텐츠
            </label>
            <label className="flex items-center gap-2 text-sm mb-2 cursor-pointer">
              <input type="checkbox" checked={embeddable} onChange={(e) => setEmbeddable(e.target.checked)} />
              퍼가기 허용
            </label>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="checkbox"
                checked={publicStatsViewable}
                onChange={(e) => setPublicStatsViewable(e.target.checked)}
              />
              좋아요/조회수 공개
            </label>
          </div>

          <div className="flex flex-col gap-2">
            <button
              onClick={save}
              disabled={saving}
              className="w-full bg-accent-primary hover:bg-purple-600 text-white rounded px-4 py-2 text-sm flex items-center justify-center gap-2 disabled:opacity-50"
            >
              <Save size={14} /> {saving ? "저장 중..." : "저장"}
            </button>
            <button
              onClick={onDelete}
              className="w-full bg-red-600/20 hover:bg-red-600 text-red-300 hover:text-white rounded px-4 py-2 text-sm flex items-center justify-center gap-2"
            >
              <Trash2 size={14} /> 영상 삭제
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
