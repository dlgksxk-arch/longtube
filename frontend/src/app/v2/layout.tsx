/**
 * v2.1.0 통합 레이아웃.
 *
 * 좌측 240px 사이드바 + 우측 메인. 사이드바는 4 섹션 아코디언
 * (프리셋/딸깍/유튜브/설정). 하단에 "자동 실행 상태" 위젯 (v2.2.0에서 채움).
 *
 * 기획 §7.
 */
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useMemo } from "react";
import {
  Layers,
  ListChecks,
  Activity,
  Calendar,
  Film,
  Youtube,
  Image as ImageIcon,
  MessageSquare,
  ListVideo,
  KeyRound,
  HardDrive,
  ChevronDown,
  ChevronRight,
} from "lucide-react";

type NavItem = { href: string; label: string; icon: React.ReactNode };
type NavSection = { key: string; label: string; items: NavItem[] };

const SECTIONS: NavSection[] = [
  {
    key: "preset",
    label: "프리셋",
    items: [
      { href: "/v2/presets", label: "프리셋 목록", icon: <Layers size={15} /> },
    ],
  },
  {
    key: "ddalkkak",
    label: "딸깍",
    items: [
      { href: "/v2/queue", label: "제작 큐", icon: <ListChecks size={15} /> },
      { href: "/v2/live", label: "실시간 현황", icon: <Activity size={15} /> },
      { href: "/v2/schedule", label: "스케줄", icon: <Calendar size={15} /> },
    ],
  },
  {
    key: "youtube",
    label: "유튜브",
    items: [
      { href: "/v2/youtube/channels", label: "채널 허브", icon: <Youtube size={15} /> },
      { href: "/v2/youtube/videos", label: "내 영상", icon: <Film size={15} /> },
      { href: "/v2/youtube/playlists", label: "재생목록", icon: <ListVideo size={15} /> },
      { href: "/v2/youtube/comments", label: "댓글", icon: <MessageSquare size={15} /> },
    ],
  },
  {
    key: "settings",
    label: "설정",
    items: [
      { href: "/v2/settings/api", label: "API 키/잔액", icon: <KeyRound size={15} /> },
      { href: "/v2/settings/storage", label: "저장소", icon: <HardDrive size={15} /> },
    ],
  },
];

export default function V2Layout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  // 현재 경로가 어느 섹션에 속하는지에 따라 기본 펼침 상태 결정.
  const defaultOpen = useMemo(() => {
    const map: Record<string, boolean> = {
      preset: false,
      ddalkkak: false,
      youtube: false,
      settings: false,
    };
    for (const s of SECTIONS) {
      for (const item of s.items) {
        if (pathname.startsWith(item.href)) map[s.key] = true;
      }
    }
    // 아무 섹션도 안 맞으면 전부 펼쳐둔다.
    if (!Object.values(map).some(Boolean)) {
      for (const k of Object.keys(map)) map[k] = true;
    }
    return map;
  }, [pathname]);

  const [open, setOpen] = useState<Record<string, boolean>>(defaultOpen);

  const toggle = (key: string) =>
    setOpen((prev) => ({ ...prev, [key]: !prev[key] }));

  return (
    <div className="v2-scope min-h-screen flex bg-bg-primary text-gray-100">
      <aside className="w-[240px] shrink-0 border-r border-border bg-bg-secondary flex flex-col">
        <div className="px-4 py-4 border-b border-border">
          <Link href="/v2" className="flex items-center gap-2 text-base font-semibold">
            <ImageIcon size={18} className="text-sky-400" />
            LongTube <span className="text-xs text-gray-500">v2</span>
          </Link>
        </div>

        <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-1">
          {SECTIONS.map((section) => {
            const isOpen = !!open[section.key];
            return (
              <div key={section.key}>
                <button
                  type="button"
                  onClick={() => toggle(section.key)}
                  className="w-full flex items-center justify-between px-2 py-1.5 rounded-md text-sm text-gray-300 hover:bg-bg-tertiary"
                >
                  <span className="font-medium">{section.label}</span>
                  {isOpen ? (
                    <ChevronDown size={14} className="text-gray-500" />
                  ) : (
                    <ChevronRight size={14} className="text-gray-500" />
                  )}
                </button>
                {isOpen && (
                  <ul className="mt-1 ml-2 space-y-0.5">
                    {section.items.map((item) => {
                      const active = pathname === item.href || pathname.startsWith(item.href + "/");
                      return (
                        <li key={item.href}>
                          <Link
                            href={item.href}
                            className={`flex items-center gap-2 px-2 py-1.5 rounded-md text-sm ${
                              active
                                ? "bg-sky-500/15 text-sky-200"
                                : "text-gray-400 hover:bg-bg-tertiary hover:text-gray-200"
                            }`}
                          >
                            <span className="shrink-0 text-gray-500">{item.icon}</span>
                            <span className="truncate">{item.label}</span>
                          </Link>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            );
          })}
        </nav>

        {/*
          자동 실행 상태 위젯. v2.1.0 은 정적 스텁. 실제 동작 상태는
          v2.2.0 큐 시스템 연결 후 채운다(기획 §7.1).
        */}
        <div className="border-t border-border px-3 py-3 text-xs text-gray-500">
          <div className="flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-slate-500" />
            <span>자동 실행 대기 중</span>
          </div>
          <p className="mt-1 text-[11px] text-gray-600">
            v2.2.0 에서 연결됩니다
          </p>
        </div>
      </aside>

      <main className="flex-1 min-w-0">{children}</main>
    </div>
  );
}
