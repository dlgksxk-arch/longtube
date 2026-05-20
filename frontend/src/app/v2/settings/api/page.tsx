/**
 * /v2/settings/api — 3영역 카드 + 키 편집 모달 + 잔액 충전 모달 (기획 §15.1).
 *
 * 카드 한 개 = 한 프로바이더. 세로로 3영역 분할:
 *   1) 상태 — last_ping_status + last_ping_at + "테스트 핑" CTA
 *   2) 키  — masked_key + "편집" CTA (모달에서 평문 입력)
 *   3) 잔액 — balance_usd + OpenAI 공식 비용 동기화
 */
"use client";

import { useCallback, useEffect, useId, useMemo, useState } from "react";
import { v2Url } from "@/lib/v2Api";
import {
  Modal,
  StatusDot,
  LoadingState,
  ErrorState,
  V2Button,
} from "@/components/v2";

interface KeyRow {
  provider: string;
  env_var: string;
  has_key: boolean;
  masked_key: string;
  last_ping_status: "ok" | "fail" | "unknown";
  last_ping_at: string | null;
  balance_usd: string | null;
  enabled: boolean;
  official_cost_sync?: OfficialCostSync | null;
}

interface OfficialCostSync {
  configured: boolean;
  status: string;
  initial_balance_usd: number | null;
  baseline_at: string | null;
  official_spend_usd: number | null;
  remaining_usd: number | null;
  last_sync_at: string | null;
  last_error: string | null;
  credential_source: string | null;
}

const PROVIDER_ROLE: Record<string, string> = {
  Anthropic: "대본",
  OpenAI: "대본/이미지/보조",
  "OpenAI Admin": "공식 비용 조회",
  ElevenLabs: "TTS · BGM",
  "fal.ai": "이미지 · 영상",
  "xAI (Grok)": "보조",
  Kling: "영상",
  Replicate: "보조",
  Runway: "영상 (보류)",
  Midjourney: "이미지 (보류)",
};

function fmtRelTime(iso: string | null): string {
  if (!iso) return "미확인";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return iso;
  const diff = Math.floor((Date.now() - t) / 1000);
  if (diff < 60) return `${diff}초 전`;
  if (diff < 3600) return `${Math.floor(diff / 60)}분 전`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}시간 전`;
  return `${Math.floor(diff / 86400)}일 전`;
}

function pingTone(s: string): { dot: "ok" | "fail" | "idle"; label: string } {
  if (s === "ok") return { dot: "ok", label: "정상" };
  if (s === "fail") return { dot: "fail", label: "실패" };
  return { dot: "idle", label: "미확인" };
}

function fmtUsd(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return `$${value.toFixed(2)}`;
}

function isoToLocalInput(iso: string | null | undefined): string {
  const d = iso ? new Date(iso) : new Date();
  if (Number.isNaN(d.getTime())) return "";
  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

function localInputToIso(value: string): string | null {
  if (!value) return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return null;
  return d.toISOString();
}

export default function V2SettingsApiPage() {
  const [rows, setRows] = useState<KeyRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [pinging, setPinging] = useState<string | null>(null);
  const [syncingOpenAI, setSyncingOpenAI] = useState(false);

  // 모달 상태 ---------------------------------------------------------------
  const [keyModalProvider, setKeyModalProvider] = useState<string | null>(null);
  const [balanceModalProvider, setBalanceModalProvider] = useState<string | null>(
    null,
  );

  const load = useCallback(async () => {
    setErr(null);
    try {
      const res = await fetch(v2Url("/v2/keys/"));
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setRows(await res.json());
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const ping = async (provider: string) => {
    setPinging(provider);
    try {
      await fetch(v2Url(`/v2/keys/ping/${encodeURIComponent(provider)}`), {
        method: "POST",
      });
      await load();
    } finally {
      setPinging(null);
    }
  };

  const syncOpenAICosts = async () => {
    setSyncingOpenAI(true);
    setErr(null);
    try {
      const res = await fetch(v2Url("/v2/keys/openai-cost-sync/sync"), {
        method: "POST",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status} ${await res.text()}`);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSyncingOpenAI(false);
    }
  };

  const activeKeyRow = useMemo(
    () => rows?.find((r) => r.provider === keyModalProvider) ?? null,
    [rows, keyModalProvider],
  );
  const activeBalanceRow = useMemo(
    () => rows?.find((r) => r.provider === balanceModalProvider) ?? null,
    [rows, balanceModalProvider],
  );

  return (
    <div className="p-6 space-y-5">
      <header>
        <h1 className="text-gray-100">API 키 · 잔액</h1>
        <p className="text-sm text-gray-500 mt-1">
          AES-GCM 암호화로 DB(api_key_vault) 에 저장됩니다. .env 파일은 건드리지
          않습니다. OpenAI는 Admin key가 있으면 공식 비용을 동기화합니다.
        </p>
      </header>

      {err && <ErrorState message={err} onRetry={load} />}
      {!rows && !err && <LoadingState />}

      {rows && (
        <ul className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {rows.map((r) => (
            <ProviderCard
              key={r.provider}
              row={r}
              pinging={pinging === r.provider}
              syncingOpenAI={syncingOpenAI && r.provider === "OpenAI"}
              onPing={() => ping(r.provider)}
              onSyncOpenAI={syncOpenAICosts}
              onOpenKey={() => setKeyModalProvider(r.provider)}
              onOpenBalance={() => setBalanceModalProvider(r.provider)}
            />
          ))}
        </ul>
      )}

      {/* 키 편집 모달 */}
      <KeyEditModal
        row={activeKeyRow}
        onClose={() => setKeyModalProvider(null)}
        onSaved={async () => {
          setKeyModalProvider(null);
          await load();
        }}
      />

      {/* 잔액 충전 모달 */}
      <BalanceEditModal
        row={activeBalanceRow}
        onClose={() => setBalanceModalProvider(null)}
        onSaved={async () => {
          setBalanceModalProvider(null);
          await load();
        }}
      />
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* 카드                                                                        */
/* -------------------------------------------------------------------------- */

function ProviderCard({
  row,
  pinging,
  syncingOpenAI,
  onPing,
  onSyncOpenAI,
  onOpenKey,
  onOpenBalance,
}: {
  row: KeyRow;
  pinging: boolean;
  syncingOpenAI: boolean;
  onPing: () => void;
  onSyncOpenAI: () => void;
  onOpenKey: () => void;
  onOpenBalance: () => void;
}) {
  const tone = pingTone(row.last_ping_status);
  const role = PROVIDER_ROLE[row.provider] ?? "—";
  const isOpenAI = row.provider === "OpenAI";
  const isOpenAIAdmin = row.provider === "OpenAI Admin";
  const sync = row.official_cost_sync;
  return (
    <li className="rounded-xl border border-border bg-bg-secondary p-4 space-y-3">
      {/* 헤더 --------------------------------------------------------- */}
      <div className="flex items-center gap-2">
        <div>
          <div className="text-sm font-semibold text-gray-100">{row.provider}</div>
          <div className="text-xs text-gray-500">
            {role} · env: <code className="text-gray-400">{row.env_var}</code>
          </div>
        </div>
        <span className="ml-auto">
          <StatusDot status={tone.dot} label={tone.label} />
        </span>
      </div>

      {/* 영역 1: 상태 ------------------------------------------------ */}
      <section className="rounded-lg border border-border bg-bg-tertiary/60 px-3 py-2 flex items-center gap-3">
        <div className="flex-1">
          <div className="text-[11px] text-gray-500 uppercase tracking-wide">상태</div>
          <div className="text-sm text-gray-100">
            {tone.label}
            <span className="text-gray-500 text-xs ml-2">
              {fmtRelTime(row.last_ping_at)}
            </span>
          </div>
        </div>
        <V2Button size="sm" variant="secondary" onClick={onPing} loading={pinging}>
          테스트 핑
        </V2Button>
      </section>

      {/* 영역 2: 키 --------------------------------------------------- */}
      <section className="rounded-lg border border-border bg-bg-tertiary/60 px-3 py-2 flex items-center gap-3">
        <div className="flex-1 min-w-0">
          <div className="text-[11px] text-gray-500 uppercase tracking-wide">키</div>
          <div className="text-sm text-gray-100 truncate font-mono">
            {row.has_key ? row.masked_key : <span className="text-gray-500 font-sans">키 미등록</span>}
          </div>
        </div>
        <V2Button size="sm" variant="secondary" onClick={onOpenKey}>
          {row.has_key ? "편집" : "등록"}
        </V2Button>
      </section>

      {!isOpenAIAdmin && (
        <section className="rounded-lg border border-border bg-bg-tertiary/60 px-3 py-2 flex items-center gap-3">
          <div className="flex-1">
            <div className="text-[11px] text-gray-500 uppercase tracking-wide">
              {isOpenAI ? "충전 기준" : "잔액"}
            </div>
            <div className="text-sm text-gray-100 tabular-nums">
              {row.balance_usd ? row.balance_usd : <span className="text-gray-500">—</span>}
            </div>
          </div>
          <V2Button size="sm" variant="secondary" onClick={onOpenBalance}>
            {isOpenAI ? "기준 설정" : "충전했어요"}
          </V2Button>
        </section>
      )}

      {isOpenAI && (
        <section className="rounded-lg border border-border bg-bg-tertiary/60 px-3 py-2 flex items-center gap-3">
          <div className="flex-1 min-w-0">
            <div className="text-[11px] text-gray-500 uppercase tracking-wide">공식 비용</div>
            <div className="text-sm text-gray-100 tabular-nums">
              {sync?.configured && sync.remaining_usd !== null
                ? `${fmtUsd(sync.remaining_usd)} 남음`
                : <span className="text-gray-500">기준 없음</span>}
            </div>
            {sync?.configured && (
              <div className="text-xs text-gray-500 truncate">
                사용 {fmtUsd(sync.official_spend_usd)} · 기준 {sync.baseline_at ? fmtRelTime(sync.baseline_at) : "미설정"} · 동기화 {fmtRelTime(sync.last_sync_at)}
              </div>
            )}
            {sync?.last_error && (
              <div className="text-xs text-red-300 truncate" title={sync.last_error}>
                {sync.last_error}
              </div>
            )}
          </div>
          <V2Button
            size="sm"
            variant="secondary"
            onClick={onSyncOpenAI}
            loading={syncingOpenAI}
            disabled={!sync?.configured}
          >
            동기화
          </V2Button>
        </section>
      )}
    </li>
  );
}

/* -------------------------------------------------------------------------- */
/* 키 편집 모달                                                                */
/* -------------------------------------------------------------------------- */

function KeyEditModal({
  row,
  onClose,
  onSaved,
}: {
  row: KeyRow | null;
  onClose: () => void;
  onSaved: () => Promise<void> | void;
}) {
  const idp = useId();
  const [value, setValue] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // 모달이 새로 열릴 때마다 초기화.
  useEffect(() => {
    setValue("");
    setErr(null);
  }, [row?.provider]);

  if (!row) return null;

  const submit = async () => {
    setSubmitting(true);
    setErr(null);
    try {
      const res = await fetch(v2Url("/v2/keys/save"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: row.provider, api_key: value }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status} ${await res.text()}`);
      await onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={!!row}
      onClose={() => !submitting && onClose()}
      title={`${row.provider} API 키`}
      widthClass="w-[520px]"
      footer={
        <>
          <V2Button variant="secondary" onClick={onClose} disabled={submitting}>
            취소
          </V2Button>
          <V2Button variant="primary" onClick={submit} loading={submitting}>
            저장
          </V2Button>
        </>
      }
    >
      <div className="space-y-3 text-sm">
        <div>
          <label htmlFor={`${idp}-key`} className="block text-xs text-gray-400 mb-1">
            새 키 (평문, 저장 시 즉시 암호화)
          </label>
          <input
            id={`${idp}-key`}
            type="password"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            autoFocus
            className="w-full bg-bg-tertiary border border-border rounded-md px-3 py-2 text-sm text-gray-100 font-mono"
            placeholder={row.has_key ? "새 키를 입력하면 덮어씁니다" : "sk-..."}
          />
          <p className="mt-1 text-xs text-gray-500">
            빈 값으로 저장하면 해당 프로바이더가 비활성화됩니다.
          </p>
        </div>
        <div className="rounded-md border border-border bg-bg-tertiary/50 px-3 py-2 text-xs text-gray-400">
          env 변수명: <code className="text-gray-300">{row.env_var}</code>
          {row.has_key && (
            <>
              <br />
              현재 값: <code className="text-gray-300">{row.masked_key}</code>
            </>
          )}
        </div>
        {err && (
          <p
            role="alert"
            className="text-xs text-red-300 bg-red-500/10 border border-red-500/40 rounded-md px-3 py-2"
          >
            {err}
          </p>
        )}
      </div>
    </Modal>
  );
}

/* -------------------------------------------------------------------------- */
/* 잔액 수정 모달                                                              */
/* -------------------------------------------------------------------------- */

function BalanceEditModal({
  row,
  onClose,
  onSaved,
}: {
  row: KeyRow | null;
  onClose: () => void;
  onSaved: () => Promise<void> | void;
}) {
  const idp = useId();
  const [value, setValue] = useState("");
  const [baselineLocal, setBaselineLocal] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setValue(row?.balance_usd ?? "");
    setBaselineLocal(isoToLocalInput(row?.official_cost_sync?.baseline_at));
    setErr(null);
  }, [row?.provider, row?.balance_usd, row?.official_cost_sync?.baseline_at]);

  if (!row) return null;
  const isOpenAI = row.provider === "OpenAI";

  const submit = async () => {
    setSubmitting(true);
    setErr(null);
    try {
      const res = await fetch(v2Url("/v2/keys/balance"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: row.provider,
          balance_usd: value,
          official_baseline_at: isOpenAI ? localInputToIso(baselineLocal) : null,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status} ${await res.text()}`);
      await onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={!!row}
      onClose={() => !submitting && onClose()}
      title={`${row.provider} 잔액`}
      widthClass="w-[420px]"
      footer={
        <>
          <V2Button variant="secondary" onClick={onClose} disabled={submitting}>
            취소
          </V2Button>
          <V2Button variant="primary" onClick={submit} loading={submitting}>
            저장
          </V2Button>
        </>
      }
    >
      <div className="space-y-3 text-sm">
        <div>
          <label htmlFor={`${idp}-bal`} className="block text-xs text-gray-400 mb-1">
            {isOpenAI ? "충전액 USD" : "현재 충전 잔액 (자유 텍스트)"}
          </label>
          <input
            id={`${idp}-bal`}
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            autoFocus
            className="w-full bg-bg-tertiary border border-border rounded-md px-3 py-2 text-sm text-gray-100 tabular-nums"
            placeholder="$25.00"
          />
          <p className="mt-1 text-xs text-gray-500">
            {isOpenAI
              ? "이 금액에서 OpenAI 공식 Costs API 사용액을 차감합니다."
              : "표기 형식 자유. 비워 두면 \"—\" 로 표시됩니다."}
          </p>
        </div>
        {isOpenAI && (
          <div>
            <label htmlFor={`${idp}-baseline`} className="block text-xs text-gray-400 mb-1">
              충전/기준 시각
            </label>
            <input
              id={`${idp}-baseline`}
              type="datetime-local"
              value={baselineLocal}
              onChange={(e) => setBaselineLocal(e.target.value)}
              className="w-full bg-bg-tertiary border border-border rounded-md px-3 py-2 text-sm text-gray-100 tabular-nums"
            />
            <p className="mt-1 text-xs text-gray-500">
              이 시각 이후의 공식 OpenAI 비용만 차감합니다.
            </p>
          </div>
        )}
        {err && (
          <p
            role="alert"
            className="text-xs text-red-300 bg-red-500/10 border border-red-500/40 rounded-md px-3 py-2"
          >
            {err}
          </p>
        )}
      </div>
    </Modal>
  );
}
