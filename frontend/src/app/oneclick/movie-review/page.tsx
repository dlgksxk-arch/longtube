"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Clapperboard,
  Download,
  ExternalLink,
  FileArchive,
  HardDrive,
  Loader2,
  PlayCircle,
  Server,
  Subtitles,
  Trash2,
} from "lucide-react";
import {
  movieReviewApi,
  movieReviewArtifactUrl,
  type MovieReviewJob,
  type MovieReviewJobStatus,
  type MovieReviewRuntime,
} from "@/lib/api";

const STATUS: Record<MovieReviewJobStatus, { label: string; color: string }> = {
  queued: { label: "대기", color: "border-slate-500/40 bg-slate-500/10 text-slate-300" },
  downloading: { label: "수집 중", color: "border-blue-400/40 bg-blue-400/10 text-blue-300" },
  extracting_audio: { label: "음성 추출", color: "border-violet-400/40 bg-violet-400/10 text-violet-300" },
  transcribing: { label: "자막 추출", color: "border-fuchsia-400/40 bg-fuchsia-400/10 text-fuchsia-300" },
  generating_preview: { label: "예고 대본", color: "border-cyan-400/40 bg-cyan-400/10 text-cyan-300" },
  ready: { label: "수집 완료", color: "border-emerald-400/40 bg-emerald-400/10 text-emerald-300" },
  failed: { label: "실패", color: "border-red-400/40 bg-red-400/10 text-red-300" },
  interrupted: { label: "중단", color: "border-amber-400/40 bg-amber-400/10 text-amber-300" },
};

function formatDate(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ko-KR", {
    year: "2-digit",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatDuration(seconds: number) {
  if (!seconds) return "-";
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remain = total % 60;
  return hours
    ? `${hours}:${String(minutes).padStart(2, "0")}:${String(remain).padStart(2, "0")}`
    : `${minutes}:${String(remain).padStart(2, "0")}`;
}

function sourceCount(job: MovieReviewJob) {
  return [
    job.video_path,
    job.audio_path,
    job.metadata_path,
    job.thumbnail_path,
    job.meta_tags_path,
    job.meta_tags_text_path,
    ...(job.subtitle_paths || []),
  ].filter(Boolean).length;
}

function cleanError(value: string) {
  return String(value || "").replace(/\u001b\[[0-9;]*m/g, "");
}

export default function MovieReviewPage() {
  const [runtime, setRuntime] = useState<MovieReviewRuntime | null>(null);
  const [jobs, setJobs] = useState<MovieReviewJob[]>([]);
  const [sourceUrl, setSourceUrl] = useState("");
  const [maxHeight, setMaxHeight] = useState<720 | 1080 | 1440 | 2160>(1080);
  const [rightsConfirmed, setRightsConfirmed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [deletingJobId, setDeletingJobId] = useState("");
  const [transcribingJobId, setTranscribingJobId] = useState("");
  const [error, setError] = useState("");

  const hasActiveJobs = useMemo(
    () => jobs.some((job) => job.running || ["queued", "downloading", "extracting_audio", "transcribing", "generating_preview"].includes(job.status)),
    [jobs],
  );

  const load = useCallback(async () => {
    try {
      const [runtimeResult, jobsResult] = await Promise.all([
        movieReviewApi.runtime(),
        movieReviewApi.listJobs(),
      ]);
      setRuntime(runtimeResult);
      setJobs(jobsResult.jobs || []);
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const timer = window.setInterval(() => void load(), hasActiveJobs ? 2500 : 10000);
    return () => window.clearInterval(timer);
  }, [hasActiveJobs, load]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!sourceUrl.trim()) return setError("YouTube 영상 URL을 입력해 주세요.");
    if (!rightsConfirmed) return setError("사용 권한 확인 항목에 체크해 주세요.");
    setSubmitting(true);
    setError("");
    try {
      const job = await movieReviewApi.createJob({
        source_url: sourceUrl.trim(),
        max_height: maxHeight,
        subtitle_languages: ["ko", "ja", "en"],
        rights_confirmed: true,
      });
      setJobs((current) => [job, ...current.filter((item) => item.job_id !== job.job_id)]);
      setSourceUrl("");
      setRightsConfirmed(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSubmitting(false);
    }
  };

  const deleteJob = async (job: MovieReviewJob) => {
    const confirmed = window.confirm(
      "삭제 시 저장된 항목이 모두 삭제됩니다.\n\n영상, 음성, 자막, 썸네일, 메타데이터, 메타태그와 작업 폴더 전체가 삭제되며 복구할 수 없습니다.\n\n계속하시겠습니까?",
    );
    if (!confirmed) return;
    setDeletingJobId(job.job_id);
    setError("");
    try {
      await movieReviewApi.deleteJob(job.job_id);
      setJobs((current) => current.filter((item) => item.job_id !== job.job_id));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setDeletingJobId("");
    }
  };

  const transcribeJob = async (job: MovieReviewJob) => {
    setTranscribingJobId(job.job_id);
    setError("");
    try {
      const updated = await movieReviewApi.transcribeJob(job.job_id);
      setJobs((current) => current.map((item) => item.job_id === job.job_id ? updated : item));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setTranscribingJobId("");
    }
  };

  return (
    <div className="mx-auto w-full max-w-[1600px] px-4 py-5 lg:px-7 lg:py-7 2xl:px-10">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-accent-primary/15 p-2.5 text-accent-primary"><Clapperboard size={24} /></div>
          <div>
            <h1 className="text-2xl font-black text-white lg:text-3xl">영화 예고 제작실</h1>
            <p className="mt-1 text-sm text-gray-400">수집 자료를 분석해 예고 대본과 업로드 메타데이터를 만듭니다.</p>
          </div>
        </div>
        <div className={`rounded-xl border px-4 py-3 ${runtime?.ready ? "border-emerald-400/25 bg-emerald-400/10" : "border-red-400/25 bg-red-400/10"}`}>
          <div className="flex items-center gap-2 text-sm font-bold text-white">
            <Server size={16} className={runtime?.ready ? "text-emerald-300" : "text-red-300"} />
            {runtime?.ready ? "수집 엔진 정상" : "수집 엔진 확인 필요"}
          </div>
          <div className="mt-1 text-xs text-gray-400">yt-dlp {runtime?.yt_dlp_version || "미설치"}</div>
        </div>
      </header>

      <section className="mt-6 rounded-2xl border border-border bg-bg-secondary p-5 shadow-xl shadow-black/10 lg:p-6">
        <form onSubmit={submit}>
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_160px_auto] lg:items-end">
            <label className="block">
              <span className="mb-2 block text-sm font-bold text-gray-200">YouTube 영상 URL</span>
              <input
                type="url"
                value={sourceUrl}
                onChange={(event) => setSourceUrl(event.target.value)}
                placeholder="https://www.youtube.com/watch?v=..."
                className="h-12 w-full rounded-xl border border-border bg-bg-primary px-4 text-sm text-white outline-none placeholder:text-gray-600 focus:border-accent-primary"
              />
            </label>
            <label className="block">
              <span className="mb-2 block text-sm font-bold text-gray-200">최대 해상도</span>
              <select
                value={maxHeight}
                onChange={(event) => setMaxHeight(Number(event.target.value) as 720 | 1080 | 1440 | 2160)}
                className="h-12 w-full rounded-xl border border-border bg-bg-primary px-3 text-sm text-white outline-none focus:border-accent-primary"
              >
                <option value={720}>720p</option><option value={1080}>1080p</option>
                <option value={1440}>1440p</option><option value={2160}>2160p</option>
              </select>
            </label>
            <button
              type="submit"
              disabled={submitting || !runtime?.ready}
              className="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-accent-primary px-5 text-sm font-black text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {submitting ? <Loader2 size={17} className="animate-spin" /> : <Download size={17} />}
              원본 자료 준비
            </button>
          </div>
          <label className="mt-4 flex cursor-pointer items-start gap-3 rounded-xl border border-amber-400/20 bg-amber-400/[0.06] px-4 py-3">
            <input type="checkbox" checked={rightsConfirmed} onChange={(event) => setRightsConfirmed(event.target.checked)} className="mt-0.5 h-4 w-4 accent-violet-500" />
            <span className="text-xs leading-5 text-amber-100/85">본인 소유, 사용 허가, 라이선스 허용 또는 퍼블릭 도메인 영상임을 확인했습니다.</span>
          </label>
          {runtime?.output_root && (
            <div className="mt-3 flex min-w-0 items-center gap-2 text-xs text-gray-500" title={runtime.output_root}>
              <HardDrive size={14} className="shrink-0" /><span className="truncate">보관 위치: {runtime.output_root}</span>
            </div>
          )}
        </form>
      </section>

      {error && (
        <div className="mt-4 flex items-start gap-2 rounded-xl border border-red-400/25 bg-red-400/10 px-4 py-3 text-sm text-red-200">
          <AlertCircle size={17} className="mt-0.5 shrink-0" /><span>{error}</span>
        </div>
      )}

      <section className="mt-7 overflow-hidden rounded-2xl border border-border bg-bg-secondary shadow-xl shadow-black/10">
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <div>
            <h2 className="text-lg font-black text-white">수집 작업 게시판</h2>
            <p className="mt-1 text-xs text-gray-500">순번은 저장 폴더명과 동일하게 유지됩니다.</p>
          </div>
          <span className="rounded-full border border-border bg-bg-primary px-3 py-1 text-xs font-bold text-gray-400">{jobs.length}건</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[1120px] border-collapse text-left">
            <thead className="bg-bg-primary/70 text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="w-20 px-4 py-3 text-center">순번</th>
                <th className="px-4 py-3">영상 제목</th>
                <th className="w-36 px-4 py-3">채널</th>
                <th className="w-24 px-4 py-3 text-center">길이</th>
                <th className="w-28 px-4 py-3 text-center">상태</th>
                <th className="w-36 px-4 py-3">수집일</th>
                <th className="w-24 px-4 py-3 text-center">자료</th>
                <th className="w-64 px-4 py-3 text-center">관리</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {loading ? (
                <tr><td colSpan={8} className="h-40 text-center text-gray-500"><Loader2 size={24} className="mx-auto animate-spin" /></td></tr>
              ) : jobs.length === 0 ? (
                <tr><td colSpan={8} className="h-40 text-center text-sm text-gray-500">수집 작업이 없습니다.</td></tr>
              ) : jobs.map((job) => {
                const status = STATUS[job.status] || STATUS.interrupted;
                const canProceed = job.status === "ready";
                return (
                  <tr key={job.job_id} className="bg-bg-secondary transition-colors hover:bg-white/[0.025]">
                    <td className="px-4 py-3 text-center text-sm font-black text-gray-300">{job.sequence_number || "-"}</td>
                    <td className="px-4 py-3">
                      <div className="flex min-w-0 items-center gap-3">
                        <div className="h-12 w-20 shrink-0 overflow-hidden rounded-lg bg-black/30">
                          {job.thumbnail_path ? <img src={movieReviewArtifactUrl(job.job_id, "thumbnail")} alt="" className="h-full w-full object-cover" /> : <Clapperboard size={22} className="m-auto mt-3 text-gray-700" />}
                        </div>
                        <div className="min-w-0">
                          <div className="max-w-xl truncate text-sm font-bold text-white">{job.title || "제목 확인 실패"}</div>
                          <div className="mt-1 max-w-xl truncate text-xs text-gray-600" title={job.folder_name || job.output_dir}>{job.folder_name || job.output_dir}</div>
                          {job.error && <div className="mt-1 max-w-xl truncate text-xs text-red-400" title={cleanError(job.error)}>{cleanError(job.error)}</div>}
                        </div>
                      </div>
                    </td>
                    <td className="max-w-36 truncate px-4 py-3 text-sm text-gray-400">{job.channel || "-"}</td>
                    <td className="px-4 py-3 text-center text-sm text-gray-400">{formatDuration(job.duration_seconds)}</td>
                    <td className="px-4 py-3 text-center">
                      <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-bold ${status.color}`}>{status.label}</span>
                      {job.running && <div className="mt-1 text-[10px] text-blue-300">{Math.round(job.progress || 0)}%</div>}
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-500">{formatDate(job.created_at)}</td>
                    <td className="px-4 py-3 text-center">
                      <span className="inline-flex items-center gap-1 text-xs text-gray-400"><FileArchive size={14} />{sourceCount(job)}</span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-center gap-2">
                        {canProceed ? (
                          <Link href={`/oneclick/movie-review/${encodeURIComponent(job.job_id)}`} className="inline-flex items-center gap-1.5 rounded-lg bg-accent-primary px-3 py-2 text-xs font-black text-white hover:opacity-90">
                            <PlayCircle size={15} /> 작업 진행
                          </Link>
                        ) : (
                          <button disabled className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-xs font-bold text-gray-600"><PlayCircle size={15} /> 작업 진행</button>
                        )}
                        {job.status === "ready" && !(job.subtitle_paths || []).length && (
                          <button
                            type="button"
                            onClick={() => void transcribeJob(job)}
                            disabled={job.running || transcribingJobId === job.job_id}
                            className="inline-flex items-center gap-1.5 rounded-lg border border-fuchsia-400/30 px-3 py-2 text-xs font-bold text-fuchsia-300 hover:bg-fuchsia-400/10 disabled:cursor-not-allowed disabled:opacity-35"
                          >
                            {transcribingJobId === job.job_id ? <Loader2 size={14} className="animate-spin" /> : <Subtitles size={14} />} Whisper 자막
                          </button>
                        )}
                        <a href={job.source_url} target="_blank" rel="noreferrer" className="rounded-lg border border-border p-2 text-gray-400 hover:text-white" title="원본 열기"><ExternalLink size={15} /></a>
                        <button
                          type="button"
                          onClick={() => void deleteJob(job)}
                          disabled={job.running || deletingJobId === job.job_id}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-red-400/30 px-3 py-2 text-xs font-bold text-red-300 hover:bg-red-400/10 disabled:cursor-not-allowed disabled:opacity-35"
                        >
                          {deletingJobId === job.job_id ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />} 삭제
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <div className="mt-4 flex items-center gap-2 text-xs text-gray-600"><CheckCircle2 size={14} /> 삭제 확인 후 해당 순번 폴더 전체가 삭제됩니다.</div>
    </div>
  );
}
