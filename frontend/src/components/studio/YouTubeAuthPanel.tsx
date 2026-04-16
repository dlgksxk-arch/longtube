"use client";

import { useEffect, useState } from "react";
import {
  ShieldCheck,
  ShieldAlert,
  AlertCircle,
  ExternalLink,
  LogOut,
  Youtube,
} from "lucide-react";
import LoadingButton from "@/components/common/LoadingButton";
import { youtubeApi, type YouTubeChannelInfo } from "@/lib/api";

interface Props {
  projectId: string;
  /** 헤더를 간결하게 할 때 true (StepYouTube 의 작은 상태 표시용). */
  compact?: boolean;
}

/**
 * YouTube OAuth 인증 UI. StepSettings 에 embed 되어 프로젝트별 토큰을
 * 관리한다. StepYouTube 는 compact 모드로 상태만 표시하고 실제 인증 버튼은
 * 누르지 않아도 되게끔 Step 1 로 안내한다.
 */
export default function YouTubeAuthPanel({ projectId, compact = false }: Props) {
  const [authChecking, setAuthChecking] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);
  const [authing, setAuthing] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [channelInfo, setChannelInfo] = useState<YouTubeChannelInfo | null>(null);
  const [channelChecking, setChannelChecking] = useState(false);
  const [channelError, setChannelError] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setAuthChecking(true);
    (async () => {
      try {
        const s = await youtubeApi.projectAuthStatus(projectId);
        if (!cancelled) setAuthenticated(s.authenticated);
      } catch (e: any) {
        if (!cancelled) setAuthError(e?.message || "인증 상태 확인 실패");
      } finally {
        if (!cancelled) setAuthChecking(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  useEffect(() => {
    if (!authenticated) {
      setChannelInfo(null);
      return;
    }
    let cancelled = false;
    setChannelChecking(true);
    setChannelError(null);
    (async () => {
      try {
        const info = await youtubeApi.projectAuthChannel(projectId);
        if (!cancelled) setChannelInfo(info);
      } catch (e: any) {
        if (!cancelled) setChannelError(e?.message || "채널 정보 조회 실패");
      } finally {
        if (!cancelled) setChannelChecking(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [authenticated, projectId]);

  const handleAuthenticate = async () => {
    setAuthing(true);
    setAuthError(null);
    try {
      await youtubeApi.projectAuthenticate(projectId);
      const s = await youtubeApi.projectAuthStatus(projectId);
      setAuthenticated(s.authenticated);
    } catch (e: any) {
      setAuthError(e?.message || "OAuth 인증 실패");
    } finally {
      setAuthing(false);
    }
  };

  const handleResetAuth = async () => {
    if (
      !confirm(
        "이 프로젝트의 YouTube 토큰을 삭제하고 계정 선택 팝업을 다시 띄웁니다. 다른 프로젝트의 인증은 영향받지 않습니다. 진행할까요?"
      )
    ) {
      return;
    }
    setResetting(true);
    setAuthError(null);
    setChannelError(null);
    try {
      await youtubeApi.projectAuthReset(projectId);
      setChannelInfo(null);
      setAuthenticated(false);
      await youtubeApi.projectAuthenticate(projectId);
      const s = await youtubeApi.projectAuthStatus(projectId);
      setAuthenticated(s.authenticated);
    } catch (e: any) {
      setAuthError(e?.message || "계정 전환 실패");
    } finally {
      setResetting(false);
    }
  };

  return (
    <div className="bg-bg-secondary border border-border rounded-lg p-5 space-y-3">
      {!compact && (
        <div className="flex items-center gap-2 text-gray-300">
          <Youtube size={16} className="text-red-500" />
          <h3 className="text-sm font-medium">YouTube 계정 인증</h3>
          <span className="text-[10px] text-gray-500">(프로젝트별 토큰)</span>
        </div>
      )}

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {authChecking ? (
            <span className="text-sm text-gray-400">인증 상태 확인 중...</span>
          ) : authenticated ? (
            <>
              <ShieldCheck className="text-accent-success" size={18} />
              <span className="text-sm text-accent-success font-medium">
                YouTube 인증 완료
              </span>
            </>
          ) : (
            <>
              <ShieldAlert className="text-accent-warning" size={18} />
              <span className="text-sm text-accent-warning font-medium">
                YouTube 인증 필요
              </span>
            </>
          )}
        </div>
        <div className="flex items-center gap-2">
          {!authChecking && !authenticated && (
            <LoadingButton
              onClick={handleAuthenticate}
              loading={authing}
              icon={<ShieldCheck size={14} />}
              variant="primary"
            >
              {authing ? "브라우저 팝업 대기 중..." : "Google 계정으로 인증"}
            </LoadingButton>
          )}
          {!authChecking && authenticated && (
            <LoadingButton
              onClick={handleResetAuth}
              loading={resetting}
              icon={<LogOut size={12} />}
              variant="ghost"
            >
              {resetting ? "전환 중..." : "다른 계정으로 전환"}
            </LoadingButton>
          )}
        </div>
      </div>

      {authError && (
        <div className="text-xs text-accent-danger flex items-center gap-1">
          <AlertCircle size={12} /> {authError}
        </div>
      )}

      {authenticated && (
        <div>
          {channelChecking && (
            <div className="text-xs text-gray-500">채널 정보 불러오는 중...</div>
          )}
          {channelError && (
            <div className="text-xs text-accent-warning flex items-center gap-1">
              <AlertCircle size={12} /> {channelError}
            </div>
          )}
          {channelInfo && (
            <div className="flex items-center gap-3 p-2 rounded border border-border bg-bg-primary">
              {channelInfo.thumbnail && (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={channelInfo.thumbnail}
                  alt={channelInfo.title}
                  className="w-10 h-10 rounded-full border border-border"
                />
              )}
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-gray-200 truncate">
                  {channelInfo.title}
                </div>
                <div className="text-[10px] text-gray-500 truncate">
                  {channelInfo.channel_id}
                  {typeof channelInfo.subscriber_count === "number" && (
                    <> · 구독자 {channelInfo.subscriber_count.toLocaleString()}명</>
                  )}
                  {typeof channelInfo.video_count === "number" && (
                    <> · 영상 {channelInfo.video_count.toLocaleString()}개</>
                  )}
                </div>
              </div>
              <a
                href={`https://studio.youtube.com/channel/${channelInfo.channel_id}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[11px] text-accent-primary hover:underline flex items-center gap-1"
              >
                <ExternalLink size={11} /> Studio
              </a>
            </div>
          )}
        </div>
      )}

      {!authChecking && !authenticated && !compact && (
        <p className="text-[11px] text-gray-500 leading-relaxed">
          "인증" 버튼을 누르면 백엔드가 로컬 서버(localhost:8090)를 잠깐 열고 브라우저에 Google 로그인 창을
          팝업합니다. 프로젝트별로 1회만 필요합니다. 토큰은 <code>data/{"{project.id}"}/youtube_token.json</code> 에
          저장되어 이 프로젝트 전용으로 자동 갱신됩니다. <code>YOUTUBE_CLIENT_ID</code> /{" "}
          <code>YOUTUBE_CLIENT_SECRET</code> 환경변수가 미리 설정되어 있어야 합니다.
        </p>
      )}
    </div>
  );
}
