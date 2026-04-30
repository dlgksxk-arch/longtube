"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Plus, Play, Trash2, ExternalLink, RefreshCw, CheckCircle, XCircle, AlertCircle, MinusCircle, Key, Youtube as YoutubeIcon, Clock, DollarSign, LayoutDashboard, Zap, Info, ListTodo, Activity, CalendarDays, Film } from "lucide-react";
import { api, apiStatusApi, type ApiStatusInfo, type ProjectEstimate } from "@/lib/api";
import { APP_VERSION } from "@/lib/version";
import { formatDurationKo, formatKrw, costTierClasses } from "@/lib/format";
import ApiKeyModal from "@/components/common/ApiKeyModal";
import LocalServiceStatus from "@/components/common/LocalServiceStatus";
import OneClickWidget from "@/components/studio/OneClickWidget";

// v1.2.1: 좌측 사이드바 네비게이션 — 메인 대시보드에만 붙임.
// /oneclick, /youtube 는 이미 자체 사이드바가 있으므로 중복 회피.
const SIDEBAR_NAV = [
  { href: "/", label: "대시보드", icon: LayoutDashboard, active: true },
  { href: "/oneclick", label: "딸깍 대시보드", icon: Zap, active: false },
  { href: "/youtube", label: "YouTube Studio", icon: YoutubeIcon, active: false },
  { href: "/settings", label: "API 설정", icon: Key, active: false },
] as const;

const ONECLICK_SUBNAV = [
  { href: "/oneclick", label: "제작 큐", icon: ListTodo },
  { href: "/oneclick/live", label: "실시간 현황", icon: Activity },
  { href: "/oneclick/schedule", label: "스케줄", icon: CalendarDays },
  { href: "/oneclick/library", label: "완성작 관리", icon: Film },
] as const;

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
  const pathname = usePathname();
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

  // v1.2.1: API 요약 통계 (사이드바 info 블록용)
  const apiOk = apiStatuses.filter((s) => s.status === "active" || s.status === "configured").length;
  const apiLow = apiStatuses.filter((s) => s.manual_balance?.low).length;
  const flatSidebarNav = [
    SIDEBAR_NAV[0],
    ...ONECLICK_SUBNAV.filter(({ href }) => href !== "/oneclick/library"),
    ...SIDEBAR_NAV.filter(({ href }) => href !== "/" && href !== "/oneclick"),
  ];

  return (
    <div className="flex h-screen overflow-hidden">
      {/* ── 좌측 사이드바 ── v1.2.1 / v1.2.2 / v1.2.4: 글씨 크게! */}
      <aside className="w-72 flex-shrink-0 bg-bg-secondary border-r border-border flex flex-col">
        {/* 로고 + 버전 */}
        <div className="flex items-center gap-3 px-6 h-20">
          <div className="w-11 h-11 rounded-xl bg-accent-primary flex items-center justify-center">
            <LayoutDashboard size={22} className="text-white" />
          </div>
          <div className="flex flex-col leading-tight">
            <span className="text-2xl font-bold text-white">LongTube</span>
            <span className="text-xs text-gray-500 font-mono">v{APP_VERSION}</span>
          </div>
        </div>

        <div className="h-px bg-border" />

        <LocalServiceStatus />

        {/* 메뉴 스택 */}
        <nav className="p-4 space-y-1.5">
          {flatSidebarNav.map(({ href, label, icon: Icon }) => {
            const active =
              href === "/"
                ? pathname === "/"
                : pathname === href || pathname.startsWith(`${href}/`);

            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-3 px-4 py-3.5 rounded-lg text-base font-medium transition-colors ${
                  active
                    ? "bg-accent-primary/15 text-accent-primary font-semibold"
                    : "text-gray-300 hover:text-white hover:bg-white/[0.04]"
                }`}
              >
                <Icon size={20} />
                {label}
              </Link>
            );
          })}
        </nav>

        <div className="flex-1" />

        {/* 하단 info 블록 — v1.2.4: 글씨 전반 확대 (절대 text-xs/10px/11px 금지) */}
        <div className="mx-4 mb-4 p-5 bg-bg-primary/60 border border-border rounded-xl">
          <div className="flex items-center gap-2.5 mb-4">
            <Info size={20} className="text-gray-300" />
            <span className="text-lg font-bold text-gray-100">시스템 정보</span>
          </div>
          <div className="space-y-2.5 text-base text-gray-300 mb-4">
            <div className="flex items-center justify-between">
              <span>버전</span>
              <span className="font-mono text-gray-100 font-semibold">v{APP_VERSION}</span>
            </div>
            <div className="flex items-center justify-between">
              <span>프리셋</span>
              <span className="font-mono text-gray-100 font-semibold">{projects.length}</span>
            </div>
          </div>

          {/* API 상태 한줄 리스트 — v1.2.3 / v1.2.4: 글씨 크게 */}
          <div className="pt-4 border-t border-border">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Key size={18} className="text-accent-secondary" />
                <span className="text-base font-bold text-gray-100">API 연결 상태</span>
              </div>
              <button
                onClick={loadApiStatus}
                disabled={loadingApis}
                className="p-1.5 rounded hover:bg-bg-tertiary text-gray-300 hover:text-white transition-colors disabled:opacity-50"
                title="새로 고침"
              >
                <RefreshCw size={16} className={loadingApis ? "animate-spin" : ""} />
              </button>
            </div>

            {apiLow > 0 && (
              <div className="mb-2.5 px-3 py-2 rounded bg-red-500/10 border border-red-500/40 text-sm text-red-200">
                잔액 부족 {apiLow}건 — <a href="/settings" className="underline hover:text-white font-semibold">충전</a>
              </div>
            )}

            <div className="space-y-1.5">
              {apiStatuses.map((s, i) => {
                const style = STATUS_STYLES[s.status] || STATUS_STYLES.error;
                const Icon = style.icon;
                const isLow = !!s.manual_balance?.low;
                return (
                  <button
                    key={i}
                    onClick={() => { setKeyModalProvider(s.provider); setKeyModalBalanceUrl(s.balance_url); }}
                    title={s.detail}
                    className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg border ${isLow ? "border-red-500/60 bg-red-500/5" : "border-border bg-bg-secondary/50"} hover:border-accent-primary/50 transition-colors text-left`}
                  >
                    <Icon size={16} className={`${style.color} flex-shrink-0`} />
                    <span className="text-sm font-semibold text-gray-100 truncate flex-shrink-0 min-w-0" style={{ maxWidth: "95px" }}>
                      {s.provider}
                    </span>
                    <span className={`ml-auto text-sm font-mono font-semibold truncate ${isLow ? "text-red-400" : s.balance ? "text-green-400" : "text-gray-500"}`}>
                      {s.balance || "—"}
                    </span>
                  </button>
                );
              })}
              {apiStatuses.length === 0 && !loadingApis && (
                <div className="text-sm text-gray-500 py-2 text-center">
                  상태 불러오기 실패
                </div>
              )}
              {loadingApis && apiStatuses.length === 0 && (
                <div className="text-sm text-gray-400 py-2 text-center flex items-center justify-center gap-1.5">
                  <RefreshCw size={14} className="animate-spin" /> 확인 중
                </div>
              )}
            </div>

            <div className="mt-3 pt-3 border-t border-border flex items-center justify-between text-sm text-gray-300">
              <span>연결</span>
              <span className="font-mono font-bold text-base">
                <span className={apiOk > 0 ? "text-green-400" : "text-gray-500"}>{apiOk}</span>
                <span className="text-gray-500"> / {apiStatuses.length || "-"}</span>
              </span>
            </div>
          </div>
        </div>
      </aside>

      {/* ── 메인 콘텐츠 ── */}
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-6xl mx-auto p-8">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-3">
              <h1 className="text-3xl font-bold">대시보드</h1>
            </div>
          </div>
          <p className="text-gray-400 mb-8">
            프리셋은 모델·자막·캐릭터 구성을 재사용하는 틀입니다. Studio 에서 프리셋을 다듬고,
            아래 <span className="text-accent-primary">딸깍 제작</span> 또는 좌측
            <span className="text-accent-primary"> 딸깍 대시보드</span> 메뉴에서 주제 리스트를
            채워 두면 매일 지정한 시각에 한 건씩 자동으로 만들어냅니다.
          </p>

          <div className="mb-8 flex items-center gap-3 flex-wrap">
            <OneClickWidget />
            <span className="text-sm text-gray-500">
              빠른 큐 편집은 여기서 하고, 전체 현황과 채널별 관리는{" "}
              <Link href="/oneclick" className="text-accent-primary hover:underline">
                딸깍 대시보드
              </Link>
              에서 확인합니다.
            </span>
          </div>

      {/* v1.2.3: API 연결 상태 패널은 좌측 사이드바 "시스템 정보" 블록으로 이동. */}

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
      </main>
    </div>
  );
}
