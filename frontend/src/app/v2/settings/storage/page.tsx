/**
 * /v2/settings/storage — 저장소 경로 + 디스크 사용량 (기획 §4, §15.3).
 *
 * v2 에서는 경로를 "조회 + 복사" 만 허용한다. 실제 변경은 `.env` 수정 +
 * 프로세스 재시작으로 안내 (기존 파일 이동 금지 규칙을 지키기 위함).
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import { v2Url } from "@/lib/v2Api";
import { LoadingState, ErrorState, V2Button } from "@/components/v2";

interface StorageInfo {
  data_dir: string;
  legacy_data_dir: string;
  base_dir: string;
  disk_total_bytes: number;
  disk_free_bytes: number;
  data_dir_bytes: number;
  legacy_bytes: number;
  presets_bytes: number;
  tasks_bytes: number;
}

const LOW_SPACE_THRESHOLD = 10 * 1024 ** 3; // 10 GB

function fmtGb(bytes: number): string {
  if (!bytes) return "0.00 GB";
  return (bytes / 1024 ** 3).toFixed(2) + " GB";
}

function fmtMb(bytes: number): string {
  return (bytes / 1024 ** 2).toFixed(1) + " MB";
}

function fmtSmart(bytes: number): string {
  if (bytes < 1024 ** 3) return fmtMb(bytes);
  return fmtGb(bytes);
}

export default function V2StoragePage() {
  const [info, setInfo] = useState<StorageInfo | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const res = await fetch(v2Url("/v2/storage/info"));
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setInfo(await res.json());
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const copy = async (key: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(key);
      setTimeout(() => setCopied((c) => (c === key ? null : c)), 1500);
    } catch {
      // 무시
    }
  };

  if (err) {
    return (
      <div className="p-6">
        <ErrorState message={err} onRetry={load} />
      </div>
    );
  }
  if (!info) {
    return (
      <div className="p-6">
        <LoadingState />
      </div>
    );
  }

  const used = info.disk_total_bytes - info.disk_free_bytes;
  const usedRatio =
    info.disk_total_bytes > 0 ? used / info.disk_total_bytes : 0;
  const lowSpace = info.disk_free_bytes > 0 && info.disk_free_bytes < LOW_SPACE_THRESHOLD;

  const paths: Array<{ key: string; label: string; value: string }> = [
    { key: "data", label: "DATA_DIR", value: info.data_dir },
    { key: "legacy", label: "LEGACY_DATA_DIR", value: info.legacy_data_dir },
    { key: "base", label: "BASE_DIR", value: info.base_dir },
  ];

  const subdirs: Array<{ key: string; label: string; bytes: number }> = [
    { key: "data", label: "data_dir (전체)", bytes: info.data_dir_bytes },
    { key: "legacy", label: "legacy", bytes: info.legacy_bytes },
    { key: "presets", label: "presets/", bytes: info.presets_bytes },
    { key: "tasks", label: "tasks/", bytes: info.tasks_bytes },
  ];
  const maxSub = Math.max(1, ...subdirs.map((d) => d.bytes));

  return (
    <div className="p-6 space-y-5">
      <header className="flex items-start gap-3">
        <div className="flex-1">
          <h1 className="text-gray-100">저장소</h1>
          <p className="text-sm text-gray-500 mt-1">
            결과 파일이 저장되는 경로와 디스크 현황. 경로 변경은{" "}
            <code className="text-gray-400">.env</code> 의 DATA_DIR 수정 +
            재시작으로 적용됩니다 (기존 파일은 이동하지 않습니다).
          </p>
        </div>
        <V2Button size="sm" variant="secondary" onClick={load}>
          새로고침
        </V2Button>
      </header>

      {/* 디스크 사용 --------------------------------------------------- */}
      <section
        className={`rounded-xl border p-5 ${
          lowSpace
            ? "border-red-500/50 bg-red-500/5"
            : "border-border bg-bg-secondary"
        }`}
      >
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-gray-200">디스크</h2>
          {lowSpace && (
            <span className="text-xs font-semibold text-red-300 border border-red-500/50 rounded px-1.5 py-0.5">
              여유 공간 부족 (&lt; 10 GB)
            </span>
          )}
        </div>
        <div className="flex items-end justify-between text-xs text-gray-400 mb-1.5">
          <span>
            사용 <span className="text-gray-100 tabular-nums">{fmtGb(used)}</span>{" "}
            / 전체 <span className="text-gray-100 tabular-nums">{fmtGb(info.disk_total_bytes)}</span>
          </span>
          <span>
            여유 <span className="text-gray-100 tabular-nums">{fmtGb(info.disk_free_bytes)}</span>
          </span>
        </div>
        <div className="h-2 rounded bg-bg-tertiary overflow-hidden">
          <div
            className={`h-full ${
              usedRatio > 0.9 ? "bg-red-400" : usedRatio > 0.7 ? "bg-amber-400" : "bg-sky-400"
            }`}
            style={{ width: `${Math.max(2, usedRatio * 100)}%` }}
          />
        </div>
      </section>

      {/* 경로 --------------------------------------------------------- */}
      <section className="rounded-xl border border-border bg-bg-secondary p-5">
        <h2 className="text-sm font-semibold text-gray-200 mb-3">경로</h2>
        <ul className="space-y-2">
          {paths.map((p) => (
            <li
              key={p.key}
              className="flex items-center gap-3 rounded border border-border bg-bg-tertiary/60 px-3 py-2"
            >
              <span className="text-xs uppercase tracking-wide text-gray-500 w-32 shrink-0">
                {p.label}
              </span>
              <code className="flex-1 text-sm text-gray-100 font-mono break-all">
                {p.value}
              </code>
              <V2Button
                size="sm"
                variant="ghost"
                onClick={() => copy(p.key, p.value)}
              >
                {copied === p.key ? "복사됨" : "복사"}
              </V2Button>
            </li>
          ))}
        </ul>
      </section>

      {/* 하위 폴더 사용량 ------------------------------------------- */}
      <section className="rounded-xl border border-border bg-bg-secondary p-5">
        <h2 className="text-sm font-semibold text-gray-200 mb-3">하위 폴더 사용량</h2>
        <ul className="space-y-2">
          {subdirs.map((d) => {
            const ratio = d.bytes / maxSub;
            return (
              <li key={d.key} className="space-y-1">
                <div className="flex items-center justify-between text-xs text-gray-400">
                  <span>{d.label}</span>
                  <span className="tabular-nums text-gray-100">{fmtSmart(d.bytes)}</span>
                </div>
                <div className="h-1.5 rounded bg-bg-tertiary overflow-hidden">
                  <div
                    className="h-full bg-sky-400/80"
                    style={{ width: `${Math.max(1, ratio * 100)}%` }}
                  />
                </div>
              </li>
            );
          })}
        </ul>
        <p className="mt-3 text-xs text-gray-500">
          막대는 4 항목 중 최대값 대비 상대 비율입니다 (절대 비율 아님).
        </p>
      </section>
    </div>
  );
}
