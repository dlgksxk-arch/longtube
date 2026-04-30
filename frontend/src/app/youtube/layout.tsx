"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  LayoutDashboard,
  Film,
  Upload,
  ListMusic,
  MessageSquare,
  Youtube as YoutubeIcon,
  RefreshCw,
  LogIn,
} from "lucide-react";
import {
  projectsApi,
  youtubeApi,
  youtubeStudioApi,
  type Project,
  type StudioAuthStatus,
} from "@/lib/api";
import { APP_VERSION } from "@/lib/version";

const NAV = [
  { href: "/youtube", label: "대시보드", icon: LayoutDashboard },
  { href: "/youtube/videos", label: "영상", icon: Film },
  { href: "/youtube/upload", label: "업로드", icon: Upload },
  { href: "/youtube/playlists", label: "재생목록", icon: ListMusic },
  { href: "/youtube/comments", label: "댓글", icon: MessageSquare },
];

function makeStudioHref(pathname: string, projectId?: string | null): string {
  const pid = (projectId || "").trim();
  return pid ? `${pathname}?project=${encodeURIComponent(pid)}` : pathname;
}

function getPresetChannelId(preset?: Project | null): number | undefined {
  const raw = preset?.config?.youtube_channel ?? preset?.config?.channel;
  const channelId =
    typeof raw === "number" ? raw : typeof raw === "string" ? Number.parseInt(raw, 10) : NaN;
  return Number.isFinite(channelId) && channelId >= 1 && channelId <= 4 ? channelId : undefined;
}

export default function YouTubeStudioLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedProjectId = (searchParams.get("project") || "").trim();

  const [presets, setPresets] = useState<Project[]>([]);
  const [authMap, setAuthMap] = useState<Record<string, StudioAuthStatus>>({});
  const [loading, setLoading] = useState(false);

  const selectedPreset = useMemo(
    () => presets.find((preset) => preset.id === requestedProjectId) || presets[0] || null,
    [presets, requestedProjectId],
  );
  const selectedProjectId = selectedPreset?.id || null;
  const selectedAuth = selectedProjectId ? authMap[selectedProjectId] : null;

  const navLinks = useMemo(
    () =>
      NAV.map((item) => ({
        ...item,
        href: makeStudioHref(item.href, selectedProjectId),
      })),
    [selectedProjectId],
  );

  const load = async () => {
    setLoading(true);
    try {
      const presetRows = await projectsApi.list();
      setPresets(presetRows);

      const results = await Promise.all(
        presetRows.map(async (preset) => {
          try {
            const data = await youtubeStudioApi.authStatus(preset.id, getPresetChannelId(preset));
            return [preset.id, data] as const;
          } catch {
            return [preset.id, { authenticated: false, project_id: preset.id }] as const;
          }
        }),
      );
      setAuthMap(Object.fromEntries(results));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (!presets.length) return;
    if (!requestedProjectId || !presets.some((preset) => preset.id === requestedProjectId)) {
      router.replace(makeStudioHref(pathname, presets[0].id));
    }
  }, [pathname, presets, requestedProjectId, router]);

  const startOAuth = async () => {
    if (!selectedProjectId) return;
    setLoading(true);
    try {
      const channelId = getPresetChannelId(selectedPreset);
      if (channelId) {
        await youtubeApi.channelAuthenticate(channelId);
      } else {
        await youtubeApi.projectAuthenticate(selectedProjectId);
      }
    } catch (e) {
      alert(`YouTube 연결 실패: ${(e as Error).message}`);
    }
    await load();
  };

  return (
    <div className="min-h-screen bg-bg-primary text-white">
      <div className="flex">
        <aside className="w-72 min-h-screen border-r border-border bg-bg-secondary flex flex-col">
          <div className="p-4 border-b border-border">
            <Link href="/" className="flex items-center gap-2 text-gray-300 hover:text-white text-sm">
              <ArrowLeft size={14} /> LongTube
            </Link>
            <div className="mt-3 flex items-center gap-2">
              <YoutubeIcon size={20} className="text-red-500" />
              <div>
                <h1 className="text-base font-bold leading-tight">YouTube Studio</h1>
                <span className="text-[10px] text-gray-500 font-mono">v{APP_VERSION}</span>
              </div>
            </div>
          </div>

          <nav className="p-2 border-b border-border">
            {navLinks.map((item) => {
              const Icon = item.icon;
              const active =
                item.href.startsWith("/youtube?")
                  ? pathname === "/youtube"
                  : pathname.startsWith(item.href.split("?")[0]);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm mb-1 transition-colors ${
                    active
                      ? "bg-accent-primary/20 text-accent-primary"
                      : "text-gray-400 hover:bg-bg-tertiary hover:text-white"
                  }`}
                >
                  <Icon size={16} />
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="mx-3 mt-3 rounded-lg border border-border bg-bg-primary/30 p-3 flex-1 min-h-0 flex flex-col">
            <div className="mb-3 flex items-center justify-between">
              <div className="text-xs font-semibold text-gray-300">프리셋 관리</div>
              <button
                onClick={load}
                className="text-[11px] text-gray-500 hover:text-gray-300 flex items-center gap-1"
              >
                <RefreshCw size={10} className={loading ? "animate-spin" : ""} /> 새로고침
              </button>
            </div>

            <div className="space-y-2 overflow-y-auto pr-1">
              {presets.map((preset) => {
                const auth = authMap[preset.id];
                const selected = preset.id === selectedProjectId;
                return (
                  <Link
                    key={preset.id}
                    href={makeStudioHref("/youtube", preset.id)}
                    className={`block rounded-lg border px-3 py-3 transition-colors ${
                      selected
                        ? "border-accent-primary bg-accent-primary/15"
                        : "border-border bg-bg-secondary hover:border-accent-primary/40"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-sm font-semibold truncate" title={preset.title}>
                          {preset.title}
                        </div>
                        <div className="mt-1 text-[11px] text-gray-500 font-mono">{preset.id}</div>
                      </div>
                      <span
                        className={`text-[11px] flex-shrink-0 ${
                          auth?.authenticated ? "text-green-400" : "text-gray-500"
                        }`}
                      >
                        {auth?.authenticated ? "연결" : "미연결"}
                      </span>
                    </div>
                    <div className="mt-2 truncate text-[11px] text-gray-400" title={auth?.channel_title || ""}>
                      {auth?.channel_title ||
                        (getPresetChannelId(preset)
                          ? `CH${getPresetChannelId(preset)} YouTube 미연결`
                          : "YouTube 미연결")}
                    </div>
                  </Link>
                );
              })}

              {presets.length === 0 && (
                <div className="rounded-lg border border-border bg-bg-secondary px-3 py-4 text-sm text-gray-500">
                  프리셋이 없습니다.
                </div>
              )}
            </div>

            {selectedPreset && (
              <div className="mt-3 rounded-lg border border-border bg-bg-secondary p-3">
                <div className="text-xs text-gray-400 mb-1">현재 관리 프리셋</div>
                <div className="text-sm font-semibold truncate" title={selectedPreset.title}>
                  {selectedPreset.title}
                </div>
                <div className="mt-1 text-[11px] text-gray-500 font-mono">{selectedPreset.id}</div>
                {selectedAuth?.authenticated ? (
                  <div className="mt-2 text-[11px] text-green-400 truncate" title={selectedAuth.channel_title || ""}>
                    연결 채널: {selectedAuth.channel_title || "연결됨"}
                  </div>
                ) : (
                  <button
                    onClick={startOAuth}
                    disabled={loading}
                    className="mt-3 w-full bg-accent-primary hover:bg-purple-600 text-white rounded px-3 py-2 flex items-center justify-center gap-2 text-sm disabled:opacity-50"
                  >
                    <LogIn size={14} />
                    {loading
                      ? "연결 중..."
                      : getPresetChannelId(selectedPreset)
                        ? `CH${getPresetChannelId(selectedPreset)} 연결`
                        : "이 프리셋 연결"}
                  </button>
                )}
              </div>
            )}
          </div>
        </aside>

        <main className="flex-1 min-w-0">
          {selectedPreset && selectedAuth && !selectedAuth.authenticated && (
            <div className="bg-amber-400/10 border-b border-amber-400/30 text-amber-300 text-sm px-6 py-3">
              현재 프리셋에 연결된 YouTube OAuth 가 없습니다. 좌측에서 해당 프리셋을 연결한 뒤 사용하십시오.
            </div>
          )}
          {children}
        </main>
      </div>
    </div>
  );
}
