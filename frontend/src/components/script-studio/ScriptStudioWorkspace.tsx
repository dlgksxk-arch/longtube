"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  CheckSquare,
  ClipboardList,
  FileJson,
  FilePenLine,
  ListChecks,
  Loader2,
  Play,
  RefreshCw,
  Save,
  Send,
  Square,
  StopCircle,
  Trash2,
} from "lucide-react";
import {
  modelsApi,
  scriptStudioApi,
  type Cut,
  type ModelInfo,
  type ScriptStudioDraft,
  type ScriptStudioQueueChannel,
  type ScriptStudioQueueTopic,
  type ScriptStudioSource,
} from "@/lib/api";

const statusLabel: Record<string, string> = {
  draft: "초안",
  story_ready: "스토리 완료",
  script_ready: "대본 완료",
  needs_review: "검사 필요",
  failed: "실패",
  cancelled: "중지",
};

const busyLabel: Record<string, string> = {
  load: "초안 불러오는 중",
  create: "초안 생성 중",
  "queue-draft": "선택 주제 초안 생성 중",
  save: "초안 저장 중",
  delete: "초안 삭제 중",
  story: "스토리 생성 중",
  script: "대본 생성 중",
  validate: "검사 중",
  export: "JSON 내보내는 중",
  apply: "롱폼공장 적용 중",
  batch: "선택 주제 연속 초안 생성 중",
};

const DEFAULT_QWEN_MODEL = "qwen3:32b";
const ACTIVE_CALLS_STORAGE_KEY = "longtube.scriptStudio.activeCalls";
const ACTIVE_CALLS_EVENT = "longtube-script-studio-active-calls";
const ACTIVE_DRAFT_STORAGE_KEY = "longtube.scriptStudio.activeDraftId";
const LAST_STORY_MODEL_STORAGE_KEY = "longtube.scriptStudio.lastStoryModel";
const LAST_SCRIPT_MODEL_STORAGE_KEY = "longtube.scriptStudio.lastScriptModel";
const SCRIPT_STUDIO_BLOCK_CUTS = 10;
const SCRIPT_STUDIO_BLOCK_TOTAL = 15;

export type ScriptStudioStage = "story" | "script" | "validate" | "apply";

const stageMeta: Record<ScriptStudioStage, { label: string; description: string }> = {
  story: {
    label: "스토리 생성",
    description: "초안의 이야기 구조, 인물 설계, 사건 인과를 먼저 확정합니다.",
  },
  script: {
    label: "대본 생성",
    description: "확정된 스토리 설계를 기준으로 컷별 대본을 생성하고 확인합니다.",
  },
  validate: {
    label: "검사",
    description: "컷 수, 구조, 대본 품질 검사 결과를 확인합니다.",
  },
  apply: {
    label: "공장 적용",
    description: "완성된 대본 JSON을 내보내거나 연결된 롱폼공장 프로젝트에 적용합니다.",
  },
};

const stageOrder: ScriptStudioStage[] = ["story", "script", "validate", "apply"];
const backgroundStages = new Set(["story", "script", "validate", "apply"]);

function compactDate(value?: string) {
  if (!value) return "";
  return value.replace("T", " ").replace("Z", "").slice(0, 16);
}

function modelName(models: ModelInfo[], id?: string | null) {
  if (!id) return "";
  const cleanId = stripOllamaPrefix(id);
  return cleanModelLabel(models.find((m) => m.id === cleanId)?.name || cleanId);
}

function stripOllamaPrefix(value?: string | null) {
  return String(value || "").replace(/^ollama:/, "");
}

function cleanModelLabel(value?: string | null) {
  return stripOllamaPrefix(value).replace(/^Ollama\s+/i, "");
}

function readStoredModel(key: string) {
  if (typeof window === "undefined") return "";
  return stripOllamaPrefix(window.localStorage.getItem(key) || "");
}

function writeStoredModel(key: string, value?: string | null) {
  if (typeof window === "undefined") return;
  const clean = stripOllamaPrefix(value);
  if (clean) window.localStorage.setItem(key, clean);
}

function storyLines(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => String(item || "").trim()).filter(Boolean);
  }
  const text = String(value || "").trim();
  return text ? [text] : [];
}

function storyCharacterFirstBlock(item: { first_appearance_block?: string | number; first_appearance_cut?: string } = {}) {
  const explicit = Number(item.first_appearance_block || 0);
  if (Number.isFinite(explicit) && explicit > 0) return `Block ${explicit}`;
  const match = String(item.first_appearance_cut || "").match(/\d+/);
  if (!match) return "-";
  const cut = Number(match[0]);
  return Number.isFinite(cut) && cut > 0 ? `Block ${Math.ceil(cut / SCRIPT_STUDIO_BLOCK_CUTS)}` : "-";
}

function defaultQwenModel(models: ModelInfo[]) {
  return (
    models.find((model) => model.id === DEFAULT_QWEN_MODEL)?.id ||
    models.find((model) => model.id.startsWith("qwen3"))?.id ||
    models.find((model) => model.provider === "ollama")?.id ||
    ""
  );
}

function normalizeTopicKey(value?: string | null) {
  return String(value || "").trim().replace(/\s+/g, " ").toLowerCase();
}

function episodeLabel(value?: number | null) {
  return typeof value === "number" && value > 0 ? `EP.${String(value).padStart(2, "0")}` : "";
}

function draftEpisodeLabel(draft?: ScriptStudioDraft | null) {
  const config = (draft?.config || {}) as Record<string, unknown>;
  const value = Number(config.episode_number || 0);
  return Number.isFinite(value) && value > 0 ? episodeLabel(value) : "초안";
}

function validationStageLabel(stage?: string, attempt?: number) {
  const round = attempt ? ` ${attempt}회` : "";
  switch (stage) {
    case "local":
      return "로컬 구조";
    case "shorts_selection":
      return "쇼츠 선정";
    case "gemma":
      return `Gemma 판정${round}`;
    case "gemma_revision":
      return `Gemma 수정${round}`;
    case "python_json_assembly":
      return "Python JSON 조립";
    case "script_revision_saved":
      return "수정본 저장";
    default:
      return stage || "-";
  }
}

function compactModelLabel(value?: string | null) {
  const text = stripOllamaPrefix(value);
  if (!text) return "-";
  if (text.includes("gpt-5.5")) return "GPT-5.5";
  if (text.includes("gemma")) return "Gemma";
  if (text.includes("qwen")) return "Qwen";
  if (text === "python") return "Python";
  return text;
}

function blockStatusLabel(status?: string) {
  switch (status) {
    case "completed":
      return "완료";
    case "running":
      return "진행";
    case "failed":
      return "실패";
    case "fallback":
      return "진행";
    case "pending":
    default:
      return "";
  }
}

function blockCellClass(status?: string, active = false) {
  const base = "h-11 min-w-12 border-r border-border/70 px-1 text-center text-xs font-black transition-colors";
  if (active || status === "running" || status === "fallback") {
    return `${base} animate-pulse border-accent-primary bg-accent-primary/25 text-white shadow-[0_0_14px_rgba(139,92,246,0.65)]`;
  }
  if (status === "completed") {
    return `${base} bg-emerald-500/10 text-emerald-200`;
  }
  if (status === "failed") return `${base} bg-red-500/15 text-red-200`;
  return `${base} bg-bg-secondary text-gray-500`;
}

function formatElapsed(seconds: number) {
  const safeSeconds = Math.max(0, Math.floor(Number(seconds) || 0));
  const min = Math.floor(safeSeconds / 60);
  const sec = safeSeconds % 60;
  return `${String(min).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

function generationStageLabel(stage?: string) {
  if (stage === "story") return "스토리";
  if (stage === "script") return "대본";
  return stage || "-";
}

function generationStatusLabel(status?: string) {
  if (status === "running") return "진행";
  if (status === "completed") return "완료";
  if (status === "failed") return "실패";
  if (status === "cancelled") return "중지";
  return status || "-";
}

function writeActiveCall(call: {
  id: string;
  label: string;
  model: string;
  title: string;
  detail: string;
}) {
  if (typeof window === "undefined") return;
  const now = Date.now();
  let calls: any[] = [];
  try {
    const parsed = JSON.parse(window.localStorage.getItem(ACTIVE_CALLS_STORAGE_KEY) || "[]");
    calls = Array.isArray(parsed) ? parsed : [];
  } catch {
    calls = [];
  }
  calls = calls.filter((item) => item?.id !== call.id && Number(item?.expires_at || 0) > now);
  calls.push({ ...call, expires_at: now + 2 * 60 * 60 * 1000 });
  window.localStorage.setItem(ACTIVE_CALLS_STORAGE_KEY, JSON.stringify(calls));
  window.dispatchEvent(new Event(ACTIVE_CALLS_EVENT));
}

function clearActiveCall(id: string) {
  if (typeof window === "undefined") return;
  let calls: any[] = [];
  try {
    const parsed = JSON.parse(window.localStorage.getItem(ACTIVE_CALLS_STORAGE_KEY) || "[]");
    calls = Array.isArray(parsed) ? parsed : [];
  } catch {
    calls = [];
  }
  calls = calls.filter((item) => item?.id !== id);
  window.localStorage.setItem(ACTIVE_CALLS_STORAGE_KEY, JSON.stringify(calls));
  window.dispatchEvent(new Event(ACTIVE_CALLS_EVENT));
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return <label className="mb-1 block text-xs font-bold uppercase tracking-wide text-gray-500">{children}</label>;
}

function ModelSelect({
  value,
  models,
  onChange,
}: {
  value?: string;
  models: ModelInfo[];
  onChange: (value: string) => void;
}) {
  return (
    <select
      value={value || ""}
      onChange={(e) => onChange(e.target.value)}
      className="h-10 w-full rounded-md border border-border bg-bg-primary px-3 text-sm font-semibold text-white outline-none focus:border-accent-primary"
    >
      {models.map((model) => (
        <option key={model.id} value={model.id}>
          {cleanModelLabel(model.name || model.id)}
        </option>
      ))}
    </select>
  );
}

function ActionButton({
  children,
  onClick,
  disabled,
  tone = "default",
  icon,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  tone?: "default" | "primary" | "danger";
  icon?: React.ReactNode;
}) {
  const cls =
    tone === "primary"
      ? "border-accent-primary/70 bg-accent-primary text-white hover:bg-accent-primary/90"
      : tone === "danger"
        ? "border-red-500/50 bg-red-500/10 text-red-200 hover:bg-red-500/20"
        : "border-border bg-bg-secondary text-gray-100 hover:bg-bg-tertiary";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex h-10 items-center justify-center gap-2 rounded-md border px-4 text-sm font-bold transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${cls}`}
    >
      {icon}
      {children}
    </button>
  );
}

export default function ScriptStudioWorkspace({
  stage = "story",
  basePath = "/script-studio",
}: {
  stage?: ScriptStudioStage;
  basePath?: string;
}) {
  const activeStage = stageMeta[stage] ? stage : "story";
  const [sources, setSources] = useState<ScriptStudioSource[]>([]);
  const [drafts, setDrafts] = useState<ScriptStudioDraft[]>([]);
  const [queueChannels, setQueueChannels] = useState<ScriptStudioQueueChannel[]>([]);
  const [selectedChannel, setSelectedChannel] = useState(1);
  const [selectedQueueItemId, setSelectedQueueItemId] = useState("");
  const [checkedQueueItemIds, setCheckedQueueItemIds] = useState<string[]>([]);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [selectedSourceId, setSelectedSourceId] = useState("");
  const [draft, setDraft] = useState<ScriptStudioDraft | null>(null);
  const [topic, setTopic] = useState("");
  const [title, setTitle] = useState("");
  const [storyModel, setStoryModel] = useState("");
  const [scriptModel, setScriptModel] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [busyElapsedSec, setBusyElapsedSec] = useState(0);
  const [message, setMessage] = useState("");
  const [restoredDraftId, setRestoredDraftId] = useState("");
  const activeRequestRef = useRef<AbortController | null>(null);

  const selectedSource = useMemo(
    () => sources.find((source) => source.id === selectedSourceId) || null,
    [sources, selectedSourceId],
  );
  const activeQueueChannel = useMemo(
    () => queueChannels.find((channel) => channel.channel === selectedChannel) || queueChannels[0] || null,
    [queueChannels, selectedChannel],
  );
  const selectedQueueItem = useMemo(() => {
    if (!selectedQueueItemId) return null;
    for (const channel of queueChannels) {
      const item = channel.items.find((row) => row.id === selectedQueueItemId);
      if (item) return item;
    }
    return null;
  }, [queueChannels, selectedQueueItemId]);
  const qwenDefaultModel = useMemo(() => defaultQwenModel(models), [models]);
  const lastStoryModel = useCallback(
    () => readStoredModel(LAST_STORY_MODEL_STORAGE_KEY) || storyModel || qwenDefaultModel,
    [qwenDefaultModel, storyModel],
  );
  const lastScriptModel = useCallback(
    () => readStoredModel(LAST_SCRIPT_MODEL_STORAGE_KEY) || scriptModel || qwenDefaultModel,
    [qwenDefaultModel, scriptModel],
  );
  const checkedQueueItems = useMemo(() => {
    const ids = new Set(checkedQueueItemIds);
    return queueChannels.flatMap((channel) => channel.items).filter((item) => ids.has(item.id));
  }, [checkedQueueItemIds, queueChannels]);
  const findExistingDraftForQueueItem = useCallback(
    (item: ScriptStudioQueueTopic) => {
      const topicKey = normalizeTopicKey(item.topic || item.title || "");
      return drafts.find((row) => {
        if (row.source_queue_item_id && row.source_queue_item_id === item.id) return true;
        if (!topicKey) return false;
        return normalizeTopicKey(row.topic || row.title || "") === topicKey;
      }) || null;
    },
    [drafts],
  );
  const findExistingDraftForTopic = useCallback(
    (value: string) => {
      const topicKey = normalizeTopicKey(value);
      if (!topicKey) return null;
      return drafts.find((row) => normalizeTopicKey(row.topic || row.title || "") === topicKey) || null;
    },
    [drafts],
  );

  const load = useCallback(async () => {
    const [sourceResult, draftResult, modelResult, queueResult] = await Promise.all([
      scriptStudioApi.sources(),
      scriptStudioApi.listDrafts(),
      scriptStudioApi.models().catch(async () => modelsApi.listLLM()),
      scriptStudioApi.queueTopics().catch(async () => ({
        channel_times: {},
        channel_presets: {},
        channels: [],
        total: 0,
      })),
    ]);
    setSources(sourceResult.projects || []);
    setDrafts(draftResult.drafts || []);
    setModels(modelResult.models || []);
    const channels = queueResult.channels || [];
    setQueueChannels(channels);
    if (!channels.some((channel) => channel.channel === selectedChannel) && channels[0]) {
      setSelectedChannel(channels[0].channel);
    }
    if (!selectedSourceId && sourceResult.projects?.[0]) {
      setSelectedSourceId(sourceResult.projects[0].id);
    }
  }, [selectedChannel, selectedSourceId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!busy) {
      setBusyElapsedSec(0);
      return;
    }
    const started = Date.now();
    setBusyElapsedSec(0);
    const timer = window.setInterval(() => {
      setBusyElapsedSec(Math.floor((Date.now() - started) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [busy]);

  useEffect(() => {
    if (!draft?.id || !busy || !backgroundStages.has(busy)) return;
    let stopped = false;
    const refreshDraft = async () => {
      try {
        const next = await scriptStudioApi.getDraft(draft.id);
        if (stopped) return;
        setDraft(next);
        setDrafts((prev) => prev.map((item) => (item.id === next.id ? next : item)));
      } catch {
        // 긴 생성 요청 중 일시적인 폴링 실패는 화면 진행률만 건너뜁니다.
      }
    };
    const timer = window.setInterval(refreshDraft, 2000);
    void refreshDraft();
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [busy, draft?.id]);

  useEffect(() => {
    const progress = draft?.generation_progress;
    const stage = String(progress?.stage || "");
    const status = String(progress?.status || "");
    if (status === "running" && backgroundStages.has(stage) && busy !== stage) {
      setBusy(stage);
      return;
    }
    if (busy && backgroundStages.has(busy) && progress?.stage === busy && status && status !== "running") {
      setBusy(null);
      if (status === "completed") {
        setMessage(progress?.message || "작업 완료");
      } else if (status === "cancelled") {
        setMessage(progress?.message || "작업 중지됨");
      } else if (status === "failed") {
        setMessage(draft?.last_error || progress?.message || "작업 실패");
      }
    }
  }, [busy, draft?.generation_progress, draft?.last_error]);

  useEffect(() => {
    if (busy !== "story" && busy !== "script") {
      clearActiveCall("script-studio-story");
      clearActiveCall("script-studio-script");
      return;
    }
    const activeDraft = draft;
    const id = busy === "story" ? "script-studio-story" : "script-studio-script";
    const modelId = busy === "story" ? (storyModel || qwenDefaultModel) : (scriptModel || qwenDefaultModel);
    const progress = activeDraft?.generation_progress;
    const progressText =
      progress?.stage === busy && typeof progress.progress_pct === "number"
        ? `${Math.round(progress.progress_pct)}%`
        : draftEpisodeLabel(activeDraft);
    writeActiveCall({
      id,
      label: busy === "story" ? "스토리" : "대본",
      model: modelName(models, modelId),
      title: activeDraft?.title || title || topic || "대본실 초안",
      detail: `${activeDraft?.source_project_title || selectedSource?.title || "대본실"} · ${progressText}`,
    });
    return () => clearActiveCall(id);
  }, [busy, draft, models, qwenDefaultModel, scriptModel, selectedSource, storyModel, title, topic]);

  useEffect(() => {
    if (!selectedSource || draft || selectedQueueItemId) return;
    setTopic(selectedSource.topic || "");
    setTitle(selectedSource.title || selectedSource.topic || "");
    setStoryModel(lastStoryModel() || stripOllamaPrefix(selectedSource.story_model) || stripOllamaPrefix(selectedSource.script_model) || "");
    setScriptModel(lastScriptModel() || stripOllamaPrefix(selectedSource.script_model) || stripOllamaPrefix(selectedSource.story_model) || "");
  }, [selectedSource, draft, selectedQueueItemId, lastScriptModel, lastStoryModel]);

  useEffect(() => {
    if (draft) return;
    const storedStory = readStoredModel(LAST_STORY_MODEL_STORAGE_KEY);
    const storedScript = readStoredModel(LAST_SCRIPT_MODEL_STORAGE_KEY);
    if ((storedStory || qwenDefaultModel) && !storyModel) setStoryModel(storedStory || qwenDefaultModel);
    if ((storedScript || qwenDefaultModel) && !scriptModel) setScriptModel(storedScript || qwenDefaultModel);
  }, [draft, qwenDefaultModel, scriptModel, storyModel]);

  useEffect(() => {
    writeStoredModel(LAST_STORY_MODEL_STORAGE_KEY, storyModel);
  }, [storyModel]);

  useEffect(() => {
    writeStoredModel(LAST_SCRIPT_MODEL_STORAGE_KEY, scriptModel);
  }, [scriptModel]);

  useEffect(() => {
    if (typeof window === "undefined" || !draft?.id) return;
    window.localStorage.setItem(ACTIVE_DRAFT_STORAGE_KEY, draft.id);
  }, [draft?.id]);

  useEffect(() => {
    if (selectedQueueItemId) return;
    const channel = queueChannels.find((item) => item.channel === selectedChannel);
    if (channel?.preset_project_id) {
      setSelectedSourceId(channel.preset_project_id);
    }
  }, [queueChannels, selectedChannel, selectedQueueItemId]);

  const openDraft = async (draftId: string) => {
    setBusy("load");
    setMessage("");
    try {
      const data = await scriptStudioApi.getDraft(draftId);
      setDraft(data);
      setSelectedQueueItemId("");
      setSelectedSourceId(data.source_project_id || "");
      setTopic(data.topic || "");
      setTitle(data.title || "");
      setStoryModel(stripOllamaPrefix(String(data.config?.story_model || data.config?.script_model || qwenDefaultModel || "")));
      setScriptModel(stripOllamaPrefix(String(data.config?.script_model || data.config?.story_model || qwenDefaultModel || "")));
    } finally {
      setBusy(null);
    }
  };

  useEffect(() => {
    if (typeof window === "undefined" || draft || busy === "load") return;
    const draftId = window.localStorage.getItem(ACTIVE_DRAFT_STORAGE_KEY) || "";
    if (!draftId || restoredDraftId === draftId) return;
    setRestoredDraftId(draftId);
    void openDraft(draftId);
  }, [busy, draft, drafts.length, restoredDraftId]);

  const selectQueueTopic = (item: ScriptStudioQueueTopic) => {
    const source = sources.find((row) => row.id === item.resolved_project_id) || null;
    setDraft(null);
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(ACTIVE_DRAFT_STORAGE_KEY);
    }
    setSelectedQueueItemId(item.id);
    setSelectedSourceId(item.resolved_project_id || "");
    setTopic(item.topic || "");
    setTitle(item.title || item.topic || "");
    if (source) {
      setStoryModel(lastStoryModel() || stripOllamaPrefix(source.story_model) || stripOllamaPrefix(source.script_model) || storyModel);
      setScriptModel(lastScriptModel() || stripOllamaPrefix(source.script_model) || stripOllamaPrefix(source.story_model) || scriptModel);
    } else if (qwenDefaultModel) {
      setStoryModel(lastStoryModel() || qwenDefaultModel);
      setScriptModel(lastScriptModel() || qwenDefaultModel);
    }
  };

  const toggleQueueCheck = (itemId: string) => {
    setCheckedQueueItemIds((prev) =>
      prev.includes(itemId) ? prev.filter((id) => id !== itemId) : [...prev, itemId],
    );
  };

  const toggleActiveChannelChecks = () => {
    const ids = (activeQueueChannel?.items || []).map((item) => item.id);
    if (!ids.length) return;
    const checked = new Set(checkedQueueItemIds);
    const allChecked = ids.every((id) => checked.has(id));
    setCheckedQueueItemIds((prev) => {
      const current = new Set(prev);
      ids.forEach((id) => {
        if (allChecked) current.delete(id);
        else current.add(id);
      });
      return Array.from(current);
    });
  };

  const createDraftFromSelectedQueue = async () => {
    if (!selectedQueueItem) {
      setMessage("선택된 제작큐 주제가 없습니다.");
      return;
    }
    const existing = findExistingDraftForQueueItem(selectedQueueItem);
    let replaceExisting = false;
    if (existing) {
      replaceExisting = window.confirm(
        `같은 주제의 기존 초안이 있습니다.\n\n${existing.title || existing.topic}\n\n새 초안을 만들면 기존 초안은 삭제 폴더로 이동됩니다.\n계속하시겠습니까?`,
      );
      if (!replaceExisting) {
        await openDraft(existing.id);
        setMessage("기존 초안을 열었습니다.");
        return;
      }
    }
    setBusy("queue-draft");
    setMessage("");
    try {
      const selectedStoryModel = lastStoryModel() || qwenDefaultModel;
      const selectedScriptModel = lastScriptModel() || qwenDefaultModel;
      const created = await scriptStudioApi.createDraftFromQueue(selectedQueueItem.id, {
        replace_existing: replaceExisting,
        config_overrides: {
          story_model: stripOllamaPrefix(selectedStoryModel),
          script_model: stripOllamaPrefix(selectedScriptModel),
        },
      });
      setDraft(created);
      setSelectedSourceId(created.source_project_id || "");
      setTopic(created.topic || "");
      setTitle(created.title || "");
      setStoryModel(stripOllamaPrefix(String(created.config?.story_model || selectedStoryModel || "")));
      setScriptModel(stripOllamaPrefix(String(created.config?.script_model || selectedScriptModel || "")));
      setDrafts((prev) => [created, ...prev.filter((item) => item.id !== created.id && item.id !== existing?.id)]);
      setMessage("선택 주제 초안 생성 완료");
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const createDraftsFromCheckedQueue = async () => {
    if (!checkedQueueItems.length) {
      setMessage("선택된 제작큐 주제가 없습니다.");
      return;
    }
    const existingByItemId = new Map<string, ScriptStudioDraft>();
    checkedQueueItems.forEach((item) => {
      const existing = findExistingDraftForQueueItem(item);
      if (existing) existingByItemId.set(item.id, existing);
    });
    if (existingByItemId.size > 0) {
      const ok = window.confirm(
        `선택 항목 중 기존 초안이 ${existingByItemId.size}개 있습니다.\n\n계속하면 해당 기존 초안은 삭제 폴더로 이동되고 새 초안이 생성됩니다.\n계속하시겠습니까?`,
      );
      if (!ok) {
        setMessage("기존 초안 삭제를 취소했습니다.");
        return;
      }
    }
    setBusy("batch");
    setMessage("");
    const created: ScriptStudioDraft[] = [];
    try {
      for (let index = 0; index < checkedQueueItems.length; index += 1) {
        const item = checkedQueueItems[index];
        setMessage(`초안 생성 중 ${index + 1}/${checkedQueueItems.length}: ${item.title || item.topic}`);
        const selectedStoryModel = lastStoryModel() || qwenDefaultModel;
        const selectedScriptModel = lastScriptModel() || qwenDefaultModel;
        const next = await scriptStudioApi.createDraftFromQueue(item.id, {
          replace_existing: existingByItemId.has(item.id),
          config_overrides: {
            story_model: stripOllamaPrefix(selectedStoryModel),
            script_model: stripOllamaPrefix(selectedScriptModel),
          },
        });
        created.push(next);
      }
      if (created.length) {
        const latest = created[created.length - 1];
        setDraft(latest);
        setSelectedSourceId(latest.source_project_id || "");
        setTopic(latest.topic || "");
        setTitle(latest.title || "");
        setStoryModel(stripOllamaPrefix(String(latest.config?.story_model || latest.config?.script_model || qwenDefaultModel || storyModel)));
        setScriptModel(stripOllamaPrefix(String(latest.config?.script_model || latest.config?.story_model || qwenDefaultModel || scriptModel)));
        const replacedIds = new Set(Array.from(existingByItemId.values()).map((item) => item.id));
        setDrafts((prev) => [
          ...created.reverse(),
          ...prev.filter((item) => !created.some((row) => row.id === item.id) && !replacedIds.has(item.id)),
        ]);
      }
      setCheckedQueueItemIds([]);
      setMessage(`선택 주제 ${created.length}개 초안 생성 완료`);
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const createDraft = async () => {
    const requestedTopic = topic.trim() || selectedSource?.topic || "";
    const existing = findExistingDraftForTopic(requestedTopic);
    let replacedId = "";
    if (existing) {
      const ok = window.confirm(
        `같은 주제의 기존 초안이 있습니다.\n\n${existing.title || existing.topic}\n\n새 초안을 만들면 기존 초안은 삭제 폴더로 이동됩니다.\n계속하시겠습니까?`,
      );
      if (!ok) {
        await openDraft(existing.id);
        setMessage("기존 초안을 열었습니다.");
        return;
      }
      replacedId = existing.id;
    }
    setBusy("create");
    setMessage("");
    try {
      if (replacedId) {
        await scriptStudioApi.deleteDraft(replacedId);
      }
      const created = await scriptStudioApi.createDraft({
        source_project_id: selectedSourceId || null,
        topic: requestedTopic,
        title: title.trim() || topic.trim() || selectedSource?.title || "",
        config_overrides: {
          story_model: lastStoryModel() || stripOllamaPrefix(selectedSource?.story_model) || undefined,
          script_model: lastScriptModel() || stripOllamaPrefix(selectedSource?.script_model) || undefined,
        },
      });
      setDraft(created);
      setDrafts((prev) => [created, ...prev.filter((item) => item.id !== created.id && item.id !== replacedId)]);
      setMessage("초안 생성 완료");
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const saveDraft = async () => {
    if (!draft) return null;
    setBusy("save");
    setMessage("");
    try {
      const saved = await scriptStudioApi.updateDraft(draft.id, {
        title,
        topic,
        config: {
          story_model: stripOllamaPrefix(storyModel),
          script_model: stripOllamaPrefix(scriptModel),
        },
      });
      setDraft(saved);
      setDrafts((prev) => prev.map((item) => (item.id === saved.id ? saved : item)));
      setMessage("저장 완료");
      return saved;
    } catch (e) {
      setMessage((e as Error).message);
      return null;
    } finally {
      setBusy(null);
    }
  };

  const deleteDraft = async (draftId: string) => {
    const target = drafts.find((item) => item.id === draftId);
    if (!confirm(`초안을 삭제 폴더로 이동합니다.\n${target?.title || target?.topic || draftId}`)) return;
    setBusy("delete");
    setMessage("");
    try {
      await scriptStudioApi.deleteDraft(draftId);
      setDrafts((prev) => prev.filter((item) => item.id !== draftId));
      if (draft?.id === draftId) {
        setDraft(null);
        setSelectedQueueItemId("");
        if (typeof window !== "undefined") {
          window.localStorage.removeItem(ACTIVE_DRAFT_STORAGE_KEY);
        }
      }
      setMessage("초안 삭제 폴더 이동 완료");
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const stopActiveRequest = async () => {
    activeRequestRef.current?.abort();
    activeRequestRef.current = null;
    if (!draft?.id) {
      setBusy(null);
      setMessage("작업 중지 요청 완료");
      return;
    }
    try {
      const next = await scriptStudioApi.cancelJob(draft.id);
      setDraft(next);
      setDrafts((prev) => prev.map((item) => (item.id === next.id ? next : item)));
      setBusy(null);
      setMessage("작업 중지 요청 완료");
    } catch (e) {
      setMessage((e as Error).message);
    }
  };

  const runStory = async () => {
    const activeCallId = "script-studio-story";
    const selectedStoryModel = lastStoryModel() || qwenDefaultModel;
    const saved = draft ? await saveDraft() : await scriptStudioApi.createDraft({
      source_project_id: selectedSourceId || null,
      topic,
      title,
      config_overrides: {
        story_model: stripOllamaPrefix(selectedStoryModel),
        script_model: lastScriptModel() || qwenDefaultModel,
      },
    });
    const target = saved || draft;
    if (!target) return;
    activeRequestRef.current = null;
    setBusy("story");
    setMessage("");
    writeActiveCall({
      id: activeCallId,
      label: "스토리",
      model: modelName(models, String(target.config?.story_model || selectedStoryModel || "")),
      title: target.title || target.topic || "대본실 초안",
      detail: `${target.source_project_title || "대본실"} · ${draftEpisodeLabel(target)}`,
    });
    try {
      const next = await scriptStudioApi.startStory(target.id);
      setDraft(next);
      setDrafts((prev) => [next, ...prev.filter((item) => item.id !== next.id)]);
      setMessage("스토리 생성 시작");
    } catch (e) {
      setMessage((e as Error).message);
      setBusy(null);
      clearActiveCall(activeCallId);
    }
  };

  const runScript = async (mode: "new" | "resume" | "block" = "new", blockIndex?: number) => {
    if (!draft) return;
    if (mode === "new" && (draft.script_partial_exists || draft.script_exists || cuts.length > 0)) {
      const ok = window.confirm("기존 대본/부분 대본을 버리고 새로 만들까요?");
      if (!ok) return;
    }
    const activeCallId = "script-studio-script";
    const selectedScriptModel = lastScriptModel() || qwenDefaultModel;
    await saveDraft();
    activeRequestRef.current = null;
    setBusy("script");
    setMessage("");
    writeActiveCall({
      id: activeCallId,
      label: mode === "block" ? `대본 Block ${blockIndex}` : "대본",
      model: modelName(models, selectedScriptModel),
      title: draft.title || draft.topic || "대본실 초안",
      detail: `${draft.source_project_title || "대본실"} · ${draftEpisodeLabel(draft)}`,
    });
    try {
      const next = await scriptStudioApi.startScript(draft.id, { mode, block_index: blockIndex });
      setDraft(next);
      setDrafts((prev) => [next, ...prev.filter((item) => item.id !== next.id)]);
      setMessage(mode === "resume" ? "대본 이어서 생성 시작" : mode === "block" ? `Block ${blockIndex} 재생성 시작` : "새 대본 생성 시작");
    } catch (e) {
      setMessage((e as Error).message);
      setBusy(null);
      clearActiveCall(activeCallId);
    }
  };

  const validate = async () => {
    if (!draft) return;
    setBusy("validate");
    try {
      const next = await scriptStudioApi.startValidate(draft.id);
      setDraft(next);
      setMessage("검사 시작");
    } catch (e) {
      setMessage((e as Error).message);
      setBusy(null);
    }
  };

  const exportJson = async () => {
    if (!draft) return;
    setBusy("export");
    try {
      const result = await scriptStudioApi.export(draft.id);
      setMessage(`내보내기 완료: ${result.path}`);
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const applyToProject = async () => {
    if (!draft) return;
    if (!draft.source_project_id) {
      setMessage("연결된 롱폼공장 프로젝트가 없습니다.");
      return;
    }
    if (!confirm("이 초안을 연결된 롱폼공장 프로젝트의 대본으로 적용합니다. 기존 대본은 버전 백업 후 교체됩니다.")) return;
    setBusy("apply");
    try {
      const next = await scriptStudioApi.startApplyToProject(draft.id);
      setDraft(next);
      setMessage("공장 적용 시작");
    } catch (e) {
      setMessage((e as Error).message);
      setBusy(null);
    }
  };

  const storyPlan = draft?.story_plan;
  const characterMap = Array.isArray(storyPlan?.character_map) ? storyPlan.character_map : [];
  const causalityChain = storyLines(storyPlan?.causality_chain);
  const sceneBlocks = Array.isArray(storyPlan?.scene_blocks) ? storyPlan.scene_blocks : [];
  const factLedger = (storyPlan?.fact_ledger || {}) as Record<string, unknown>;
  const visualPlan = (storyPlan?.visual_plan || {}) as Record<string, unknown>;
  const confirmedFacts = storyLines(factLedger.confirmed_facts);
  const carefulInferences = storyLines(factLedger.careful_inferences);
  const unknownOrDebated = storyLines(factLedger.unknown_or_debated);
  const forbiddenClaims = storyLines(factLedger.forbidden_claims);
  const finalCuts = (draft?.script?.cuts || []) as Cut[];
  const textBlockCuts = (((draft?.script as any)?.script_text_blocks || []) as any[])
    .flatMap((block) => Array.isArray(block?.lines) ? block.lines : [])
    .map((line) => ({
      ...line,
      image_prompt: "",
      scene_block_id: Number(line?.scene_block_id || Math.ceil(Number(line?.cut_number || 0) / SCRIPT_STUDIO_BLOCK_CUTS)),
    })) as Cut[];
  const cuts = finalCuts.length ? finalCuts : textBlockCuts;
  const hasScriptForValidation = !!draft?.script_exists || !!draft?.script_partial_exists || cuts.length > 0;
  const canResumeScript = !!draft?.script_partial_exists && draft?.script_status !== "completed";
  const issues = draft?.validation_report?.issues || [];
  const validationPipeline = draft?.validation_report?.validation_pipeline || [];
  const validationStage = (stage: string) => validationPipeline.slice().reverse().find((item) => item.stage === stage);
  const validationStageByAttempt = (stage: string, attempt: number) =>
    validationPipeline.find((item) => item.stage === stage && Number(item.attempt || 0) === attempt);
  const validationRunning =
    draft?.generation_progress?.stage === "validate" && draft.generation_progress.status === "running";
  const validationFailed = !!draft?.validation_report && draft.validation_report.ok === false;
  const validationPassed = !!draft?.validation_report?.ok;
  const validationCurrentMessage = String(draft?.generation_progress?.message || "");
  const validationCurrentModel = String(draft?.generation_progress?.model || "");
  const validationCurrentText = `${validationCurrentMessage} ${validationCurrentModel}`.toLowerCase();
  const validationCurrentStep =
    validationRunning
      ? validationCurrentMessage || validationCurrentModel || "검수 진행 중"
      : validationPassed
        ? "Gemma 통과 완료"
          : validationFailed
            ? "Gemma 실패, 재검토 결과 확인"
            : "검수 대기";
  const isBusy = !!busy;
  const rawGenerationProgress = draft?.generation_progress;
  const activeProgress =
    rawGenerationProgress?.stage === busy ? rawGenerationProgress : null;
  const activeProgressPct =
    typeof activeProgress?.progress_pct === "number"
      ? Math.max(0, Math.min(100, activeProgress.progress_pct))
      : null;
  const activeProgressTotal = Number(activeProgress?.total || 0);
  const activeProgressCompleted = Number(activeProgress?.completed || 0);
  const activeElapsedSec =
    typeof activeProgress?.elapsed_seconds === "number"
      ? Math.max(activeProgress.elapsed_seconds, busyElapsedSec)
      : busyElapsedSec;
  const jobHistory = (draft?.job_history || []).filter((item) => item.stage === "story" || item.stage === "script");
  const jobStats = draft?.job_stats || {};
  const storyJobStats = jobStats.story || {};
  const scriptJobStats = jobStats.script || {};
  const activeJobRow =
    activeProgress && (activeProgress.stage === "story" || activeProgress.stage === "script")
      ? {
          job_id: activeProgress.job_id || "running",
          stage: activeProgress.stage,
          status: activeProgress.status,
          model: activeProgress.model,
          message: activeProgress.message,
          started_at: activeProgress.started_at,
          finished_at: activeProgress.finished_at,
          elapsed_seconds: activeElapsedSec,
        }
      : null;
  const displayJobRows = [
    ...(activeJobRow ? [activeJobRow] : []),
    ...jobHistory.slice().reverse().slice(0, activeJobRow ? 5 : 6),
  ];
  const scriptProgress = rawGenerationProgress?.stage === "script" ? rawGenerationProgress : null;
  const blockProgress = rawGenerationProgress?.block_progress;
  const blockMap = blockProgress?.blocks || {};
  const progressTotalBlocks = Number(scriptProgress?.total || 0);
  const progressCompletedBlocks = Number(scriptProgress?.completed || 0);
  const inferredBlockTotal = Math.ceil((draft?.cut_count || cuts.length || sceneBlocks.length * SCRIPT_STUDIO_BLOCK_CUTS || 150) / SCRIPT_STUDIO_BLOCK_CUTS);
  const rawBlockTotal = Math.max(1, Number(blockProgress?.total_blocks || 0) || progressTotalBlocks || inferredBlockTotal || SCRIPT_STUDIO_BLOCK_TOTAL);
  const blockTotal = Math.min(SCRIPT_STUDIO_BLOCK_TOTAL, rawBlockTotal);
  const blockIndexes = Array.from({ length: blockTotal }, (_, index) => index + 1);
  const completedBlockCount = Math.min(
    blockTotal,
    Math.max(
      progressCompletedBlocks,
      Math.floor((draft?.cut_count || cuts.length || 0) / SCRIPT_STUDIO_BLOCK_CUTS),
      draft?.script_status === "completed" ? blockTotal : 0,
    ),
  );
  const reportedCurrentBlock = Number(blockProgress?.current_block || 0);
  const currentBlock =
    (reportedCurrentBlock > 0 ? Math.min(blockTotal, reportedCurrentBlock) : 0) ||
    (scriptProgress?.status === "running" ? Math.min(blockTotal, completedBlockCount + 1) : 0);
  const inferredGenerationStatus = (index: number, explicitStatus?: string) => {
    if (explicitStatus) return explicitStatus;
    if (index <= completedBlockCount) return "completed";
    if (scriptProgress?.status === "running" && index === currentBlock) return "running";
    if (scriptProgress?.status === "failed" && index === currentBlock) return "failed";
    return "pending";
  };
  const inferredPythonStatus = (index: number, explicitStatus?: string) => {
    if (explicitStatus) return explicitStatus;
    if (index <= completedBlockCount) return "completed";
    const messageText = String(scriptProgress?.message || "");
    if (
      scriptProgress?.status === "running" &&
      index === currentBlock &&
      (messageText.includes("Python") || messageText.includes("검수"))
    ) {
      return "running";
    }
    return "pending";
  };
  const gemmaStage = validationStage("gemma");
  const gemmaCheck1 = validationStageByAttempt("gemma", 1);
  const gemmaCheck2 = validationStageByAttempt("gemma", 2);
  const gemmaCheck3 = validationStageByAttempt("gemma", 3);
  const gemmaRevision1Stage = validationStageByAttempt("gemma_revision", 1);
  const gemmaRevision2Stage = validationStageByAttempt("gemma_revision", 2);
  const gemmaRevision3Stage = validationStageByAttempt("gemma_revision", 3);
  const gemmaRevisionRunning = validationRunning && validationCurrentText.includes("gemma") && validationCurrentMessage.includes("수정");
  const activeGemmaCheckAttempt =
    validationRunning && validationCurrentText.includes("gemma") && !gemmaRevisionRunning
      ? validationCurrentMessage.includes("1차")
        ? 1
        : validationCurrentMessage.includes("2차")
          ? 2
          : validationCurrentMessage.includes("3차")
            ? 3
            : 0
      : 0;
  const latestGemmaAttempt = Math.max(
    0,
    ...validationPipeline
      .filter((item) => item.stage === "gemma")
      .map((item) => Number(item.attempt || 0)),
  );
  const activeGemmaRevisionAttempt = gemmaRevisionRunning ? latestGemmaAttempt : 0;
  const gemmaRunning = validationRunning && validationCurrentText.includes("gemma") && !gemmaRevisionRunning;
  const currentValidationModelLabel = compactModelLabel(validationCurrentModel);
  const currentValidationStageLabel =
    gemmaRevisionRunning
      ? "Gemma 수정 진행"
      : gemmaRunning
          ? "Gemma 블럭검사 진행"
          : validationRunning
            ? "검수 진행"
            : "";
  const cutBlockLookup = new Map<number, number>();
  cuts.forEach((cut) => {
    const cutNumber = Number(cut.cut_number || 0);
    if (cutNumber > 0) {
      cutBlockLookup.set(cutNumber, Number(cut.scene_block_id || Math.ceil(cutNumber / SCRIPT_STUDIO_BLOCK_CUTS)));
    }
  });
  const cutsByBlock = new Map<number, Cut[]>();
  cuts.forEach((cut) => {
    const cutNumber = Number(cut.cut_number || 0);
    const blockId = Number(cut.scene_block_id || (cutNumber > 0 ? Math.ceil(cutNumber / SCRIPT_STUDIO_BLOCK_CUTS) : 0));
    if (blockId <= 0) return;
    const rows = cutsByBlock.get(blockId) || [];
    rows.push(cut);
    cutsByBlock.set(blockId, rows);
  });
  const scriptBlockResults = blockIndexes
    .map((index) => {
      const block = blockMap[String(index)] || {};
      const storyBlock = sceneBlocks.find((item) => Number(item.block_id || 0) === index);
      const blockCuts = (cutsByBlock.get(index) || [])
        .slice()
        .sort((a, b) => Number(a.cut_number || 0) - Number(b.cut_number || 0));
      const status = inferredGenerationStatus(index, String(block.generation_status || ""));
      const pythonStatus = inferredPythonStatus(index, String(block.validation_status || ""));
      const fallbackUsed = !!block.fallback_used;
      const firstCut = Number(blockCuts[0]?.cut_number || 0);
      const lastCut = Number(blockCuts[blockCuts.length - 1]?.cut_number || 0);
      const fallbackRange = firstCut && lastCut ? `${firstCut}-${lastCut}` : `${(index - 1) * SCRIPT_STUDIO_BLOCK_CUTS + 1}-${index * SCRIPT_STUDIO_BLOCK_CUTS}`;
      return {
        index,
        block,
        storyBlock,
        cuts: blockCuts,
        status,
        pythonStatus,
        fallbackUsed,
        range: String(block.cut_range || storyBlock?.cut_range || fallbackRange),
      };
    })
    .filter((item) => (
      item.cuts.length > 0 ||
      item.status === "running" ||
      item.status === "failed" ||
      item.status === "fallback" ||
      currentBlock === item.index
    ));
  const touchedBlocksForReport = (report?: { fix_plan?: any[]; patches?: any[] } | null) => {
    const touched = new Set<number>();
    ((report as any)?.block_reports || []).forEach((item: any) => {
      const blockId = Number(item?.block_id || 0);
      if (blockId > 0) touched.add(blockId);
    });
    report?.fix_plan?.forEach((item) => {
      const blockId = Number(item?.block_id || 0);
      if (blockId > 0) touched.add(blockId);
      (Array.isArray(item?.affected_cuts) ? item.affected_cuts : []).forEach((cutNumber: number) => {
        const mapped = cutBlockLookup.get(Number(cutNumber));
        if (mapped) touched.add(mapped);
      });
      const mapped = cutBlockLookup.get(Number(item?.cut_number || 0));
      if (mapped) touched.add(mapped);
    });
    report?.patches?.forEach((patch) => {
      const mapped = cutBlockLookup.get(Number(patch?.cut_number || 0));
      if (mapped) touched.add(mapped);
    });
    return touched;
  };
  const blockReportForIndex = (report: any, index: number) => {
    const reports = Array.isArray(report?.block_reports) ? report.block_reports : [];
    return reports.find((item: any) => Number(item?.block_id || 0) === index);
  };
  const validationBlockStatus = (report: any, index: number, attempt: number) => {
    if (activeGemmaCheckAttempt === attempt && currentBlock === index) return "running";
    const blockReport = blockReportForIndex(report, index);
    if (blockReport) return blockReport.passed ? "completed" : "failed";
    return report ? "pending" : "pending";
  };
  const validationBlockLabel = (report: any, index: number, attempt: number) => {
    if (activeGemmaCheckAttempt === attempt && currentBlock === index) return "검사";
    const blockReport = blockReportForIndex(report, index);
    if (!blockReport) return "";
    return blockReport.passed ? "통과" : "문제";
  };
  const generationJobLogSection = draft ? (
    <section className="mb-5 rounded-md border border-border bg-bg-secondary">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h2 className="text-base font-black">생성 작업록</h2>
        <div className="flex items-center gap-3 text-xs text-gray-500">
          <span>스토리 평균 {formatElapsed(Number(storyJobStats.avg_elapsed_seconds || 0))}</span>
          <span>대본 평균 {formatElapsed(Number(scriptJobStats.avg_elapsed_seconds || 0))}</span>
        </div>
      </div>
      {displayJobRows.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-bg-tertiary text-left text-xs uppercase text-gray-500">
              <tr>
                <th className="px-3 py-2">단계</th>
                <th className="px-3 py-2">상태</th>
                <th className="px-3 py-2">모델</th>
                <th className="px-3 py-2">시작</th>
                <th className="px-3 py-2">완료</th>
                <th className="px-3 py-2 text-right">소요</th>
              </tr>
            </thead>
            <tbody>
              {displayJobRows.map((row, index) => (
                <tr key={`${row.job_id || index}-${index}`} className="border-t border-border/70">
                  <td className="px-3 py-2 font-bold text-gray-100">{generationStageLabel(row.stage)}</td>
                  <td className="px-3 py-2 text-gray-300">{generationStatusLabel(row.status)}</td>
                  <td className="max-w-[260px] truncate px-3 py-2 text-xs text-gray-400">{stripOllamaPrefix(row.model) || "-"}</td>
                  <td className="px-3 py-2 font-mono text-xs text-gray-500">{compactDate(row.started_at)}</td>
                  <td className="px-3 py-2 font-mono text-xs text-gray-500">{row.finished_at ? compactDate(row.finished_at) : "-"}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs font-black text-accent-secondary">
                    {formatElapsed(Number(row.elapsed_seconds || 0))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="px-4 py-6 text-center text-sm text-gray-500">생성 작업 기록 없음</div>
      )}
    </section>
  ) : null;

  return (
    <div className="min-h-screen bg-bg-primary text-white">
      <header className="sticky top-0 z-10 border-b border-border bg-bg-primary/95 backdrop-blur">
        <div className="flex h-16 items-center justify-between px-6">
          <div className="flex items-center gap-4">
            <Link href="/" className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-border bg-bg-secondary text-gray-200 hover:bg-bg-tertiary">
              <ArrowLeft size={18} />
            </Link>
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent-primary">
                <FilePenLine size={20} />
              </div>
              <div>
                <h1 className="text-xl font-black">대본실</h1>
                <div className="text-xs text-gray-500">Script Studio</div>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {message && (
              <div className="max-w-[520px] truncate rounded-md border border-border bg-bg-secondary px-3 py-2 text-sm text-gray-200">
                {message}
              </div>
            )}
            <ActionButton onClick={() => void load()} disabled={isBusy} icon={<RefreshCw size={16} />}>
              새로고침
            </ActionButton>
          </div>
        </div>
      </header>

      <main className="grid grid-cols-[360px_minmax(0,1fr)] gap-0">
        <aside className="min-h-[calc(100vh-64px)] border-r border-border bg-bg-secondary/70 p-4">
          <section className="mb-5 rounded-md border border-border bg-bg-primary/70 p-3">
            <div className="mb-3 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <ClipboardList size={16} className="text-accent-primary" />
                <h2 className="text-sm font-black text-gray-100">롱폼공장 제작큐</h2>
              </div>
              <span className="text-xs font-mono text-gray-500">
                {queueChannels.reduce((sum, channel) => sum + channel.items.length, 0)}
              </span>
            </div>
            <div className="mb-3 flex items-center justify-between gap-2">
              <button
                type="button"
                onClick={toggleActiveChannelChecks}
                disabled={!activeQueueChannel?.items.length}
                className="inline-flex h-8 items-center gap-1.5 rounded border border-border bg-bg-secondary px-2 text-xs font-bold text-gray-200 transition-colors hover:bg-bg-tertiary disabled:cursor-not-allowed disabled:opacity-50"
              >
                <CheckSquare size={14} />
                채널 전체 선택
              </button>
              <span className="text-xs font-mono text-accent-secondary">{checkedQueueItemIds.length} 선택</span>
            </div>

            <div className="mb-3 grid grid-cols-4 gap-1.5">
              {queueChannels.map((channel) => (
                <button
                  key={channel.channel}
                  type="button"
                  onClick={() => {
                    setSelectedChannel(channel.channel);
                    setSelectedQueueItemId("");
                    setSelectedSourceId(channel.preset_project_id || "");
                  }}
                  className={`h-8 rounded border text-xs font-black transition-colors ${
                    selectedChannel === channel.channel
                      ? "border-accent-primary bg-accent-primary/15 text-accent-primary"
                      : "border-border bg-bg-secondary text-gray-300 hover:bg-bg-tertiary"
                  }`}
                  title={channel.preset_project_title || ""}
                >
                  CH{channel.channel}
                </button>
              ))}
            </div>

            <div className="mb-3 max-h-72 space-y-2 overflow-y-auto pr-1">
              {activeQueueChannel?.items.length ? (
                activeQueueChannel.items.map((item) => {
                  const active = selectedQueueItemId === item.id;
                  const ep = episodeLabel(item.episode_number);
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => selectQueueTopic(item)}
                      className={`w-full rounded-md border px-3 py-2 text-left transition-colors ${
                        active
                          ? "border-accent-primary bg-accent-primary/10"
                        : "border-border bg-bg-secondary hover:bg-bg-tertiary"
                      }`}
                    >
                      <div className="flex items-start gap-2">
                        <span
                          role="checkbox"
                          aria-checked={checkedQueueItemIds.includes(item.id)}
                          tabIndex={0}
                          onClick={(event) => {
                            event.stopPropagation();
                            toggleQueueCheck(item.id);
                          }}
                          onKeyDown={(event) => {
                            if (event.key === " " || event.key === "Enter") {
                              event.preventDefault();
                              event.stopPropagation();
                              toggleQueueCheck(item.id);
                            }
                          }}
                          className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded border border-border bg-bg-primary text-accent-primary"
                        >
                          {checkedQueueItemIds.includes(item.id) ? <CheckSquare size={14} /> : <Square size={14} />}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="mb-1 flex items-center gap-1.5">
                            {ep && (
                              <span className="shrink-0 rounded border border-accent-secondary/40 bg-accent-secondary/10 px-1.5 py-0.5 text-[10px] font-black text-accent-secondary">
                                {ep}
                              </span>
                            )}
                            <span className="min-w-0 truncate text-xs font-bold text-white">
                              {item.title || item.topic}
                            </span>
                          </span>
                          <span className="flex items-center justify-between gap-2 text-[11px] text-gray-500">
                            <span className="min-w-0 truncate">{item.resolved_project_title || "프리셋 없음"}</span>
                            <span className={`shrink-0 font-bold ${item.has_existing_script ? "text-emerald-300" : "text-gray-500"}`}>
                              {item.has_existing_script ? "대본 있음" : "대본 없음"}
                            </span>
                          </span>
                        </span>
                      </div>
                    </button>
                  );
                })
              ) : (
                <div className="rounded-md border border-dashed border-border px-3 py-8 text-center text-xs text-gray-500">
                  선택 채널의 큐 주제 없음
                </div>
              )}
            </div>

            <ActionButton
              onClick={createDraftFromSelectedQueue}
              disabled={isBusy || !selectedQueueItem}
              tone="primary"
              icon={busy === "queue-draft" ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
            >
              선택 주제 초안 생성
            </ActionButton>
            <div className="mt-2">
              <ActionButton
                onClick={createDraftsFromCheckedQueue}
                disabled={isBusy || checkedQueueItems.length === 0}
                icon={busy === "batch" ? <Loader2 size={16} className="animate-spin" /> : <CheckSquare size={16} />}
              >
                선택된 주제 연속 생성
              </ActionButton>
            </div>
          </section>

          <section className="mb-4 grid grid-cols-2 gap-2">
            <div>
              <FieldLabel>스토리 모델</FieldLabel>
              <ModelSelect value={storyModel} models={models} onChange={setStoryModel} />
            </div>
            <div>
              <FieldLabel>대본 모델</FieldLabel>
              <ModelSelect value={scriptModel} models={models} onChange={setScriptModel} />
            </div>
          </section>

          <section className="mb-4">
            <FieldLabel>제목</FieldLabel>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="h-10 w-full rounded-md border border-border bg-bg-primary px-3 text-sm text-white outline-none focus:border-accent-primary"
            />
          </section>

          <div className="mb-5 grid grid-cols-2 gap-2">
            <ActionButton onClick={createDraft} disabled={isBusy || !topic.trim()} icon={busy === "create" ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}>
              초안 생성
            </ActionButton>
            <ActionButton onClick={() => void saveDraft()} disabled={isBusy || !draft} icon={busy === "save" ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}>
              저장
            </ActionButton>
          </div>

          <section>
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-sm font-black text-gray-100">초안 목록</h2>
              <span className="text-xs font-mono text-gray-500">{drafts.length}</span>
            </div>
            <div className="space-y-2">
              {drafts.map((item) => {
                const active = draft?.id === item.id;
                return (
                  <div
                    key={item.id}
                    className={`w-full rounded-md border px-3 py-2 text-left transition-colors ${
                      active
                        ? "border-accent-primary bg-accent-primary/10"
                        : "border-border bg-bg-primary/70 hover:bg-bg-tertiary"
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      <button
                        type="button"
                        onClick={() => void openDraft(item.id)}
                        className="min-w-0 flex-1 text-left"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="min-w-0 truncate text-sm font-bold text-white">{item.title || item.topic}</div>
                          <span className="shrink-0 rounded border border-border px-1.5 py-0.5 text-[10px] font-bold text-gray-300">
                            {statusLabel[item.status] || item.status}
                          </span>
                        </div>
                        <div className="mt-1 flex items-center justify-between text-xs text-gray-500">
                          <span className="truncate">{item.source_project_title || "독립 초안"}</span>
                          <span>{item.cut_count || 0}컷</span>
                        </div>
                      </button>
                      <button
                        type="button"
                        onClick={() => void deleteDraft(item.id)}
                        disabled={isBusy}
                        className="mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded border border-red-500/40 bg-red-500/10 text-red-200 transition-colors hover:bg-red-500/20 disabled:cursor-not-allowed disabled:opacity-50"
                        title="초안 삭제"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        </aside>

        <section className="min-w-0 p-6">
          <div className="mb-5 rounded-md border border-border bg-bg-secondary p-4">
            <div className="mb-4 grid grid-cols-4 gap-2">
              {stageOrder.map((item) => {
                const active = activeStage === item;
                return (
                  <Link
                    key={item}
                    href={`${basePath}/${item}`}
                    className={`inline-flex h-10 items-center justify-center rounded-md border text-sm font-black transition-colors ${
                      active
                        ? "border-accent-primary bg-accent-primary text-white"
                        : "border-border bg-bg-primary text-gray-300 hover:bg-bg-tertiary"
                    }`}
                  >
                    {stageMeta[item].label}
                  </Link>
                );
              })}
            </div>
            <div className="flex items-center justify-between gap-4">
              <div className="min-w-0">
                <h2 className="text-lg font-black">{stageMeta[activeStage].label}</h2>
                <p className="mt-1 text-sm text-gray-400">{stageMeta[activeStage].description}</p>
              </div>
              <div className="shrink-0">
                {activeStage === "story" && (
                  <ActionButton onClick={runStory} disabled={isBusy || !topic.trim()} tone="primary" icon={busy === "story" ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}>
                    스토리 생성
                  </ActionButton>
                )}
                {activeStage === "script" && (
                  <div className="flex flex-wrap justify-end gap-2">
                    {canResumeScript && (
                      <ActionButton onClick={() => void runScript("resume")} disabled={isBusy || !draft} tone="primary" icon={busy === "script" ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}>
                        이어서 하기
                      </ActionButton>
                    )}
                    <ActionButton onClick={() => void runScript("new")} disabled={isBusy || !draft} tone={canResumeScript ? "default" : "primary"} icon={busy === "script" ? <Loader2 size={16} className="animate-spin" /> : canResumeScript ? <RefreshCw size={16} /> : <FilePenLine size={16} />}>
                      {canResumeScript ? "새로 만들기" : "대본 생성"}
                    </ActionButton>
                  </div>
                )}
                {activeStage === "validate" && (
                  <ActionButton onClick={validate} disabled={isBusy || !hasScriptForValidation} icon={<ListChecks size={16} />}>
                    검사 실행
                  </ActionButton>
                )}
                {activeStage === "apply" && (
                  <ActionButton onClick={applyToProject} disabled={isBusy || !draft?.script_exists || !draft?.source_project_id} tone="danger" icon={<Send size={16} />}>
                    공장 적용
                  </ActionButton>
                )}
              </div>
            </div>
          </div>

          {busy && (
            <div className="mb-5 rounded-md border border-accent-primary/45 bg-accent-primary/10 px-4 py-3">
              <div className="mb-2 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-sm font-black text-white">
                  <Loader2 size={16} className="animate-spin text-accent-primary" />
                  {busyLabel[busy] || "처리 중"}
                </div>
                <div className="flex items-center gap-2">
                  {busy && backgroundStages.has(busy) && (
                    <button
                      type="button"
                      onClick={() => void stopActiveRequest()}
                      className="inline-flex h-8 items-center gap-1.5 rounded border border-red-500/50 bg-red-500/10 px-2 text-xs font-bold text-red-200 transition-colors hover:bg-red-500/20"
                    >
                      <StopCircle size={14} />
                      작업 중지
                    </button>
                  )}
                  <div className="font-mono text-sm font-black text-accent-secondary">
                    {formatElapsed(activeElapsedSec)}
                  </div>
                </div>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-bg-primary">
                {activeProgressPct !== null ? (
                  <div
                    className="h-full rounded-full bg-accent-primary transition-all duration-500"
                    style={{ width: `${activeProgressPct}%` }}
                  />
                ) : (
                  <div className="h-full w-1/3 animate-[slide_1.25s_ease-in-out_infinite] rounded-full bg-accent-primary" />
                )}
              </div>
              <div className="mt-2 flex items-center justify-between gap-3 text-xs text-gray-400">
                <span className="truncate">
                  {activeProgress?.message || "모델 응답 대기 중"}
                </span>
                {activeProgressTotal > 0 && (
                  <span className="shrink-0 font-mono text-accent-secondary">
                    {activeProgressCompleted}/{activeProgressTotal} · {Math.round(activeProgressPct || 0)}%
                  </span>
                )}
              </div>
            </div>
          )}

          {draft && (
            <div className="mb-5 grid grid-cols-4 gap-3">
              <div className="rounded-md border border-border bg-bg-secondary px-4 py-3">
                <div className="text-xs text-gray-500">연결 프로젝트</div>
                <div className="mt-1 truncate text-sm font-bold">{draft.source_project_title || "-"}</div>
              </div>
              <div className="rounded-md border border-border bg-bg-secondary px-4 py-3">
                <div className="text-xs text-gray-500">스토리</div>
                <div className="mt-1 text-sm font-bold">{draft.story_status}</div>
                <div className="mt-1 text-xs text-gray-500">
                  평균 {formatElapsed(Number(storyJobStats.avg_elapsed_seconds || 0))} · {storyJobStats.count || 0}회
                </div>
              </div>
              <div className="rounded-md border border-border bg-bg-secondary px-4 py-3">
                <div className="text-xs text-gray-500">대본</div>
                <div className="mt-1 text-sm font-bold">{draft.script_status} · {draft.cut_count || 0}컷</div>
                <div className="mt-1 text-xs text-gray-500">
                  평균 {formatElapsed(Number(scriptJobStats.avg_elapsed_seconds || 0))} · {scriptJobStats.count || 0}회
                </div>
              </div>
              <div className="rounded-md border border-border bg-bg-secondary px-4 py-3">
                <div className="text-xs text-gray-500">검사</div>
                <div className="mt-1 flex items-center gap-2 text-sm font-bold">
                  {draft.validation_report?.ok ? <CheckCircle2 size={16} className="text-green-400" /> : <AlertTriangle size={16} className="text-amber-400" />}
                  {draft.validation_report ? `${draft.validation_report.issue_count}건` : "-"}
                </div>
              </div>
            </div>
          )}

          {draft && activeStage === "validate" && (
            <section className="mb-5 overflow-hidden rounded-md border border-border bg-bg-secondary">
              <div className="flex items-center justify-between border-b border-border px-4 py-3">
                <div>
                  <h2 className="text-base font-black">블럭 진행표</h2>
                  <div className="mt-1 text-xs text-gray-500">
                    15개 블럭 · 블럭당 10컷 기준으로 블럭 텍스트 생성, Gemma 3단계 검수, Python 최종 JSON 조립 흐름입니다.
                  </div>
                </div>
                <div className="text-right text-xs text-gray-500">
                  <div>{currentBlock ? `현재 블럭 ${currentBlock}/${blockTotal}` : `${blockTotal}블럭`}</div>
                  <div className="mt-1 text-accent-primary">{scriptProgress?.message || activeProgress?.message || validationCurrentStep}</div>
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-[980px] table-fixed border-collapse text-sm">
                  <tbody>
                    <tr className="border-b border-border/70">
                      <th className="w-20 border-r border-border/70 bg-bg-primary px-2 py-3 text-xs text-gray-500" />
                      <th className="w-44 border-r border-border/70 bg-bg-primary px-2 py-3 text-center font-black text-gray-200">블럭</th>
                      {blockIndexes.map((index) => (
                        <th key={`head-${index}`} className="h-11 min-w-12 border-r border-border/70 bg-bg-primary px-1 text-center font-mono text-sm text-gray-200">
                          {index}
                        </th>
                      ))}
                    </tr>
                    <tr className="border-b border-border/70">
                      <th className="border-r border-border/70 bg-bg-primary px-2 py-3 text-center font-black text-gray-200">생성</th>
                      <th className="border-r border-border/70 bg-bg-primary px-2 py-3 text-center text-gray-300">진행용 모델</th>
                      {blockIndexes.map((index) => {
                        const block = blockMap[String(index)] || {};
                        const status = inferredGenerationStatus(index, String(block.generation_status || ""));
                        return (
                          <td key={`gen-${index}`} className={blockCellClass(status, currentBlock === index && status === "running")}>
                            {blockStatusLabel(status)}
                          </td>
                        );
                      })}
                    </tr>
                    <tr className="border-b border-border/70">
                      <th className="border-r border-border/70 bg-bg-primary px-2 py-3 text-center text-xs text-gray-500" />
                      <th className="border-r border-border/70 bg-bg-primary px-2 py-3 text-center text-gray-300">실패횟수</th>
                      {blockIndexes.map((index) => {
                        const block = blockMap[String(index)] || {};
                        const count = Number(block.generation_failures || 0);
                        return (
                          <td key={`gen-fail-${index}`} className={blockCellClass(count > 0 ? "failed" : "pending")}>
                            {count || ""}
                          </td>
                        );
                      })}
                    </tr>
                    <tr className="border-b border-border/70">
                      <th className="border-r border-border/70 bg-bg-primary px-2 py-3 text-center font-black text-gray-200">검사</th>
                      <th className="border-r border-border/70 bg-bg-primary px-2 py-3 text-center text-gray-300">Python</th>
                      {blockIndexes.map((index) => {
                        const block = blockMap[String(index)] || {};
                        const status = inferredPythonStatus(index, String(block.validation_status || ""));
                        return (
                          <td key={`py-${index}`} className={blockCellClass(status, currentBlock === index && status === "running")}>
                            {blockStatusLabel(status)}
                          </td>
                        );
                      })}
                    </tr>
                    <tr className="border-b border-border/70">
                      <th className="border-r border-border/70 bg-bg-primary px-2 py-3 text-center text-xs text-gray-500" />
                      <th className="border-r border-border/70 bg-bg-primary px-2 py-3 text-center text-gray-300">실패횟수</th>
                      {blockIndexes.map((index) => {
                        const block = blockMap[String(index)] || {};
                        const count = Number(block.validation_failures || 0);
                        return (
                          <td key={`py-fail-${index}`} className={blockCellClass(count > 0 ? "failed" : "pending")}>
                            {count || ""}
                          </td>
                        );
                      })}
                    </tr>
                    {validationRunning && (
                      <tr className="border-b border-border/70">
                        <th className="border-r border-border/70 bg-bg-primary px-2 py-3 text-center font-black text-gray-200">현재검수</th>
                        <th className="border-r border-border/70 bg-bg-primary px-2 py-3 text-center text-gray-300">
                          {currentValidationModelLabel}
                        </th>
                        <td colSpan={blockIndexes.length} className={blockCellClass("running", true)}>
                          <div className="flex items-center justify-center gap-2">
                            <Loader2 size={14} className="animate-spin" />
                            <span>{currentValidationStageLabel}</span>
                            <span className="font-semibold text-gray-200">{validationCurrentStep}</span>
                          </div>
                        </td>
                      </tr>
                    )}
                    <tr className="border-b border-border/70">
                      <th className="border-r border-border/70 bg-bg-primary px-2 py-3 text-center font-black text-gray-200">1차 검사</th>
                      <th className="border-r border-border/70 bg-bg-primary px-2 py-3 text-center text-gray-300">Gemma</th>
                      {blockIndexes.map((index) => {
                        const status = validationBlockStatus(gemmaCheck1, index, 1);
                        return (
                          <td key={`gemma-check-1-${index}`} className={blockCellClass(status, activeGemmaCheckAttempt === 1 && currentBlock === index)}>
                            {validationBlockLabel(gemmaCheck1, index, 1)}
                          </td>
                        );
                      })}
                    </tr>
                    <tr className="border-b border-border/70">
                      <th className="border-r border-border/70 bg-bg-primary px-2 py-3 text-center font-black text-gray-200">1차 수정</th>
                      <th className="border-r border-border/70 bg-bg-primary px-2 py-3 text-center text-gray-300">Gemma</th>
                      {blockIndexes.map((index) => {
                        const touched = touchedBlocksForReport(gemmaRevision1Stage).has(index);
                        const running = activeGemmaRevisionAttempt === 1;
                        const status = running && currentBlock === index ? "running" : touched ? "completed" : "pending";
                        return (
                          <td key={`gemma-revision-1-${index}`} className={blockCellClass(status, running && currentBlock === index)}>
                            {running && currentBlock === index ? "진행" : touched ? "수정" : ""}
                          </td>
                        );
                      })}
                    </tr>
                    <tr className="border-b border-border/70">
                      <th className="border-r border-border/70 bg-bg-primary px-2 py-3 text-center font-black text-gray-200">2차 검사</th>
                      <th className="border-r border-border/70 bg-bg-primary px-2 py-3 text-center text-gray-300">Gemma</th>
                      {blockIndexes.map((index) => {
                        const status = validationBlockStatus(gemmaCheck2, index, 2);
                        return (
                          <td key={`gemma-check-2-${index}`} className={blockCellClass(status, activeGemmaCheckAttempt === 2 && currentBlock === index)}>
                            {validationBlockLabel(gemmaCheck2, index, 2)}
                          </td>
                        );
                      })}
                    </tr>
                    <tr className="border-b border-border/70">
                      <th className="border-r border-border/70 bg-bg-primary px-2 py-3 text-center font-black text-gray-200">2차 수정</th>
                      <th className="border-r border-border/70 bg-bg-primary px-2 py-3 text-center text-gray-300">Gemma</th>
                      {blockIndexes.map((index) => {
                        const touched = touchedBlocksForReport(gemmaRevision2Stage).has(index);
                        const running = activeGemmaRevisionAttempt === 2;
                        const status = running && currentBlock === index ? "running" : touched ? "completed" : "pending";
                        return (
                          <td key={`gemma-revision-2-${index}`} className={blockCellClass(status, running && currentBlock === index)}>
                            {running && currentBlock === index ? "진행" : touched ? "수정" : ""}
                          </td>
                        );
                      })}
                    </tr>
                    <tr className="border-b border-border/70">
                      <th className="border-r border-border/70 bg-bg-primary px-2 py-3 text-center font-black text-gray-200">3차 검사</th>
                      <th className="border-r border-border/70 bg-bg-primary px-2 py-3 text-center text-gray-300">Gemma</th>
                      {blockIndexes.map((index) => {
                        const status = validationBlockStatus(gemmaCheck3, index, 3);
                        return (
                          <td key={`gemma-check-3-${index}`} className={blockCellClass(status, activeGemmaCheckAttempt === 3 && currentBlock === index)}>
                            {validationBlockLabel(gemmaCheck3, index, 3)}
                          </td>
                        );
                      })}
                    </tr>
                    <tr className="border-b border-border/70">
                      <th className="border-r border-border/70 bg-bg-primary px-2 py-3 text-center font-black text-gray-200">3차 수정</th>
                      <th className="border-r border-border/70 bg-bg-primary px-2 py-3 text-center text-gray-300">Gemma</th>
                      {blockIndexes.map((index) => {
                        const touched = touchedBlocksForReport(gemmaRevision3Stage).has(index);
                        const running = activeGemmaRevisionAttempt === 3;
                        const status = running && currentBlock === index ? "running" : touched ? "completed" : "pending";
                        return (
                          <td key={`gemma-revision-3-${index}`} className={blockCellClass(status, running && currentBlock === index)}>
                            {running && currentBlock === index ? "진행" : touched ? "수정" : ""}
                          </td>
                        );
                      })}
                    </tr>
                    <tr>
                      <th className="border-r border-border/70 bg-bg-primary px-2 py-3 text-center font-black text-gray-200">최종</th>
                      <th className="border-r border-border/70 bg-bg-primary px-2 py-3 text-center text-gray-300">Gemma</th>
                      <td colSpan={blockIndexes.length} className={blockCellClass(draft.validation_report?.ok ? "completed" : gemmaCheck3?.passed === false ? "failed" : gemmaRunning && !gemmaCheck3 ? "running" : "pending", gemmaRunning && !gemmaCheck3)}>
                        {draft.validation_report?.ok ? "검수 완료" : gemmaRunning && !gemmaCheck3 ? "3차 종합검사 중" : gemmaCheck3?.passed === false ? "검수 실패" : "검수 완료 대기"}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div className="flex flex-wrap gap-3 border-t border-border px-4 py-2 text-xs text-gray-500">
                <span>{compactModelLabel(draft.config?.script_model as string)} 생성</span>
                <span>블럭 텍스트 생성</span>
                <span>Gemma 블럭검사</span>
                <span>각 차수 문제 블럭 즉시 수정</span>
                <span>3차 블럭검사/수정 후 Python JSON 조립</span>
              </div>
            </section>
          )}

          {draft?.last_error && (
            <div className="mb-5 rounded-md border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm font-semibold text-red-100">
              {draft.last_error}
            </div>
          )}

          {(activeStage === "story" || activeStage === "apply") && (
          <div className="mb-5 grid grid-cols-1 gap-5">
            {activeStage === "story" && (
            <section className="min-w-0 rounded-md border border-border bg-bg-secondary">
              <div className="flex items-center justify-between border-b border-border px-4 py-3">
                <h2 className="text-base font-black">스토리 설계</h2>
                <span className="text-xs text-gray-500">{modelName(models, String(draft?.config?.story_model || ""))}</span>
              </div>
              {characterMap.length > 0 && (
                <div className="px-4 py-3">
                  <h3 className="mb-3 text-sm font-black">인물 설계</h3>
                  <div className="grid gap-2">
                    {characterMap.slice(0, 4).map((item, index) => (
                      <div key={`${item.name || "character"}-${index}`} className="rounded-md border border-border bg-bg-primary p-3 text-sm">
                        <div className="font-black text-gray-100">{item.name || `인물 ${index + 1}`}</div>
                        <div className="mt-2 grid gap-1 text-xs leading-5 text-gray-400">
                          <div>설명: {item.identity || item.first_appearance_explanation || "-"}</div>
                          <div>첫출현 블럭: {storyCharacterFirstBlock(item)}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {causalityChain.length > 0 && (
                <div className="border-t border-border px-4 py-3">
                  <h3 className="mb-3 text-sm font-black">사건 인과</h3>
                  <ol className="space-y-2 text-sm leading-6 text-gray-200">
                    {causalityChain.map((line, index) => (
                      <li key={`${line}-${index}`} className="flex gap-2">
                        <span className="shrink-0 font-mono text-xs text-gray-500">{String(index + 1).padStart(2, "0")}</span>
                        <span>{line}</span>
                      </li>
                    ))}
                  </ol>
                </div>
              )}
              {(confirmedFacts.length > 0 || carefulInferences.length > 0 || unknownOrDebated.length > 0 || forbiddenClaims.length > 0) && (
                <div className="border-t border-border px-4 py-3">
                  <h3 className="mb-3 text-sm font-black">팩트 장부</h3>
                  <div className="grid grid-cols-2 gap-2 text-xs leading-5">
                    {[
                      ["확정 사실", confirmedFacts],
                      ["조심스러운 해석", carefulInferences],
                      ["단정 금지", unknownOrDebated],
                      ["금지 주장", forbiddenClaims],
                    ].map(([label, rows]) => (
                      <div key={String(label)} className="rounded-md border border-border bg-bg-primary p-3">
                        <div className="mb-2 font-black text-gray-400">{String(label)}</div>
                        <div className="text-gray-200">{Array.isArray(rows) && rows.length ? rows.join(" / ") : "-"}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {Object.keys(visualPlan).length > 0 && (
                <div className="border-t border-border px-4 py-3">
                  <h3 className="mb-3 text-sm font-black">비주얼 계획</h3>
                  <div className="rounded-md border border-border bg-bg-primary p-3 text-xs leading-5 text-gray-300">
                    {storyLines(visualPlan.five_cut_rhythm).length > 0 && (
                      <div><span className="text-gray-500">10컷 리듬</span> {storyLines(visualPlan.five_cut_rhythm).join(" → ")}</div>
                    )}
                    {storyLines(visualPlan.avoid).length > 0 && (
                      <div><span className="text-gray-500">회피</span> {storyLines(visualPlan.avoid).join(" / ")}</div>
                    )}
                  </div>
                </div>
              )}
              {sceneBlocks.length > 0 && (
                <div className="border-t border-border px-4 py-3">
                  <h3 className="mb-3 text-sm font-black">15블럭 흐름 · 10컷/블럭</h3>
                  <div className="max-h-[520px] space-y-2 overflow-y-auto pr-1">
                    {sceneBlocks.map((block) => (
                      <div key={block.block_id || block.cut_range} className="rounded-md border border-border bg-bg-primary p-3 text-xs leading-5 text-gray-300">
                        <div className="mb-2 flex items-center justify-between gap-3">
                          <div className="font-black text-gray-100">블럭 {block.block_id} · {block.cut_range}</div>
                          <div className="text-gray-500">{block.block_role}</div>
                        </div>
                        <div><span className="text-gray-500">목표</span> {block.block_goal || "-"}</div>
                        <div>
                          <span className="text-gray-500">{Number(block.block_id || 0) === 1 ? "질문" : "핵심"}</span>{" "}
                          {block.mini_question || "-"}
                        </div>
                        <div><span className="text-gray-500">새 정보</span> {block.new_information || "-"}</div>
                        <div><span className="text-gray-500">인과</span> {block.continuity_from_previous || "-"}</div>
                        <div><span className="text-gray-500">압박</span> {block.tension || "-"}</div>
                        <div><span className="text-gray-500">전환</span> {block.turn || "-"}</div>
                        <div><span className="text-gray-500">다음</span> {block.turn_to_next || "-"}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </section>
            )}

            {activeStage === "apply" && (
            <>
              <section className="rounded-md border border-border bg-bg-secondary">
                <div className="flex items-center justify-between border-b border-border px-4 py-3">
                  <h2 className="text-base font-black">내보내기</h2>
                  <FileJson size={18} className="text-gray-500" />
                </div>
                <div className="space-y-3 p-4">
                  <ActionButton onClick={exportJson} disabled={isBusy || !draft?.script_exists} icon={<FileJson size={16} />}>
                    JSON 파일 생성
                  </ActionButton>
                  <div className="rounded-md border border-border bg-bg-primary p-3 text-xs leading-5 text-gray-400">
                    {draft?.path || "초안 경로 없음"}
                  </div>
                  {draft?.last_applied_at && (
                    <div className="rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-200">
                      {draft.last_applied_project_id} · {compactDate(draft.last_applied_at)}
                    </div>
                  )}
                </div>
              </section>
              {generationJobLogSection}
            </>
            )}
          </div>
          )}

          {activeStage === "validate" && (
          <>
          <section className="mb-5 rounded-md border border-border bg-bg-secondary">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <h2 className="text-base font-black">검사 결과</h2>
              <span className="text-xs text-gray-500">{draft?.validation_report?.checked_at ? compactDate(draft.validation_report.checked_at) : ""}</span>
            </div>
            {validationPipeline.length > 0 && (
              <div className="grid grid-cols-4 border-b border-border text-xs">
                {validationPipeline.map((item, index) => (
                  <div key={`${item.stage || "stage"}-${index}`} className="border-r border-border/70 px-3 py-2 last:border-r-0">
                    <div className="mb-1 flex items-center justify-between gap-2">
                      <span className="font-black text-gray-200">{validationStageLabel(item.stage, item.attempt)}</span>
                      <span className={item.passed ? "text-emerald-300" : "text-amber-300"}>
                        {item.passed ? "통과" : "확인"}
                      </span>
                    </div>
                    <div className="truncate text-gray-500">{item.model || "-"}</div>
                    {!!(item.applied_patch_count || item.patch_count) && (
                      <div className="mt-1 text-emerald-300">
                        패치 {item.applied_patch_count || item.patch_count}개
                      </div>
                    )}
                    {!!item.ignored_patch_count && (
                      <div className="mt-1 text-gray-500">
                        미적용 패치 {item.ignored_patch_count}개
                      </div>
                    )}
                    {!!item.fix_plan?.length && (
                      <div className="mt-1 text-amber-300">
                        수정방안 {item.fix_plan.length}개
                      </div>
                    )}
                    {typeof item.score === "number" && item.score > 0 && (
                      <div className="mt-1 font-mono text-gray-400">{item.score}/10</div>
                    )}
                    {item.summary && (
                      <div className="mt-1 line-clamp-2 text-gray-400">{item.summary}</div>
                    )}
                  </div>
                ))}
              </div>
            )}
            <div className="max-h-48 overflow-y-auto">
              {issues.length ? (
                issues.slice(0, 80).map((issue, index) => (
                  <div key={`${issue.block_id || issue.cut_number || 0}-${index}`} className="flex gap-3 border-b border-border/70 px-4 py-2 text-sm">
                    <span className={issue.level === "error" ? "text-red-300" : "text-amber-300"}>{issue.level}</span>
                    <span className="w-20 shrink-0 text-gray-500">
                      {issue.block_id ? `block ${issue.block_id}` : issue.cut_number ? `cut ${issue.cut_number}` : ""}
                    </span>
                    <span className="text-gray-200">{issue.message}</span>
                  </div>
                ))
              ) : (
                <div className="px-4 py-8 text-center text-sm text-gray-500">검사 결과 없음</div>
              )}
            </div>
          </section>
          </>
          )}

          {activeStage === "script" && (
          <section className="rounded-md border border-border bg-bg-secondary">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <h2 className="text-base font-black">블럭별 대본 결과</h2>
              <span className="text-xs text-gray-500">
                {draft?.script_is_partial
                  ? `부분 생성 중 · ${cuts.length}컷 · ${modelName(models, String(draft?.config?.script_model || ""))}`
                  : modelName(models, String(draft?.config?.script_model || ""))}
              </span>
            </div>
            <div className="max-h-[680px] space-y-3 overflow-y-auto p-3">
              {scriptBlockResults.length ? (
                scriptBlockResults.map((item) => (
                  <div key={`script-block-${item.index}`} className="overflow-hidden rounded-md border border-border bg-bg-primary">
                    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-bg-tertiary px-4 py-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-black text-gray-100">Block {item.index}</span>
                          <span className="rounded border border-border px-2 py-0.5 font-mono text-xs text-gray-400">{item.range}컷</span>
                          <span className={item.status === "running" || item.status === "fallback" ? "animate-pulse text-accent-primary" : item.status === "completed" ? "text-emerald-300" : item.status === "failed" ? "text-red-300" : "text-gray-500"}>
                            {blockStatusLabel(item.status) || "대기"}
                          </span>
                          {item.pythonStatus && item.pythonStatus !== "pending" && (
                            <span className={item.pythonStatus === "completed" ? "text-emerald-300" : item.pythonStatus === "running" ? "animate-pulse text-accent-secondary" : item.pythonStatus === "failed" ? "text-red-300" : "text-gray-500"}>
                              Python {blockStatusLabel(item.pythonStatus)}
                            </span>
                          )}
                        </div>
                        <div className="mt-1 truncate text-xs text-gray-500">
                          {item.storyBlock?.mini_question || item.storyBlock?.new_information || item.block.message || "생성 결과"}
                        </div>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <div className="font-mono text-xs font-black text-gray-400">{item.cuts.length}/10컷</div>
                        <button
                          type="button"
                          onClick={() => void runScript("block", item.index)}
                          disabled={isBusy || !draft || item.cuts.length === 0}
                          className="inline-flex h-8 items-center gap-1.5 rounded border border-border bg-bg-secondary px-2 text-xs font-bold text-gray-100 transition-colors hover:bg-bg-tertiary disabled:cursor-not-allowed disabled:opacity-50"
                          title={`Block ${item.index} 재생성`}
                        >
                          <RefreshCw size={13} />
                          재생성
                        </button>
                      </div>
                    </div>
                    {item.cuts.length ? (
                      <table className="w-full table-fixed text-sm">
                        <thead className="bg-bg-secondary text-left text-xs uppercase text-gray-500">
                          <tr>
                            <th className="w-16 px-3 py-2">컷</th>
                            <th className="px-3 py-2">내레이션</th>
                            <th className="w-[34%] px-3 py-2">장면</th>
                          </tr>
                        </thead>
                        <tbody>
                          {item.cuts.map((cut) => (
                            <tr key={cut.cut_number} className="border-t border-border/70 align-top">
                              <td className="px-3 py-3 font-mono text-xs text-gray-500">{cut.cut_number}</td>
                              <td className="px-3 py-3 leading-6 text-gray-100">{cut.narration}</td>
                              <td className="px-3 py-3 text-xs leading-5 text-gray-400">{(cut as any).visual_scene || cut.image_prompt || "-"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : (
                      <div className="px-4 py-8 text-center text-sm text-gray-500">이 블럭 결과 대기 중</div>
                    )}
                  </div>
                ))
              ) : (
                <div className="px-4 py-16 text-center text-sm text-gray-500">대본 없음</div>
              )}
            </div>
          </section>
          )}
        </section>
      </main>
      <style jsx>{`
        @keyframes slide {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(400%); }
        }
      `}</style>
    </div>
  );
}
