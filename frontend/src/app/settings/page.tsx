"use client";

// v1.1.55: API 설정 전용 페이지.
// - API 키 입력/교체/삭제
// - 수동 입력 잔액 (콘솔에서 확인한 숫자를 직접 입력 → 대시보드 타일에 표시)
//
// 자동 잔액 조회는 ElevenLabs 만 공식 엔드포인트가 있다. 나머지(Anthropic/OpenAI/
// fal.ai/xAI)는 일반 API 키로 잔액을 가져올 수 없어 여기에 수동 입력 칸을 둔다.

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Key,
  Save,
  Trash2,
  Eye,
  EyeOff,
  ExternalLink,
  ArrowLeft,
  CheckCircle,
  AlertCircle,
  RefreshCw,
} from "lucide-react";
import {
  apiKeysApi,
  apiBalancesApi,
  apiStatusApi,
  type ProviderInfo,
  type ApiBalanceRow,
  type ApiStatusInfo,
} from "@/lib/api";

// 화면에 표시할 제공자 고정 순서
const PROVIDERS = ["Anthropic", "OpenAI", "ElevenLabs", "fal.ai", "xAI (Grok)"];

// 제공자별 콘솔 잔액 확인 URL
const CONSOLE_URL: Record<string, string> = {
  Anthropic: "https://console.anthropic.com/settings/billing",
  OpenAI: "https://platform.openai.com/settings/organization/billing/overview",
  ElevenLabs: "https://elevenlabs.io/app/subscription",
  "fal.ai": "https://fal.ai/dashboard/billing",
  "xAI (Grok)": "https://console.x.ai/",
};

type RowState = {
  keyInput: string;
  showKey: boolean;
  amountInput: string;
  unitInput: string;
  noteInput: string;
  thresholdInput: string;
  savingKey: boolean;
  savingBalance: boolean;
  resettingSpend: boolean;
  flash: { type: "ok" | "err"; msg: string } | null;
};

const emptyRow = (): RowState => ({
  keyInput: "",
  showKey: false,
  amountInput: "",
  unitInput: "USD",
  noteInput: "",
  thresholdInput: "",
  savingKey: false,
  savingBalance: false,
  resettingSpend: false,
  flash: null,
});

export default function SettingsPage() {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [balances, setBalances] = useState<ApiBalanceRow[]>([]);
  const [statuses, setStatuses] = useState<ApiStatusInfo[]>([]);
  const [rows, setRows] = useState<Record<string, RowState>>({});
  const [loading, setLoading] = useState(true);
  const [defaultUnits, setDefaultUnits] = useState<string[]>([
    "USD",
    "KRW",
    "credits",
    "chars",
  ]);

  const load = async () => {
    setLoading(true);
    try {
      const [p, b, s] = await Promise.all([
        apiKeysApi.listProviders().catch(() => ({ providers: [] })),
        apiBalancesApi.list().catch(() => ({ balances: [], default_units: [] })),
        apiStatusApi.check().catch(() => ({ apis: [] })),
      ]);
      setProviders(p.providers || []);
      setBalances(b.balances || []);
      setStatuses(s.apis || []);
      if (b.default_units && b.default_units.length) setDefaultUnits(b.default_units);

      // 기존 rows state 는 유지하되, 새로 조회된 값으로 초기 unit 을 맞춘다.
      setRows((prev) => {
        const next = { ...prev };
        for (const pr of PROVIDERS) {
          const exists = next[pr] || emptyRow();
          const bal = (b.balances || []).find((x) => x.provider === pr);
          next[pr] = {
            ...exists,
            unitInput: bal?.unit || exists.unitInput || "USD",
          };
        }
        return next;
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const patchRow = (provider: string, patch: Partial<RowState>) => {
    setRows((prev) => ({
      ...prev,
      [provider]: { ...(prev[provider] || emptyRow()), ...patch },
    }));
  };

  const saveKey = async (provider: string) => {
    const row = rows[provider] || emptyRow();
    if (!row.keyInput.trim()) return;
    patchRow(provider, { savingKey: true, flash: null });
    try {
      await apiKeysApi.save(provider, row.keyInput.trim());
      patchRow(provider, {
        savingKey: false,
        keyInput: "",
        flash: { type: "ok", msg: "API 키 저장 완료" },
      });
      load();
    } catch (e: any) {
      patchRow(provider, {
        savingKey: false,
        flash: { type: "err", msg: e?.message || "저장 실패" },
      });
    }
  };

  const deleteKey = async (provider: string) => {
    if (!confirm(`${provider} API 키를 삭제할까요?`)) return;
    try {
      await apiKeysApi.remove(provider);
      patchRow(provider, { flash: { type: "ok", msg: "API 키 삭제 완료" } });
      load();
    } catch (e: any) {
      patchRow(provider, {
        flash: { type: "err", msg: e?.message || "삭제 실패" },
      });
    }
  };

  const saveBalance = async (provider: string) => {
    const row = rows[provider] || emptyRow();
    const amt = parseFloat(row.amountInput);
    if (Number.isNaN(amt) || amt < 0) {
      patchRow(provider, {
        flash: { type: "err", msg: "잔액은 0 이상 숫자로 입력하세요" },
      });
      return;
    }
    patchRow(provider, { savingBalance: true, flash: null });
    try {
      const th = row.thresholdInput.trim() === ""
        ? null
        : parseFloat(row.thresholdInput);
      await apiBalancesApi.save(
        provider,
        amt,
        row.unitInput || "USD",
        row.noteInput,
        th !== null && !Number.isNaN(th) ? th : null,
      );
      patchRow(provider, {
        savingBalance: false,
        amountInput: "",
        noteInput: "",
        flash: { type: "ok", msg: "잔액 저장 완료 — 대시보드에 반영됨" },
      });
      load();
    } catch (e: any) {
      patchRow(provider, {
        savingBalance: false,
        flash: { type: "err", msg: e?.message || "저장 실패" },
      });
    }
  };

  const resetSpend = async (provider: string) => {
    if (!confirm(`${provider} 지출 기준점을 지금으로 리셋할까요?\n(방금 새 크레딧을 충전했을 때 사용)`)) return;
    patchRow(provider, { resettingSpend: true, flash: null });
    try {
      await apiBalancesApi.resetSpend(provider);
      patchRow(provider, {
        resettingSpend: false,
        flash: { type: "ok", msg: "지출 리셋 완료 — 이제부터 새로 감산됩니다" },
      });
      load();
    } catch (e: any) {
      patchRow(provider, {
        resettingSpend: false,
        flash: { type: "err", msg: e?.message || "리셋 실패" },
      });
    }
  };

  const deleteBalance = async (provider: string) => {
    if (!confirm(`${provider} 수동 잔액을 삭제할까요?`)) return;
    try {
      await apiBalancesApi.remove(provider);
      patchRow(provider, { flash: { type: "ok", msg: "잔액 삭제 완료" } });
      load();
    } catch (e: any) {
      patchRow(provider, {
        flash: { type: "err", msg: e?.message || "삭제 실패" },
      });
    }
  };

  return (
    <div className="min-h-screen bg-bg-primary text-white p-8">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Link
              href="/"
              className="text-gray-400 hover:text-white flex items-center gap-1 text-sm"
            >
              <ArrowLeft size={16} /> 대시보드
            </Link>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Key size={20} className="text-accent-secondary" />
              API 설정
            </h1>
          </div>
          <button
            onClick={load}
            disabled={loading}
            className="p-2 rounded hover:bg-bg-tertiary text-gray-400 hover:text-white disabled:opacity-50"
            title="새로고침"
          >
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
          </button>
        </div>

        <p className="text-sm text-gray-400 mb-6">
          각 제공자의 API 키와 현재 잔액을 여기서 관리합니다. 잔액은 콘솔에서 직접
          확인한 값을 입력하면 대시보드 "API 연결 상태" 타일에 그대로 표시됩니다.
          (ElevenLabs 는 자동 조회가 가능해 표시만 활용됩니다.)
        </p>

        <div className="space-y-4">
          {PROVIDERS.map((provider) => {
            const pinfo = providers.find((x) => x.provider === provider);
            const bal = balances.find((x) => x.provider === provider);
            const status = statuses.find((x) => x.provider === provider);
            const row = rows[provider] || emptyRow();
            return (
              <div
                key={provider}
                className="bg-bg-secondary border border-border rounded-lg p-5"
              >
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <h2 className="text-base font-semibold">{provider}</h2>
                    {pinfo?.has_key ? (
                      <span className="text-[11px] text-green-400 bg-green-400/10 px-2 py-0.5 rounded">
                        키 설정됨
                      </span>
                    ) : (
                      <span className="text-[11px] text-gray-500 bg-gray-500/10 px-2 py-0.5 rounded">
                        키 없음
                      </span>
                    )}
                    {status && (
                      <span
                        className="text-[11px] text-gray-400 truncate max-w-[320px]"
                        title={status.detail}
                      >
                        · {status.detail}
                      </span>
                    )}
                    {/* v1.1.64: 파이프라인 사용 단계 배지 */}
                    {status?.used_in_steps && status.used_in_steps.length > 0 && (
                      <div className="flex flex-wrap gap-1 ml-1">
                        {status.used_in_steps.map((u) => (
                          <span
                            key={u.step}
                            title={`${u.label} 단계에서 사용 — ${u.models.join(", ")}`}
                            className="inline-flex items-center gap-0.5 px-1.5 py-[1px] rounded border border-border bg-bg-tertiary text-[10px] text-gray-300"
                          >
                            <span className="text-[9px] text-gray-500">{u.step}</span>
                            <span>{u.label}</span>
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <a
                    href={CONSOLE_URL[provider] || "#"}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-accent-primary hover:text-purple-300 flex items-center gap-1"
                  >
                    <ExternalLink size={12} /> 콘솔에서 확인
                  </a>
                </div>

                {/* Row 1: API Key */}
                <div className="grid grid-cols-12 gap-3 items-center mb-3">
                  <label className="col-span-2 text-xs text-gray-400">
                    API Key
                    {pinfo?.has_key && (
                      <div className="text-[10px] text-gray-500 mt-0.5">
                        현재: <code>{pinfo.masked_key}</code>
                      </div>
                    )}
                  </label>
                  <div className="col-span-7 relative">
                    <input
                      type={row.showKey ? "text" : "password"}
                      value={row.keyInput}
                      onChange={(e) =>
                        patchRow(provider, { keyInput: e.target.value })
                      }
                      placeholder={
                        pinfo?.has_key
                          ? "새 키로 교체하려면 입력..."
                          : "API 키 입력"
                      }
                      className="w-full bg-bg-primary border border-border rounded-lg px-3 py-2 pr-10 text-sm font-mono focus:outline-none focus:border-accent-primary"
                    />
                    <button
                      type="button"
                      onClick={() =>
                        patchRow(provider, { showKey: !row.showKey })
                      }
                      className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-500 hover:text-gray-300"
                    >
                      {row.showKey ? <EyeOff size={14} /> : <Eye size={14} />}
                    </button>
                  </div>
                  <div className="col-span-3 flex gap-2">
                    <button
                      onClick={() => saveKey(provider)}
                      disabled={row.savingKey || !row.keyInput.trim()}
                      className="flex-1 bg-accent-primary hover:bg-purple-600 text-white px-3 py-2 rounded text-sm font-medium transition-colors disabled:opacity-50 flex items-center justify-center gap-1"
                    >
                      <Save size={12} />
                      {row.savingKey ? "저장 중" : "키 저장"}
                    </button>
                    {pinfo?.has_key && (
                      <button
                        onClick={() => deleteKey(provider)}
                        className="p-2 rounded text-red-400 hover:bg-red-400/10"
                        title="키 삭제"
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                </div>

                {/* Row 2: 잔액 */}
                <div className="grid grid-cols-12 gap-3 items-center">
                  <label className="col-span-2 text-xs text-gray-400">
                    현재 잔액
                    {bal?.has_balance && (
                      <div className={`text-[10px] mt-0.5 ${bal.low ? "text-red-400" : "text-green-400"}`}>
                        남음: {bal.display}
                      </div>
                    )}
                    {bal?.has_balance && bal.display_initial && bal.display_initial !== bal.display && (
                      <div className="text-[10px] text-gray-500">
                        초기: {bal.display_initial}
                        {bal.spent != null && bal.spent > 0 && (
                          <> · 지출: ${bal.spent.toFixed(4)}</>
                        )}
                      </div>
                    )}
                  </label>
                  <div className="col-span-2">
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={row.amountInput}
                      onChange={(e) =>
                        patchRow(provider, { amountInput: e.target.value })
                      }
                      placeholder={
                        bal?.initial_amount != null
                          ? String(bal.initial_amount)
                          : "초기 잔액"
                      }
                      className="w-full bg-bg-primary border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-accent-primary"
                    />
                  </div>
                  <div className="col-span-2">
                    <select
                      value={row.unitInput}
                      onChange={(e) =>
                        patchRow(provider, { unitInput: e.target.value })
                      }
                      className="w-full bg-bg-primary border border-border rounded-lg px-2 py-2 text-sm focus:outline-none focus:border-accent-primary"
                    >
                      {defaultUnits.map((u) => (
                        <option key={u} value={u}>
                          {u}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="col-span-2">
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={row.thresholdInput}
                      onChange={(e) =>
                        patchRow(provider, { thresholdInput: e.target.value })
                      }
                      placeholder={
                        bal?.low_threshold != null ? `경고: ${bal.low_threshold}` : "경고선(옵션)"
                      }
                      className="w-full bg-bg-primary border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-accent-primary"
                      title="남은 잔액이 이 값 미만이면 대시보드에 빨간 경고가 뜹니다"
                    />
                  </div>
                  <div className="col-span-1">
                    <input
                      type="text"
                      value={row.noteInput}
                      onChange={(e) =>
                        patchRow(provider, { noteInput: e.target.value })
                      }
                      placeholder="메모"
                      className="w-full bg-bg-primary border border-border rounded-lg px-2 py-2 text-sm focus:outline-none focus:border-accent-primary"
                    />
                  </div>
                  <div className="col-span-3 flex gap-2">
                    <button
                      onClick={() => saveBalance(provider)}
                      disabled={row.savingBalance || !row.amountInput}
                      className="flex-1 bg-accent-secondary hover:bg-yellow-600 text-black px-2 py-2 rounded text-xs font-medium transition-colors disabled:opacity-50 flex items-center justify-center gap-1"
                    >
                      <Save size={12} />
                      {row.savingBalance ? "저장" : "잔액 저장"}
                    </button>
                    {bal?.has_balance && (
                      <button
                        onClick={() => resetSpend(provider)}
                        disabled={row.resettingSpend}
                        className="p-2 rounded text-blue-400 hover:bg-blue-400/10 disabled:opacity-50"
                        title="충전 후 지출 기준점 리셋"
                      >
                        <RefreshCw size={14} className={row.resettingSpend ? "animate-spin" : ""} />
                      </button>
                    )}
                    {bal?.has_balance && (
                      <button
                        onClick={() => deleteBalance(provider)}
                        className="p-2 rounded text-red-400 hover:bg-red-400/10"
                        title="잔액 삭제"
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                </div>

                {row.flash && (
                  <div
                    className={`mt-3 flex items-center gap-2 text-xs ${
                      row.flash.type === "ok"
                        ? "text-green-400"
                        : "text-red-400"
                    }`}
                  >
                    {row.flash.type === "ok" ? (
                      <CheckCircle size={12} />
                    ) : (
                      <AlertCircle size={12} />
                    )}
                    {row.flash.msg}
                  </div>
                )}
                {bal?.has_balance && bal.updated_at && (
                  <div className="mt-2 text-[10px] text-gray-500">
                    잔액 업데이트: {new Date(bal.updated_at).toLocaleString("ko-KR")}
                    {bal.note ? ` · ${bal.note}` : ""}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {loading && (
          <div className="mt-6 text-center text-sm text-gray-500 flex items-center justify-center gap-2">
            <RefreshCw size={12} className="animate-spin" /> 불러오는 중...
          </div>
        )}
      </div>
    </div>
  );
}
