import type { OneClickTask } from "@/lib/api";

export const STEPS = [
  { key: "2", label: "스크립트", modelKey: "script" as const },
  { key: "3", label: "음성", modelKey: "tts" as const },
  { key: "4", label: "이미지", modelKey: "image" as const },
  { key: "5", label: "영상", modelKey: "video" as const },
  { key: "6", label: "렌더", modelKey: null },
  { key: "7", label: "업로드", modelKey: null },
] as const;

export const STEP_ORDER = ["2", "3", "4", "5", "6", "7"] as const;

const FAILURE_STEP_LABELS: Record<string, string> = {
  "2": "대본 생성",
  "3": "음성 생성",
  "4": "이미지 생성",
  "5": "영상 생성",
  "6": "최종 렌더링",
  "7": "유튜브 업로드",
};

export function getTaskFailureStepName(task: OneClickTask): string {
  if (task.current_step_name) return task.current_step_name;
  const failedStep = STEP_ORDER.find((key) => {
    const state = task.step_states?.[key];
    return state === "failed" || state === "cancelled";
  });
  return failedStep ? FAILURE_STEP_LABELS[failedStep] : "알 수 없음";
}

export function getStepState(
  task: OneClickTask | null,
  stepKey: string,
): "done" | "active" | "pending" | "failed" {
  if (!task) return "pending";

  const stepStates = task.step_states || {};
  const val = stepStates[stepKey];
  if (val === "completed" || val === "done") return "done";
  if (val === "running" || val === "in_progress") return "active";
  if (val === "failed" || val === "cancelled") return "failed";

  const stepOrder = ["2", "3", "4", "5", "6", "7"];
  const highestCompletedIndex = stepOrder.reduce((acc, key, index) => {
    const state = stepStates[key];
    return state === "completed" || state === "done" ? index : acc;
  }, -1);

  if (
    highestCompletedIndex >= 0 &&
    stepOrder.indexOf(stepKey) <= highestCompletedIndex
  ) {
    return "done";
  }

  return "pending";
}

export function inferLiveStepKey(task: OneClickTask | null): string | null {
  if (!task || task.status !== "running") return null;

  const cuts = task.completed_cuts_by_step || {};
  const text = [
    task.current_step_name || "",
    task.current_step_label || "",
    task.current_step_progress_text || "",
    task.sub_status || "",
    ...(task.logs || []).slice(-6).map((log) => log?.msg || ""),
  ].join(" ");

  if (/youtube|upload/i.test(text)) return "7";
  if (/final_with_subtitles|post[-_\s]?process|mux|render/i.test(text)) return "6";
  if (/ffmpeg|\.mp4|video/i.test(text)) return "5";
  if (/comfyui|ksampler|saveimage|dreamshaper|\.png|cut_\d+/i.test(text)) return "4";
  if (/elevenlabs|tts|audio|\.mp3/i.test(text)) return "3";

  const current = task.current_step ? String(task.current_step) : null;
  if ((current === "2" || !current) && Number(cuts["5"] || 0) > 0) return "5";
  if ((current === "2" || !current) && Number(cuts["4"] || 0) > 0) return "4";
  if ((current === "2" || !current) && Number(cuts["3"] || 0) > 0) return "3";
  return current;
}

export function getEffectiveStepStates(task: OneClickTask | null): Record<string, string> {
  const states = { ...(task?.step_states || {}) };
  const activeKey = inferLiveStepKey(task);
  if (!task || !activeKey) return states;

  for (const key of STEP_ORDER) {
    if (key === activeKey) break;
    if (states[key] !== "failed" && states[key] !== "cancelled") {
      states[key] = "completed";
    }
  }

  if (states[activeKey] !== "completed") {
    states[activeKey] = "running";
  }

  for (const key of STEP_ORDER.slice(STEP_ORDER.indexOf(activeKey as any) + 1)) {
    if (states[key] === "running") states[key] = "pending";
  }

  return states;
}

export function getEffectiveTask(task: OneClickTask | null): OneClickTask | null {
  if (!task) return null;
  const activeKey = inferLiveStepKey(task);
  if (!activeKey) return task;
  const text = `${task.current_step_progress_text || ""} ${task.sub_status || ""}`;
  const cutMatch = text.match(/(?:cut|컷|ì»·)?\s*(\d+)\s*\/\s*(\d+)/i);
  const stepLabel = STEPS.find((step) => step.key === activeKey)?.label || task.current_step_name;
  const hasCutProgress = ["3", "4", "5"].includes(activeKey);
  const completed = Number(task.completed_cuts_by_step?.[activeKey] || 0);
  const parsedCut = cutMatch ? Number(cutMatch[1]) : 0;
  const parsedTotal = cutMatch ? Number(cutMatch[2]) : 0;
  return {
    ...task,
    current_step: Number(activeKey),
    current_step_name: stepLabel || task.current_step_name,
    current_step_label: stepLabel || task.current_step_label,
    current_step_completed: hasCutProgress
      ? Math.max(completed, parsedCut || 0)
      : task.current_step_completed,
    current_step_total: hasCutProgress
      ? parsedTotal || task.total_cuts || task.current_step_total
      : task.current_step_total,
    step_states: getEffectiveStepStates(task),
  };
}
