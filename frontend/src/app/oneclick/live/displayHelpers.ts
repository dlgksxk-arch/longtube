import type { OneClickTask } from "@/lib/api";
import { withEpisodeTitle } from "./queueHelpers";

export interface LogEntry {
  time: string;
  msg: string;
  level: "info" | "success" | "warn" | "error" | "muted";
}

type ServerLogEntry = NonNullable<OneClickTask["logs"]>[number];

export const timeValue = (value?: string | null) => {
  if (!value) return 0;
  const parsed = new Date(value).getTime();
  return Number.isFinite(parsed) ? parsed : 0;
};

export const isUploadRecoverableTask = (task: OneClickTask) => {
  const states = task.step_states || {};
  return states["6"] === "completed" && states["7"] !== "completed";
};

export function serverLogToEntry(log: ServerLogEntry): LogEntry {
  return {
    time: log.ts || "",
    msg: log.msg,
    level:
      log.level === "error"
        ? "error"
        : log.level === "warn"
          ? "warn"
          : "info",
  };
}

export function isConsoleProgressLog(log: ServerLogEntry | LogEntry): boolean {
  const msg = String(log?.msg || "");
  return /ComfyUI\s+진행:\s*KSampler/i.test(msg);
}

export function taskLogsToEntries(task: OneClickTask | null): LogEntry[] {
  return (task?.logs || [])
    .filter((log) => !isConsoleProgressLog(log))
    .map(serverLogToEntry);
}

export function taskTitle(item: OneClickTask) {
  return withEpisodeTitle(item.topic || item.title, item.episode_number);
}

export function compactSeconds(sec: number | null | undefined) {
  if (typeof sec !== "number" || !Number.isFinite(sec) || sec < 0) return "00:00:00";
  const safe = Math.floor(sec);
  const hh = Math.floor(safe / 3600);
  const mm = Math.floor((safe % 3600) / 60);
  const ss = safe % 60;
  return `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
}

export function stepApiName(stepKey: string, task?: OneClickTask | null) {
  const model = task?.models || {};
  const estimatedModel: Partial<NonNullable<OneClickTask["estimate"]>["models_used"]> =
    task?.estimate?.models_used || {};
  if (stepKey === "2") {
    const script = String(model.script || estimatedModel.script || "").toLowerCase();
    if (script.includes("gpt") || script.includes("openai")) return "OpenAI";
    if (script.includes("xai") || script.includes("grok")) return "xAI";
    return "Anthropic";
  }
  if (stepKey === "3") {
    const tts = String(model.tts || estimatedModel.tts || "").toLowerCase();
    if (tts.includes("openai")) return "OpenAI";
    return "ElevenLabs";
  }
  if (stepKey === "4") {
    const image = String(model.image || estimatedModel.image || "").toLowerCase();
    if (image.includes("comfy")) return "ComfyUI";
    if (image.includes("openai")) return "OpenAI";
    if (image.includes("grok")) return "xAI";
    if (image.includes("fal")) return "fal.ai";
    return "ComfyUI";
  }
  if (stepKey === "5") {
    const video = String(model.video || estimatedModel.video || "").toLowerCase();
    if (video.includes("ffmpeg")) return "FFmpeg";
    if (video.includes("comfy")) return "ComfyUI";
    if (video.includes("fal")) return "fal.ai";
    if (video.includes("kling")) return "Kling";
    return "FFmpeg";
  }
  return "Local";
}

export function stepModelName(stepKey: string, task?: OneClickTask | null) {
  const model = task?.models || {};
  const estimatedModel: Partial<NonNullable<OneClickTask["estimate"]>["models_used"]> =
    task?.estimate?.models_used || {};
  if (stepKey === "2") {
    const script = String(model.script || estimatedModel.script || "").trim();
    return script.replace(/^Claude\s+/i, "").replace(/^Anthropic\s*\|\s*/i, "");
  }
  if (stepKey === "3") return model.tts_voice || model.tts || estimatedModel.tts || "";
  if (stepKey === "4") {
    const image = String(model.image || estimatedModel.image || "").trim();
    const names: Record<string, string> = {
      "comfyui-dreamshaper-xl": "SDXL Lightning",
      "comfyui-dreamshaper-xl-longtube": "SDXL 로컬모델 v1",
      "openai-image-1": "GPT Image 1 (gpt-image-1)",
      "openai-image-2": "OpenAI Image 2 (gpt-image-2)",
      "nano-banana-3": "Nano Banana 3 (Reference style lock)",
      "nano-banana-2": "Nano Banana 2",
      "nano-banana-pro": "Nano Banana Pro",
    };
    return names[image] || image.replace(/^DreamShaper XL/i, "SDXL");
  }
  if (stepKey === "5") {
    const video = String(model.video || estimatedModel.video || "").trim();
    const names: Record<string, string> = {
      "ffmpeg-static": "FFmpeg Static (no motion)",
      "ffmpeg-safe-motion": "숏츠",
      "seedance-lite": "Seedance 1.0 Lite",
    };
    return names[video] || video;
  }
  return "";
}

export function stepTargetText(stepKey: string, task?: OneClickTask | null) {
  if (!task) return "0 / 0";
  const total = Math.max(0, Number(task.total_cuts || task.current_step_total || 0));
  const done = Math.max(0, Number(task.completed_cuts_by_step?.[stepKey] || 0));
  if (stepKey === "2") {
    const text = `${task.current_step_progress_text || ""} ${task.sub_status || ""}`;
    const chunk = text.match(/chunk\s*(\d+)\s*\/\s*(\d+)/i);
    if (chunk) return `chunk ${chunk[1]} / ${chunk[2]}`;
    return task.current_step === 2 ? "chunk 1 / 3" : "chunk 0 / 3";
  }
  if (["3", "4", "5"].includes(stepKey)) return `${done} / ${total || 120}`;
  return task.step_states?.[stepKey] === "completed" ? "완료" : "대기";
}

export function taskProgressHeartbeat(task: OneClickTask | null | undefined) {
  if (!task) return "";
  return [
    task.status || "",
    task.current_step ?? "",
    task.current_step_name || "",
    task.current_step_completed ?? "",
    task.current_step_total ?? "",
    task.current_step_cut_progress_pct ?? "",
    task.progress_pct ?? "",
    task.sub_status || "",
    task.logs?.length || 0,
  ].join("|");
}
