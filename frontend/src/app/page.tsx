"use client";

import { useEffect, useState } from "react";
import { Plus, Play, Trash2, ExternalLink, RefreshCw, CheckCircle, XCircle, AlertCircle, MinusCircle, Key, Youtube as YoutubeIcon, Clock, DollarSign } from "lucide-react";
import { api, apiStatusApi, type ApiStatusInfo, type ProjectEstimate } from "@/lib/api";
import { APP_VERSION } from "@/lib/version";
import { formatDurationKo, formatKrw, costTierClasses } from "@/lib/format";
import ApiKeyModal from "@/components/common/ApiKeyModal";

interface Project {
  id: string;
  title: string;
  topic: string;
  status: string;
  current_step: number;
  total_cuts: number;
  youtube_url: string | null;
  api_cost: number;
  created_at: string;
  // v1.1.33: 서버가 계산한 예상 소요시간/비용
  estimate?: ProjectEstimate;
}


const STATUS_STYLES: Record<string, { icon: typeof CheckCircle; color: string; bg: string }> = {
  active:         { icon: CheckCircle,  color: "text-green-400",  bg: "bg-green-400/10" },
  configured:     { icon: CheckCircle,  color: "text-blue-400",   bg: "bg-blue-400/10" },
  not_configured: { icon: MinusCircle,  color: "text-gray-500",   bg: "bg-gray-500/10" },
  invalid:        { icon: XCircle,      color: "text-red-400",    bg: "bg-red-400/10" },
  error:          { icon: AlertCircle,  color: "text-amber-400",  bg: "bg-amber-400/10" },
};

export default function Dashboard() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [topic, setTopic] = useState("");
  const [creating, setCreating] = useState(false);
  const [apiStatuses, setApiStatuses] = useState<ApiStatusInfo[]>([]);
  const [loadingApis, setLoadingApis] = useState(false);
  const [keyModalProvider, setKeyModalProvider] = useState<string | null>(null);
  const [keyModalBalanceUrl, setKeyModalBalanceUrl] = useState<string | undefined>();

  useEffect(() => {
    loadProjects();
    loadApiStatus();
  }, []);

  const loadProjects = async () => {
    try {
      const data = await api.get("/projects");
      setProjects(data);
    } catch {}
  };

  const loadApiStatus = async () => {
    setLoadingApis(true);
    try {
      const data = await apiStatusApi.check();
      setApiStatuses(data.apis || []);
    } catch {}
    setLoadingApis(false);
  };

  const createProject = async () => {
    if (!topic.trim()) return;
    setCreating(true);
    await api.post("/projects", { topic });
    setTopic("");
    setCreating(false);
    loadProjects();
  };

  const deleteProject = async (id: string) => {
    if (!confirm("프리셋을 삭제하시겠습니까?")) return;
    await api.delete(`/projects/${id}`);
    loadProjects();
  };

  const statusColor: Record<string, string> = {
    draft: "text-gray-400",
    processing: "text-accent-primary",
    paused: "text-accent-warning",
    completed: "text-accent-success",
    failed: "text-accent-danger",
  };

  return (
    <div className="max-w-6xl mx-auto p-8">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-3">
          <h1 className="text-3xl font-bold">LongTube</h1>
          <span className="text-xs text-gray-500 border border-gray-700 rounded px-2 py-0.5 font-mono">v{APP_VERSION}</span>
        </div>
        <div className="flex items-center gap-2">
          <a
            href="/youtube"
            className="bg-red-600 hover:bg-red-500 text-white font-semibold px-4 py-2 rounded-lg flex items-center gap-2 text-sm"
          >
            <YoutubeIcon size={16} />
            YouTube Studio
          </a>
          {/* v1.1.55: API 설정 페이지 링크 */}
          <a
            href="/settings"
            className="bg-bg-secondary border border-border text-gray-300 hover:text-white hover:border-accent-primary/50 font-semibold px-4 py-2 rounded-lg flex items-center gap-2 text-sm transition-colors"
          >
            <Key size={14} />
            API 설정
          </a>
          {/* v1.1.49: 딸깍 대시보드 링크 + 기존 모달 버튼 */}
          <a
            href="/oneclick"
            className="bg-accent-primary/15 border border-accent-primary/40 text-accent-primary hover:bg-accent-primary/25 font-semibold px-4 py-2 rounded-lg flex items-center gap-2 text-sm transition-colors"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/></svg>
            딸깍 대시보드
          </a>
        </div>
      </div>
      <p className="text-gray-400 mb-8">
        프리셋은 모델·자막·캐릭터 구성을 재사용하는 틀입니다. Studio 에서 프리셋을 다듬고,
        상단의 <span className="text-accent-primary">딸깍 대시보드</span> 버튼으로 주제 리스트를
        채워 두면 매일 지정한 시각에 한 건씩 자동으로 만들어냅니다.
      </p>

      {/* API Status Panel */}
      <div className="bg-bg-secondary border border-border rounded-lg p-5 mb-8">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Key size={18} className="text-accent-secondary" />
            <h2 className="text-sm font-semibold text-gray-300">API 연결 상태</h2>
          </div>
          <button
            onClick={loadApiStatus}
            disabled={loadingApis}
            className="p-1.5 rounded hover:bg-bg-tertiary text-gray-400 hover:text-white transition-colors disabled:opacity-50"
          >
            <RefreshCw size={14} className={loadingApis ? "animate-spin" : ""} />
          </button>
        </div>
        {/* v1.1.55: 잔액 부족 경고 배너 — low_threshold 미만인 제공자가 있으면 표시 */}
        {apiStatuses.some((s) => s.manual_balance?.low) && (
          <div className="mb-3 p-3 rounded-lg border border-red-500/60 bg-red-500/10 flex items-start gap-2">
            <AlertCircle size={16} className="text-red-400 mt-0.5 flex-shrink-0" />
            <div className="text-xs">
              <div className="font-semibold text-red-300 mb-0.5">잔액 부족 경고</div>
              <div className="text-red-200/90">
                {apiStatuses
                  .filter((s) => s.manual_balance?.low)
                  .map((s) => `${s.provider}: ${s.manual_balance?.display ?? s.balance}`)
                  .join(" · ")}
                {" — "}
                <a href="/settings" className="underline hover:text-white">
                  API 설정에서 충전 후 리셋
                </a>
              </div>
            </div>
          </div>
        )}
        <div className="grid grid-cols-4 gap-3">
          {apiStatuses.map((s, i) => {
            const style = STATUS_STYLES[s.status] || STATUS_STYLES.error;
            const Icon = style.icon;
            const isLow = !!s.manual_balance?.low;
            return (
              <button
                key={i}
                onClick={() => { setKeyModalProvider(s.provider); setKeyModalBalanceUrl(s.balance_url); }}
                className={`${style.bg} border ${isLow ? "border-red-500/60" : "border-border"} rounded-lg px-3 py-2.5 text-left hover:border-accent-primary/50 transition-colors cursor-pointer`}
              >
                <div className="flex items-center gap-2 mb-1">
                  <Icon size={14} className={style.color} />
                  <span className="text-xs font-semibold text-gray-200">{s.provider}</span>
                </div>
                {s.balance ? (
                  <p className={`text-sm font-bold ${isLow ? "text-red-400" : "text-green-400"}`}>
                    {s.balance}
                    {s.manual && (
                      <span
                        className="ml-1 text-[9px] text-amber-300 font-normal align-middle"
                        title="수동 입력 잔액 (API 설정에서 갱신)"
                      >
                        수동
                      </span>
                    )}
                    {isLow && (
                      <span className="ml-1 text-[9px] text-red-300 font-normal align-middle">
                        부족
                      </span>
                    )}
                  </p>
                ) : s.balance_url && s.status === "active" ? (
                  <a
                    href="/settings"
                    className="text-[10px] text-accent-primary hover:underline"
                    onClick={(e) => e.stopPropagation()}
                  >
                    잔액 입력 →
                  </a>
                ) : null}
                <p className="text-[10px] text-gray-500 truncate" title={s.detail}>{s.detail}</p>
                {s.usage_pct !== undefined && s.usage_pct > 0 && (
                  <div className="mt-1.5 w-full h-1.5 bg-gray-700 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${s.usage_pct > 80 ? "bg-red-400" : s.usage_pct > 50 ? "bg-amber-400" : "bg-green-400"}`}
                      style={{ width: `${Math.min(s.usage_pct, 100)}%` }}
                    />
                  </div>
                )}
                {/* v1.1.64: 파이프라인 사용 단계 배지 */}
                {s.used_in_steps && s.used_in_steps.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {s.used_in_steps.map((u) => (
                      <span
                        key={u.step}
                        title={`${u.label} 단계에서 사용 — ${u.models.join(", ")}`}
                        className="inline-flex items-center gap-0.5 px-1.5 py-[1px] rounded border border-border bg-bg-tertiary text-[9px] text-gray-300"
                      >
                        <span className="text-[8px] text-gray-500">{u.step}</span>
                        <span>{u.label}</span>
                      </span>
                    ))}
                  </div>
                )}
              </button>
            );
          })}
          {apiStatuses.length === 0 && !loadingApis && (
            <div className="col-span-4 text-center text-xs text-gray-600 py-2">
              API 상태를 불러올 수 없습니다. 서버가 실행 중인지 확인하세요.
            </div>
          )}
          {loadingApis && apiStatuses.length === 0 && (
            <div className="col-span-4 text-center text-xs text-gray-500 py-2 flex items-center justify-center gap-2">
              <RefreshCw size={12} className="animate-spin" /> 확인 중...
            </div>
          )}
        </div>
      </div>

      {/* New Preset (구 "새 프로젝트") — 프리셋 자체를 빈 상태로 하나 생성. Studio 에서 모델/스타일/캐릭터 등 구성 후 대시보드 딸깍에서 사용 */}
      <div className="flex items-end justify-between mb-3">
        <div>
          <h2 className="text-sm font-semibold text-gray-300">프리셋 목록</h2>
          <p className="text-[11px] text-gray-500">
            모델·자막·캐릭터 구성을 재사용하는 틀. Studio 에서 편집합니다.
          </p>
        </div>
      </div>
      <div className="flex gap-3 mb-6">
        <input
          type="text"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && createProject()}
          placeholder="새 프리셋 이름 / 초기 주제 (예: 호르무즈 해협의 역사)"
          className="flex-1 bg-bg-secondary border border-border rounded-lg px-4 py-3 text-white placeholder-gray-500 focus:outline-none focus:border-accent-primary"
        />
        <button
          onClick={createProject}
          disabled={creating}
          className="bg-accent-secondary hover:bg-yellow-600 text-black font-semibold px-6 py-3 rounded-lg flex items-center gap-2 transition-colors"
        >
          <Plus size={18} />
          새 프리셋
        </button>
      </div>

      {/* Preset List */}
      <div className="grid gap-4">
        {projects.map((p) => {
          const est = p.estimate;
          const estCost = est?.estimated_cost_usd ?? 0;
          const estDur = est?.estimated_seconds ?? 0;
          const estCuts = est?.estimated_cuts ?? 0;
          return (
          <div
            key={p.id}
            className="bg-bg-secondary border border-border rounded-lg p-5 flex items-center justify-between hover:border-accent-primary/50 transition-colors"
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-3 mb-1">
                <h3 className="text-lg font-semibold truncate">{p.title}</h3>
                <span className={`text-sm ${statusColor[p.status] || "text-gray-400"}`}>
                  {p.status}
                </span>
                {p.api_cost > 0 && (
                  <span
                    className="text-xs text-amber-400 bg-amber-400/10 px-1.5 py-0.5 rounded"
                    title="실제 사용된 API 비용 (누적)"
                  >
                    실사용 ${p.api_cost.toFixed(2)}
                  </span>
                )}
              </div>
              <p className="text-sm text-gray-400 truncate">
                {p.topic} · {p.total_cuts || estCuts}컷 · {new Date(p.created_at).toLocaleDateString("ko-KR")}
              </p>
              {/* v1.1.33 → v1.1.35: 예상 소요시간 / 비용 (원화 + 월 예상 + tier) */}
              {est && (() => {
                const tier = costTierClasses(est.cost_tier);
                return (
                  <div className="mt-2 flex items-center flex-wrap gap-2 text-xs">
                    <span
                      className="flex items-center gap-1 text-sky-300 bg-sky-400/10 px-2 py-0.5 rounded"
                      title={`LLM ${est.time_breakdown.llm_script}s + 이미지 ${est.time_breakdown.image_generation}s + TTS ${est.time_breakdown.tts}s + 비디오 ${est.time_breakdown.video}s + 합성 ${est.time_breakdown.post_process}s`}
                    >
                      <Clock size={12} />
                      예상 {formatDurationKo(estDur)}
                    </span>
                    <span
                      className={`flex items-center gap-1 ${tier.text} ${tier.bg} border ${tier.border} px-2 py-0.5 rounded font-medium`}
                      title={`1편 $${estCost.toFixed(2)} (${formatKrw(est.estimated_cost_krw ?? estCost * 1360)})\n월 30편 예상: ${formatKrw(est.monthly_cost_krw ?? estCost * 1360 * 30)}\n환율 가정 1 USD ≈ 1,360 KRW\n\nLLM $${est.cost_breakdown.llm_script.toFixed(3)} · 이미지 $${est.cost_breakdown.image_generation.toFixed(3)} · TTS $${est.cost_breakdown.tts.toFixed(3)} · 비디오 $${est.cost_breakdown.video.toFixed(3)}`}
                    >
                      <DollarSign size={12} />
                      {formatKrw(est.estimated_cost_krw ?? estCost * 1360)}
                      <span className="opacity-60">/편</span>
                    </span>
                    {est.monthly_cost_krw !== undefined && (
                      <span
                        className={`text-[10px] ${tier.text} opacity-80`}
                        title="일 1편 × 30일 기준"
                      >
                        월 {formatKrw(est.monthly_cost_krw)}
                      </span>
                    )}
                    {est.cost_tier === "expensive" && (
                      <span className="text-[10px] text-accent-danger font-semibold">
                        ⚠ 비용 과다
                      </span>
                    )}
                    <span
                      className="text-[10px] text-gray-500 truncate"
                      title={`스크립트: ${est.models_used.script} / 이미지: ${est.models_used.image} / TTS: ${est.models_used.tts} / 비디오: ${est.models_used.video}`}
                    >
                      {est.models_used.image} · {est.models_used.video}
                    </span>
                  </div>
                );
              })()}
            </div>

            <div className="flex items-center gap-2 flex-shrink-0">
              {p.youtube_url && (
                <a
                  href={p.youtube_url}
                  target="_blank"
                  className="p-2 text-gray-400 hover:text-white transition-colors"
                >
                  <ExternalLink size={18} />
                </a>
              )}
              <a
                href={`/studio/${p.id}`}
                className="bg-accent-primary hover:bg-purple-600 text-white px-4 py-2 rounded-lg flex items-center gap-2 text-sm transition-colors"
              >
                <Play size={14} />
                스튜디오
              </a>
              <button
                onClick={() => deleteProject(p.id)}
                className="p-2 text-gray-400 hover:text-accent-danger transition-colors"
              >
                <Trash2 size={18} />
              </button>
            </div>
          </div>
          );
        })}

        {projects.length === 0 && (
          <div className="text-center py-20 text-gray-500">
            아직 프리셋이 없습니다. 위에서 이름/주제를 입력해 첫 프리셋을 만드세요.
          </div>
        )}
      </div>

      {/* API Key Modal */}
      {keyModalProvider && (
        <ApiKeyModal
          provider={keyModalProvider}
          balanceUrl={keyModalBalanceUrl}
          onClose={() => setKeyModalProvider(null)}
          onSaved={() => loadApiStatus()}
        />
      )}
    </div>
  );
}
