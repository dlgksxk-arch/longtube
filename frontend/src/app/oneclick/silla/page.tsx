"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  FileSpreadsheet,
  FolderOpen,
  Loader2,
  Plus,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { api } from "@/lib/api";


interface WorkbookItem {
  filename: string;
  path: string;
  valid: boolean;
  errors: string[];
  size_bytes?: number;
  modified_at?: string;
  episode_number?: number;
  episode_code?: string;
  title?: string;
  cut_count?: number;
  krea_prompt_count?: number;
  actual_asset_count?: number;
  h3_tag_count?: number;
  shorts_cut_count?: number;
  quote_count?: number;
  speaker_count?: number;
  source_sha256?: string;
}

interface WorkbookResponse {
  factory_version: number;
  source_schema: string;
  source_root: string;
  source_root_exists: boolean;
  actual_asset_root: string;
  actual_asset_root_exists: boolean;
  workbooks: WorkbookItem[];
}

interface SillaPreset {
  id: string;
  title: string;
  topic: string;
  status: string;
  config: Record<string, unknown>;
}

interface SillaRegistration {
  registered: boolean;
  episode_code: string;
  prepared_script: string;
  prepared_script_sha256: string;
  source_sha256: string;
}

function formatBytes(value = 0) {
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))}KB`;
  return `${(value / 1024 / 1024).toFixed(1)}MB`;
}

export default function SillaFactoryPage() {
  const [source, setSource] = useState<WorkbookResponse | null>(null);
  const [presets, setPresets] = useState<SillaPreset[]>([]);
  const [selectedPreset, setSelectedPreset] = useState("");
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [importing, setImporting] = useState<string | null>(null);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [imported, setImported] = useState<Record<string, string>>({});
  const [registrations, setRegistrations] = useState<Record<string, SillaRegistration>>({});
  const [registrationPresetId, setRegistrationPresetId] = useState("");
  const [lastCheckedAt, setLastCheckedAt] = useState("");
  const loadRequestRef = useRef(0);
  const loadAbortRef = useRef<AbortController | null>(null);

  const load = useCallback(async (manual = false) => {
    const requestId = loadRequestRef.current + 1;
    loadRequestRef.current = requestId;
    loadAbortRef.current?.abort();
    const controller = new AbortController();
    loadAbortRef.current = controller;
    setLoading(true);
    setMessage(null);
    try {
      const refreshKey = Date.now();
      const [workbookResult, presetResult] = await Promise.allSettled([
        api.getWithTimeout(
          `/factory-v5/silla/workbooks?refresh=${refreshKey}`,
          60_000,
          controller.signal,
        ),
        api.get(`/factory-v5/silla/presets?refresh=${refreshKey}`, controller.signal),
      ]);
      if (requestId !== loadRequestRef.current) return;

      if (workbookResult.status === "fulfilled") {
        const workbookData = workbookResult.value as WorkbookResponse;
        setSource(workbookData);
        if (manual) setImported({});
        const checkedAt = new Date().toLocaleTimeString("ko-KR", {
          hour12: false,
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        });
        setLastCheckedAt(checkedAt);
        if (manual && presetResult.status === "fulfilled") {
          const valid = workbookData.workbooks.filter((item) => item.valid).length;
          setMessage({
            kind: "ok",
            text: `새로 확인 완료: ${workbookData.workbooks.length}개 파일 중 ${valid}개 정상 · ${checkedAt}`,
          });
        }
      }

      if (presetResult.status === "fulfilled") {
        const presetData = presetResult.value as SillaPreset[];
        setPresets(presetData);
        setSelectedPreset((current) => current || presetData[0]?.id || "");
      }

      const errors: string[] = [];
      if (workbookResult.status === "rejected") {
        errors.push(`대본 검증 실패: ${(workbookResult.reason as Error).message}`);
      }
      if (presetResult.status === "rejected") {
        errors.push(`프리셋 확인 실패: ${(presetResult.reason as Error).message}`);
      }
      if (errors.length > 0) {
        setMessage({ kind: "error", text: errors.join(" / ") });
      }
    } catch (error) {
      if (requestId !== loadRequestRef.current) return;
      setMessage({ kind: "error", text: (error as Error).message });
    } finally {
      if (requestId === loadRequestRef.current) {
        setLoading(false);
        if (loadAbortRef.current === controller) loadAbortRef.current = null;
      }
    }
  }, []);

  useEffect(() => {
    void load(false);
    return () => loadAbortRef.current?.abort();
  }, [load]);

  useEffect(() => {
    let cancelled = false;
    if (!selectedPreset) {
      setRegistrations({});
      setRegistrationPresetId("");
      return;
    }
    setRegistrationPresetId("");
    void api.get(`/factory-v5/silla/registrations?project_id=${encodeURIComponent(selectedPreset)}`)
      .then((result) => {
        if (cancelled) return;
        setRegistrations(result.registrations || {});
        setRegistrationPresetId(selectedPreset);
      })
      .catch((error) => {
        if (cancelled) return;
        setRegistrations({});
        setRegistrationPresetId(selectedPreset);
        setMessage({ kind: "error", text: `대본 등록 상태 확인 실패: ${(error as Error).message}` });
      });
    return () => { cancelled = true; };
  }, [selectedPreset, lastCheckedAt]);

  const createPreset = async () => {
    setCreating(true);
    setMessage(null);
    try {
      const preset = await api.post("/factory-v5/silla/presets");
      setPresets((current) => [preset, ...current]);
      setSelectedPreset(preset.id);
      setMessage({ kind: "ok", text: `신라사 전용 프리셋을 만들었습니다. (${preset.id})` });
    } catch (error) {
      setMessage({ kind: "error", text: (error as Error).message });
    } finally {
      setCreating(false);
    }
  };

  const importWorkbook = async (workbook: WorkbookItem) => {
    if (!selectedPreset || !workbook.valid) return;
    setImporting(workbook.filename);
    setMessage(null);
    try {
      const result = await api.postWithTimeout(
        "/factory-v5/silla/import",
        { filename: workbook.filename, project_id: selectedPreset },
        120_000,
      );
      setImported((current) => ({
        ...current,
        [workbook.filename]: result.import.prepared_script,
      }));
      setRegistrations((current) => ({
        ...current,
        [workbook.filename]: {
          registered: true,
          episode_code: workbook.episode_code || "",
          prepared_script: result.import.prepared_script,
          prepared_script_sha256: result.import.prepared_script_sha256,
          source_sha256: workbook.source_sha256 || "",
        },
      }));
      setMessage({
        kind: "ok",
        text: `${workbook.episode_code} 대본 등록 완료. 제작 큐는 변경하지 않았습니다.`,
      });
    } catch (error) {
      setMessage({ kind: "error", text: (error as Error).message });
    } finally {
      setImporting(null);
    }
  };

  const validCount = source?.workbooks.filter((item) => item.valid).length || 0;

  return (
    <div className="min-h-full bg-bg-primary px-5 py-6 lg:px-8 lg:py-8">
      <div className="mx-auto max-w-6xl">
        <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="mb-2 flex items-center gap-2 text-sm font-bold text-amber-300">
              <ShieldCheck size={17} /> 공장 V5 · 원본 보존형 입력
            </div>
            <h1 className="text-3xl font-black text-white">신라사 제작</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-400">
              에피소드당 XLSX 한 파일과 외부 실제사진 경로를 함께 검증해 선택한 신라사 프리셋에 대본으로 등록합니다.
              XLSX 내장 이미지는 차단하며 원본 XLSX와 기존 제작 큐, 기존 대본은 변경하지 않습니다.
            </p>
          </div>
          <button
            onClick={() => void load(true)}
            disabled={loading}
            className="flex items-center gap-2 rounded-lg border border-border bg-bg-secondary px-4 py-2.5 text-sm font-bold text-gray-200 hover:border-accent-primary disabled:opacity-50"
          >
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
            {loading ? "확인 중" : "새로 확인"}
          </button>
        </div>

        <div className="mb-6 grid gap-4 md:grid-cols-3">
          <div className="rounded-xl border border-border bg-bg-secondary p-4 md:col-span-2">
            <div className="mb-2 flex items-center gap-2 text-sm font-bold text-gray-200">
              <FolderOpen size={17} className="text-accent-primary" /> 대본 원본 폴더
            </div>
            <div className="break-all rounded-lg bg-black/20 px-3 py-2 font-mono text-sm text-gray-300">
              {source?.source_root || "확인 중..."}
            </div>
            <div className="mb-1 mt-3 text-xs font-bold text-gray-500">실제사진 저장소</div>
            <div className="break-all rounded-lg bg-black/20 px-3 py-2 font-mono text-sm text-gray-300">
              {source?.actual_asset_root || "확인 중..."}
            </div>
          </div>
          <div className="rounded-xl border border-border bg-bg-secondary p-4">
            <div className="mb-2 flex items-center gap-2 text-sm font-bold text-gray-200">
              <Database size={17} className="text-emerald-300" /> 검증 결과
            </div>
            <div className="text-2xl font-black text-white">
              {validCount}<span className="ml-1 text-sm font-medium text-gray-500">/ {source?.workbooks.length || 0} 파일</span>
            </div>
            <div className="mt-2 text-xs text-gray-500">
              최근 확인 {lastCheckedAt || "-"}
            </div>
          </div>
        </div>

        <section className="mb-6 rounded-xl border border-border bg-bg-secondary p-5">
          <div className="flex flex-wrap items-end gap-3">
            <label className="min-w-[260px] flex-1">
              <span className="mb-2 block text-sm font-bold text-gray-200">대본 등록 대상 신라사 프리셋</span>
              <select
                value={selectedPreset}
                onChange={(event) => setSelectedPreset(event.target.value)}
                className="w-full rounded-lg border border-border bg-bg-primary px-3 py-3 text-sm text-white outline-none focus:border-accent-primary"
              >
                <option value="">전용 프리셋을 먼저 만드세요</option>
                {presets.map((preset) => (
                  <option key={preset.id} value={preset.id}>{preset.title} · {preset.id}</option>
                ))}
              </select>
            </label>
            <button
              onClick={createPreset}
              disabled={creating}
              className="flex items-center gap-2 rounded-lg bg-accent-primary px-4 py-3 text-sm font-black text-white hover:bg-purple-600 disabled:opacity-50"
            >
              {creating ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />}
              신라사 전용 프리셋 생성
            </button>
          </div>
          <p className="mt-3 text-xs text-gray-500">
            기존 프리셋에는 등록할 수 없습니다. 같은 EP 번호의 백제사·유럽사 대본과 충돌하지 않도록 전용 프리셋만 허용합니다.
          </p>
        </section>

        {message && (
          <div className={`mb-5 flex items-start gap-2 rounded-lg border px-4 py-3 text-sm ${
            message.kind === "ok"
              ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-200"
              : "border-red-400/30 bg-red-400/10 text-red-200"
          }`}>
            {message.kind === "ok" ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}
            <span>{message.text}</span>
          </div>
        )}

        <div className="space-y-4">
          {loading && !source ? (
            <div className="flex items-center justify-center gap-2 rounded-xl border border-border bg-bg-secondary py-16 text-gray-400">
              <Loader2 size={20} className="animate-spin" /> XLSX 구조와 외부 실제사진을 확인하고 있습니다.
            </div>
          ) : source?.workbooks.map((workbook) => {
            const persistedRegistration = registrations[workbook.filename];
            const persistedIsCurrent = Boolean(
              persistedRegistration?.registered
              && persistedRegistration.source_sha256
              && persistedRegistration.source_sha256 === workbook.source_sha256,
            );
            const registeredPath = imported[workbook.filename]
              || (persistedIsCurrent ? persistedRegistration.prepared_script : "");
            const registrationReady = registrationPresetId === selectedPreset;
            return (
            <article
              key={workbook.filename}
              className={`rounded-xl border bg-bg-secondary p-5 ${
                workbook.valid ? "border-border" : "border-red-400/40"
              }`}
            >
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="mb-1 flex flex-wrap items-center gap-2">
                    <FileSpreadsheet size={20} className={workbook.valid ? "text-emerald-300" : "text-red-300"} />
                    <h2 className="truncate text-lg font-black text-white">
                      {workbook.episode_code || "검증 실패"} {workbook.title || workbook.filename}
                    </h2>
                    {workbook.valid ? (
                      <span className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2 py-0.5 text-xs font-bold text-emerald-300">정상</span>
                    ) : (
                      <span className="rounded-full border border-red-400/30 bg-red-400/10 px-2 py-0.5 text-xs font-bold text-red-300">차단</span>
                    )}
                    {registeredPath && (
                      <span className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2 py-0.5 text-xs font-bold text-emerald-300">
                        대본 등록됨
                      </span>
                    )}
                  </div>
                  <div className="font-mono text-xs text-gray-500">
                    {workbook.filename} · {formatBytes(workbook.size_bytes)}
                  </div>
                  {workbook.valid ? (
                    <div className="mt-4 grid grid-cols-3 gap-2 sm:grid-cols-6">
                      {[
                        ["전체 컷", workbook.cut_count],
                        ["KREA", workbook.krea_prompt_count],
                        ["실제자료", workbook.actual_asset_count],
                        ["H3", workbook.h3_tag_count],
                        ["숏츠", workbook.shorts_cut_count],
                        ["명대사", workbook.quote_count],
                      ].map(([label, value]) => (
                        <div key={String(label)} className="rounded-lg bg-bg-primary/70 px-3 py-2 text-center">
                          <div className="text-xs text-gray-500">{label}</div>
                          <div className="mt-1 font-mono text-base font-black text-gray-100">{value}</div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <ul className="mt-3 space-y-1 text-sm text-red-200">
                      {(workbook.errors || []).map((error) => <li key={error}>· {error}</li>)}
                    </ul>
                  )}
                  {registeredPath && (
                    <div className="mt-3 break-all text-xs text-emerald-300">
                      대본 등록본: {registeredPath}
                    </div>
                  )}
                </div>
                <button
                  onClick={() => void importWorkbook(workbook)}
                  disabled={!workbook.valid || !selectedPreset || !registrationReady || importing !== null || Boolean(registeredPath)}
                  className="flex items-center gap-2 rounded-lg border border-accent-primary/50 bg-accent-primary/10 px-4 py-2.5 text-sm font-black text-accent-primary hover:bg-accent-primary/20 disabled:cursor-not-allowed disabled:opacity-35"
                >
                  {importing === workbook.filename ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : registeredPath ? (
                    <CheckCircle2 size={16} />
                  ) : (
                    <Database size={16} />
                  )}
                  {importing === workbook.filename
                    ? "대본 등록 중"
                    : registeredPath
                      ? "대본 등록 완료"
                      : !registrationReady
                        ? "등록 상태 확인 중"
                      : "대본 등록"}
                </button>
              </div>
            </article>
            );
          })}

          {!loading && source && source.workbooks.length === 0 && (
            <div className="rounded-xl border border-dashed border-border bg-bg-secondary py-16 text-center text-gray-500">
              폴더에 XLSX 파일이 없습니다.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
