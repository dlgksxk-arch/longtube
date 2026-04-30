"use client";

/**
 * v1.1.50 — 딸깍 대시보드 > 제작 큐
 * - 대기 행: 개별 실행 / 삭제
 * - 진행 행: 게이지 바 + 중지 버튼
 * - 실패/취소 행: 이어하기 / 삭제
 * - 2초 폴링으로 진행 상태 업데이트 (페이지 떠나도 백엔드 계속 진행)
 */
import { useCallback, useEffect, useRef, useState, type ChangeEvent } from "react";
import {
  Loader2,
  Play,
  Clock,
  AlertCircle,
  Plus,
  Trash2,
  Save,
  Check,
  X,
  Zap,
  RefreshCw,
  AlertTriangle,
  Square,
  CheckCircle2,
  ChevronRight,
  Calendar,
  Upload,
  Download,
} from "lucide-react";
import * as XLSX from "xlsx";
import {
  oneclickApi,
  projectsApi,
  youtubeStudioApi,
  type OneClickTask,
  type OneClickQueueItem,
  type OrphanProject,
  type Project,
} from "@/lib/api";
import { formatDurationKo } from "@/lib/format";

const STEPS = ["스크립트", "음성", "이미지", "영상", "렌더", "업로드"] as const;
const LIST_PAGE_SIZE = 5;
// 백엔드 step_states 키는 "2"~"7" (숫자 문자열), 프론트 STEPS 인덱스는 0~5
const BACKEND_STEP_NUMS = [2, 3, 4, 5, 6, 7]; // STEPS[0]=step2, STEPS[1]=step3, ...
// 컷 기반 단계인지 (스크립트/음성/이미지/영상 = 인덱스 0~3)
const CUT_BASED_STEPS = new Set([0, 1, 2, 3]);

type StepState = "done" | "active" | "pending" | "failed";
type ChannelListPageKey = "queue" | "active" | "completed" | "failed" | "orphans";

function normalizeUploadTitle(title?: string | null): string {
  const raw = (title || "")
    .normalize("NFKC")
    .toLowerCase()
    .trim()
    .replaceAll("’", "'")
    .replaceAll("‘", "'")
    .replaceAll("“", "\"")
    .replaceAll("”", "\"")
    .replaceAll("—", "-")
    .replaceAll("–", "-")
    .replace(/^ep\.\s*\d+\s*[째-]?\s*/i, "");
  return Array.from(raw).filter((ch) => /[0-9a-zA-Z가-힣]/.test(ch)).join("");
}

function normalizeSheetKey(value: unknown): string {
  return String(value ?? "")
    .normalize("NFKC")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "")
    .replace(/[()[\]{}._\-/:]/g, "");
}

function normalizeQueueItems(items: OneClickQueueItem[] = []): OneClickQueueItem[] {
  return items.map((it) => ({
    ...it,
    id: it.id || Math.random().toString(36).slice(2, 10),
    template_project_id: it.template_project_id || null,
    target_duration: it.target_duration || null,
    channel: it.channel || 1,
    queued_source: it.queued_source || "manual",
    queued_at: it.queued_at || null,
    queued_note: it.queued_note || "",
    requeued_from_task_id: it.requeued_from_task_id || "",
    restored_from_project_id: it.restored_from_project_id || "",
    openings: Array.isArray(it.openings)
      ? [...it.openings.slice(0, 5), "", "", "", "", ""].slice(0, 5)
      : ["", "", "", "", ""],
    endings: Array.isArray(it.endings)
      ? [...it.endings.slice(0, 5), "", "", "", "", ""].slice(0, 5)
      : ["", "", "", "", ""],
    core_content: it.core_content || "",
  }));
}

function parsePositiveInt(value: unknown): number | null {
  const text = String(value ?? "").trim();
  if (!text) return null;
  const match = text.match(/\d+/);
  if (!match) return null;
  const parsed = parseInt(match[0], 10);
  return parsed > 0 ? parsed : null;
}

function parseDurationSeconds(value: unknown): number | null {
  const text = String(value ?? "").trim();
  if (!text) return null;
  const hhmmss = text.match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/);
  if (hhmmss) {
    const a = parseInt(hhmmss[1], 10);
    const b = parseInt(hhmmss[2], 10);
    const c = hhmmss[3] ? parseInt(hhmmss[3], 10) : 0;
    return hhmmss[3] ? (a * 3600 + b * 60 + c) : (a * 60 + b);
  }
  const match = text.match(/\d+/);
  if (!match) return null;
  const parsed = parseInt(match[0], 10);
  return parsed > 0 ? parsed : null;
}

function parseChannelTimeCell(value: unknown): string | null {
  const text = String(value ?? "").trim();
  if (!text) return null;
  const match = text.match(/(\d{1,2}):(\d{2})/);
  if (!match) return null;
  const hh = parseInt(match[1], 10);
  const mm = parseInt(match[2], 10);
  if (Number.isNaN(hh) || Number.isNaN(mm) || hh < 0 || hh > 23 || mm < 0 || mm > 59) {
    return null;
  }
  return `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
}

function parseExcelQueueFile(
  workbook: XLSX.WorkBook,
  channel: number,
  projects: Project[],
): { items: OneClickQueueItem[]; channelTime: string | null } {
  const targetSheetName = workbook.SheetNames.find((name) =>
    normalizeSheetKey(name).includes("자동화스케줄"),
  ) || workbook.SheetNames[0];
  if (!targetSheetName) {
    throw new Error("엑셀 시트를 찾지 못했습니다.");
  }

  const sheet = workbook.Sheets[targetSheetName];
  const rows = XLSX.utils.sheet_to_json<(string | number)[]>(sheet, {
    header: 1,
    defval: "",
    raw: false,
  });
  const headerRowIndex = rows.findIndex((row) =>
    Array.isArray(row) && row.some((cell) => ["주제", "topic", "title"].includes(normalizeSheetKey(cell))),
  );
  if (headerRowIndex < 0) {
    throw new Error("엑셀에서 '주제' 열을 찾지 못했습니다.");
  }

  const headerRow = rows[headerRowIndex] || [];
  const findCol = (...keys: string[]) =>
    headerRow.findIndex((cell) => keys.includes(normalizeSheetKey(cell)));

  const topicCol = findCol("주제", "topic", "title");
  if (topicCol < 0) {
    throw new Error("엑셀에서 '주제' 열을 찾지 못했습니다.");
  }

  const epCol = findCol(
    "ep",
    "회차",
    "번호",
    "episode",
    "episodenumber",
    "에피소드번호",
    "에피소드no",
    "episodeno",
  );
  const timeCol = findCol("시간", "time", "업로드시간", "실행시간");
  const presetIdCol = findCol("프리셋id", "templateprojectid", "presetid", "templateid");
  const presetNameCol = findCol("프리셋", "프리셋명", "preset", "template");
  const durationCol = findCol("길이", "duration", "targetduration", "seconds", "초");
  const coreContentCol = findCol("핵심내용", "핵심콘텐츠", "본문", "내용", "corecontent");
  const nextPreviewCol = findCol("다음화예고", "nextepisodepreview", "nextpreview");
  const openingCols = [1, 2, 3, 4, 5].map((i) => findCol(`오프닝${i}`, `opening${i}`));
  const endingCols = [1, 2, 3, 4, 5].map((i) => findCol(`엔딩${i}`, `ending${i}`));

  const projectTitleMap = new Map(
    projects.map((project) => [normalizeUploadTitle(project.title || project.topic || ""), project.id]),
  );

  const importedItems: OneClickQueueItem[] = [];
  const importedTimes = new Set<string>();

  for (const row of rows.slice(headerRowIndex + 1)) {
    const topic = String(row?.[topicCol] ?? "").trim();
    if (!topic) continue;

    const presetName = presetNameCol >= 0 ? String(row?.[presetNameCol] ?? "").trim() : "";
    const resolvedTemplateProjectId =
      (presetIdCol >= 0 ? String(row?.[presetIdCol] ?? "").trim() : "") ||
      (presetName ? projectTitleMap.get(normalizeUploadTitle(presetName)) || null : null);

    const openings = openingCols
      .map((col) => (col >= 0 ? String(row?.[col] ?? "").trim() : ""))
      .filter(Boolean);
    const endings = endingCols
      .map((col) => (col >= 0 ? String(row?.[col] ?? "").trim() : ""))
      .filter(Boolean);

    const importedTime = timeCol >= 0 ? parseChannelTimeCell(row?.[timeCol]) : null;
    if (importedTime) importedTimes.add(importedTime);

    importedItems.push({
      id: Math.random().toString(36).slice(2, 10),
      topic,
      template_project_id: resolvedTemplateProjectId,
      target_duration: durationCol >= 0 ? parseDurationSeconds(row?.[durationCol]) : null,
      channel,
      openings,
      endings,
      core_content: coreContentCol >= 0 ? String(row?.[coreContentCol] ?? "").trim() : "",
      episode_number: epCol >= 0 ? parsePositiveInt(row?.[epCol]) : null,
      next_episode_preview: nextPreviewCol >= 0 ? String(row?.[nextPreviewCol] ?? "").trim() : "",
      queued_source: "import",
      queued_at: new Date().toISOString(),
      queued_note: "엑셀 업로드",
    });
  }

  if (importedItems.length === 0) {
    throw new Error("엑셀에서 가져올 주제가 없습니다.");
  }

  return {
    items: normalizeQueueItems(importedItems),
    channelTime: importedTimes.size === 1 ? Array.from(importedTimes)[0] : null,
  };
}

function toQueueErrorMessage(error: unknown, fallback: string): string {
  const raw =
    error instanceof Error
      ? error.message
      : typeof error === "string"
        ? error
        : "";
  const text = raw.trim();
  if (!text) return fallback;
  if (text.includes("script.json 이 없는 깨진 작업입니다")) {
    return "깨진 복구 작업이라 이어서 하기를 막았습니다. 이 항목은 삭제하거나 전체 초기화 후 다시 등록해 주세요.";
  }
  return text;
}

function stepStatus(task: OneClickTask, stepIdx: number): StepState {
  const backendKey = String(BACKEND_STEP_NUMS[stepIdx]);
  if (task.step_states) {
    const val = task.step_states[backendKey];
    if (val === "completed" || val === "done") return "done";
    if (val === "running" || val === "in_progress") return "active";
    if (val === "failed") return "failed";
    if (val === "cancelled") return "failed";
  }
  return "pending";
}

/** 단계별 진행률 (0~100) */
function stepProgress(task: OneClickTask, stepIdx: number): number {
  const st = stepStatus(task, stepIdx);
  if (st === "done") return 100;
  if (st === "pending") return 0;
  if (st === "failed") {
    // 실패 시에도 진행된 만큼 표시
    const bk = String(BACKEND_STEP_NUMS[stepIdx]);
    const done = task.completed_cuts_by_step?.[bk] || 0;
    const total = task.total_cuts || 1;
    if (CUT_BASED_STEPS.has(stepIdx) && total > 0) return Math.round((done / total) * 100);
    return 0;
  }
  // active
  if (CUT_BASED_STEPS.has(stepIdx)) {
    const bk = String(BACKEND_STEP_NUMS[stepIdx]);
    const done = task.completed_cuts_by_step?.[bk] || 0;
    const total = task.total_cuts || 1;
    if (total > 0) return Math.round((done / total) * 100);
  }
  // 렌더/업로드는 0 or 100
  return 0;
}

function ProgressBar({ pct, color = "bg-accent-primary" }: { pct: number; color?: string }) {
  return (
    <div className="w-full h-1.5 bg-gray-700/50 rounded-full overflow-hidden">
      <div
        className={`h-full ${color} rounded-full transition-all duration-1000`}
        style={{ width: `${Math.min(100, pct)}%` }}
      />
    </div>
  );
}

function resolveTemplateProject(projects: Project[], templateProjectId?: string | null): Project | null {
  if (!templateProjectId) return null;
  return projects.find((project) => project.id === templateProjectId) || null;
}

function formatEpisodeTitle(topic?: string | null, episodeNumber?: number | null): string {
  const cleanTopic = String(topic || "").trim();
  if (episodeNumber && episodeNumber > 0) {
    return cleanTopic ? `EP.${episodeNumber} ${cleanTopic}` : `EP.${episodeNumber}`;
  }
  return cleanTopic;
}

function getPresetLabel(project: Project | null): string {
  if (!project) return "기본 설정";
  return project.title || project.topic || project.id;
}

function channelBadgeClass(channel?: number | null): string {
  switch (channel || 1) {
    case 1:
      return "text-blue-400 bg-blue-400/15";
    case 2:
      return "text-green-400 bg-green-400/15";
    case 3:
      return "text-amber-400 bg-amber-400/15";
    case 4:
      return "text-purple-400 bg-purple-400/15";
    default:
      return "text-gray-400 bg-gray-400/15";
  }
}

function QueueMetaBadges({
  channel,
  templateProjectId,
  triggeredBy,
  projects,
  channelPresets,
}: {
  channel?: number | null;
  templateProjectId?: string | null;
  triggeredBy?: "manual" | "schedule";
  projects: Project[];
  channelPresets?: Record<string, string>;
}) {
  const ch = String(channel || 1);
  const channelPresetId = channelPresets?.[ch] || null;
  const usesChannelPreset = !templateProjectId && !!channelPresetId;
  const templateProject = resolveTemplateProject(projects, templateProjectId || channelPresetId);

  return (
    <div className="mt-1 flex items-center gap-1.5 flex-wrap">
      <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${channelBadgeClass(channel)}`}>
        CH{channel || 1}
      </span>
      <span
        className="text-[10px] text-gray-300 bg-bg-secondary/70 border border-border rounded px-1.5 py-0.5 max-w-[220px] truncate"
        title={getPresetLabel(templateProject)}
      >
        {getPresetLabel(templateProject)}
      </span>
      {usesChannelPreset && (
        <span className="text-[10px] text-accent-primary bg-accent-primary/10 border border-accent-primary/30 rounded px-1.5 py-0.5">
          채널 기본
        </span>
      )}
      {triggeredBy && (
        <span className="text-[10px] text-gray-500 bg-bg-primary/80 border border-border rounded px-1.5 py-0.5">
          {triggeredBy === "schedule" ? "스케줄" : "수동"}
        </span>
      )}
    </div>
  );
}

function paginateItems<T>(items: T[], page: number, pageSize = LIST_PAGE_SIZE) {
  const totalPages = Math.max(1, Math.ceil(items.length / pageSize));
  const safePage = Math.min(Math.max(page, 1), totalPages);
  const start = (safePage - 1) * pageSize;
  return {
    page: safePage,
    totalPages,
    items: items.slice(start, start + pageSize),
  };
}

function PaginationControls({
  page,
  totalPages,
  onPageChange,
}: {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}) {
  if (totalPages <= 1) return null;

  return (
    <div className="mt-2 flex items-center justify-end gap-2 text-[11px] text-gray-500">
      <button
        onClick={() => onPageChange(page - 1)}
        disabled={page <= 1}
        className="px-2 py-1 rounded border border-border bg-bg-primary/50 hover:bg-bg-primary disabled:opacity-30 disabled:cursor-not-allowed"
      >
        이전
      </button>
      <span className="font-mono">
        {page} / {totalPages}
      </span>
      <button
        onClick={() => onPageChange(page + 1)}
        disabled={page >= totalPages}
        className="px-2 py-1 rounded border border-border bg-bg-primary/50 hover:bg-bg-primary disabled:opacity-30 disabled:cursor-not-allowed"
      >
        다음
      </button>
    </div>
  );
}

function StepChips({ task }: { task: OneClickTask }) {
  return (
    <div className="flex gap-1 flex-nowrap">
      {STEPS.map((s, i) => {
        const st = stepStatus(task, i);
        return (
          <span
            key={s}
            className={`px-2 py-0.5 rounded text-sm font-medium whitespace-nowrap flex-shrink-0 ${
              st === "done"
                ? "bg-accent-success/15 text-accent-success"
                : st === "active"
                  ? "bg-amber-400/15 text-amber-400 border border-amber-400/40"
                  : st === "failed"
                    ? "bg-accent-danger/10 text-accent-danger"
                    : "bg-bg-primary text-gray-600"
            }`}
          >
            {s}
          </span>
        );
      })}
    </div>
  );
}

export default function QueuePage() {
  const [queue, setQueue] = useState<OneClickQueueItem[]>([]);
  // v1.1.57: 채널별 스케줄 시간
  const [channelTimes, setChannelTimes] = useState<Record<string, string>>({
    "1": "", "2": "", "3": "", "4": "",
  });
  const [channelPresets, setChannelPresets] = useState<Record<string, string>>({
    "1": "", "2": "", "3": "", "4": "",
  });
  const [tasks, setTasks] = useState<OneClickTask[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busyIds, setBusyIds] = useState<Set<string>>(new Set());
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // v1.1.56: 프로젝트 복구
  const [recoverInput, setRecoverInput] = useState("");
  const [recovering, setRecovering] = useState(false);
  // v1.2.6: 채널별 탭 필터 제거 — 채널별 섹션 구조로 전환 (탭 불필요).
  // v1.2.7: 채널 편집 모달 오픈 상태 — null 이면 닫힘. CH1~4 버튼 클릭시 해당 번호.
  const [openChannel, setOpenChannel] = useState<"1" | "2" | "3" | "4" | null>(null);
  // v1.2.9: 주제 편집 팝업(중첩). 어떤 queue index 를 편집하는지. null 이면 닫힘.
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  // v1.2.28: 채널 편집 모달 — 실패 멀티셀렉트 + 고아 프로젝트 섹션
  const [selectedFailed, setSelectedFailed] = useState<Set<string>>(new Set());
  const [selectedOrphans, setSelectedOrphans] = useState<Set<string>>(new Set());
  const [orphans, setOrphans] = useState<OrphanProject[]>([]);
  const [allOrphans, setAllOrphans] = useState<OrphanProject[]>([]);
  const [loadingOrphans, setLoadingOrphans] = useState(false);
  const [loadingAllOrphans, setLoadingAllOrphans] = useState(false);
  const [showAllFailures, setShowAllFailures] = useState(false);
  const [importingExcel, setImportingExcel] = useState(false);
  const [studioUploadedTaskIds, setStudioUploadedTaskIds] = useState<Set<string>>(new Set());
  const studioFailedKeyRef = useRef("");
  const excelInputRef = useRef<HTMLInputElement | null>(null);
  const [listPages, setListPages] = useState<Record<ChannelListPageKey, number>>({
    queue: 1,
    active: 1,
    completed: 1,
    failed: 1,
    orphans: 1,
  });

  const addBusy = (id: string) => setBusyIds((s) => new Set(s).add(id));
  const removeBusy = (id: string) => setBusyIds((s) => { const n = new Set(s); n.delete(id); return n; });

  // v1.1.52: 사용자 편집 중인지 추적 — 폴링이 로컬 변경을 덮어쓰는 것 방지
  const dirtyRef = useRef(false);
  // v1.1.55: save 직후 일정 시간 폴링 덮어쓰기 차단 — save 전에 출발한
  // 폴링 응답이 구 데이터로 덮어쓰는 race condition 방지
  const saveGuardRef = useRef(false);

  const buildChannelPresetPayload = useCallback((): Record<string, string | null> => {
    const cp: Record<string, string | null> = {};
    for (const ch of ["1", "2", "3", "4"]) {
      cp[ch] = (channelPresets[ch] || "").trim() || null;
    }
    return cp;
  }, [channelPresets]);

  const syncUploadedFromStudio = useCallback(async (taskItems: OneClickTask[]) => {
    const failedOnly = taskItems.filter((t) => ["failed", "cancelled", "paused"].includes(t.status));
    if (failedOnly.length === 0) {
      setStudioUploadedTaskIds(new Set());
      return;
    }

    try {
      let pageToken: string | undefined;
      const uploadedTitles: string[] = [];
      for (let i = 0; i < 5; i += 1) {
        const res = await youtubeStudioApi.listVideos({ maxResults: 50, pageToken });
        for (const video of res.items || []) {
          const normalized = normalizeUploadTitle(video.title);
          if (normalized) uploadedTitles.push(normalized);
        }
        if (!res.next_page_token) break;
        pageToken = res.next_page_token;
      }

      const uploadedCounts = new Map<string, number>();
      for (const title of uploadedTitles) {
        uploadedCounts.set(title, (uploadedCounts.get(title) || 0) + 1);
      }

      const failedCounts = new Map<string, number>();
      for (const task of failedOnly) {
        const normalized = normalizeUploadTitle(task.title || task.topic);
        if (!normalized) continue;
        failedCounts.set(normalized, (failedCounts.get(normalized) || 0) + 1);
      }

      const next = new Set<string>();
      for (const task of failedOnly) {
        const normalized = normalizeUploadTitle(task.title || task.topic);
        if (!normalized) continue;
        if ((failedCounts.get(normalized) || 0) !== 1) continue;
        if ((uploadedCounts.get(normalized) || 0) !== 1) continue;
        next.add(task.task_id);
      }
      setStudioUploadedTaskIds(next);
    } catch {
      setStudioUploadedTaskIds(new Set());
    }
  }, []);

  const load = useCallback(async () => {
    try {
      const [q, { tasks: t }, p] = await Promise.all([
        oneclickApi.getQueue(),
        oneclickApi.list(),
        projectsApi.list(),
      ]);
      // v1.1.55: 편집 중(dirty) 이거나 save 직후 보호 기간(saveGuard) 이면
      // 큐 데이터를 서버 데이터로 덮어쓰지 않는다.
      if (!dirtyRef.current && !saveGuardRef.current) {
        setQueue(normalizeQueueItems(q.items || []));
        // v1.1.57: 채널별 시간
        const ct = q.channel_times || {};
        setChannelTimes({ "1": ct["1"] || "", "2": ct["2"] || "", "3": ct["3"] || "", "4": ct["4"] || "" });
        const cp = q.channel_presets || {};
        setChannelPresets({ "1": cp["1"] || "", "2": cp["2"] || "", "3": cp["3"] || "", "4": cp["4"] || "" });
      }
      const nextTasks = t || [];
      setTasks(nextTasks);
      setProjects(p || []);

      const failedKey = nextTasks
        .filter((task) => ["failed", "cancelled", "paused"].includes(task.status))
        .map((task) => task.task_id)
        .sort()
        .join("|");
      if (failedKey !== studioFailedKeyRef.current) {
        studioFailedKeyRef.current = failedKey;
        void syncUploadedFromStudio(nextTasks);
      }
    } catch {
      // ignore polling errors
    }
  }, [syncUploadedFromStudio]);

  // 초기 로드
  useEffect(() => {
    setLoading(true);
    load().finally(() => setLoading(false));
  }, [load]);

  // 진행 중 태스크가 있으면 2초 폴링
  const hasActive = tasks.some((t) => ["prepared", "queued", "running"].includes(t.status));
  useEffect(() => {
    if (hasActive) {
      pollRef.current = setInterval(load, 2000);
    } else {
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [hasActive, load]);

  // 통계
  const activeTasksAll = tasks.filter((t) => ["prepared", "queued", "running"].includes(t.status));
  const persistedCompletedTasksAll = tasks
    .filter((t) => t.status === "completed")
    .sort((a, b) =>
      new Date(b.finished_at || b.created_at).getTime() -
      new Date(a.finished_at || a.created_at).getTime(),
    );
  const rawFailedTasksAll = tasks.filter((t) => t.status === "failed" || t.status === "cancelled" || t.status === "paused");
  const studioCompletedTasks = rawFailedTasksAll.filter((t) => studioUploadedTaskIds.has(t.task_id));
  const completedTasksAll = [...persistedCompletedTasksAll, ...studioCompletedTasks].sort((a, b) =>
    new Date(b.finished_at || b.created_at).getTime() -
    new Date(a.finished_at || a.created_at).getTime(),
  );
  const failedTasksAll = rawFailedTasksAll.filter((t) => !studioUploadedTaskIds.has(t.task_id));
  // v1.2.6: 채널 필터 제거 — 각 채널 섹션 내부에서 필터. *All 원본만 사용.

  useEffect(() => {
    const visibleFailed = new Set(failedTasksAll.map((t) => t.task_id));
    setSelectedFailed((prev) => {
      const next = new Set(Array.from(prev).filter((id) => visibleFailed.has(id)));
      return next.size === prev.size ? prev : next;
    });
  }, [failedTasksAll]);

  // 큐 편집
  const updateItem = (idx: number, patch: Partial<OneClickQueueItem>) => {
    setQueue((prev) => { const n = [...prev]; n[idx] = { ...n[idx], ...patch }; return n; });
    setSaved(false);
    dirtyRef.current = true;  // v1.1.52: 폴링 덮어쓰기 방지
  };
  const removeItem = useCallback(async (idx: number) => {
    const next = queue.filter((_, i) => i !== idx);
    setQueue(next);
    // 즉시 서버 저장
    try {
      const clean = next.map((it) => ({ ...it, topic: (it.topic || "").trim() })).filter((it) => it.topic.length > 0);
      const ct: Record<string, string | null> = {};
      for (const ch of ["1","2","3","4"]) ct[ch] = channelTimes[ch] || null;
      const res = await oneclickApi.setQueue({
        channel_times: ct,
        channel_presets: buildChannelPresetPayload(),
        items: clean,
      });
      setQueue(normalizeQueueItems(res.items || []));
      const cp = res.channel_presets || {};
      setChannelPresets({ "1": cp["1"] || "", "2": cp["2"] || "", "3": cp["3"] || "", "4": cp["4"] || "" });
      setSaved(true);
      dirtyRef.current = false;
      saveGuardRef.current = true;
      setTimeout(() => { saveGuardRef.current = false; }, 6000);
    } catch (e) { setErr((e as Error).message || "삭제 저장 실패"); }
  }, [queue, channelTimes, buildChannelPresetPayload]);
  // v1.2.6: 채널별 섹션에서 호출 — ch 파라미터로 어느 채널에 넣을지 명시.
  // v1.2.9: 새 항목은 에피소드 상세 필드까지 기본값을 채워 생성 후 즉시
  // 편집 팝업을 띄워 사용자에게 주제·대사·핵심을 입력받는다. 반환값으로
  // 추가된 항목의 index 를 돌려줘 호출부가 팝업을 띄울 수 있다.
  const addItemForChannel = (ch: number): number => {
    let newIdx = -1;
    setQueue((prev) => {
      newIdx = prev.length;
      return [
        ...prev,
        {
          id: Math.random().toString(36).slice(2, 10),
          topic: "",
          template_project_id: null,
          target_duration: null,
          channel: ch,
          openings: ["", "", "", "", ""],
          endings: ["", "", "", "", ""],
          core_content: "",
          queued_source: "manual",
          queued_at: new Date().toISOString(),
          queued_note: "제작 큐에서 직접 추가",
        },
      ];
    });
    setSaved(false);
    dirtyRef.current = true;  // 폴링 덮어쓰기 방지
    return newIdx;
  };

  const handleSave = useCallback(async () => {
    const clean = queue.map((it) => ({ ...it, topic: (it.topic || "").trim() })).filter((it) => it.topic.length > 0);
    // v1.1.57: 채널별 시간 검증 + 정규화
    const ct: Record<string, string | null> = {};
    for (const ch of ["1", "2", "3", "4"]) {
      const v = (channelTimes[ch] || "").trim();
      if (!v) { ct[ch] = null; continue; }
      const m = /^(\d{1,2}):(\d{2})$/.exec(v);
      if (!m) { setErr(`채널 ${ch} 시간은 HH:MM 형태로 입력해 주세요.`); return; }
      ct[ch] = `${String(parseInt(m[1])).padStart(2, "0")}:${m[2]}`;
    }
    setSaving(true); setErr(null);
    try {
      const res = await oneclickApi.setQueue({
        channel_times: ct,
        channel_presets: buildChannelPresetPayload(),
        items: clean,
      });
      setQueue(normalizeQueueItems(res.items || []));
      const rct = res.channel_times || {};
      setChannelTimes({ "1": rct["1"] || "", "2": rct["2"] || "", "3": rct["3"] || "", "4": rct["4"] || "" });
      const cp = res.channel_presets || {};
      setChannelPresets({ "1": cp["1"] || "", "2": cp["2"] || "", "3": cp["3"] || "", "4": cp["4"] || "" });
      setSaved(true);
      dirtyRef.current = false;
      // v1.1.57: save 전에 출발한 폴링이 구 데이터로 덮어쓰는 것을 방지.
      // 폴링 주기(2초)보다 충분히 긴 보호 기간을 둔다.
      saveGuardRef.current = true;
      setTimeout(() => { saveGuardRef.current = false; }, 6000);
    } catch (e) { setErr((e as Error).message || "저장 실패"); }
    finally { setSaving(false); }
  }, [queue, channelTimes, buildChannelPresetPayload]);

  const handleExcelImport = useCallback(async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !openChannel) return;

    const channel = parseInt(openChannel, 10);
    setImportingExcel(true);
    setErr(null);
    try {
      const workbook = XLSX.read(await file.arrayBuffer(), {
        type: "array",
        cellDates: true,
      });
      const parsed = parseExcelQueueFile(workbook, channel, projects);

      const nextQueue = [...queue];
      let insertAt = nextQueue.length;
      for (let i = nextQueue.length - 1; i >= 0; i -= 1) {
        if ((nextQueue[i].channel || 1) === channel) {
          insertAt = i + 1;
          break;
        }
      }
      nextQueue.splice(insertAt, 0, ...parsed.items);

      const nextChannelTimes = { ...channelTimes };
      if (parsed.channelTime) {
        nextChannelTimes[openChannel] = parsed.channelTime;
      }

      const clean = nextQueue
        .map((it) => ({ ...it, topic: (it.topic || "").trim() }))
        .filter((it) => it.topic.length > 0);
      const ct: Record<string, string | null> = {};
      for (const ch of ["1", "2", "3", "4"]) {
        const value = (nextChannelTimes[ch] || "").trim();
        if (!value) {
          ct[ch] = null;
          continue;
        }
        const match = /^(\d{1,2}):(\d{2})$/.exec(value);
        if (!match) {
          throw new Error(`채널 ${ch} 시간은 HH:MM 형태로 입력해 주세요.`);
        }
        ct[ch] = `${String(parseInt(match[1], 10)).padStart(2, "0")}:${match[2]}`;
      }

      const res = await oneclickApi.setQueue({
        channel_times: ct,
        channel_presets: buildChannelPresetPayload(),
        items: clean,
      });
      setQueue(normalizeQueueItems(res.items || []));
      const rct = res.channel_times || {};
      setChannelTimes({ "1": rct["1"] || "", "2": rct["2"] || "", "3": rct["3"] || "", "4": rct["4"] || "" });
      const cp = res.channel_presets || {};
      setChannelPresets({ "1": cp["1"] || "", "2": cp["2"] || "", "3": cp["3"] || "", "4": cp["4"] || "" });
      setSaved(true);
      dirtyRef.current = false;
      saveGuardRef.current = true;
      setTimeout(() => { saveGuardRef.current = false; }, 6000);
    } catch (error) {
      setErr((error as Error).message || "엑셀 업로드에 실패했습니다.");
    } finally {
      setImportingExcel(false);
    }
  }, [channelTimes, openChannel, projects, queue, buildChannelPresetPayload]);

  // v1.1.53: 큐 변경 시 자동저장 (2초 디바운스)
  const autoSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (!dirtyRef.current) return;  // 사용자 편집이 아니면 무시
    // v1.1.58: 빈 주제가 있으면 아직 입력 중이므로 자동저장 보류
    const hasEmptyTopic = queue.some((it) => !(it.topic || "").trim());
    if (hasEmptyTopic) return;
    if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current);
    autoSaveTimer.current = setTimeout(() => {
      handleSave();
    }, 2000);
    return () => { if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current); };
  }, [queue, channelTimes, channelPresets, handleSave]);

  // v1.1.58: 실행 전 다른 작업이 진행 중인지 체크
  const checkRunningAndWarn = useCallback(async (): Promise<boolean> => {
    try {
      const { running } = await oneclickApi.getRunning();
      if (running) {
        const remaining = running.estimated_remaining_seconds;
        let msg = `현재 "${running.topic}" 작업이 진행 중입니다 (${Math.round(running.progress_pct)}%).`;
        if (remaining && remaining > 0) {
          const min = Math.ceil(remaining / 60);
          msg += ` 약 ${min}분 후 완료 예정입니다.`;
        }
        msg += " 요청한 작업은 대기열에 추가되어 현재 작업 완료 후 순서대로 실행됩니다.";
        setErr(msg);
        return true;
      }
    } catch { /* 조회 실패 시 그냥 진행 허용 */ }
    return false;
  }, []);

  // 개별 실행: 선택 항목을 해당 채널 맨 앞으로 올린 뒤 실행한다.
  // 진행 중 작업이 있으면 실행 호출은 보류되고, 다음 순번으로 맨 앞에 남는다.
  const handleRunItem = useCallback(async (idx: number) => {
    const item = queue[idx];
    if (!(item.topic || "").trim()) { setErr("주제가 비어 있습니다."); return; }
    const itemId = item.id || String(idx);
    addBusy(itemId);
    setErr(null);
    try {
      const hasRunning = await checkRunningAndWarn();
      const channel = item.channel || 1;
      const selected = {
        ...item,
        topic: item.topic.trim(),
        queued_source: "manual",
        queued_at: new Date().toISOString(),
        queued_note: "제작 큐에서 수동 실행",
      };
      const withoutSelected = queue.filter((_, i) => i !== idx);
      const insertAt = withoutSelected.findIndex((it) => (it.channel || 1) === channel);
      const nextQueue = [...withoutSelected];
      nextQueue.splice(insertAt >= 0 ? insertAt : nextQueue.length, 0, selected);
      const clean = nextQueue
        .map((it) => ({ ...it, topic: (it.topic || "").trim() }))
        .filter((it) => it.topic.length > 0);
      const ct: Record<string, string | null> = {};
      for (const ch of ["1","2","3","4"]) ct[ch] = channelTimes[ch] || null;
      const saved = await oneclickApi.setQueue({
        channel_times: ct,
        channel_presets: buildChannelPresetPayload(),
        items: clean,
      });
      setQueue(normalizeQueueItems(saved.items || []));
      saveGuardRef.current = true;
      setTimeout(() => { saveGuardRef.current = false; }, 6000);
      if (!hasRunning) {
        await oneclickApi.runQueueNext(channel);
      }
      await load();
    } catch (e) { setErr((e as Error).message || "실행 실패"); }
    finally { removeBusy(itemId); }
  }, [queue, channelTimes, load, checkRunningAndWarn, buildChannelPresetPayload]);

  // 지금 1건 실행 (큐 맨 위)
  const handleRunNext = useCallback(async () => {
    if (!queue.some((it) => (it.topic || "").trim())) { setErr("큐에 실행할 주제가 없습니다."); return; }
    void checkRunningAndWarn();
    await handleSave();
    try {
      await oneclickApi.runQueueNext();
      // v1.1.57: 실행 후 큐 보호
      saveGuardRef.current = true;
      setTimeout(() => { saveGuardRef.current = false; }, 6000);
      await load();
    } catch (e) { setErr((e as Error).message || "실행 실패"); }
  }, [queue, handleSave, load, checkRunningAndWarn]);

  // 중지
  const handleCancel = useCallback(async (taskId: string) => {
    addBusy(taskId);
    try {
      await oneclickApi.cancel(taskId);
      await load();
    } catch (e) { setErr((e as Error).message || "중지 실패"); }
    finally { removeBusy(taskId); }
  }, [load]);

  // 이어하기
  const handleResume = useCallback(async (taskId: string) => {
    // v1.1.58: 실행 중 작업 있으면 대기 안내
    void checkRunningAndWarn();
    addBusy(taskId);
    try {
      await oneclickApi.resume(taskId);
      await load();
    } catch (e) {
      setErr(toQueueErrorMessage(e, "이어서 하기 실패"));
      await load();
    }
    finally { removeBusy(taskId); }
  }, [load, checkRunningAndWarn]);

  // v1.1.56: 프로젝트 ID 로 태스크 복구
  const handleRecover = async () => {
    const pid = recoverInput.trim();
    if (!pid) { setErr("프로젝트 ID를 입력해 주세요."); return; }
    setRecovering(true);
    setErr(null);
    try {
      await oneclickApi.recoverProject(pid);
      setRecoverInput("");
      await load();
    } catch (e: any) {
      setErr(e?.message || String(e) || "복구 실패");
    } finally {
      setRecovering(false);
    }
  };

  // 태스크 삭제 (실패/완료된 것)
  const handleDeleteTask = useCallback(async (taskId: string) => {
    addBusy(taskId);
    try {
      await oneclickApi.deleteTask(taskId);
      setTasks((prev) => prev.filter((t) => t.task_id !== taskId));
    } catch (e) { setErr((e as Error).message || "삭제 실패"); }
    finally { removeBusy(taskId); }
  }, []);

  const handleCleanupTasks = useCallback(async (taskIds: string[], label = "실패/취소") => {
    const ids = Array.from(new Set(taskIds.filter(Boolean)));
    if (ids.length === 0) return;
    if (!window.confirm(`${label} ${ids.length}건을 완전히 정리할까요?\n태스크 기록과 남은 프로젝트 파일을 삭제해서 다시 뜨지 않게 합니다.`)) {
      return;
    }
    ids.forEach(addBusy);
    try {
      const res = await oneclickApi.bulkDelete(ids);
      const skipped = Array.isArray(res.skipped) ? res.skipped.length : 0;
      setTasks((prev) => prev.filter((t) => !ids.includes(t.task_id)));
      setSelectedFailed(new Set());
      if (skipped > 0) {
        setErr(`일부 정리 건너뜀: ${skipped}건`);
      } else {
        setErr(null);
      }
      await load();
    } catch (e) {
      setErr((e as Error).message || "정리 실패");
    } finally {
      ids.forEach(removeBusy);
    }
  }, [load]);

  // v1.2.28: 채널 편집 모달 — 고아 프로젝트 조회
  const refreshOrphans = useCallback(async () => {
    if (!openChannel) return;
    const n = parseInt(openChannel);
    setLoadingOrphans(true);
    try {
      const res = await oneclickApi.listOrphanProjects(n);
      setOrphans(res.items || []);
    } catch (e) {
      setErr((e as Error).message || "고아 프로젝트 조회 실패");
    } finally {
      setLoadingOrphans(false);
    }
  }, [openChannel]);

  const refreshAllOrphans = useCallback(async () => {
    setLoadingAllOrphans(true);
    try {
      const res = await oneclickApi.listOrphanProjects();
      setAllOrphans(res.items || []);
    } catch (e) {
      setErr((e as Error).message || "전체 고아 프로젝트 조회 실패");
    } finally {
      setLoadingAllOrphans(false);
    }
  }, []);

  const openAllFailures = useCallback(() => {
    setOpenChannel(null);
    setShowAllFailures(true);
    setSelectedFailed(new Set());
    setSelectedOrphans(new Set());
    setListPages({
      queue: 1,
      active: 1,
      completed: 1,
      failed: 1,
      orphans: 1,
    });
    void refreshAllOrphans();
  }, [refreshAllOrphans]);

  // 모달이 열릴 때 고아 조회 + 선택 상태 초기화. 닫힐 때 목록 비우기.
  useEffect(() => {
    if (openChannel) {
      setShowAllFailures(false);
      setSelectedFailed(new Set());
      setSelectedOrphans(new Set());
      setListPages({
        queue: 1,
        active: 1,
        completed: 1,
        failed: 1,
        orphans: 1,
      });
      refreshOrphans();
    } else {
      setOrphans([]);
    }
  }, [openChannel, refreshOrphans]);

  const updateListPage = useCallback((key: ChannelListPageKey, page: number) => {
    setListPages((prev) => ({
      ...prev,
      [key]: Math.max(1, page),
    }));
  }, []);

  // 선택된 실패 태스크 복구 (requeueTask 를 순차 호출)
  const handleRequeueSelected = useCallback(async () => {
    const ids = Array.from(selectedFailed);
    if (ids.length === 0) return;
    const failedIds: string[] = [];
    for (const id of ids) {
      try {
        await oneclickApi.requeueTask(id);
      } catch (e) {
        failedIds.push(`${id}: ${(e as Error).message}`);
      }
    }
    if (failedIds.length > 0) {
      setErr(`일부 복구 실패 — ${failedIds.join(", ")}`);
    }
    setSelectedFailed(new Set());
    await load();
  }, [selectedFailed, load]);

  // 채널 전체 실패 복구
  const handleRequeueChannelFailed = useCallback(async (ch: number) => {
    try {
      await oneclickApi.requeueChannelFailed(ch);
      setSelectedFailed(new Set());
      await load();
    } catch (e) {
      setErr((e as Error).message || "채널 복구 실패");
    }
  }, [load]);

  // 선택된 고아 프로젝트 복구
  const handleRequeueSelectedOrphans = useCallback(async () => {
    if (!openChannel) return;
    const ids = Array.from(selectedOrphans);
    if (ids.length === 0) return;
    const ch = parseInt(openChannel);
    try {
      await oneclickApi.requeueOrphanProjects(ids, ch);
      setSelectedOrphans(new Set());
      await refreshOrphans();
      await load();
    } catch (e) {
      setErr((e as Error).message || "고아 복구 실패");
    }
  }, [openChannel, selectedOrphans, load, refreshOrphans]);

  const handleRequeueSelectedAllOrphans = useCallback(async () => {
    const ids = Array.from(selectedOrphans);
    if (ids.length === 0) return;
    try {
      await oneclickApi.requeueOrphanProjects(ids, null);
      setSelectedOrphans(new Set());
      await refreshAllOrphans();
      await load();
    } catch (e) {
      setErr((e as Error).message || "고아 복구 실패");
    }
  }, [selectedOrphans, load, refreshAllOrphans]);

  // 해당 채널 맨 위 1건 즉시 실행
  const handleRunChannelNext = useCallback(async (ch: number) => {
    void checkRunningAndWarn();
    try {
      await oneclickApi.runQueueNext(ch);
      await load();
    } catch (e) {
      setErr((e as Error).message || "실행 실패");
    }
  }, [load, checkRunningAndWarn]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 size={20} className="animate-spin text-gray-500" />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-5">
      {/* 헤더 — v1.2.5: 상단 액션 버튼 4종 제거 (저장 / 지금 실행 / 주제 추가 / 큐 비우기).
          저장은 수정 시 자동/다른 흐름으로, 실행은 스케줄(스케줄 탭)로 일임.
          주제 추가 UI 는 별도 위치에서 제공 예정 — 이 페이지는 "보는" 화면. */}
      <div className="flex items-center">
        <h1 className="text-2xl font-bold text-white">제작 큐</h1>
      </div>

      {/* 통계 카드 — v1.2.6: 탭 제거 → 전체 기준 카운트 */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: "전체 대기", value: queue.length, color: "text-blue-400" },
          { label: "진행 중", value: activeTasksAll.length, color: "text-amber-400" },
          { label: "완료", value: completedTasksAll.length, color: "text-accent-success" },
          { label: "실패", value: failedTasksAll.length, color: "text-accent-danger", onClick: openAllFailures },
        ].map((s) => {
          const CardTag = s.onClick ? "button" : "div";
          return (
            <CardTag
              key={s.label}
              type={s.onClick ? "button" : undefined}
              onClick={s.onClick}
              className={`bg-bg-secondary border border-border rounded-xl p-4 text-center ${
                s.onClick ? "hover:border-accent-danger/60 transition-colors cursor-pointer" : ""
              }`}
              title={s.onClick ? "전체 실패/고아 항목 보기" : undefined}
            >
              <div className={`text-2xl font-bold ${s.color}`}>{s.value}</div>
              <div className="text-sm text-gray-500 mt-1">{s.label}</div>
            </CardTag>
          );
        })}
      </div>

      {/* v1.2.5: 채널별 매일 자동 실행 시간 블록 제거 — "스케줄" 탭에 동일 UI 존재. */}

      {/* 에러 / 대기 안내 */}
      {err && (
        <div className={`flex items-center gap-2 text-sm rounded-lg px-4 py-2.5 ${
          err.includes("기다려 주세요")
            ? "text-amber-400 bg-amber-400/10 border border-amber-400/30"
            : "text-accent-danger bg-accent-danger/10 border border-accent-danger/30"
        }`}>
          {err.includes("기다려 주세요") ? <Clock size={14} /> : <AlertCircle size={14} />}
          <span>{err}</span>
          <button onClick={() => setErr(null)} className="ml-auto"><X size={12} /></button>
        </div>
      )}

      {/* v1.1.56: 프로젝트 복구 */}
      <div className="flex items-center gap-2">
        <input
          value={recoverInput}
          onChange={(e) => setRecoverInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleRecover()}
          placeholder="프로젝트 ID로 태스크 복구 (예: 딸깍_비키니의_비하인드_스토리_260414-1)"
          className="flex-1 text-sm bg-bg-secondary text-gray-200 border border-border rounded-lg px-4 py-2.5 outline-none placeholder:text-gray-600 focus:border-accent-primary/50"
        />
        <button
          onClick={() => { handleRecover(); }}
          disabled={recovering}
          className="flex items-center gap-1.5 text-sm font-semibold bg-amber-400/15 text-amber-400 border border-amber-400/30 rounded-lg px-4 py-2.5 hover:bg-amber-400/25 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {recovering ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
          복구
        </button>
      </div>



      {/* v1.2.7: CH 1~4 를 큰 버튼 그리드로. 클릭시 해당 채널 편집 모달 오픈. */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {(["1", "2", "3", "4"] as const).map((ch) => {
          const n = parseInt(ch);
          const chActive = activeTasksAll.filter((t) => (t.channel || 1) === n);
          const chFailed = failedTasksAll.filter((t) => (t.channel || 1) === n);
          const chCompleted = completedTasksAll.filter((t) => (t.channel || 1) === n);
          const chQueue = queue.filter((q) => (q.channel || 1) === n);
          const total = chActive.length + chFailed.length + chCompleted.length + chQueue.length;
          const autoTime = channelTimes[ch] || "";
          const channelPreset = resolveTemplateProject(projects, channelPresets[ch] || null);
          const theme =
            n === 1 ? { badge: "bg-blue-500/20 text-blue-400 border-blue-500/40", ring: "hover:border-blue-500/60", text: "text-blue-400" } :
            n === 2 ? { badge: "bg-green-500/20 text-green-400 border-green-500/40", ring: "hover:border-green-500/60", text: "text-green-400" } :
            n === 3 ? { badge: "bg-amber-500/20 text-amber-400 border-amber-500/40", ring: "hover:border-amber-500/60", text: "text-amber-400" } :
                      { badge: "bg-purple-500/20 text-purple-400 border-purple-500/40", ring: "hover:border-purple-500/60", text: "text-purple-400" };
          return (
            <button
              key={ch}
              type="button"
              onClick={() => setOpenChannel(ch)}
              className={`group text-left bg-bg-secondary border border-border ${theme.ring} rounded-xl p-5 transition-colors`}
            >
              <div className="flex items-start gap-3">
                <span className={`text-lg font-bold px-3 py-1.5 rounded-lg border ${theme.badge}`}>
                  CH {ch}
                </span>
                <div className="flex flex-wrap items-center gap-2 pt-1">
                  <span className="text-base text-gray-300">총 {total}건</span>
                  <span className="text-xs font-semibold px-2 py-1 rounded-md bg-blue-500/10 text-blue-400 border border-blue-500/20">
                    대기 {chQueue.length}
                  </span>
                  <span className="text-xs font-semibold px-2 py-1 rounded-md bg-accent-success/10 text-accent-success border border-accent-success/20">
                    완료 {chCompleted.length}
                  </span>
                  <span className="text-xs font-semibold px-2 py-1 rounded-md bg-accent-danger/10 text-accent-danger border border-accent-danger/20">
                    실패 {chFailed.length}
                  </span>
                </div>
                <div className="flex-1" />
                <ChevronRight size={20} className="text-gray-500 group-hover:text-gray-300 transition-colors" />
              </div>

              <div className="mt-4 grid grid-cols-4 gap-2">
                <div className="bg-bg-primary/50 rounded-lg px-3 py-2 text-center">
                  <div className="text-xl font-bold text-blue-400">{chQueue.length}</div>
                  <div className="text-sm text-gray-500 mt-0.5">대기</div>
                </div>
                <div className="bg-bg-primary/50 rounded-lg px-3 py-2 text-center">
                  <div className="text-xl font-bold text-amber-400">{chActive.length}</div>
                  <div className="text-sm text-gray-500 mt-0.5">진행</div>
                </div>
                <div className="bg-bg-primary/50 rounded-lg px-3 py-2 text-center">
                  <div className="text-xl font-bold text-accent-success">{chCompleted.length}</div>
                  <div className="text-sm text-gray-500 mt-0.5">완료</div>
                </div>
                <div className="bg-bg-primary/50 rounded-lg px-3 py-2 text-center">
                  <div className="text-xl font-bold text-accent-danger">{chFailed.length}</div>
                  <div className="text-sm text-gray-500 mt-0.5">실패</div>
                </div>
              </div>

              <div className="mt-3 flex items-center gap-2 text-sm">
                <Calendar size={14} className="text-gray-500" />
                {autoTime ? (
                  <span className="text-gray-300">매일 <span className={`font-mono font-semibold ${theme.text}`}>{autoTime}</span> 자동 실행</span>
                ) : (
                  <span className="text-gray-600">자동 실행 시간 미설정</span>
                )}
              </div>
              <div className="mt-1 text-sm text-gray-500 truncate" title={getPresetLabel(channelPreset)}>
                프리셋: <span className={theme.text}>{getPresetLabel(channelPreset)}</span>
              </div>
            </button>
          );
        })}
      </div>

      {/* v1.2.28: 채널 편집 모달 — 자동실행 시간 + 대기/진행/완료/실패 목록 + 고아 프로젝트 섹션. */}
      {openChannel && (() => {
        const n = parseInt(openChannel);
        const chQueue = queue
          .map((q, i) => ({ q, i }))
          .filter(({ q }) => (q.channel || 1) === n);
        const chActive = activeTasksAll.filter((t) => (t.channel || 1) === n);
        const chCompleted = completedTasksAll.filter((t) => (t.channel || 1) === n);
        const chFailed = failedTasksAll.filter((t) => (t.channel || 1) === n);
        const queuePage = paginateItems(chQueue, listPages.queue);
        const activePage = paginateItems(chActive, listPages.active);
        const completedPage = paginateItems(chCompleted, listPages.completed);
        const failedPage = paginateItems(chFailed, listPages.failed);
        const orphanPage = paginateItems(orphans, listPages.orphans);
        const allFailedIds = chFailed.map((t) => t.task_id);
        const selectedFailedCount = allFailedIds.filter((id) => selectedFailed.has(id)).length;
        const allFailedSelected =
          allFailedIds.length > 0 && allFailedIds.every((id) => selectedFailed.has(id));
        const allOrphanIds = orphans.map((o) => o.project_id);
        const selectedOrphanCount = allOrphanIds.filter((id) => selectedOrphans.has(id)).length;
        const allOrphanSelected =
          allOrphanIds.length > 0 && allOrphanIds.every((id) => selectedOrphans.has(id));
        const chTheme =
          n === 1 ? "text-blue-400" :
          n === 2 ? "text-green-400" :
          n === 3 ? "text-amber-400" :
                    "text-purple-400";
        const currentChannelPreset = resolveTemplateProject(projects, channelPresets[openChannel] || null);
        return (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
            <div className="bg-bg-secondary border border-border rounded-xl w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
              {/* 헤더 */}
              <div className="flex items-center gap-3 px-5 py-4 border-b border-border">
                <h2 className={`text-lg font-bold ${chTheme}`}>CH {openChannel} 편집</h2>
                <span className="text-sm text-gray-500">
                  대기 {chQueue.length} · 진행 {chActive.length} · 완료 {chCompleted.length} · 실패 {chFailed.length}
                </span>
                <div className="flex-1" />
                <div className="flex items-center gap-2 min-w-[300px]">
                  <span className="text-sm text-gray-500 whitespace-nowrap">채널 프리셋</span>
                  <select
                    value={channelPresets[openChannel] || ""}
                    onChange={(e) => {
                      const value = e.target.value;
                      setChannelPresets((prev) => ({ ...prev, [openChannel]: value }));
                      dirtyRef.current = true;
                      setSaved(false);
                    }}
                    className="flex-1 text-sm bg-bg-primary text-gray-200 border border-border rounded-lg px-3 py-2 outline-none focus:border-accent-primary/50"
                    title={getPresetLabel(currentChannelPreset)}
                  >
                    <option value="">기본 설정</option>
                    {projects.map((project) => (
                      <option key={project.id} value={project.id}>
                        {project.title || project.topic || project.id}
                      </option>
                    ))}
                  </select>
                </div>
                <button
                  onClick={() => setOpenChannel(null)}
                  className="text-gray-400 hover:text-gray-200 transition-colors"
                  aria-label="닫기"
                >
                  <X size={18} />
                </button>
              </div>

              <div className="px-5 py-4 overflow-y-auto space-y-5">
                {/* 자동 실행 시간 + 즉시 실행 */}
                <section>
                  <div className="flex items-center gap-2 mb-2">
                    <Calendar size={14} className="text-gray-500" />
                    <span className="text-sm font-semibold text-gray-300">매일 자동 실행 시간</span>
                    <span className="text-[11px] text-gray-600">저장은 자동(2초 후)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={channelTimes[openChannel] || ""}
                      onChange={(e) => {
                        const v = e.target.value;
                        setChannelTimes((prev) => ({ ...prev, [openChannel]: v }));
                        dirtyRef.current = true;
                        setSaved(false);
                      }}
                      placeholder="HH:MM (예: 07:00), 비우면 미설정"
                      className="flex-1 text-sm bg-bg-primary text-gray-200 border border-border rounded-lg px-3 py-2 outline-none focus:border-accent-primary/50 font-mono"
                    />
                    <button
                      onClick={() => handleRunChannelNext(n)}
                      className="text-sm bg-accent-primary/15 text-accent-primary border border-accent-primary/40 rounded-lg px-3 py-2 hover:bg-accent-primary/25 transition-colors flex items-center gap-1.5 flex-shrink-0"
                    >
                      <Play size={12} /> 맨 위 1건 실행
                    </button>
                  </div>
                  <input
                    ref={excelInputRef}
                    type="file"
                    accept=".xlsx,.xls,.csv,.tsv"
                    onChange={handleExcelImport}
                    className="hidden"
                  />
                  <div className="flex items-center gap-2 flex-wrap mt-2">
                    <button
                      onClick={() => excelInputRef.current?.click()}
                      disabled={importingExcel}
                      className="text-sm bg-blue-400/10 text-blue-400 border border-blue-400/30 rounded-lg px-3 py-2 hover:bg-blue-400/20 transition-colors flex items-center gap-1.5 disabled:opacity-40"
                    >
                      {importingExcel ? (
                        <Loader2 size={12} className="animate-spin" />
                      ) : (
                        <Upload size={12} />
                      )}
                      엑셀 업로드
                    </button>
                    <a
                      href={oneclickApi.queueTemplateUrl()}
                      target="_blank"
                      rel="noreferrer"
                      className="text-sm bg-bg-primary/60 text-gray-300 border border-border rounded-lg px-3 py-2 hover:bg-bg-primary transition-colors flex items-center gap-1.5"
                    >
                      <Download size={12} />
                      템플릿
                    </a>
                    <span className="text-[11px] text-gray-600">
                      `에피소드번호` / `주제` / `핵심내용` / `오프닝1~5` / `엔딩1~5` 형식을 읽습니다. 시간 열이 있으면 채널 시간도 같이 반영합니다.
                    </span>
                  </div>
                  <div className="text-[11px] text-gray-500 mt-2">
                    개별 항목 프리셋이 비어 있으면 <span className={chTheme}>{getPresetLabel(currentChannelPreset)}</span> 프리셋 파이프라인으로 실행됩니다.
                  </div>
                </section>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                  {/* 왼쪽: 대기 + 진행 + 완료 */}
                  <div className="space-y-4">
                    {/* 대기 */}
                    <section>
                      <div className="text-sm font-semibold text-blue-400 mb-2">
                        대기 {chQueue.length}건
                      </div>
                      {chQueue.length === 0 ? (
                        <div className="text-xs text-gray-600 italic">대기 항목 없음</div>
                      ) : (
                        <>
                          <ul className="space-y-1.5">
                            {queuePage.items.map(({ q, i }) => {
                              const itemKey = q.id || String(i);
                              return (
                                <li
                                  key={itemKey}
                                  className="flex items-start gap-2 bg-bg-primary/40 border border-border rounded-lg px-2.5 py-1.5"
                                >
                                  <div className="flex-1 min-w-0">
                                    <span
                                      className="block text-sm text-gray-200 truncate"
                                      title={formatEpisodeTitle(q.topic, q.episode_number)}
                                    >
                                      {formatEpisodeTitle(q.topic, q.episode_number) || (
                                        <em className="text-gray-600">(주제 미입력)</em>
                                      )}
                                    </span>
                                    <QueueMetaBadges
                                      channel={q.channel}
                                      templateProjectId={q.template_project_id}
                                      projects={projects}
                                      channelPresets={channelPresets}
                                    />
                                  </div>
                                  <button
                                    onClick={() => handleRunItem(i)}
                                    disabled={busyIds.has(itemKey)}
                                    className="text-[11px] bg-accent-primary/15 text-accent-primary rounded px-2 py-1 hover:bg-accent-primary/25 disabled:opacity-40 flex items-center gap-1"
                                  >
                                    {busyIds.has(itemKey) ? (
                                      <Loader2 size={10} className="animate-spin" />
                                    ) : (
                                      <Play size={10} />
                                    )}
                                    실행
                                  </button>
                                  <button
                                    onClick={() => removeItem(i)}
                                    className="text-gray-500 hover:text-accent-danger"
                                    aria-label="삭제"
                                  >
                                    <Trash2 size={12} />
                                  </button>
                                </li>
                              );
                            })}
                          </ul>
                          <PaginationControls
                            page={queuePage.page}
                            totalPages={queuePage.totalPages}
                            onPageChange={(page) => updateListPage("queue", page)}
                          />
                        </>
                      )}
                    </section>

                    {/* 진행 */}
                    <section>
                      <div className="text-sm font-semibold text-amber-400 mb-2">
                        진행 {chActive.length}건
                      </div>
                      {chActive.length === 0 ? (
                        <div className="text-xs text-gray-600 italic">진행 중 항목 없음</div>
                      ) : (
                        <>
                          <ul className="space-y-1.5">
                            {activePage.items.map((t) => (
                              <li
                                key={t.task_id}
                                className="bg-bg-primary/40 border border-border rounded-lg px-2.5 py-1.5 space-y-1"
                              >
                                <div className="flex items-start gap-2">
                                  <div className="flex-1 min-w-0">
                                    <span
                                      className="block text-sm text-gray-200 truncate"
                                      title={formatEpisodeTitle(t.topic, t.episode_number)}
                                    >
                                      {formatEpisodeTitle(t.topic, t.episode_number)}
                                    </span>
                                    <QueueMetaBadges
                                      channel={t.channel}
                                      templateProjectId={t.template_project_id}
                                      triggeredBy={t.triggered_by}
                                      projects={projects}
                                      channelPresets={channelPresets}
                                    />
                                  </div>
                                  <button
                                    onClick={() => handleCancel(t.task_id)}
                                    disabled={busyIds.has(t.task_id)}
                                    className="text-[11px] bg-accent-danger/15 text-accent-danger rounded px-2 py-1 hover:bg-accent-danger/25 disabled:opacity-40 flex items-center gap-1"
                                    title={t.topic}
                                  >
                                    <Square size={10} /> 중지
                                  </button>
                                </div>
                                <ProgressBar pct={t.progress_pct || 0} />
                              </li>
                            ))}
                          </ul>
                          <PaginationControls
                            page={activePage.page}
                            totalPages={activePage.totalPages}
                            onPageChange={(page) => updateListPage("active", page)}
                          />
                        </>
                      )}
                    </section>

                    {/* 완료 */}
                    <section>
                      <div className="text-sm font-semibold text-accent-success mb-2">
                        완료 {chCompleted.length}건
                      </div>
                      {chCompleted.length === 0 ? (
                        <div className="text-xs text-gray-600 italic">완료 항목 없음</div>
                      ) : (
                        <>
                          <ul className="space-y-1">
                            {completedPage.items.map((t) => (
                              <li
                                key={t.task_id}
                                className="flex items-start gap-2 text-xs text-gray-400 bg-bg-primary/30 rounded px-2 py-1"
                              >
                                <CheckCircle2
                                  size={10}
                                  className="text-accent-success flex-shrink-0 mt-0.5"
                                />
                                <div className="flex-1 min-w-0">
                                  <span className="block truncate" title={formatEpisodeTitle(t.topic, t.episode_number)}>
                                    {formatEpisodeTitle(t.topic, t.episode_number)}
                                  </span>
                                  <QueueMetaBadges
                                    channel={t.channel}
                                    templateProjectId={t.template_project_id}
                                    triggeredBy={t.triggered_by}
                                    projects={projects}
                                    channelPresets={channelPresets}
                                  />
                                </div>
                                <button
                                  onClick={() => handleDeleteTask(t.task_id)}
                                  className="text-gray-600 hover:text-accent-danger"
                                  aria-label="삭제"
                                >
                                  <Trash2 size={10} />
                                </button>
                              </li>
                            ))}
                          </ul>
                          <PaginationControls
                            page={completedPage.page}
                            totalPages={completedPage.totalPages}
                            onPageChange={(page) => updateListPage("completed", page)}
                          />
                        </>
                      )}
                    </section>
                  </div>

                  {/* 오른쪽: 실패 + 고아 */}
                  <div className="space-y-4">
                    {/* 실패 / 취소 / 일시중지 */}
                    <section>
                      <div className="flex items-center gap-2 mb-2 flex-wrap">
                        <span className="text-sm font-semibold text-accent-danger">
                          실패/취소 {chFailed.length}건
                        </span>
                        {chFailed.length > 0 && (
                          <>
                            <button
                              onClick={() => {
                                if (allFailedSelected) setSelectedFailed(new Set());
                                else setSelectedFailed(new Set(allFailedIds));
                              }}
                              className="text-[11px] text-gray-400 hover:text-gray-200 underline"
                            >
                              {allFailedSelected ? "전체 해제" : "전체 선택"}
                            </button>
                            <div className="flex-1" />
                            <button
                              onClick={handleRequeueSelected}
                              disabled={selectedFailedCount === 0}
                              className="text-[11px] bg-amber-400/15 text-amber-400 border border-amber-400/40 rounded px-2 py-1 hover:bg-amber-400/25 disabled:opacity-30 flex items-center gap-1"
                            >
                              <RefreshCw size={10} />
                              선택 {selectedFailedCount}건 복구
                            </button>
                            <button
                              onClick={() => handleCleanupTasks(
                                allFailedIds.filter((id) => selectedFailed.has(id)),
                                `CH${n} 선택 실패/취소`
                              )}
                              disabled={selectedFailedCount === 0}
                              className="text-[11px] bg-red-500/10 text-red-300 border border-red-400/30 rounded px-2 py-1 hover:bg-red-500/20 disabled:opacity-30 flex items-center gap-1"
                            >
                              <Trash2 size={10} />
                              선택 정리
                            </button>
                            <button
                              onClick={() => handleRequeueChannelFailed(n)}
                              className="text-[11px] bg-amber-400/10 text-amber-400/90 border border-amber-400/30 rounded px-2 py-1 hover:bg-amber-400/20"
                            >
                              전체 복구
                            </button>
                            <button
                              onClick={() => handleCleanupTasks(allFailedIds, `CH${n} 실패/취소 전체`)}
                              className="text-[11px] bg-red-500/10 text-red-300 border border-red-400/30 rounded px-2 py-1 hover:bg-red-500/20 flex items-center gap-1"
                            >
                              <Trash2 size={10} />
                              전체 정리
                            </button>
                          </>
                        )}
                      </div>
                      {chFailed.length === 0 ? (
                        <div className="text-xs text-gray-600 italic">실패 항목 없음</div>
                      ) : (
                        <>
                          <ul className="space-y-1.5">
                            {failedPage.items.map((t) => (
                              <li
                                key={t.task_id}
                                className="flex items-start gap-2 bg-bg-primary/40 border border-border rounded-lg px-2.5 py-1.5"
                              >
                                <input
                                  type="checkbox"
                                  checked={selectedFailed.has(t.task_id)}
                                  onChange={(e) => {
                                    setSelectedFailed((s) => {
                                      const next = new Set(s);
                                      if (e.target.checked) next.add(t.task_id);
                                      else next.delete(t.task_id);
                                      return next;
                                    });
                                  }}
                                  className="accent-amber-400 flex-shrink-0"
                                />
                                <div className="flex-1 min-w-0">
                                  <span
                                    className="block text-sm text-gray-200 truncate"
                                    title={`${t.topic}${t.error ? ` — ${t.error}` : ""}`}
                                  >
                                    {formatEpisodeTitle(t.topic, t.episode_number)}
                                  </span>
                                  <QueueMetaBadges
                                    channel={t.channel}
                                    templateProjectId={t.template_project_id}
                                    triggeredBy={t.triggered_by}
                                    projects={projects}
                                    channelPresets={channelPresets}
                                  />
                                </div>
                                <button
                                  onClick={() => handleResume(t.task_id)}
                                  disabled={busyIds.has(t.task_id)}
                                  className="text-[11px] text-amber-400 hover:underline disabled:opacity-40"
                                >
                                  이어하기
                                </button>
                                <button
                                  onClick={() => handleDeleteTask(t.task_id)}
                                  className="text-gray-500 hover:text-accent-danger"
                                  aria-label="삭제"
                                >
                                  <Trash2 size={12} />
                                </button>
                              </li>
                            ))}
                          </ul>
                          <PaginationControls
                            page={failedPage.page}
                            totalPages={failedPage.totalPages}
                            onPageChange={(page) => updateListPage("failed", page)}
                          />
                        </>
                      )}
                    </section>

                    {/* 고아 프로젝트 (v1.2.28) */}
                    <section>
                      <div className="flex items-center gap-2 mb-2 flex-wrap">
                        <span className="text-sm font-semibold text-gray-300">
                          고아 프로젝트 {orphans.length}건
                        </span>
                        <button
                          onClick={refreshOrphans}
                          disabled={loadingOrphans}
                          className="text-gray-500 hover:text-gray-300 disabled:opacity-40"
                          aria-label="새로고침"
                        >
                          {loadingOrphans ? (
                            <Loader2 size={11} className="animate-spin" />
                          ) : (
                            <RefreshCw size={11} />
                          )}
                        </button>
                        {orphans.length > 0 && (
                          <>
                            <button
                              onClick={() => {
                                if (allOrphanSelected) setSelectedOrphans(new Set());
                                else setSelectedOrphans(new Set(allOrphanIds));
                              }}
                              className="text-[11px] text-gray-400 hover:text-gray-200 underline"
                            >
                              {allOrphanSelected ? "전체 해제" : "전체 선택"}
                            </button>
                            <div className="flex-1" />
                            <button
                              onClick={handleRequeueSelectedOrphans}
                              disabled={selectedOrphanCount === 0}
                              className="text-[11px] bg-amber-400/15 text-amber-400 border border-amber-400/40 rounded px-2 py-1 hover:bg-amber-400/25 disabled:opacity-30 flex items-center gap-1"
                            >
                              <RefreshCw size={10} />
                              선택 {selectedOrphanCount}건 복구
                            </button>
                          </>
                        )}
                      </div>
                      {loadingOrphans ? (
                        <div className="text-xs text-gray-500 flex items-center gap-1">
                          <Loader2 size={11} className="animate-spin" /> 조회 중...
                        </div>
                      ) : orphans.length === 0 ? (
                        <div className="text-xs text-gray-600 italic">
                          고아 프로젝트 없음 (태스크 목록과 DB/디스크가 일치)
                        </div>
                      ) : (
                        <>
                          <ul className="space-y-1.5">
                            {orphanPage.items.map((o) => {
                              const mb = (o.progress.disk_bytes / 1024 / 1024).toFixed(1);
                              return (
                                <li
                                  key={o.project_id}
                                  className="flex items-center gap-2 bg-bg-primary/40 border border-border rounded-lg px-2.5 py-1.5"
                                >
                                  <input
                                    type="checkbox"
                                    checked={selectedOrphans.has(o.project_id)}
                                    onChange={(e) => {
                                      setSelectedOrphans((s) => {
                                        const next = new Set(s);
                                        if (e.target.checked) next.add(o.project_id);
                                        else next.delete(o.project_id);
                                        return next;
                                      });
                                    }}
                                    className="accent-amber-400 flex-shrink-0"
                                  />
                                  <span className="flex-1 min-w-0">
                                    <span
                                      className="block text-sm text-gray-200 truncate"
                                      title={o.topic || o.project_id}
                                    >
                                      {o.unattributed && (
                                        <span className="text-[10px] text-amber-400 mr-1">
                                          ⚠ 미지정
                                        </span>
                                      )}
                                      {o.episode_number ? (
                                        <span className="text-[10px] text-gray-500 mr-1">
                                          EP.{o.episode_number}
                                        </span>
                                      ) : null}
                                      {o.topic || o.project_id}
                                    </span>
                                    <span
                                      className="block text-[10px] text-gray-500 font-mono truncate"
                                      title={o.project_id}
                                    >
                                      {o.project_id} · {mb}MB
                                    </span>
                                  </span>
                                </li>
                              );
                            })}
                          </ul>
                          <PaginationControls
                            page={orphanPage.page}
                            totalPages={orphanPage.totalPages}
                            onPageChange={(page) => updateListPage("orphans", page)}
                          />
                        </>
                      )}
                      {orphans.length > 0 && (
                        <div className="text-[10px] text-gray-600 mt-1">
                          ※ 복구 시 프로젝트 폴더가 삭제되고 CH {openChannel} 큐 맨 뒤에 재등록됩니다.
                        </div>
                      )}
                    </section>
                  </div>
                </div>
              </div>
            </div>
          </div>
        );
      })()}

      {showAllFailures && (() => {
        const failedPage = paginateItems(failedTasksAll, listPages.failed);
        const orphanPage = paginateItems(allOrphans, listPages.orphans);
        const allFailedIds = failedTasksAll.map((t) => t.task_id);
        const selectedFailedCount = allFailedIds.filter((id) => selectedFailed.has(id)).length;
        const allFailedSelected =
          allFailedIds.length > 0 && allFailedIds.every((id) => selectedFailed.has(id));
        const allOrphanIds = allOrphans.map((o) => o.project_id);
        const selectedOrphanCount = allOrphanIds.filter((id) => selectedOrphans.has(id)).length;
        const allOrphanSelected =
          allOrphanIds.length > 0 && allOrphanIds.every((id) => selectedOrphans.has(id));

        return (
          <div className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm flex items-center justify-center p-6">
            <div className="w-full max-w-5xl max-h-[86vh] bg-bg-secondary border border-border rounded-xl shadow-2xl overflow-hidden flex flex-col">
              <div className="flex items-center gap-3 px-5 py-4 border-b border-border">
                <h2 className="text-lg font-bold text-accent-danger">전체 실패/고아</h2>
                <span className="text-sm text-gray-500">
                  실패 {failedTasksAll.length} · 고아 {allOrphans.length}
                </span>
                <button
                  onClick={refreshAllOrphans}
                  disabled={loadingAllOrphans}
                  className="text-gray-500 hover:text-gray-300 disabled:opacity-40"
                  aria-label="새로고침"
                >
                  {loadingAllOrphans ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : (
                    <RefreshCw size={13} />
                  )}
                </button>
                <div className="flex-1" />
                <button
                  onClick={() => {
                    setShowAllFailures(false);
                    setAllOrphans([]);
                    setSelectedFailed(new Set());
                    setSelectedOrphans(new Set());
                  }}
                  className="text-gray-400 hover:text-gray-200 transition-colors"
                  aria-label="닫기"
                >
                  <X size={18} />
                </button>
              </div>

              <div className="px-5 py-4 overflow-y-auto grid grid-cols-1 md:grid-cols-2 gap-5">
                <section>
                  <div className="flex items-center gap-2 mb-2 flex-wrap">
                    <span className="text-sm font-semibold text-accent-danger">
                      실패/취소 {failedTasksAll.length}건
                    </span>
                    {failedTasksAll.length > 0 && (
                      <>
                        <button
                          onClick={() => {
                            if (allFailedSelected) setSelectedFailed(new Set());
                            else setSelectedFailed(new Set(allFailedIds));
                          }}
                          className="text-[11px] text-gray-400 hover:text-gray-200 underline"
                        >
                          {allFailedSelected ? "전체 해제" : "전체 선택"}
                        </button>
                        <div className="flex-1" />
                        <button
                          onClick={handleRequeueSelected}
                          disabled={selectedFailedCount === 0}
                          className="text-[11px] bg-amber-400/15 text-amber-400 border border-amber-400/40 rounded px-2 py-1 hover:bg-amber-400/25 disabled:opacity-30 flex items-center gap-1"
                        >
                          <RefreshCw size={10} />
                          선택 {selectedFailedCount}건 복구
                        </button>
                        <button
                          onClick={() => handleCleanupTasks(
                            allFailedIds.filter((id) => selectedFailed.has(id)),
                            "선택 실패/취소"
                          )}
                          disabled={selectedFailedCount === 0}
                          className="text-[11px] bg-red-500/10 text-red-300 border border-red-400/30 rounded px-2 py-1 hover:bg-red-500/20 disabled:opacity-30 flex items-center gap-1"
                        >
                          <Trash2 size={10} />
                          선택 정리
                        </button>
                        <button
                          onClick={() => handleCleanupTasks(allFailedIds, "전체 실패/취소")}
                          className="text-[11px] bg-red-500/10 text-red-300 border border-red-400/30 rounded px-2 py-1 hover:bg-red-500/20 flex items-center gap-1"
                        >
                          <Trash2 size={10} />
                          전체 정리
                        </button>
                      </>
                    )}
                  </div>
                  {failedTasksAll.length === 0 ? (
                    <div className="text-xs text-gray-600 italic">실패 항목 없음</div>
                  ) : (
                    <>
                      <ul className="space-y-1.5">
                        {failedPage.items.map((t) => (
                          <li
                            key={t.task_id}
                            className="flex items-start gap-2 bg-bg-primary/40 border border-border rounded-lg px-2.5 py-1.5"
                          >
                            <input
                              type="checkbox"
                              checked={selectedFailed.has(t.task_id)}
                              onChange={(e) => {
                                setSelectedFailed((s) => {
                                  const next = new Set(s);
                                  if (e.target.checked) next.add(t.task_id);
                                  else next.delete(t.task_id);
                                  return next;
                                });
                              }}
                              className="accent-amber-400 flex-shrink-0"
                            />
                            <div className="flex-1 min-w-0">
                              <span
                                className="block text-sm text-gray-200 truncate"
                                title={`${t.topic}${t.error ? ` — ${t.error}` : ""}`}
                              >
                                {formatEpisodeTitle(t.topic, t.episode_number)}
                              </span>
                              <QueueMetaBadges
                                channel={t.channel}
                                templateProjectId={t.template_project_id}
                                triggeredBy={t.triggered_by}
                                projects={projects}
                                channelPresets={channelPresets}
                              />
                            </div>
                            <button
                              onClick={() => handleResume(t.task_id)}
                              disabled={busyIds.has(t.task_id)}
                              className="text-[11px] text-amber-400 hover:underline disabled:opacity-40"
                            >
                              이어하기
                            </button>
                            <button
                              onClick={() => handleDeleteTask(t.task_id)}
                              className="text-gray-500 hover:text-accent-danger"
                              aria-label="삭제"
                            >
                              <Trash2 size={12} />
                            </button>
                          </li>
                        ))}
                      </ul>
                      <PaginationControls
                        page={failedPage.page}
                        totalPages={failedPage.totalPages}
                        onPageChange={(page) => updateListPage("failed", page)}
                      />
                    </>
                  )}
                </section>

                <section>
                  <div className="flex items-center gap-2 mb-2 flex-wrap">
                    <span className="text-sm font-semibold text-gray-300">
                      고아 프로젝트 {allOrphans.length}건
                    </span>
                    {allOrphans.length > 0 && (
                      <>
                        <button
                          onClick={() => {
                            if (allOrphanSelected) setSelectedOrphans(new Set());
                            else setSelectedOrphans(new Set(allOrphanIds));
                          }}
                          className="text-[11px] text-gray-400 hover:text-gray-200 underline"
                        >
                          {allOrphanSelected ? "전체 해제" : "전체 선택"}
                        </button>
                        <div className="flex-1" />
                        <button
                          onClick={handleRequeueSelectedAllOrphans}
                          disabled={selectedOrphanCount === 0}
                          className="text-[11px] bg-amber-400/15 text-amber-400 border border-amber-400/40 rounded px-2 py-1 hover:bg-amber-400/25 disabled:opacity-30 flex items-center gap-1"
                        >
                          <RefreshCw size={10} />
                          선택 {selectedOrphanCount}건 복구
                        </button>
                      </>
                    )}
                  </div>
                  {loadingAllOrphans ? (
                    <div className="text-xs text-gray-500 flex items-center gap-1">
                      <Loader2 size={11} className="animate-spin" /> 조회 중...
                    </div>
                  ) : allOrphans.length === 0 ? (
                    <div className="text-xs text-gray-600 italic">고아 프로젝트 없음</div>
                  ) : (
                    <>
                      <ul className="space-y-1.5">
                        {orphanPage.items.map((o) => {
                          const mb = (o.progress.disk_bytes / 1024 / 1024).toFixed(1);
                          return (
                            <li
                              key={o.project_id}
                              className="flex items-center gap-2 bg-bg-primary/40 border border-border rounded-lg px-2.5 py-1.5"
                            >
                              <input
                                type="checkbox"
                                checked={selectedOrphans.has(o.project_id)}
                                onChange={(e) => {
                                  setSelectedOrphans((s) => {
                                    const next = new Set(s);
                                    if (e.target.checked) next.add(o.project_id);
                                    else next.delete(o.project_id);
                                    return next;
                                  });
                                }}
                                className="accent-amber-400 flex-shrink-0"
                              />
                              <span className="flex-1 min-w-0">
                                <span
                                  className="block text-sm text-gray-200 truncate"
                                  title={o.topic || o.project_id}
                                >
                                  <span className="text-[10px] text-gray-500 mr-1">CH{o.channel}</span>
                                  {o.unattributed && (
                                    <span className="text-[10px] text-amber-400 mr-1">미지정</span>
                                  )}
                                  {o.episode_number ? (
                                    <span className="text-[10px] text-gray-500 mr-1">
                                      EP.{o.episode_number}
                                    </span>
                                  ) : null}
                                  {o.topic || o.project_id}
                                </span>
                                <span
                                  className="block text-[10px] text-gray-500 font-mono truncate"
                                  title={o.project_id}
                                >
                                  {o.project_id} · {mb}MB
                                </span>
                              </span>
                            </li>
                          );
                        })}
                      </ul>
                      <PaginationControls
                        page={orphanPage.page}
                        totalPages={orphanPage.totalPages}
                        onPageChange={(page) => updateListPage("orphans", page)}
                      />
                    </>
                  )}
                </section>
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  );
}
