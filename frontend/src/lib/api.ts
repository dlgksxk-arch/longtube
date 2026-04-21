// v2.0.74: LAN 접속 지원.
// 백엔드 호스트는 다음 우선순위로 결정한다:
//   1) NEXT_PUBLIC_API_BASE 환경변수 (빌드 타임 주입)
//   2) 브라우저에서 로드된 호스트명 + :8000 (같은 머신에서 프런트/백이 도는 전형적 셋업)
//   3) 로컬 개발 폴백 http://localhost:8000
// 2)를 쓰면 192.168.x.x 로 접속한 다른 PC 도 자동으로 그 IP 의 백엔드를 바라본다.
const _envApi = process.env.NEXT_PUBLIC_API_BASE;
const _envAsset = process.env.NEXT_PUBLIC_ASSET_BASE;
function _deriveAssetBase(): string {
  if (_envAsset) return _envAsset.replace(/\/$/, "");
  if (typeof window !== "undefined" && window.location?.hostname) {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return "http://localhost:8000";
}
function _deriveApiBase(): string {
  if (_envApi) return _envApi.replace(/\/$/, "");
  return `${_deriveAssetBase()}/api`;
}
const BASE_URL = _deriveApiBase();

// v1.1.28: AbortSignal 지원. 호출 측에서 취소할 수 있어야 "긴급중지" 가 가능.
// v1.1.29: 네트워크 오류 / HTTP 오류 / JSON 파싱 오류를 구분해서 구체적인 메시지로 던진다.
async function request(
  method: string,
  path: string,
  body?: any,
  isFormData?: boolean,
  signal?: AbortSignal,
) {
  const options: RequestInit = {
    method,
    headers: isFormData ? {} : { "Content-Type": "application/json" },
    signal,
  };
  if (body) {
    options.body = isFormData ? body : JSON.stringify(body);
  }
  const url = `${BASE_URL}${path}`;
  let res: Response;
  try {
    res = await fetch(url, options);
  } catch (e) {
    // fetch 자체가 실패 — 백엔드 미기동, CORS 차단, 네트워크 단절 등
    const msg = (e as Error)?.message || String(e);
    console.error(`[api] ${method} ${url} → NETWORK ERROR:`, e);
    throw new Error(`네트워크 오류: ${method} ${url} (${msg}) — 백엔드 서버(8000)가 켜져있는지 확인하세요.`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = j?.detail || JSON.stringify(j);
    } catch {
      try {
        detail = await res.text();
      } catch {
        /* empty */
      }
    }
    console.error(`[api] ${method} ${url} → HTTP ${res.status}: ${detail}`);
    throw new Error(`HTTP ${res.status} ${method} ${path}: ${detail}`);
  }
  return res.json();
}

export const api = {
  get: (path: string, signal?: AbortSignal) => request("GET", path, undefined, false, signal),
  post: (path: string, body?: any, signal?: AbortSignal) =>
    request("POST", path, body, false, signal),
  put: (path: string, body?: any, signal?: AbortSignal) =>
    request("PUT", path, body, false, signal),
  delete: (path: string, signal?: AbortSignal) =>
    request("DELETE", path, undefined, false, signal),
  upload: (path: string, formData: FormData, signal?: AbortSignal) =>
    request("POST", path, formData, true, signal),
};

// ─── Models ───
export interface ModelInfo {
  id: string;
  name: string;
  provider: string;
  description?: string;
  cost_per_unit?: string;
  cost_value?: number;
  cost_input?: number;
  cost_output?: number;
  available?: boolean;
}

export const modelsApi = {
  listLLM: (): Promise<{ models: ModelInfo[] }> => api.get("/models/llm"),
  listImage: (): Promise<{ models: ModelInfo[] }> => api.get("/models/image"),
  listVideo: (): Promise<{ models: ModelInfo[] }> => api.get("/models/video"),
  listTTS: (): Promise<{ models: ModelInfo[] }> => api.get("/models/tts"),
};

// ─── Projects ───
export interface ProjectConfig {
  aspect_ratio: string;
  target_duration: number;
  cut_transition: string;
  style: string;
  script_model: string;
  image_model: string;
  thumbnail_model?: string;
  video_model: string;
  // v1.1.36: 영상 제작 대상 — "all" | "every_3" | "every_4" | "every_5" | "character_only"
  video_target_selection?: string;
  tts_model: string;
  tts_voice_id: string;
  tts_voice_lang?: string;
  tts_voice_preset?: string;
  /** 음성 속도. 1.0=기본, <1.0=느리게, >1.0=빠르게. OpenAI:0.25~4.0, ElevenLabs:0.7~1.2. */
  tts_speed?: number;
  language: string;
  auto_pause_after_step: boolean;
  image_global_prompt?: string;
  character_description?: string;
  /** v1.1.73: 대본 생성 시 LLM 에 "최우선 제약" 으로 주입되는 자유 텍스트.
   *  예: "환단고기 등 위서 인용 금지 / 사료 부족 시 '설이 있다' 로 열어둘 것". */
  content_constraints?: string;
  // 레퍼런스 자산 경로 목록 (DB 대신 project.config 에 보관)
  reference_images?: string[];
  character_images?: string[];
  logo_images?: string[];
  subtitle_style: {
    font: string;
    size: number;
    color: string;
    outline_color: string;
    position: string;
    bg_enabled?: boolean;
    bg_color?: string;
    bg_opacity?: number;
  };
  /** v1.1.55: YouTube 공개 범위 — "private" | "unlisted" | "public" */
  youtube_privacy?: string;
}

// v1.1.33: 프로젝트 예상 소요시간/비용
// v1.1.35: 원화 환산 + 월 예상 + tier 추가
export interface ProjectEstimate {
  estimated_cuts: number;
  target_duration: number;
  estimated_cost_usd: number;
  estimated_cost_krw?: number;
  monthly_cost_usd?: number;
  monthly_cost_krw?: number;
  cost_tier?: "cheap" | "normal" | "expensive";
  usd_to_krw?: number;
  days_per_month?: number;
  estimated_seconds: number;
  cost_breakdown: {
    llm_script: number;
    image_generation: number;
    tts: number;
    video: number;
  };
  time_breakdown: {
    llm_script: number;
    image_generation: number;
    tts: number;
    video: number;
    post_process: number;
  };
  models_used: {
    script: string;
    image: string;
    tts: string;
    video: string;
  };
  // v1.1.36: 영상 제작 대상 — 선택되지 않은 컷은 ffmpeg-kenburns 폴백 (비용 0)
  video_target_selection?: string;
  ai_video_cuts?: number;
  fallback_video_cuts?: number;
}

export interface Project {
  id: string;
  title: string;
  topic: string;
  config: ProjectConfig;
  status: string;
  current_step: number;
  step_states: Record<string, string>;
  total_cuts: number;
  youtube_url: string;
  api_cost: number;
  created_at: string;
  updated_at: string;
  // v1.1.33: 선택된 모델 조합 기반 추정치 (서버 계산, 모든 응답에 포함)
  estimate?: ProjectEstimate;
}

export interface Cut {
  cut_number: number;
  narration: string;
  image_prompt: string;
  scene_type: string;
  duration_estimate?: number;
  audio_path?: string;
  audio_duration?: number;
  image_path?: string;
  image_model?: string;
  video_path?: string;
  video_model?: string;
  status?: string;
  is_custom_image?: boolean;
}

export const projectsApi = {
  list: (): Promise<Project[]> => api.get("/projects"),
  get: (id: string): Promise<Project> => api.get(`/projects/${id}`),
  create: (topic: string, title?: string) => api.post("/projects", { topic, title }),
  update: (id: string, data: { title?: string; topic?: string; config?: Partial<ProjectConfig> }) =>
    api.put(`/projects/${id}`, data),
  delete: (id: string) => api.delete(`/projects/${id}`),
};

// ─── Pipeline ───
export interface StepProgress {
  state: string;
  completed_cuts: number;
  total_cuts: number;
  progress_pct: number;
  eta_seconds: number;
}

export interface PipelineStatus {
  status: string;
  current_step: number;
  step_states: Record<string, string>;
  step_progress: Record<string, StepProgress>;
  is_paused: boolean;
  total_cuts: number;
}

export const pipelineApi = {
  runAll: (id: string, startStep?: number, endStep?: number) =>
    api.post(`/pipeline/${id}/run-all`, { start_step: startStep, end_step: endStep }),
  runStep: (id: string, step: number) => api.post(`/pipeline/${id}/step/${step}`),
  pause: (id: string) => api.post(`/pipeline/${id}/pause`),
  pauseStep: (id: string, step: number) => api.post(`/pipeline/${id}/pause-step/${step}`),
  resume: (id: string) => api.post(`/pipeline/${id}/resume`),
  resumeStep: (id: string, step: number) => api.post(`/pipeline/${id}/resume-step/${step}`),
  resumeFrom: (id: string, step: number) => api.post(`/pipeline/${id}/resume-from/${step}`),
  resetStep: (id: string, step: number) => api.post(`/pipeline/${id}/reset-step/${step}`),
  cancel: (id: string) => api.post(`/pipeline/${id}/cancel`),
  status: (id: string): Promise<PipelineStatus> => api.get(`/pipeline/${id}/status`),
};

// ─── Script ───
export const scriptApi = {
  listCuts: (id: string): Promise<{ project_id: string; total: number; cuts: Cut[] }> =>
    api.get(`/script/${id}/cuts`),
  generate: (id: string): Promise<{ cuts: Cut[]; total_duration_estimate: number }> =>
    api.post(`/script/${id}/generate`),
  generateAsync: (id: string) => api.post(`/script/${id}/generate-async`),
  editCut: (id: string, cutNumber: number, data: { narration?: string; image_prompt?: string }) =>
    api.put(`/script/${id}/cuts/${cutNumber}`, data),
  addCut: (id: string, data: { cut_number: number; narration: string; image_prompt: string; scene_type: string }) =>
    api.post(`/script/${id}/cuts/add`, data),
  deleteCut: (id: string, cutNumber: number) => api.delete(`/script/${id}/cuts/${cutNumber}`),
  reorderCuts: (id: string, order: number[]) => api.put(`/script/${id}/cuts/reorder`, { order }),
  clearStep: (id: string, step: string) => api.post(`/script/${id}/clear/${step}`),
};

// ─── Voice ───
export const voiceApi = {
  generateAll: (id: string) => api.post(`/voice/${id}/generate`),
  generateAsync: (id: string) => api.post(`/voice/${id}/generate-async`),
  resumeAsync: (id: string) => api.post(`/voice/${id}/resume-async`),
  regenerate: (id: string, cutNumber: number) => api.post(`/voice/${id}/generate/${cutNumber}`),
  listVoices: (id: string, ttsModel?: string) =>
    api.get(
      `/voice/${id}/voices${ttsModel ? `?tts_model=${encodeURIComponent(ttsModel)}` : ""}`,
    ),
  /** v1.1.47: override 를 넘기면 저장된 프로젝트 config 대신 사용. */
  preview: (
    id: string,
    override?: {
      tts_model?: string;
      tts_voice_id?: string;
      tts_voice_preset?: string;
      tts_voice_lang?: string;
      tts_speed?: number;
    },
  ) => api.post(`/voice/${id}/preview`, override || {}),
};

// ─── Image ───
export interface AssetRef {
  path: string;      // relative-from-project-dir path
  filename: string;  // bare filename
  exists: boolean;   // does the file currently exist on disk
}

export interface ProjectAssets {
  project_id: string;
  reference_images: AssetRef[];
  character_images: AssetRef[];
  logo_images: AssetRef[];
}

export interface CharacterSlot {
  cut_number: number;
  has_character: boolean;
}

export interface CharacterSlotsResponse {
  project_id: string;
  slots: CharacterSlot[];
}

/**
 * 결정론적 규칙: 5컷마다 1장 캐릭터 (20%) — 컷 1, 6, 11, 16… 이 캐릭터 컷.
 * 백엔드 `cut_has_character()` 와 반드시 동일해야 함.
 */
export const cutHasCharacter = (cutNumber: number): boolean => {
  if (cutNumber == null || cutNumber < 1) return false;
  return (cutNumber - 1) % 5 === 0;
};

export const imageApi = {
  generateAll: (id: string) => api.post(`/image/${id}/generate`),
  generateAsync: (id: string) => api.post(`/image/${id}/generate-async`),
  resumeAsync: (id: string) => api.post(`/image/${id}/resume-async`),
  regenerate: (id: string, cutNumber: number) => api.post(`/image/${id}/generate/${cutNumber}`),
  upload: (id: string, cutNumber: number, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return api.upload(`/image/${id}/${cutNumber}/upload`, fd);
  },
  uploadReference: (id: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return api.upload(`/image/${id}/reference/upload`, fd);
  },
  uploadCharacter: (id: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return api.upload(`/image/${id}/character/upload`, fd);
  },
  uploadLogo: (id: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return api.upload(`/image/${id}/logo/upload`, fd);
  },
  deleteReference: (id: string, filename: string) => api.delete(`/image/${id}/reference/${filename}`),
  deleteCharacter: (id: string, filename: string) => api.delete(`/image/${id}/character/${filename}`),
  deleteLogo: (id: string, filename: string) => api.delete(`/image/${id}/logo/${filename}`),
  getAssets: (id: string): Promise<ProjectAssets> => api.get(`/image/${id}/assets`),
  getCharacterSlots: (id: string): Promise<CharacterSlotsResponse> =>
    api.get(`/image/${id}/character-slots`),
};

// ─── Video ───
export const videoApi = {
  generateAll: (id: string) => api.post(`/video/${id}/generate`),
  generateAsync: (id: string) => api.post(`/video/${id}/generate-async`),
  resumeAsync: (id: string) => api.post(`/video/${id}/resume-async`),
};

// ─── Background Tasks ───
export interface TaskItemError {
  cut_number: number;
  error: string;
}

export interface TaskStatus {
  task_id?: string;
  project_id: string;
  step: string;
  status: "idle" | "running" | "completed" | "failed" | "cancelled";
  total: number;
  completed: number;
  progress_pct: number;
  elapsed: number;
  eta_seconds: number;
  error?: string;
  item_errors?: TaskItemError[];
}

export const taskApi = {
  status: (projectId: string, step: string): Promise<TaskStatus> =>
    api.get(`/tasks/${projectId}/${step}`),
  cancel: (projectId: string, step: string) =>
    api.post(`/tasks/${projectId}/${step}/cancel`),
};

// ─── Subtitle ───
export const subtitleApi = {
  generate: (id: string) => api.post(`/subtitle/${id}/generate`),
  render: (id: string) => api.post(`/subtitle/${id}/render`),
  renderAsync: (id: string) => api.post(`/subtitle/${id}/render-async`),
};

// ─── YouTube ───
export type YouTubePrivacy = "private" | "unlisted" | "public";

export interface YouTubeUploadRequest {
  title?: string;
  description?: string;
  tags?: string[];
  privacy: YouTubePrivacy;
  language?: string;
  category_id?: string;
  made_for_kids?: boolean;
  use_generated_thumbnail?: boolean;
}

export interface YouTubeUploadResult {
  status: "uploaded";
  project_id: string;
  video_id: string;
  video_url: string;
  title: string;
  privacy: YouTubePrivacy;
  thumbnail_used: boolean;
  thumbnail_error?: string;
}

export interface YouTubeDeleteRequest {
  /** 삭제할 video id. 생략하면 서버가 project.youtube_url 에서 파싱함. */
  video_id?: string;
  /** 반드시 true 여야 삭제 실행. 프론트는 사용자 확인 후에만 true 로 보냄. */
  confirm: boolean;
  /** 삭제 성공 시 project.youtube_url 을 비울지 여부 (기본 true). */
  clear_project_url?: boolean;
}

export interface YouTubeDeleteResult {
  status: "deleted" | "already_gone";
  project_id: string;
  video_id: string;
  cleared_project_url?: boolean;
  message?: string;
}

export interface YouTubeAuthStatus {
  authenticated: boolean;
  project_id?: string;
  global_authenticated?: boolean;
}

export interface YouTubeChannelInfo {
  channel_id: string;
  title: string;
  custom_url?: string | null;
  thumbnail?: string | null;
  subscriber_count?: number | null;
  video_count?: number | null;
}

export type ThumbnailMode = "ai_overlay" | "ai_only" | "cut_overlay";

export interface ThumbnailGenerateRequest {
  title?: string;
  subtitle?: string;
  episode_label?: string;
  cut_number?: number;
  mode?: ThumbnailMode;
  image_model?: string;
  prompt?: string;
}

export interface ThumbnailGenerateResult {
  status: "generated";
  project_id: string;
  thumbnail_path: string;
  thumbnail_url: string;
  mode: ThumbnailMode;
  title: string;
  subtitle?: string | null;
  episode_label?: string | null;
  // ai 모드일 때만
  image_model?: string;
  prompt_used?: string;
  prompt_source?: "user" | "llm" | "template";
  overlay_applied?: boolean;
  language?: string;
  // cut_overlay 모드일 때만
  base_image_used?: string | null;
  // 레퍼런스 스타일 파이프라인 진단 (v1.1.29)
  reference_images_used?: number;
  reference_fallback?: string | null;
  reference_diagnostics?: {
    registered_reference_images: number;
    registered_character_images: number;
    resolved_reference_images: number;
    resolved_character_images: number;
    missing_reference_images: number;
    missing_character_images: number;
    sent_to_model: number;
  };
}

export interface TagRecommendRequest {
  title?: string;
  topic?: string;
  max_tags?: number;
  language?: string;
}

export interface TagRecommendResult {
  tags: string[];
  source: "llm" | "heuristic";
  language: string;
  error?: string | null;
}

export interface MetadataRecommendRequest {
  title?: string;
  topic?: string;
  max_tags?: number;
  language?: string;
  episode_number?: number | null;
}

export interface MetadataRecommendResult {
  title: string;
  title_hook?: string | null;
  description: string;
  tags: string[];
  language: string;
  episode_number?: number | null;
  source: "llm" | "partial" | "heuristic";
  error?: string | null;
}

export const youtubeApi = {
  // Legacy 전역 토큰
  authStatus: (): Promise<YouTubeAuthStatus> => api.get("/youtube/auth/status"),
  authenticate: (): Promise<{ status: string; message: string }> => api.post("/youtube/auth"),
  authChannel: (): Promise<YouTubeChannelInfo> => api.get("/youtube/auth/channel"),
  authReset: (): Promise<{ status: string; token_removed: boolean }> =>
    api.post("/youtube/auth/reset"),
  // 채널별 토큰 (딸깍 CH1~CH4)
  channelAuthStatus: (ch: number): Promise<{ channel: number; authenticated: boolean }> =>
    api.get(`/youtube/auth/channel/${ch}/status`),
  channelAuthenticate: (ch: number): Promise<{ status: string; channel: number; message: string }> =>
    api.post(`/youtube/auth/channel/${ch}`),
  channelAuthInfo: (ch: number): Promise<YouTubeChannelInfo & { channel: number }> =>
    api.get(`/youtube/auth/channel/${ch}/info`),
  channelAuthReset: (ch: number): Promise<{ status: string; channel: number; token_removed: boolean }> =>
    api.post(`/youtube/auth/channel/${ch}/reset`),
  // 프로젝트별 토큰
  projectAuthStatus: (id: string): Promise<YouTubeAuthStatus> =>
    api.get(`/youtube/${id}/auth/status`),
  projectAuthenticate: (id: string): Promise<{ status: string; project_id: string; message: string }> =>
    api.post(`/youtube/${id}/auth`),
  projectAuthChannel: (id: string): Promise<YouTubeChannelInfo> =>
    api.get(`/youtube/${id}/auth/channel`),
  projectAuthReset: (id: string): Promise<{ status: string; project_id: string; token_removed: boolean }> =>
    api.post(`/youtube/${id}/auth/reset`),
  generateThumbnail: (id: string, body: ThumbnailGenerateRequest = {}): Promise<ThumbnailGenerateResult> =>
    api.post(`/youtube/${id}/thumbnail`, body),
  recommendTags: (id: string, body: TagRecommendRequest = {}): Promise<TagRecommendResult> =>
    api.post(`/youtube/${id}/tags/recommend`, body),
  recommendMetadata: (id: string, body: MetadataRecommendRequest = {}): Promise<MetadataRecommendResult> =>
    api.post(`/youtube/${id}/metadata/recommend`, body),
  upload: (id: string, body: YouTubeUploadRequest): Promise<YouTubeUploadResult> =>
    api.post(`/youtube/${id}/upload`, body),
  // 업로드된 영상을 YouTube 에서 삭제. 복구 불가능이므로 confirm=true 필수.
  deleteUpload: (id: string, body: YouTubeDeleteRequest): Promise<YouTubeDeleteResult> =>
    request("DELETE", `/youtube/${id}/upload`, body, false),
};

// ─── Interlude (오프닝/인터미션/엔딩 영상 업로드) ───
// v1.1.29 이후: 간지영상 생성 스텝 제거. 사용자가 직접 업로드한 영상을
// project.config["interlude"][kind].video_path 에 저장하고, 최종 합성 시
// build_interlude_sequence 가 이 경로를 읽어 final_with_interludes.mp4 생성.
export type InterludeKind = "opening" | "intermission" | "ending";

export interface InterludeEntry {
  video_path?: string | null;
  filename?: string;
  size_bytes?: number;
  duration?: number;
  source?: "upload";
}

export interface InterludeState {
  project_id: string;
  opening: InterludeEntry | null;
  intermission: InterludeEntry | null;
  ending: InterludeEntry | null;
  intermission_every_sec: number;
}

export interface InterludeUploadResult {
  status: "uploaded";
  project_id: string;
  kind: InterludeKind;
  video_path: string;
  filename: string;
  size_bytes: number;
  duration: number;
}

export interface InterludeComposeResult {
  status: "composed";
  project_id: string;
  output_path: string;
  total_clips: number;
  cuts_used: number;
  opening_used: boolean;
  intermission_used: boolean;
  intermission_every_sec: number;
  ending_used: boolean;
}

export const interludeApi = {
  get: (id: string): Promise<InterludeState> =>
    api.get(`/interlude/${id}`),
  updateConfig: (id: string, body: { intermission_every_sec?: number }): Promise<{ status: string; intermission_every_sec: number }> =>
    api.put(`/interlude/${id}/config`, body),
  upload: (
    id: string,
    kind: InterludeKind,
    file: File,
    signal?: AbortSignal,
  ): Promise<InterludeUploadResult> => {
    const fd = new FormData();
    fd.append("file", file);
    return api.upload(`/interlude/${id}/upload/${kind}`, fd, signal);
  },
  remove: (id: string, kind: InterludeKind): Promise<{ status: string; kind: InterludeKind }> =>
    api.delete(`/interlude/${id}/${kind}`),
  compose: (id: string, body: { intermission_every_sec?: number } = {}): Promise<InterludeComposeResult> =>
    api.post(`/interlude/${id}/compose`, body),
};

// ─── Downloads ───
// v2.0.74: BASE_URL 과 같은 규칙으로 유도 — env > window host > localhost.
export const DOWNLOAD_BASE = `${BASE_URL}/downloads`;
export const downloadUrls = {
  all: (id: string) => `${DOWNLOAD_BASE}/${id}/download-all`,
  step: (id: string, step: string) => `${DOWNLOAD_BASE}/${id}/step/${step}`,
};

// ─── API Status ───
export interface ManualBalance {
  amount: number;
  initial_amount?: number;
  remaining?: number;
  spent?: number;
  unit: string;
  display: string;
  display_initial?: string;
  updated_at: string;
  set_at?: string;
  note: string;
  low_threshold?: number | null;
  low?: boolean;
}

// v1.1.64: 어떤 파이프라인 단계에서 사용되는지 표시용 (백엔드 registry 에서 자동 도출)
export interface ApiUsageStep {
  step: number;          // 2=Script, 3=Voice, 4=Image, 5=Video
  label: string;         // "스크립트"/"음성"/"이미지"/"영상"
  models: string[];      // 이 provider 로 묶이는 model_id 목록
}

export interface ApiStatusInfo {
  provider: string;
  status: string;
  balance: string | null;
  detail: string;
  usage_pct?: number;
  balance_url?: string;
  manual?: boolean;
  manual_balance?: ManualBalance;
  used_in_steps?: ApiUsageStep[];
}

export interface FalVideoProbeResult {
  ok: boolean;
  model: string;
  input_model: string;
  http_code: number;
  status: "not_configured" | "auth_failed" | "key_valid" | "unknown_ok" | "timeout" | "error";
  detail: string;
  body: string;
}

export const apiStatusApi = {
  // v1.1.55: 클라이언트 측 18초 abort. 백엔드가 답을 안 주면 UI 가 영원히
  // "확인 중..." 으로 멈추던 문제 방지.
  check: async (): Promise<{ apis: ApiStatusInfo[] }> => {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 18_000);
    try {
      return await api.get("/api-status/status", ctrl.signal);
    } finally {
      clearTimeout(t);
    }
  },
  probeFalVideo: (model: string): Promise<FalVideoProbeResult> =>
    api.get(`/api-status/fal/video-probe?model=${encodeURIComponent(model)}`),
};

// ─── API Keys ───
export interface ProviderInfo {
  provider: string;
  env_var: string;
  has_key: boolean;
  masked_key: string;
  url: string;
}

export const apiKeysApi = {
  listProviders: (): Promise<{ providers: ProviderInfo[] }> => api.get("/api-keys/providers"),
  save: (provider: string, apiKey: string) => api.post("/api-keys/save", { provider, api_key: apiKey }),
  remove: (provider: string) => request("DELETE", "/api-keys/delete", { provider }),
};

// ─── API Balances (수동 입력 잔액, v1.1.55) ───
export interface ApiBalanceRow {
  provider: string;
  has_balance: boolean;
  amount: number | null;           // = remaining (하위호환)
  initial_amount: number | null;
  remaining: number | null;
  spent: number | null;
  unit: string;
  note: string;
  set_at: string | null;
  updated_at: string | null;
  low_threshold: number | null;
  low: boolean;
  display: string | null;           // remaining 표시용
  display_initial: string | null;   // 초기 입력값 표시용
}

export const apiBalancesApi = {
  list: (): Promise<{ balances: ApiBalanceRow[]; default_units: string[] }> =>
    api.get("/api-balances"),
  save: (provider: string, amount: number, unit: string, note?: string, lowThreshold?: number | null) =>
    api.put("/api-balances", {
      provider,
      amount,
      unit,
      note: note || "",
      low_threshold: lowThreshold ?? null,
    }),
  remove: (provider: string) =>
    api.delete(`/api-balances/${encodeURIComponent(provider)}`),
  // v1.1.55: 충전 후 지출 기준점 리셋
  resetSpend: (provider: string) =>
    api.post(`/api-balances/${encodeURIComponent(provider)}/reset-spend`),
};

// v1.1.42: 자동화 스케줄(17행 EP 그리드) 전체 삭제. scheduleApi / ScheduleItem /
// ScheduleItemInput / SchedulePrivacy / ScheduleStatus 전부 제거됨.
// 사용자 요구: "자동화 스케쥴 삭제하고 그자리에 버튼 넣어".

// ─── YouTube Studio (v1.1.31) ───
//
// LongTube 파이프라인과 독립된 전역 Studio. /api/youtube-studio/* 엔드포인트를
// 호출해 채널 단위로 영상/재생목록/댓글을 조작합니다. project_id 파라미터는
// 선택 — 생략하면 전역 토큰을 씁니다.

export interface StudioAuthStatus {
  authenticated: boolean;
  project_id?: string | null;
  channel_id?: string | null;
  channel_title?: string | null;
}

export interface StudioVideoListItem {
  video_id: string;
  title: string;
  description?: string;
  published_at?: string;
  thumbnail?: string | null;
  channel_title?: string;
  privacy_status?: "private" | "unlisted" | "public" | null;
  publish_at?: string | null;
  made_for_kids?: boolean | null;
  view_count?: number | null;
  like_count?: number | null;
  comment_count?: number | null;
  duration?: string | null; // ISO 8601 (PT#M#S)
  longtube?: {
    project_id: string;
    project_title: string;
    uploaded_at: string | null;
    source: "oneclick" | "preset";
  } | null;
}

export interface StudioVideoListResponse {
  items: StudioVideoListItem[];
  next_page_token?: string | null;
  prev_page_token?: string | null;
  total_results?: number | null;
}

export interface StudioVideoDetail {
  video_id: string;
  title: string;
  description: string;
  tags: string[];
  category_id?: string | null;
  default_language?: string | null;
  default_audio_language?: string | null;
  channel_id?: string | null;
  channel_title?: string | null;
  published_at?: string | null;
  thumbnail?: string | null;
  privacy_status?: "private" | "unlisted" | "public" | null;
  publish_at?: string | null;
  made_for_kids?: boolean | null;
  self_declared_made_for_kids?: boolean | null;
  embeddable?: boolean | null;
  license?: string | null;
  public_stats_viewable?: boolean | null;
  view_count?: number | null;
  like_count?: number | null;
  comment_count?: number | null;
  duration?: string | null;
  definition?: string | null;
}

export interface StudioVideoUpdateBody {
  title?: string;
  description?: string;
  tags?: string[];
  category_id?: string;
  default_language?: string;
  privacy_status?: "private" | "unlisted" | "public";
  /** RFC3339. 빈 문자열을 보내면 예약 해제. */
  publish_at?: string;
  made_for_kids?: boolean;
  embeddable?: boolean;
  public_stats_viewable?: boolean;
}

export interface StudioPlaylist {
  playlist_id: string;
  title: string;
  description?: string;
  thumbnail?: string | null;
  item_count?: number | null;
  privacy_status?: "private" | "unlisted" | "public" | null;
  published_at?: string | null;
}

export interface StudioPlaylistItem {
  item_id: string;
  video_id: string;
  position?: number | null;
  title: string;
  thumbnail?: string | null;
  published_at?: string | null;
}

export interface StudioCommentReply {
  comment_id: string;
  author: string;
  author_channel_id?: string | null;
  text: string;
  like_count?: number | null;
  published_at?: string | null;
  updated_at?: string | null;
}

export interface StudioCommentThread {
  thread_id: string;
  top_comment_id: string;
  author: string;
  author_channel_id?: string | null;
  text: string;
  like_count?: number | null;
  published_at?: string | null;
  updated_at?: string | null;
  total_reply_count: number;
  can_reply?: boolean | null;
  replies: StudioCommentReply[];
}

export interface StudioCategory {
  category_id: string;
  title: string;
}

function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const parts: string[] = [];
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  }
  return parts.length ? `?${parts.join("&")}` : "";
}

export const youtubeStudioApi = {
  authStatus: (projectId?: string): Promise<StudioAuthStatus> =>
    api.get(`/youtube-studio/auth/status${qs({ project_id: projectId })}`),

  // Videos
  listVideos: (opts: {
    query?: string;
    pageToken?: string;
    maxResults?: number;
    projectId?: string;
  } = {}): Promise<StudioVideoListResponse> =>
    api.get(
      `/youtube-studio/videos${qs({
        query: opts.query,
        page_token: opts.pageToken,
        max_results: opts.maxResults ?? 25,
        project_id: opts.projectId,
      })}`,
    ),
  getVideo: (videoId: string, projectId?: string): Promise<StudioVideoDetail> =>
    api.get(`/youtube-studio/videos/${encodeURIComponent(videoId)}${qs({ project_id: projectId })}`),
  updateVideo: (
    videoId: string,
    body: StudioVideoUpdateBody,
    projectId?: string,
  ): Promise<{ video_id: string; snippet: any; status: any }> =>
    request(
      "PATCH",
      `/youtube-studio/videos/${encodeURIComponent(videoId)}${qs({ project_id: projectId })}`,
      body,
      false,
    ),
  setThumbnail: (
    videoId: string,
    file: File,
    projectId?: string,
  ): Promise<{ video_id: string; thumbnail_path: string }> => {
    const fd = new FormData();
    fd.append("file", file);
    return api.upload(
      `/youtube-studio/videos/${encodeURIComponent(videoId)}/thumbnail${qs({ project_id: projectId })}`,
      fd,
    );
  },
  deleteVideo: (videoId: string, projectId?: string): Promise<{ status: string; video_id: string }> =>
    api.delete(
      `/youtube-studio/videos/${encodeURIComponent(videoId)}${qs({ confirm: true, project_id: projectId })}`,
    ),

  // Direct upload
  directUpload: (
    params: {
      file: File;
      title: string;
      description?: string;
      tags?: string[];
      privacyStatus?: "private" | "unlisted" | "public";
      categoryId?: string;
      defaultLanguage?: string;
      madeForKids?: boolean;
      publishAt?: string;
      thumbnail?: File | null;
      projectId?: string;
    },
    signal?: AbortSignal,
  ): Promise<{ video_id: string; url: string; publish_at?: string; publish_at_error?: string; thumbnail_error?: string }> => {
    const fd = new FormData();
    fd.append("file", params.file);
    fd.append("title", params.title);
    fd.append("description", params.description ?? "");
    fd.append("tags", (params.tags ?? []).join(","));
    fd.append("privacy_status", params.privacyStatus ?? "private");
    if (params.categoryId) fd.append("category_id", params.categoryId);
    if (params.defaultLanguage) fd.append("default_language", params.defaultLanguage);
    fd.append("made_for_kids", String(Boolean(params.madeForKids)));
    if (params.publishAt) fd.append("publish_at", params.publishAt);
    if (params.thumbnail) fd.append("thumbnail", params.thumbnail);
    return api.upload(
      `/youtube-studio/upload${qs({ project_id: params.projectId })}`,
      fd,
      signal,
    );
  },

  // Playlists
  listPlaylists: (projectId?: string): Promise<{ items: StudioPlaylist[] }> =>
    api.get(`/youtube-studio/playlists${qs({ project_id: projectId })}`),
  createPlaylist: (
    body: { title: string; description?: string; privacy_status?: "private" | "unlisted" | "public" },
    projectId?: string,
  ): Promise<{ playlist_id: string; title: string }> =>
    api.post(`/youtube-studio/playlists${qs({ project_id: projectId })}`, body),
  updatePlaylist: (
    playlistId: string,
    body: { title?: string; description?: string; privacy_status?: "private" | "unlisted" | "public" },
    projectId?: string,
  ): Promise<{ playlist_id: string; snippet: any }> =>
    request(
      "PATCH",
      `/youtube-studio/playlists/${encodeURIComponent(playlistId)}${qs({ project_id: projectId })}`,
      body,
      false,
    ),
  deletePlaylist: (playlistId: string, projectId?: string): Promise<{ status: string; playlist_id: string }> =>
    api.delete(
      `/youtube-studio/playlists/${encodeURIComponent(playlistId)}${qs({ confirm: true, project_id: projectId })}`,
    ),
  listPlaylistItems: (
    playlistId: string,
    opts: { pageToken?: string; maxResults?: number; projectId?: string } = {},
  ): Promise<{ items: StudioPlaylistItem[]; next_page_token?: string | null; total_results?: number | null }> =>
    api.get(
      `/youtube-studio/playlists/${encodeURIComponent(playlistId)}/items${qs({
        page_token: opts.pageToken,
        max_results: opts.maxResults ?? 50,
        project_id: opts.projectId,
      })}`,
    ),
  addPlaylistItem: (
    playlistId: string,
    videoId: string,
    projectId?: string,
  ): Promise<{ item_id: string; playlist_id: string; video_id: string }> =>
    api.post(
      `/youtube-studio/playlists/${encodeURIComponent(playlistId)}/items${qs({ project_id: projectId })}`,
      { video_id: videoId },
    ),
  removePlaylistItem: (
    playlistId: string,
    itemId: string,
    projectId?: string,
  ): Promise<{ status: string; item_id: string }> =>
    api.delete(
      `/youtube-studio/playlists/${encodeURIComponent(playlistId)}/items/${encodeURIComponent(itemId)}${qs({
        project_id: projectId,
      })}`,
    ),

  // Comments
  listComments: (
    videoId: string,
    opts: { order?: "time" | "relevance"; pageToken?: string; maxResults?: number; projectId?: string } = {},
  ): Promise<{ items: StudioCommentThread[]; next_page_token?: string | null; total_results?: number | null }> =>
    api.get(
      `/youtube-studio/videos/${encodeURIComponent(videoId)}/comments${qs({
        order: opts.order ?? "time",
        page_token: opts.pageToken,
        max_results: opts.maxResults ?? 50,
        project_id: opts.projectId,
      })}`,
    ),
  replyComment: (parentId: string, text: string, projectId?: string): Promise<StudioCommentReply> =>
    api.post(`/youtube-studio/comments/${encodeURIComponent(parentId)}/reply${qs({ project_id: projectId })}`, {
      text,
    }),
  moderateComment: (
    commentId: string,
    status: "heldForReview" | "published" | "rejected",
    banAuthor: boolean,
    projectId?: string,
  ): Promise<{ status: string; comment_id: string; moderation: string }> =>
    api.post(
      `/youtube-studio/comments/${encodeURIComponent(commentId)}/moderation${qs({ project_id: projectId })}`,
      { status, ban_author: banAuthor },
    ),
  markCommentSpam: (commentId: string, projectId?: string): Promise<{ status: string; comment_id: string }> =>
    api.post(`/youtube-studio/comments/${encodeURIComponent(commentId)}/spam${qs({ project_id: projectId })}`),
  deleteComment: (commentId: string, projectId?: string): Promise<{ status: string; comment_id: string }> =>
    api.delete(`/youtube-studio/comments/${encodeURIComponent(commentId)}${qs({ project_id: projectId })}`),

  // Categories
  listCategories: (regionCode = "KR", projectId?: string): Promise<{ items: StudioCategory[]; region_code: string }> =>
    api.get(`/youtube-studio/categories${qs({ region_code: regionCode, project_id: projectId })}`),
};

// ─── OneClick (v1.1.34 딸깍 제작) ───
export interface OneClickTask {
  task_id: string;
  template_project_id: string | null;
  project_id: string;
  topic: string;
  title: string;
  status: "prepared" | "queued" | "running" | "completed" | "failed" | "cancelled";
  current_step: number | null;
  current_step_name: string | null;
  step_states: Record<string, string>;
  progress_pct: number;
  total_cuts: number;
  completed_cuts_by_step: Record<string, number>;
  // v1.1.38: 현재 실행 중 단계의 세부 컷 카운터 (UI 의 "N/M 컷" 용)
  current_step_completed?: number;
  current_step_total?: number;
  current_step_label?: string | null;
  triggered_by?: "manual" | "schedule";
  channel?: number;  // v1.1.58: 채널 1~4 (없으면 수동 실행)
  // v1.1.52: 각 스텝에서 사용하는 AI 모델명
  models?: {
    script?: string;
    tts?: string;
    tts_voice?: string;
    image?: string;
    video?: string;
    thumbnail?: string;
  };
  // v1.1.53: 썸네일 생성 상태
  thumbnail_status?: "waiting" | "generating" | "done" | "failed";
  // v1.1.55: 썸네일 실패 사유
  thumbnail_error?: string | null;
  estimate: ProjectEstimate;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  // v2.1.2: 제작 로그
  logs?: { ts: string; level: "info" | "warn" | "error"; msg: string }[];
}

// v1.1.54: 완성작 상세 + 라이브러리 통계 타입
export interface TaskDetail {
  task_id: string;
  project_id: string;
  topic: string;
  title: string;
  status: string;
  total_cuts: number;
  disk_bytes: number;
  disk_mb: number;
  has_final_video: boolean;
  final_video_path: string;
  has_thumbnail: boolean;
  thumbnail_path: string;
  cut_images: string[];
  cut_image_count: number;
  models?: Record<string, string>;
  estimate?: ProjectEstimate;
  elapsed_sec: number | null;
  youtube_url: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  error: string | null;
}

export interface LibraryStats {
  total_completed: number;
  total_failed: number;
  uploaded: number;
  not_uploaded: number;
  total_disk_bytes: number;
  total_disk_mb: number;
}

// v1.1.42: OneClickSchedule / OneClickScheduleUpdate 타입 및
// getSchedule / updateSchedule 엔드포인트 전체 삭제. 매일 HH:MM 자동 실행
// 기능이 제거되었다.

// v1.1.43: 주제 큐 + 매일 HH:MM 스케줄 재도입 (새 모델).
// 각 큐 항목은 주제/프리셋/길이를 개별 지정.
export interface OneClickQueueItem {
  id?: string;
  topic: string;
  template_project_id: string | null;
  target_duration: number | null;  // 초 단위. null 이면 템플릿 기본값
  channel: number;                 // v1.1.57: 채널 1~4 (기본 1)
}

export interface OneClickQueueState {
  // v1.1.57: 채널별 스케줄 시간
  channel_times: Record<string, string | null>;  // {"1": "07:00", "2": "12:00", ...}
  last_run_dates: Record<string, string | null>;  // 백엔드가 관리하는 읽기 전용 필드
  items: OneClickQueueItem[];
}

export const oneclickApi = {
  // v1.1.42: `target_duration` (초) 추가 — 모달의 "시간" 입력을 백엔드로 전달.
  prepare: (body: {
    template_project_id?: string | null;
    topic: string;
    title?: string;
    target_duration?: number;
  }): Promise<OneClickTask> => api.post(`/oneclick/prepare`, body),
  start: (taskId: string): Promise<OneClickTask> => api.post(`/oneclick/${taskId}/start`),
  resume: (taskId: string): Promise<OneClickTask> => api.post(`/oneclick/${taskId}/resume`),
  cancel: (taskId: string): Promise<OneClickTask> => api.post(`/oneclick/${taskId}/cancel`),
  // v1.1.70: 비상 정지 — 서버 + ComfyUI 의 모든 작업 강제 중단
  emergencyStop: (): Promise<{
    ok: boolean;
    stopped_count: number;
    stopped_task_ids: string[];
    comfyui_interrupt: boolean;
    comfyui_queue_cleared: boolean;
    errors: string[];
  }> => api.post(`/oneclick/emergency-stop`),
  get: (taskId: string): Promise<OneClickTask> => api.get(`/oneclick/tasks/${taskId}`),
  list: (): Promise<{ tasks: OneClickTask[] }> => api.get(`/oneclick/tasks`),
  deleteTask: (taskId: string): Promise<{ ok: boolean }> => api.delete(`/oneclick/tasks/${taskId}`),
  // v1.1.52: 특정 단계 생성물 삭제 (이미지/음성/영상 초기화)
  clearStep: (taskId: string, step: number): Promise<{ ok: boolean; deleted_files: number }> =>
    api.post(`/oneclick/${taskId}/clear-step/${step}`),
  // v1.1.52: 썸네일 재생성
  regenerateThumbnail: (taskId: string, imageModel?: string): Promise<{ ok: boolean; path: string; model: string }> =>
    api.post(`/oneclick/${taskId}/regenerate-thumbnail`, { image_model: imageModel || null }),
  // v1.1.53: 프로젝트 초기화 (from_step 부터 전부 리셋)
  resetTask: (taskId: string, fromStep: number = 2): Promise<{ ok: boolean; from_step: number; deleted_files: number }> =>
    api.post(`/oneclick/${taskId}/reset`, { from_step: fromStep }),
  // v1.1.56: 프로젝트 ID 로 태스크 복구
  recoverProject: (projectId: string): Promise<OneClickTask> =>
    api.post(`/oneclick/recover`, { project_id: projectId }),
  prune: (keep = 20) => api.post(`/oneclick/prune?keep=${keep}`),
  // v1.1.54: 완성작 관리
  getTaskDetail: (taskId: string): Promise<TaskDetail> =>
    api.get(`/oneclick/tasks/${taskId}/detail`),
  manualUpload: (taskId: string): Promise<{ ok: boolean; youtube_url: string | null }> =>
    api.post(`/oneclick/tasks/${taskId}/upload`),
  bulkDelete: (taskIds: string[]): Promise<{ ok: boolean; deleted: number; freed_mb: number; skipped: string[] }> =>
    api.post(`/oneclick/tasks/bulk-delete`, { task_ids: taskIds }),
  libraryStats: (): Promise<LibraryStats> =>
    api.get(`/oneclick/library/stats`),

  // v1.1.58: 실행 중 태스크 조회
  getRunning: (): Promise<{ running: {
    task_id: string; topic: string; status: string;
    progress_pct: number; started_at: string | null;
    estimated_remaining_seconds: number | null;
  } | null }> => api.get(`/oneclick/running`),

  // v1.1.43: 주제 큐
  getQueue: (): Promise<OneClickQueueState> => api.get(`/oneclick/queue`),
  setQueue: (body: {
    channel_times: Record<string, string | null>;
    items: OneClickQueueItem[];
  }): Promise<OneClickQueueState> => api.put(`/oneclick/queue`, body),
  runQueueNext: (): Promise<OneClickTask> =>
    api.post(`/oneclick/queue/run-next`),
};

// ─── Asset URL helper ───
// v2.0.74: 정적 에셋(/assets/<id>/...) 도 env > window host > localhost 규칙.
export const ASSET_BASE = _deriveAssetBase();
export const assetUrl = (projectId: string, relativePath: string) =>
  `${ASSET_BASE}/assets/${projectId}/${relativePath}`;

/**
 * Resolve a path returned by the backend (e.g. "/assets/<id>/output/final.mp4")
 * into an absolute URL the browser can open. Pass-through for already-absolute URLs.
 */
export const resolveAssetUrl = (pathOrUrl: string): string => {
  if (!pathOrUrl) return pathOrUrl;
  if (/^https?:\/\//i.test(pathOrUrl)) return pathOrUrl;
  if (pathOrUrl.startsWith("/")) return `${ASSET_BASE}${pathOrUrl}`;
  return `${ASSET_BASE}/${pathOrUrl}`;
};
