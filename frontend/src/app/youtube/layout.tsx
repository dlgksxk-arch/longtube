"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
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
import { youtubeStudioApi, type StudioAuthStatus } from "@/lib/api";
import { APP_VERSION } from "@/lib/version";

// v1.1.31: YouTube Studio 전역 레이아웃.
// - 좌측 사이드 네비 + 상단 채널 상태 바.
// - 로그인 상태 체크는 /api/youtube-studio/auth/status 한 번만 쏘고
//   자식 페이지에서도 재사용할 수 있도록 여기서만 관리. (children 은 별도로
//   자기 상태 호출)

const NAV = [
  { href: "/youtube", label: "대시보드", icon: LayoutDashboard },
  { href: "/youtube/videos", label: "영상", icon: Film },
  { href: "/youtube/upload", label: "업로드", icon: Upload },
  { href: "/youtube/playlists", label: "재생목록", icon: ListMusic },
  { href: "/youtube/comments", label: "댓글", icon: MessageSquare },
];

export default function YouTubeStudioLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [auth, setAuth] = useState<StudioAuthStatus | null>(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const data = await youtubeStudioApi.authStatus();
      setAuth(data);
    } catch {
      setAuth({ authenticated: false });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const startOAuth = async () => {
    // 전역 OAuth 플로우는 기존 /api/youtube/auth 를 그대로 재사용.
    setLoading(true);
    try {
      const res = await fetch("http://localhost:8000/api/youtube/auth", { method: "POST" });
      if (!res.ok) {
        const t = await res.text();
        alert(`OAuth 실패: ${t}`);
      }
    } catch (e) {
      alert(`OAuth 오류: ${(e as Error).message}`);
    }
    await load();
  };

  return (
    <div className="min-h-screen bg-bg-primary text-white">
      <div className="flex">
        {/* Sidebar */}
        <aside className="w-56 min-h-screen border-r border-border bg-bg-secondary flex flex-col">
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

          <nav className="flex-1 p-2">
            {NAV.map((item) => {
              const Icon = item.icon;
              const active =
                item.href === "/youtube"
                  ? pathname === "/youtube"
                  : pathname.startsWith(item.href);
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

          <div className="p-3 border-t border-border text-xs">
            {auth?.authenticated ? (
              <div>
                <div className="text-gray-400 mb-1">연결된 채널</div>
                <div className="font-semibold text-gray-200 truncate" title={auth.channel_title || ""}>
                  {auth.channel_title || "(이름 없음)"}
                </div>
                <button
                  onClick={load}
                  className="mt-2 text-[11px] text-gray-500 hover:text-gray-300 flex items-center gap-1"
                >
                  <RefreshCw size={10} className={loading ? "animate-spin" : ""} /> 새로고침
                </button>
              </div>
            ) : (
              <button
                onClick={startOAuth}
                disabled={loading}
                className="w-full bg-accent-primary hover:bg-purple-600 text-white rounded px-3 py-2 flex items-center justify-center gap-2 text-sm disabled:opacity-50"
              >
                <LogIn size={14} />
                {loading ? "인증 중..." : "YouTube 로그인"}
              </button>
            )}
          </div>
        </aside>

        {/* Content */}
        <main className="flex-1 min-w-0">
          {auth && !auth.authenticated && (
            <div className="bg-amber-400/10 border-b border-amber-400/30 text-amber-300 text-sm px-6 py-3">
              YouTube 인증이 필요합니다. 좌측 사이드바에서 로그인해주세요. 먼저 로그인해야 이 페이지의
              데이터가 로드됩니다.
            </div>
          )}
          {children}
        </main>
      </div>
    </div>
  );
}
