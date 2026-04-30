"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
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
  type StudioCategory,
  type StudioVideoDetail,
} from "@/lib/api";

function studioHref(path: string, projectId?: string | null): string {
  const pid = (projectId || "").trim();
  return pid ? `${path}?project=${encodeURIComponent(pid)}` : path;
}

function toLocalInput(rfc3339?: string | null): string {
  if (!rfc3339) return "";
  try {
    const d = new Date(rfc3339);
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch {
    return "";
  }
}

function fromLocalInput(value: string): string {
  if (!value) return "";
  try {
    return new Date(value).toISOString();
  } catch {
    return value;
  }
}

export default function StudioVideoDetailPage() {
  const params = useParams<{ videoId: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const projectId = (searchParams.get("project") || "").trim();
  const videoId = params.videoId;

  const [detail, setDetail] = useState<StudioVideoDetail | null>(null);
  const [categories, setCategories] = useState<StudioCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const thumbInputRef = useRef<HTMLInputElement | null>(null);

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
    if (!projectId) return;
    setLoading(true);
    setErr(null);
    try {
      const [video, categoriesRes] = await Promise.all([
        youtubeStudioApi.getVideo(videoId, projectId),
        youtubeStudioApi.listCategories("KR", projectId).catch(() => ({
          items: [],
          region_code: "KR",
        })),
      ]);
      setDetail(video);
      setCategories(categoriesRes.items || []);
      setTitle(video.title || "");
      setDescription(video.description || "");
      setTags((video.tags || []).join(", "));
      setCategoryId(video.category_id || "");
      setDefaultLanguage(video.default_language || "");
      setPrivacyStatus(video.privacy_status || "private");
      setPublishAtLocal(toLocalInput(video.publish_at));
      setMadeForKids(Boolean(video.self_declared_made_for_kids ?? video.made_for_kids));
      setEmbeddable(video.embeddable ?? true);
      setPublicStatsViewable(video.public_stats_viewable ?? true);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (videoId && projectId) reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoId, projectId]);

  const save = async () => {
    if (!projectId) return;
    setSaving(true);
    setErr(null);
    setMsg(null);
    try {
      const tagList = tags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      await youtubeStudioApi.updateVideo(
        videoId,
        {
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
        },
        projectId,
      );
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
    if (!projectId) return;
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      await youtubeStudioApi.setThumbnail(videoId, file, projectId);
      setMsg("썸네일을 교체했습니다. 잠시 후 반영됩니다.");
      setTimeout(reload, 1500);
    } catch (thumbErr) {
      setErr((thumbErr as Error).message);
    } finally {
      if (thumbInputRef.current) thumbInputRef.current.value = "";
    }
  };

  const onDelete = async () => {
    if (!projectId || !confirm(`정말 삭제하시겠습니까?\n\n"${detail?.title}"\n\n복구할 수 없습니다.`)) return;
    try {
      await youtubeStudioApi.deleteVideo(videoId, projectId);
      router.push(studioHref("/youtube/videos", projectId));
    } catch (e) {
      alert(`삭제 실패: ${(e as Error).message}`);
    }
  };

  if (!projectId) {
    return <div className="p-8 text-gray-500 text-sm">좌측에서 프리셋을 선택하십시오.</div>;
  }

  if (loading && !detail) {
    return <div className="p-8 text-gray-500 text-sm">불러오는 중...</div>;
  }

  if (!detail) {
    return <div className="p-8 text-red-300 text-sm">{err || "영상을 찾을 수 없습니다."}</div>;
  }

  return (
    <div className="p-8 max-w-5xl">
      <Link
        href={studioHref("/youtube/videos", projectId)}
        className="text-xs text-gray-400 hover:text-white flex items-center gap-1 mb-4"
      >
        <ArrowLeft size={12} /> 영상 목록
      </Link>

      <div className="flex items-start gap-6 mb-6">
        <div className="w-64 aspect-video bg-black rounded overflow-hidden relative flex-shrink-0">
          {detail.thumbnail ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={detail.thumbnail} alt={detail.title} className="w-full h-full object-cover" />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-gray-600 text-xs">
              썸네일 없음
            </div>
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
            <span className="flex items-center gap-1">
              <Eye size={12} /> {detail.view_count ?? 0}
            </span>
            <span className="flex items-center gap-1">
              <ThumbsUp size={12} /> {detail.like_count ?? 0}
            </span>
            <span className="flex items-center gap-1">
              <MessageSquare size={12} /> {detail.comment_count ?? 0}
            </span>
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
            <ExternalLink size={12} /> YouTube에서 보기
          </a>
        </div>
      </div>

      {err && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-300 text-sm rounded p-3 mb-4">
          {err}
        </div>
      )}
      {msg && (
        <div className="bg-green-500/10 border border-green-500/30 text-green-300 text-sm rounded p-3 mb-4">
          {msg}
        </div>
      )}

      <div className="grid grid-cols-[1fr_280px] gap-6">
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
                {categories.map((category) => (
                  <option key={category.category_id} value={category.category_id}>
                    {category.title}
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

        <div className="space-y-4">
          <div className="bg-bg-secondary border border-border rounded-lg p-4">
            <h3 className="text-xs font-semibold text-gray-300 mb-3">공개 설정</h3>
            <div className="space-y-2 text-sm">
              {(["private", "unlisted", "public"] as const).map((privacy) => (
                <label key={privacy} className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    checked={privacyStatus === privacy}
                    onChange={() => setPrivacyStatus(privacy)}
                  />
                  <span>
                    {privacy === "private"
                      ? "비공개"
                      : privacy === "unlisted"
                        ? "일부 공개"
                        : "공개"}
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
              조회수 공개
            </label>
          </div>

          <div className="bg-bg-secondary border border-border rounded-lg p-4 space-y-2">
            <button
              onClick={save}
              disabled={saving}
              className="w-full bg-accent-primary hover:bg-purple-600 text-white rounded px-4 py-2 text-sm font-semibold flex items-center justify-center gap-2 disabled:opacity-50"
            >
              <Save size={16} /> {saving ? "저장 중..." : "저장"}
            </button>
            <button
              onClick={onDelete}
              className="w-full bg-red-600/90 hover:bg-red-600 text-white rounded px-4 py-2 text-sm font-semibold flex items-center justify-center gap-2"
            >
              <Trash2 size={16} /> 영상 삭제
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
