"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Upload, File as FileIcon, Image as ImageIcon, ExternalLink } from "lucide-react";
import {
  youtubeStudioApi,
  type StudioCategory,
} from "@/lib/api";

function studioHref(path: string, projectId?: string | null): string {
  const pid = (projectId || "").trim();
  return pid ? `${path}?project=${encodeURIComponent(pid)}` : path;
}

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export default function StudioUploadPage() {
  const searchParams = useSearchParams();
  const projectId = (searchParams.get("project") || "").trim();

  const [file, setFile] = useState<File | null>(null);
  const [thumbnail, setThumbnail] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [defaultLanguage, setDefaultLanguage] = useState("ko");
  const [privacyStatus, setPrivacyStatus] = useState<"private" | "unlisted" | "public">("private");
  const [publishAt, setPublishAt] = useState("");
  const [madeForKids, setMadeForKids] = useState(false);
  const [categories, setCategories] = useState<StudioCategory[]>([]);
  const [uploading, setUploading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<{ video_id: string; url: string } | null>(null);

  useEffect(() => {
    if (!projectId) {
      setCategories([]);
      return;
    }
    youtubeStudioApi
      .listCategories("KR", projectId)
      .then((res) => setCategories(res.items || []))
      .catch(() => {});
  }, [projectId]);

  const submit = async () => {
    if (!projectId) {
      setErr("좌측에서 프리셋을 선택하십시오.");
      return;
    }
    if (!file) {
      setErr("영상 파일을 선택해 주십시오.");
      return;
    }
    if (!title.trim()) {
      setErr("제목을 입력해 주십시오.");
      return;
    }

    setUploading(true);
    setErr(null);
    setResult(null);
    try {
      const tagList = tags
        .split(",")
        .map((tag) => tag.trim())
        .filter(Boolean);
      const res = await youtubeStudioApi.directUpload({
        file,
        title: title.trim(),
        description,
        tags: tagList,
        privacyStatus,
        categoryId: categoryId || undefined,
        defaultLanguage: defaultLanguage || undefined,
        madeForKids,
        publishAt: publishAt ? new Date(publishAt).toISOString() : undefined,
        thumbnail,
        projectId,
      });
      setResult({ video_id: res.video_id, url: res.url });
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="p-8 max-w-3xl">
      <h2 className="text-2xl font-bold mb-1">직접 업로드</h2>
      <p className="text-gray-400 text-sm mb-6">선택된 프리셋의 YouTube OAuth 로 바로 업로드합니다.</p>

      {err && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-300 text-sm rounded p-3 mb-4">
          {err}
        </div>
      )}
      {result && (
        <div className="bg-green-500/10 border border-green-500/30 text-green-300 text-sm rounded p-4 mb-4">
          <div className="font-semibold mb-1">업로드 완료</div>
          <div className="flex items-center gap-3 text-xs">
            <a href={result.url} target="_blank" className="underline flex items-center gap-1">
              <ExternalLink size={12} /> {result.url}
            </a>
            <Link href={studioHref(`/youtube/videos/${result.video_id}`, projectId)} className="underline">
              편집 페이지로 이동
            </Link>
          </div>
        </div>
      )}

      {!projectId ? (
        <div className="bg-bg-secondary border border-border rounded-lg p-8 text-sm text-gray-500">
          좌측에서 프리셋을 선택하십시오.
        </div>
      ) : (
        <div className="bg-bg-secondary border border-border rounded-lg p-5 space-y-4">
          <div>
            <label className="block text-xs text-gray-400 mb-1">영상 파일</label>
            <label className="block border-2 border-dashed border-border rounded-lg p-6 text-center cursor-pointer hover:border-accent-primary/50">
              <input
                type="file"
                accept="video/mp4,video/quicktime,video/x-matroska,video/webm,video/x-msvideo"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                className="hidden"
              />
              {file ? (
                <div className="flex items-center justify-center gap-2 text-sm text-gray-200">
                  <FileIcon size={16} /> {file.name}
                  <span className="text-xs text-gray-500">({fmtSize(file.size)})</span>
                </div>
              ) : (
                <div className="text-gray-500 text-sm flex items-center justify-center gap-2">
                  <Upload size={16} /> 클릭해서 영상 파일 선택
                </div>
              )}
            </label>
          </div>

          <div>
            <label className="block text-xs text-gray-400 mb-1">썸네일 (선택)</label>
            <label className="block border border-border rounded px-3 py-2 text-sm cursor-pointer hover:border-accent-primary/50 bg-bg-primary">
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp"
                onChange={(e) => setThumbnail(e.target.files?.[0] || null)}
                className="hidden"
              />
              <span className="flex items-center gap-2 text-gray-300">
                <ImageIcon size={14} /> {thumbnail ? thumbnail.name : "썸네일 이미지 선택"}
              </span>
            </label>
          </div>

          <div>
            <label className="block text-xs text-gray-400 mb-1">제목</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={100}
              className="w-full bg-bg-primary border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-primary"
            />
          </div>

          <div>
            <label className="block text-xs text-gray-400 mb-1">설명</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={6}
              className="w-full bg-bg-primary border border-border rounded px-3 py-2 text-sm font-mono focus:outline-none focus:border-accent-primary"
              maxLength={5000}
            />
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

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">공개</label>
              <select
                value={privacyStatus}
                onChange={(e) => setPrivacyStatus(e.target.value as "private" | "unlisted" | "public")}
                className="w-full bg-bg-primary border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-primary"
              >
                <option value="private">비공개</option>
                <option value="unlisted">일부 공개</option>
                <option value="public">공개</option>
              </select>
            </div>
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
              <label className="block text-xs text-gray-400 mb-1">언어</label>
              <input
                type="text"
                value={defaultLanguage}
                onChange={(e) => setDefaultLanguage(e.target.value)}
                placeholder="ko"
                className="w-full bg-bg-primary border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-primary"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">예약 게시 (선택)</label>
              <input
                type="datetime-local"
                value={publishAt}
                onChange={(e) => setPublishAt(e.target.value)}
                className="w-full bg-bg-primary border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-primary"
              />
            </div>
            <label className="flex items-end gap-2 text-sm mb-1 cursor-pointer">
              <input
                type="checkbox"
                checked={madeForKids}
                onChange={(e) => setMadeForKids(e.target.checked)}
              />
              아동용 콘텐츠
            </label>
          </div>

          <button
            onClick={submit}
            disabled={uploading || !file || !title.trim()}
            className="w-full bg-red-600 hover:bg-red-500 text-white rounded px-4 py-3 text-sm font-semibold flex items-center justify-center gap-2 disabled:opacity-50"
          >
            <Upload size={16} /> {uploading ? "업로드 중..." : "업로드"}
          </button>
        </div>
      )}
    </div>
  );
}
