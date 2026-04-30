"use client";

import { useEffect, useState } from "react";
import {
  Youtube,
  ImageIcon,
  Upload,
  CheckCircle2,
  AlertCircle,
  ShieldCheck,
  ShieldAlert,
  ExternalLink,
  Sparkles,
  Trash2,
} from "lucide-react";
import LoadingButton from "@/components/common/LoadingButton";
import ModelSelector from "@/components/common/ModelSelector";
import {
  youtubeApi,
  modelsApi,
  projectsApi,
  scriptApi,
  resolveAssetUrl,
  type ModelInfo,
  type Project,
  type Cut,
  type YouTubePrivacy,
  type YouTubeUploadResult,
  type ThumbnailGenerateResult,
  type MetadataRecommendResult,
} from "@/lib/api";

interface Props {
  project: Project;
  cuts: Cut[];
  onUpdate: () => void;
}

function formatThumbnailEpisodeLabel(value: string): string {
  const digits = (value || "").replace(/\D/g, "");
  if (!digits) return "";
  return `EP.${digits.padStart(2, "0")}`;
}

function sanitizeThumbnailHook(value: string): string {
  return (value || "")
    .replace(/\bEP\.?\s*0*\d{1,3}\b/gi, "")
    .replace(/\s*[\[\(【][^\]\)】]{1,30}[\]\)】]\s*$/, "")
    .replace(/\s{2,}/g, " ")
    .trim()
    .replace(/^[·\-:\s]+|[·\-:\s]+$/g, "")
    .trim();
}

function getYouTubeChannelId(project: Project): number | null {
  const raw = (project.config as any)?.youtube_channel ?? (project.config as any)?.channel;
  const channelId =
    typeof raw === "number" ? raw : typeof raw === "string" ? Number.parseInt(raw, 10) : NaN;
  return Number.isFinite(channelId) && channelId >= 1 && channelId <= 4 ? channelId : null;
}

const PRIVACY_OPTIONS: { value: YouTubePrivacy; label: string; description: string }[] = [
  {
    value: "private",
    label: "비공개 (private)",
    description: "본인만 볼 수 있음. 안전하게 테스트할 때 권장.",
  },
  {
    value: "unlisted",
    label: "일부 공개 (unlisted)",
    description: "링크가 있는 사람만 볼 수 있음. 검색 노출 안 됨.",
  },
  {
    value: "public",
    label: "전체 공개 (public)",
    description: "모든 사람이 볼 수 있음. 되돌리려면 YouTube Studio 에서 직접 변경해야 함.",
  },
];

export default function StepYouTube({ project, cuts, onUpdate }: Props) {
  const youtubeChannelId = getYouTubeChannelId(project);
  const [authChecking, setAuthChecking] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);

  const [episodeNumber, setEpisodeNumber] = useState<string>("");
  const [title, setTitle] = useState(project.title || "");
  const [titleHook, setTitleHook] = useState("");
  // ★ 영상 설명은 DB 의 project.topic 이 아니라 config.youtube_description 에 저장한다.
  // 과거 버그: `useState(project.topic || "")` + onBlur persist 가 topic 을 통째로
  // 덮어써서, AI 가 써준 5000자짜리 YouTube 설명 전문이 project.topic 에 들어가
  // 헤더가 거대한 벽이 되어 버렸다. topic 은 짧은 주제어 전용, description 은
  // config 로 분리.
  const [description, setDescription] = useState<string>(
    (project.config as any)?.youtube_description || "",
  );
  const [tagsInput, setTagsInput] = useState("");
  // v1.1.55: 공개 범위는 프리셋 설정(config.youtube_privacy) 에서 관리.
  // StepYouTube 에서는 config 값을 읽기만 한다.
  const privacy: YouTubePrivacy = ((project.config as any)?.youtube_privacy || "private") as YouTubePrivacy;
  const [madeForKids, setMadeForKids] = useState(false);

  const [thumbMainHook, setThumbMainHook] = useState("");
  const [thumbMainHookTouched, setThumbMainHookTouched] = useState(false);
  const [thumbSubtitle, setThumbSubtitle] = useState("");
  const [thumbEpisodeLabel, setThumbEpisodeLabel] = useState("");
  const [thumbGenerating, setThumbGenerating] = useState(false);
  const [thumbResult, setThumbResult] = useState<ThumbnailGenerateResult | null>(null);
  const [thumbError, setThumbError] = useState<string | null>(null);
  const [thumbBust, setThumbBust] = useState<number>(0);
  // 썸네일 전용 이미지 모델. 기본값은 프로젝트 설정의 image_model 을 그대로 쓴다.
  const [thumbModel, setThumbModel] = useState<string>((project.config as any).thumbnail_model || project.config.image_model || "");
  const [imageModels, setImageModels] = useState<ModelInfo[]>([]);
  const [thumbCustomPrompt, setThumbCustomPrompt] = useState<string>("");

  const [tagsRecommending, setTagsRecommending] = useState(false);
  const [tagsSource, setTagsSource] = useState<"llm" | "heuristic" | null>(null);
  const [tagsError, setTagsError] = useState<string | null>(null);

  const [metaRecommending, setMetaRecommending] = useState(false);
  const [metaResult, setMetaResult] = useState<MetadataRecommendResult | null>(null);
  const [metaError, setMetaError] = useState<string | null>(null);

  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<YouTubeUploadResult | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // 프로젝트 제목/주제 자동 저장 상태 (onBlur PUT)
  const [savingProject, setSavingProject] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleteMessage, setDeleteMessage] = useState<string | null>(null);

  const [clearingStep, setClearingStep] = useState(false);
  const [clearStepError, setClearStepError] = useState<string | null>(null);

  // 이미지 모델 목록 — 썸네일용 드롭다운에 사용.
  useEffect(() => {
    modelsApi.listImage().then((d) => setImageModels(d.models || [])).catch(() => {});
  }, []);

  // OAuth 상태 체크 (브라우저 팝업 없음) — 실제 인증은 Step 1 설정에서 수행.
  // 여기서는 업로드 버튼 활성화 여부만 판단한다.
  useEffect(() => {
    let cancelled = false;
    setAuthChecking(true);
    (async () => {
      try {
        const s = youtubeChannelId
          ? await youtubeApi.channelAuthStatus(youtubeChannelId)
          : await youtubeApi.projectAuthStatus(project.id);
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
  }, [project.id, youtubeChannelId]);

  // 썸네일 메인 후크 텍스트 자동 기본값 — titleHook 이 있을 때만 세팅.
  // title 은 절대 fallback 으로 쓰지 않는다 (project.title 이 채널명으로 잘못
  // 잡힌 과거 사례 때문에). titleHook 이 없으면 사용자가 직접 입력하거나
  // 'AI 전체 추천' 을 눌러야 한다.
  useEffect(() => {
    if (thumbMainHookTouched) return;
    const fromHook = sanitizeThumbnailHook(titleHook.trim());
    if (fromHook) setThumbMainHook(fromHook);
  }, [titleHook, thumbMainHookTouched]);

  // 에피소드 번호가 바뀌면 썸네일 배지 라벨 기본값 자동 세팅 (사용자가 수동 편집 안 했을 때만)
  useEffect(() => {
    const n = episodeNumber.trim();
    if (!n) return;
    const defaultLabel = formatThumbnailEpisodeLabel(n);
    setThumbEpisodeLabel((prev) => {
      // 기존 값이 비어있거나 자동값 패턴이면 갱신
      if (!prev || /^EP\.?\s*\d+$/i.test(prev)) return defaultLabel;
      return prev;
    });
  }, [episodeNumber]);

  // 이미 업로드된 적이 있으면 초기 표시
  useEffect(() => {
    if (project.youtube_url && !uploadResult) {
      setUploadResult({
        status: "uploaded",
        project_id: project.id,
        video_id: "",
        video_url: project.youtube_url,
        title: project.title,
        privacy,
        thumbnail_used: false,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.youtube_url]);

  // project.title 과 config.youtube_description 을 백엔드에 PUT 저장.
  // ★ 절대 project.topic 을 description 으로 덮어쓰지 않는다 — topic 은 프로젝트
  // 생성 시 사용자가 넣은 짧은 주제어 전용이고, 헤더에 그대로 노출되기 때문.
  // description 은 config.youtube_description 에 분리 저장.
  const persistProjectMeta = async (nextTitle: string, nextDescription: string) => {
    const payload: { title?: string; config?: Record<string, any> } = {};
    if (nextTitle !== (project.title || "")) payload.title = nextTitle;
    const prevDesc = (project.config as any)?.youtube_description || "";
    if (nextDescription !== prevDesc) {
      payload.config = { youtube_description: nextDescription };
    }
    if (Object.keys(payload).length === 0) return;
    setSavingProject(true);
    setSaveError(null);
    try {
      await projectsApi.update(project.id, payload);
      setSavedAt(Date.now());
      onUpdate();
    } catch (e: any) {
      setSaveError(e?.message || "프로젝트 저장 실패");
    } finally {
      setSavingProject(false);
    }
  };

  const handleRecommendMetadata = async () => {
    setMetaRecommending(true);
    setMetaError(null);
    try {
      const epRaw = episodeNumber.trim();
      const epNum = epRaw ? Number(epRaw) : undefined;
      const res = await youtubeApi.recommendMetadata(project.id, {
        title: title.trim() || undefined,
        // ★ 원본 topic 을 그대로 LLM 컨텍스트로 넘김. 이전엔 description 을 topic
        // 으로 넘겨서 description 길이가 점점 부풀어 올라가는 피드백 루프가 있었음.
        topic: (project.topic || "").trim() || undefined,
        max_tags: 15,
        episode_number: epNum && Number.isFinite(epNum) ? epNum : null,
      });
      // 모든 필드를 덮어씀 — 사용자가 "AI 전체 추천" 을 누른 의도는 교체이지 병합이 아님.
      setTitle(res.title);
      setTitleHook(res.title_hook || "");
      setDescription(res.description);
      setTagsInput(res.tags.join(", "));
      // AI 가 갈아낀 title 과 description 을 즉시 DB 반영. description 은 topic 이
      // 아니라 config.youtube_description 에 저장됨 (persistProjectMeta 내부 분리).
      persistProjectMeta(res.title.trim(), res.description.trim()).catch(() => {});
      // title_hook 이 있으면 썸네일 메인 후크 텍스트로 그대로 넘기기 좋음
      if (res.title_hook) {
        setThumbSubtitle((prev) => prev || ""); // subtitle 은 건드리지 않음
      }
      setMetaResult(res);
      setTagsSource(null); // 태그 소스 뱃지는 태그 전용 버튼용으로 리셋
      if (res.error) {
        setMetaError(`LLM 일부 실패 → 폴백 사용: ${res.error}`);
      }
    } catch (e: any) {
      setMetaError(e?.message || "메타데이터 추천 실패");
    } finally {
      setMetaRecommending(false);
    }
  };

  const handleRecommendTags = async () => {
    setTagsRecommending(true);
    setTagsError(null);
    try {
      const res = await youtubeApi.recommendTags(project.id, {
        title: title.trim() || undefined,
        topic: (project.topic || "").trim() || undefined,
        max_tags: 15,
      });
      // 기존 태그와 병합 (사용자가 먼저 입력한 건 유지)
      const existing = tagsInput
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      const merged: string[] = [...existing];
      for (const t of res.tags) {
        if (!merged.some((m) => m.toLowerCase() === t.toLowerCase())) {
          merged.push(t);
        }
      }
      setTagsInput(merged.join(", "));
      setTagsSource(res.source);
      if (res.error) {
        setTagsError(`LLM 호출 실패 → 휴리스틱 폴백: ${res.error}`);
      }
    } catch (e: any) {
      setTagsError(e?.message || "태그 추천 실패");
    } finally {
      setTagsRecommending(false);
    }
  };

  const handleGenerateThumbnail = async () => {
    setThumbGenerating(true);
    setThumbError(null);
    try {
      // 썸네일 메인 후크 텍스트는 전용 입력 필드에서 그대로 가져온다.
      // 비어 있으면 아예 생성을 막는다 — 과거에 project.title(= 채널명)이
      // 실수로 썸네일에 박히던 버그 방지.
      const mainHook = sanitizeThumbnailHook(thumbMainHook.trim());
      if (!mainHook) {
        setThumbError("썸네일 메인 후크 텍스트가 비어있습니다. 'AI 전체 추천' 을 누르거나 직접 입력하세요.");
        setThumbGenerating(false);
        return;
      }
      const res = await youtubeApi.generateThumbnail(project.id, {
        title: mainHook,
        subtitle: thumbSubtitle.trim() || undefined,
        episode_label: formatThumbnailEpisodeLabel(thumbEpisodeLabel.trim()) || undefined,
        image_model: thumbModel || undefined,
        prompt: thumbCustomPrompt.trim() || undefined,
      });
      setThumbResult(res);
      setThumbBust(Date.now());
    } catch (e: any) {
      setThumbError(e?.message || "썸네일 생성 실패");
    } finally {
      setThumbGenerating(false);
    }
  };

  const handleDeleteUpload = async () => {
    // 업로드된 영상이 있거나 upload_result 가 있어야 삭제 가능
    const urlToDelete = uploadResult?.video_url || project.youtube_url;
    if (!urlToDelete) {
      setDeleteError("삭제할 영상이 없습니다.");
      return;
    }
    const ok = window.confirm(
      "정말로 YouTube 에서 이 영상을 삭제하시겠습니까?\n" +
        "삭제된 영상은 복구할 수 없습니다.\n\n" +
        urlToDelete,
    );
    if (!ok) return;

    setDeleting(true);
    setDeleteError(null);
    setDeleteMessage(null);
    try {
      const res = await youtubeApi.deleteUpload(project.id, {
        confirm: true,
        clear_project_url: true,
      });
      setUploadResult(null);
      setDeleteMessage(
        res.status === "already_gone"
          ? "YouTube 에는 이미 없는 영상이었습니다. 프로젝트 링크를 비웠습니다."
          : "YouTube 에서 영상을 삭제했습니다.",
      );
      onUpdate();
    } catch (e: any) {
      setDeleteError(e?.message || "영상 삭제 실패");
    } finally {
      setDeleting(false);
    }
  };

  const handleClearStep = async () => {
    const ok = window.confirm(
      "유튜브 스텝을 초기화하시겠습니까?\n(제목·설명·태그·썸네일·업로드 기록이 모두 리셋됩니다)",
    );
    if (!ok) return;
    setClearingStep(true);
    setClearStepError(null);
    try {
      await scriptApi.clearStep(project.id, "youtube");
      // 로컬 state 전부 리셋
      setTitle(project.topic || "");
      setTitleHook("");
      setDescription("");
      setTagsInput("");
      setThumbMainHook("");
      setThumbMainHookTouched(false);
      setThumbSubtitle("");
      setThumbEpisodeLabel("");
      setThumbResult(null);
      setThumbError(null);
      setThumbCustomPrompt("");
      setUploadResult(null);
      setUploadError(null);
      setDeleteMessage(null);
      setDeleteError(null);
      setMetaResult(null);
      onUpdate();
    } catch (e: any) {
      setClearStepError(e?.message || "초기화 실패");
    } finally {
      setClearingStep(false);
    }
  };

  const handleUpload = async () => {
    setUploading(true);
    setUploadError(null);
    try {
      const parsedTags = tagsInput
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      const res = await youtubeApi.upload(project.id, {
        title: title.trim() || undefined,
        description: description.trim() || undefined,
        tags: parsedTags.length > 0 ? parsedTags : undefined,
        privacy,
        language: "ko",
        made_for_kids: madeForKids,
        use_generated_thumbnail: thumbResult !== null,
      });
      setUploadResult(res);
      onUpdate();
    } catch (e: any) {
      setUploadError(e?.message || "업로드 실패");
    } finally {
      setUploading(false);
    }
  };

  const hasImageCut = cuts.some((c) => c.image_path);
  const thumbUrl = thumbResult
    ? `${resolveAssetUrl(thumbResult.thumbnail_url)}?t=${thumbBust}`
    : null;

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {/* 고정 헤더 */}
      <div className="flex-shrink-0 flex items-center justify-between pb-4">
        <div className="flex items-center gap-3">
          <Youtube className="text-red-500" size={28} />
          <div>
            <h2 className="text-xl font-semibold">YouTube 업로드</h2>
            <p className="text-xs text-gray-500">최종 영상을 YouTube 에 게시합니다.</p>
          </div>
        </div>
        <LoadingButton
          onClick={handleClearStep}
          loading={clearingStep}
          icon={<Trash2 size={14} />}
          variant="danger"
          disabled={clearingStep || uploading}
        >
          초기화
        </LoadingButton>
      </div>
      {clearStepError && (
        <div className="flex-shrink-0 text-xs text-accent-danger flex items-center gap-1 pb-2">
          <AlertCircle size={12} /> {clearStepError}
        </div>
      )}

      {/* 스크롤 영역 */}
      <div className="flex-1 overflow-y-auto space-y-6">

      {/* OAuth 상태 요약 (실제 인증은 Step 1 설정에서 수행) */}
      <div className="border border-border rounded-lg p-3 bg-bg-secondary flex items-center justify-between">
        <div className="flex items-center gap-2">
          {authChecking ? (
            <span className="text-sm text-gray-400">인증 상태 확인 중...</span>
          ) : authenticated ? (
            <>
              <ShieldCheck className="text-accent-success" size={16} />
              <span className="text-sm text-accent-success font-medium">
                YouTube 인증 완료
              </span>
              <span className="text-[10px] text-gray-500">(이 프로젝트 전용)</span>
            </>
          ) : (
            <>
              <ShieldAlert className="text-accent-warning" size={16} />
              <span className="text-sm text-accent-warning font-medium">
                YouTube 인증이 필요합니다
              </span>
            </>
          )}
        </div>
        {!authChecking && !authenticated && (
          <span className="text-[11px] text-gray-400">
            Step 1 <span className="text-accent-primary font-medium">설정</span> → YouTube 계정 인증에서 연결하세요.
          </span>
        )}
      </div>
      {authError && (
        <div className="text-xs text-accent-danger flex items-center gap-1">
          <AlertCircle size={12} /> {authError}
        </div>
      )}

      {/* project.title 이 아직 비어있거나 의심스러우면 경고 */}
      {project.title && !titleHook && title === (project.title || "") && (
        <div className="border border-accent-warning/40 bg-accent-warning/10 rounded-lg p-3 text-[11px] text-accent-warning">
          <AlertCircle size={12} className="inline mr-1" />
          현재 영상 제목이 DB 에 저장된 <code className="font-mono">project.title</code> 값 "{project.title}" 그대로입니다.
          채널명이나 잘못된 값이 들어가 있다면 아래 <strong>제목</strong> 입력란에서 직접 수정하거나
          <strong> "AI 전체 추천"</strong> 을 눌러 다시 생성하세요. 입력란을 떠나면 자동 저장됩니다.
        </div>
      )}

      {/* 메타데이터 폼 */}
      <div className="border border-border rounded-lg p-4 bg-bg-secondary space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-300">영상 정보</h3>
          <LoadingButton
            onClick={handleRecommendMetadata}
            loading={metaRecommending}
            icon={<Sparkles size={14} />}
            variant="primary"
          >
            {metaRecommending ? "생성 중..." : "AI 전체 추천 (제목·설명·태그)"}
          </LoadingButton>
        </div>
        {metaResult && (
          <div className="text-[11px] text-gray-500 flex items-center gap-2">
            <span>언어: {metaResult.language.toUpperCase()}</span>
            <span>·</span>
            <span>
              {metaResult.source === "llm"
                ? "LLM 전체 생성"
                : metaResult.source === "partial"
                ? "LLM 부분 + 폴백 일부"
                : "휴리스틱 폴백"}
            </span>
          </div>
        )}
        {metaError && (
          <div className="text-[11px] text-accent-warning flex items-center gap-1">
            <AlertCircle size={11} /> {metaError}
          </div>
        )}

        <div className="grid grid-cols-[90px_1fr] gap-2">
          <div>
            <label className="block text-xs text-gray-400 mb-1">에피소드</label>
            <input
              type="number"
              min={1}
              value={episodeNumber}
              onChange={(e) => setEpisodeNumber(e.target.value)}
              placeholder="1"
              className="w-full px-3 py-2 bg-bg-primary border border-border rounded text-sm"
            />
            <div className="text-[10px] text-gray-500 mt-1">EP. N</div>
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1 flex items-center gap-2">
              제목
              {savingProject && <span className="text-[10px] text-gray-500">저장 중...</span>}
              {!savingProject && savedAt && (
                <span className="text-[10px] text-accent-success">저장됨</span>
              )}
              {saveError && (
                <span className="text-[10px] text-accent-danger">저장 실패: {saveError}</span>
              )}
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onBlur={() => persistProjectMeta(title.trim(), description.trim())}
              placeholder={episodeNumber ? `EP. ${episodeNumber} - 짧은 후크` : "영상 제목"}
              className="w-full px-3 py-2 bg-bg-primary border border-border rounded text-sm"
              maxLength={100}
            />
            <div className="text-[10px] text-gray-500 mt-1">
              {title.length}/100
              {titleHook && <span className="ml-2 text-gray-600">후크: "{titleHook}"</span>}
              <span className="ml-2 text-gray-600">· 입력란을 떠나면 자동 저장됨</span>
            </div>
          </div>
        </div>

        <div>
          <label className="block text-xs text-gray-400 mb-1">설명</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            onBlur={() => persistProjectMeta(title.trim(), description.trim())}
            placeholder="영상 설명"
            className="w-full px-3 py-2 bg-bg-primary border border-border rounded text-sm min-h-[220px] resize-y font-mono"
            maxLength={5000}
          />
          <div className="text-[10px] text-gray-500 mt-1">{description.length}/5000 · 입력란을 떠나면 자동 저장됨</div>
        </div>

        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="block text-xs text-gray-400">태그 (쉼표로 구분)</label>
            <LoadingButton
              onClick={handleRecommendTags}
              loading={tagsRecommending}
              icon={<Sparkles size={12} />}
              variant="ghost"
            >
              {tagsRecommending ? "추천 중..." : "AI 태그 추천"}
            </LoadingButton>
          </div>
          <input
            type="text"
            value={tagsInput}
            onChange={(e) => setTagsInput(e.target.value)}
            placeholder="예: 역사, 다큐, 한국사"
            className="w-full px-3 py-2 bg-bg-primary border border-border rounded text-sm"
          />
          <div className="text-[10px] text-gray-500 mt-1 flex items-center gap-2">
            <span>제목 · 주제 · 대본 기반 자동 추천</span>
            {tagsSource === "llm" && <span className="text-accent-success">LLM 사용</span>}
            {tagsSource === "heuristic" && (
              <span className="text-accent-warning">키워드 폴백</span>
            )}
          </div>
          {tagsError && (
            <div className="text-[11px] text-accent-warning flex items-center gap-1 mt-1">
              <AlertCircle size={11} /> {tagsError}
            </div>
          )}
        </div>

        {/* v1.1.55: 공개 범위는 프리셋 설정(Step 1)에서 관리. 여기선 읽기 전용 표시. */}
        <div>
          <label className="block text-xs text-gray-400 mb-2">
            공개 범위{" "}
            <span className="text-gray-600">(설정 탭에서 변경)</span>
          </label>
          <div className="px-3 py-2 rounded border border-border bg-bg-primary text-sm text-gray-300">
            {PRIVACY_OPTIONS.find((o) => o.value === privacy)?.label || "비공개 (private)"}
          </div>
        </div>

        <label className="flex items-center gap-2 text-xs text-gray-400">
          <input
            type="checkbox"
            checked={madeForKids}
            onChange={(e) => setMadeForKids(e.target.checked)}
          />
          아동용 콘텐츠 (YouTube Kids 정책 적용)
        </label>
      </div>

      {/* 썸네일 */}
      <div className="border border-border rounded-lg p-4 bg-bg-secondary">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-300 flex items-center gap-2">
            <ImageIcon size={16} /> 썸네일
          </h3>
          <LoadingButton
            onClick={handleGenerateThumbnail}
            loading={thumbGenerating}
            icon={<ImageIcon size={14} />}
            variant="ghost"
          >
            {thumbResult ? "다시 생성" : "썸네일 생성"}
          </LoadingButton>
        </div>

        <div className="mb-3">
          <label className="block text-xs text-gray-400 mb-1">
            메인 후크 텍스트 <span className="text-accent-warning">(썸네일에 크게 박힘)</span>
          </label>
          <input
            type="text"
            value={thumbMainHook}
            onChange={(e) => {
              setThumbMainHook(e.target.value);
              setThumbMainHookTouched(true);
            }}
            placeholder="예: 석유의 진짜 비밀"
            className="w-full px-3 py-2 bg-bg-primary border border-border rounded text-sm"
            maxLength={60}
          />
          <div className="text-[10px] text-gray-500 mt-1">
            {thumbMainHookTouched
              ? "직접 편집한 상태입니다."
              : "자동값: titleHook > title 에서 'EP. N - ' 제거. 'AI 전체 추천' 후 바뀝니다."}
            {titleHook && <span className="ml-2 text-gray-600">후크: "{titleHook}"</span>}
          </div>
        </div>
        <div className="grid grid-cols-[120px_1fr] gap-2 mb-3">
          <div>
            <label className="block text-xs text-gray-400 mb-1">에피소드 배지</label>
            <input
              type="text"
              value={thumbEpisodeLabel}
              onChange={(e) => setThumbEpisodeLabel(e.target.value)}
              placeholder="EP.01"
              className="w-full px-3 py-2 bg-bg-primary border border-border rounded text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">
              보조 라인 <span className="text-gray-600">(선택)</span>
            </label>
            <input
              type="text"
              value={thumbSubtitle}
              onChange={(e) => setThumbSubtitle(e.target.value)}
              placeholder="메인 후크 위에 들어가는 짧은 문구"
              className="w-full px-3 py-2 bg-bg-primary border border-border rounded text-sm"
            />
          </div>
        </div>

        {/* 썸네일 이미지 모델 + 커스텀 프롬프트 */}
        <div className="grid grid-cols-[240px_1fr] gap-2 mb-3">
          <ModelSelector
            label="썸네일 이미지 모델"
            models={imageModels}
            value={thumbModel || project.config.image_model}
            onChange={setThumbModel}
          />
          <div>
            <label className="block text-xs text-gray-400 mb-1">
              커스텀 프롬프트 <span className="text-gray-600">(선택 · 비워두면 LLM 이 제목·주제 기반으로 자동 생성)</span>
            </label>
            <textarea
              value={thumbCustomPrompt}
              onChange={(e) => setThumbCustomPrompt(e.target.value)}
              rows={2}
              placeholder="예: cinematic dramatic lighting, extreme close-up, high contrast, bold colors, shocking expression, 4k"
              className="w-full px-3 py-2 bg-bg-primary border border-border rounded text-sm placeholder:text-gray-600 resize-none"
            />
          </div>
        </div>

        {!hasImageCut && (
          <div className="text-xs text-accent-warning flex items-center gap-1 mb-2">
            <AlertCircle size={12} /> 이미지가 생성된 컷이 없습니다. cut_overlay 모드에서는 다크 폴백 배경이 사용됩니다.
          </div>
        )}

        {thumbError && (
          <div className="text-xs text-accent-danger flex items-center gap-1 mb-2">
            <AlertCircle size={12} /> {thumbError}
          </div>
        )}

        <div className="w-full aspect-video bg-bg-primary rounded border border-border overflow-hidden flex items-center justify-center">
          {thumbUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={thumbUrl} alt="Generated thumbnail" className="w-full h-full object-cover" />
          ) : (
            <div className="text-xs text-gray-600">아직 썸네일이 생성되지 않았습니다.</div>
          )}
        </div>

        {thumbResult && (
          <div className="mt-2 space-y-1">
            <p className="text-[10px] text-gray-500">
              저장 경로: {thumbResult.thumbnail_path}
            </p>
            {/* 레퍼런스 스타일 진단 — "이미지가 레퍼런스와 다르다" 원인 즉시 확인 */}
            {thumbResult.reference_diagnostics && (
              <p
                className={
                  thumbResult.reference_images_used && thumbResult.reference_images_used > 0
                    ? "text-[10px] text-accent-success"
                    : "text-[10px] text-accent-warning"
                }
              >
                레퍼런스 스타일:{" "}
                {thumbResult.reference_images_used && thumbResult.reference_images_used > 0 ? (
                  <>
                    {thumbResult.reference_images_used}장 전달됨 (등록{" "}
                    {thumbResult.reference_diagnostics.registered_reference_images}장, 캐릭터{" "}
                    {thumbResult.reference_diagnostics.registered_character_images}장)
                    {thumbResult.reference_fallback && (
                      <> · 모델 폴백: {thumbResult.reference_fallback}</>
                    )}
                  </>
                ) : (
                  <>
                    ⚠ 모델에 전달된 레퍼런스 0장 — 프로젝트 설정 '이미지' 탭에서 '스타일
                    레퍼런스' 를 업로드해야 생성 이미지가 해당 스타일을 따라갑니다. (설정에
                    등록 {thumbResult.reference_diagnostics.registered_reference_images}장,
                    디스크에서 찾음 {thumbResult.reference_diagnostics.resolved_reference_images}장
                    {thumbResult.reference_diagnostics.missing_reference_images > 0 && (
                      <>
                        , 누락{" "}
                        {thumbResult.reference_diagnostics.missing_reference_images}장
                      </>
                    )})
                  </>
                )}
              </p>
            )}
          </div>
        )}
      </div>

      {/* 업로드 버튼 + 결과 */}
      <div className="border border-border rounded-lg p-4 bg-bg-secondary">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-300">업로드</h3>
          <LoadingButton
            onClick={handleUpload}
            loading={uploading}
            disabled={!authenticated || uploading}
            icon={<Upload size={14} />}
            variant="primary"
          >
            {uploading ? "업로드 중..." : "YouTube 에 업로드"}
          </LoadingButton>
        </div>

        {!authenticated && (
          <div className="text-xs text-gray-500 mb-2">
            업로드하려면 먼저 Step 1 설정에서 "Google 계정으로 인증" 을 완료해주세요.
          </div>
        )}

        {uploadError && (
          <div className="text-xs text-accent-danger flex items-center gap-1">
            <AlertCircle size={12} /> {uploadError}
          </div>
        )}

        {uploadResult && uploadResult.video_url && (
          <div className="mt-2 p-3 bg-accent-success/10 border border-accent-success/30 rounded">
            <div className="flex items-center gap-2 mb-2">
              <CheckCircle2 className="text-accent-success" size={16} />
              <span className="text-sm font-medium text-accent-success">업로드 완료</span>
            </div>
            <a
              href={uploadResult.video_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-accent-primary hover:underline flex items-center gap-1 break-all"
            >
              <ExternalLink size={12} /> {uploadResult.video_url}
            </a>
            {uploadResult.thumbnail_error && (
              <div className="mt-2 text-[11px] text-accent-warning">
                ⚠ 썸네일 업로드는 실패했습니다: {uploadResult.thumbnail_error}
              </div>
            )}
            <div className="mt-3 pt-3 border-t border-accent-success/20 flex items-center justify-between">
              <span className="text-[11px] text-gray-500">
                잘못 올렸으면 YouTube 에서 직접 삭제할 수 있습니다.
              </span>
              <LoadingButton
                onClick={handleDeleteUpload}
                loading={deleting}
                disabled={deleting || !authenticated}
                icon={<Trash2 size={12} />}
                variant="danger"
              >
                {deleting ? "삭제 중..." : "YouTube 에서 삭제"}
              </LoadingButton>
            </div>
          </div>
        )}

        {deleteMessage && (
          <div className="mt-2 text-[11px] text-accent-success flex items-center gap-1">
            <CheckCircle2 size={11} /> {deleteMessage}
          </div>
        )}
        {deleteError && (
          <div className="mt-2 text-[11px] text-accent-danger flex items-center gap-1">
            <AlertCircle size={11} /> {deleteError}
          </div>
        )}
      </div>
      </div>{/* 스크롤 영역 끝 */}
    </div>
  );
}
