/**
 * /v2/youtube/channels — 채널 허브 (기획 §14.1).
 *
 * CH1~CH4 각 채널의 OAuth 연결 상태와 채널 정보를 표시한다.
 *
 * 연결 백엔드 (v1 엔드포인트 재사용; v2.4.0 에서 /api/v2/youtube 로 이관 예정):
 *   GET  /api/youtube/auth/channel/{ch}/status  → { channel, authenticated }
 *   GET  /api/youtube/auth/channel/{ch}/info    → { title, subscriber_count, video_count, ... }
 *   POST /api/youtube/auth/channel/{ch}         → 브라우저 OAuth 팝업 (blocking)
 *   POST /api/youtube/auth/channel/{ch}/reset   → 토큰 삭제
 *
 * POST /auth/channel/{ch} 는 브라우저 팝업을 열고 사용자가 로그인을 마칠
 * 때까지 완료되지 않는다. 그래서 타임아웃을 길게 (5분) 두고 로딩 표시만
 * 유지한다. 실패하면 사용자에게 안내한다.
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import { channelColor, type ChannelId } from "@/lib/channelColor";
import { V2_API_BASE } from "@/lib/v2Api";
import { StatusDot } from "@/components/v2/StatusDot";
import { V2Button } from "@/components/v2/V2Button";
import { ConfirmDialog } from "@/components/v2/ConfirmDialog";

type Ch = 1 | 2 | 3 | 4;
const CHANNELS: Ch[] = [1, 2, 3, 4];

/** v1 네임스페이스(`/api/youtube/...`) URL 헬퍼. */
function v1Url(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${V2_API_BASE}${p}`;
}

interface ChannelInfo {
  channel_id?: string;
  title?: string;
  custom_url?: string | null;
  thumbnail?: string | null;
  subscriber_count?: number | null;
  video_count?: number | null;
}

interface ChannelState {
  authenticated: boolean | null; // null = 로딩 중
  info: ChannelInfo | null;
  busy: boolean;                 // OAuth / reset 진행 중
  error: string | null;
}

const INITIAL_STATE: ChannelState = {
  authenticated: null,
  info: null,
  busy: false,
  error: null,
};

function fmtCount(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n >= 10_000) return `${(n / 10_000).toFixed(1)}만`;
  return n.toLocaleString("ko-KR");
}

export default function V2YouTubeChannelsPage() {
  const [state, setState] = useState<Record<Ch, ChannelState>>({
    1: { ...INITIAL_STATE },
    2: { ...INITIAL_STATE },
    3: { ...INITIAL_STATE },
    4: { ...INITIAL_STATE },
  });
  const [confirmReset, setConfirmReset] = useState<Ch | null>(null);
  const [authInProgress, setAuthInProgress] = useState<Ch | null>(null);

  const patch = useCallback((ch: Ch, next: Partial<ChannelState>) => {
    setState((prev) => ({ ...prev, [ch]: { ...prev[ch], ...next } }));
  }, []);

  const loadChannel = useCallback(async (ch: Ch) => {
    patch(ch, { error: null });
    try {
      const sres = await fetch(v1Url(`/youtube/auth/channel/${ch}/status`));
      if (!sres.ok) throw new Error(`status HTTP ${sres.status}`);
      const sdata = (await sres.json()) as { authenticated: boolean };
      if (!sdata.authenticated) {
        patch(ch, { authenticated: false, info: null });
        return;
      }
      // 인증되어 있으면 info 까지 가져온다.
      try {
        const ires = await fetch(v1Url(`/youtube/auth/channel/${ch}/info`));
        if (!ires.ok) throw new Error(`info HTTP ${ires.status}`);
        const info = (await ires.json()) as ChannelInfo;
        patch(ch, { authenticated: true, info });
      } catch (e) {
        // status 만 true 여도 info 는 실패할 수 있다 → 그대로 둔다.
        patch(ch, {
          authenticated: true,
          info: null,
          error: e instanceof Error ? e.message : String(e),
        });
      }
    } catch (e) {
      patch(ch, {
        authenticated: false,
        info: null,
        error: e instanceof Error ? e.message : String(e),
      });
    }
  }, [patch]);

  useEffect(() => {
    for (const ch of CHANNELS) void loadChannel(ch);
  }, [loadChannel]);

  const startAuth = async (ch: Ch) => {
    patch(ch, { busy: true, error: null });
    setAuthInProgress(ch);
    try {
      // OAuth 플로우는 사용자가 브라우저에서 로그인할 때까지 블로킹된다.
      // 타임아웃을 두지 않고 기다린다 (AbortController 없이).
      const res = await fetch(v1Url(`/youtube/auth/channel/${ch}`), {
        method: "POST",
      });
      if (!res.ok) {
        const body = await res.text().catch(() => "");
        throw new Error(`HTTP ${res.status}${body ? `: ${body}` : ""}`);
      }
      await loadChannel(ch);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      patch(ch, { error: msg });
    } finally {
      patch(ch, { busy: false });
      setAuthInProgress((cur) => (cur === ch ? null : cur));
    }
  };

  const doReset = async (ch: Ch) => {
    setConfirmReset(null);
    patch(ch, { busy: true, error: null });
    try {
      const res = await fetch(v1Url(`/youtube/auth/channel/${ch}/reset`), {
        method: "POST",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await loadChannel(ch);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      patch(ch, { error: msg });
    } finally {
      patch(ch, { busy: false });
    }
  };

  return (
    <div className="p-6 space-y-5">
      <header>
        <h1 className="text-gray-100">채널 허브</h1>
        <p className="text-sm text-gray-500 mt-1">
          CH1~CH4 OAuth 연결과 채널 정보. 최근 업로드는 v2.4.0 에서 전용
          엔드포인트가 붙으면 추가됩니다.
        </p>
      </header>

      {authInProgress && (
        <div className="rounded-md border border-sky-500/40 bg-sky-500/5 px-3 py-2 text-xs text-sky-200">
          CH{authInProgress} 브라우저 인증을 진행 중입니다. 서버(FastAPI)가
          띄운 팝업 창에서 로그인을 마치세요. 완료 전까지 이 요청은 열려
          있습니다.
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {CHANNELS.map((ch) => (
          <ChannelCard
            key={ch}
            ch={ch}
            state={state[ch]}
            onAuth={() => startAuth(ch)}
            onReset={() => setConfirmReset(ch)}
            onRefresh={() => loadChannel(ch)}
          />
        ))}
      </div>

      <ConfirmDialog
        open={confirmReset != null}
        title={confirmReset ? `CH${confirmReset} 토큰을 삭제할까요?` : ""}
        description={
          "저장된 토큰(token_chN.json)이 삭제됩니다. " +
          "다시 인증하면 계정 선택 팝업이 뜹니다."
        }
        confirmLabel="삭제"
        cancelLabel="취소"
        danger
        onConfirm={() => {
          if (confirmReset) void doReset(confirmReset);
        }}
        onCancel={() => setConfirmReset(null)}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------

interface ChannelCardProps {
  ch: Ch;
  state: ChannelState;
  onAuth: () => void;
  onReset: () => void;
  onRefresh: () => void;
}

function ChannelCard({ ch, state, onAuth, onReset, onRefresh }: ChannelCardProps) {
  const c = channelColor(ch as ChannelId);
  const { authenticated, info, busy, error } = state;

  let dot: React.ReactNode;
  if (authenticated == null) dot = <StatusDot status="idle" label="확인 중" />;
  else if (busy) dot = <StatusDot status="busy" label="진행 중" />;
  else if (authenticated) dot = <StatusDot status="ok" label="연결됨" />;
  else dot = <StatusDot status="fail" label="미연결" />;

  return (
    <article
      className={`rounded-xl border ${c.border} ${c.bgSoft} p-5 min-h-[180px] flex flex-col`}
    >
      <div className="flex items-center gap-2">
        <span
          className={`px-2 py-0.5 rounded-md text-xs font-semibold ${c.bgSoft} ${c.text} border ${c.border}`}
        >
          CH{ch}
        </span>
        <span className="ml-auto">{dot}</span>
      </div>

      {/* 본문 --------------------------------------------------------- */}
      <div className="mt-4 flex-1">
        {authenticated === true && info ? (
          <div className="flex items-start gap-3">
            {info.thumbnail ? (
              // 외부 호스트(googleusercontent) 이미지라 next/image 대신 <img> 사용.
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={info.thumbnail}
                alt={info.title ?? `CH${ch}`}
                width={56}
                height={56}
                className="rounded-full border border-border"
              />
            ) : (
              <div className="w-14 h-14 rounded-full bg-bg-tertiary border border-border" />
            )}
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-gray-100 truncate">
                {info.title ?? "(제목 없음)"}
              </p>
              {info.custom_url && (
                <p className="text-xs text-gray-500 truncate">
                  {info.custom_url}
                </p>
              )}
              <dl className="mt-2 flex gap-4 text-xs">
                <div>
                  <dt className="text-gray-500">구독자</dt>
                  <dd className="tabular-nums text-gray-100">
                    {fmtCount(info.subscriber_count)}
                  </dd>
                </div>
                <div>
                  <dt className="text-gray-500">영상</dt>
                  <dd className="tabular-nums text-gray-100">
                    {fmtCount(info.video_count)}
                  </dd>
                </div>
              </dl>
            </div>
          </div>
        ) : authenticated === true ? (
          <p className="text-sm text-gray-400">
            인증은 유효하지만 채널 정보를 읽지 못했습니다. 네트워크 또는
            쿼터 문제일 수 있습니다.
          </p>
        ) : authenticated === false ? (
          <p className="text-sm text-gray-400">
            이 채널에 연결된 Google 계정이 없습니다. 인증 버튼을 누르면
            서버가 브라우저 팝업을 띄웁니다.
          </p>
        ) : (
          <p className="text-sm text-gray-500">상태 확인 중…</p>
        )}

        {error && (
          <p className="mt-3 text-xs text-red-300 break-all">오류: {error}</p>
        )}
      </div>

      {/* 액션 --------------------------------------------------------- */}
      <div className="mt-4 flex items-center gap-2">
        <V2Button size="sm" variant="ghost" onClick={onRefresh} disabled={busy}>
          새로고침
        </V2Button>
        <span className="flex-1" />
        {authenticated === true ? (
          <V2Button
            size="sm"
            variant="secondary"
            onClick={onReset}
            disabled={busy}
          >
            토큰 삭제
          </V2Button>
        ) : (
          <V2Button
            size="sm"
            variant="primary"
            onClick={onAuth}
            loading={busy}
            disabled={busy}
          >
            인증하기
          </V2Button>
        )}
      </div>
    </article>
  );
}
