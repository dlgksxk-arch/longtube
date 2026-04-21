"use client";

/**
 * v1.1.50 — 딸깍 대시보드 > 제작 큐
 * - 대기 행: 개별 실행 / 삭제
 * - 진행 행: 게이지 바 + 중지 버튼
 * - 실패/취소 행: 이어하기 / 삭제
 * - 2초 폴링으로 진행 상태 업데이트 (페이지 떠나도 백엔드 계속 진행)
 */
import { useCallback, useEffect, useRef, useState } from "react";
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
} from "lucide-react";
import {
  oneclickApi,
  projectsApi,
  type OneClickTask,
  type OneClickQueueItem,
  type Project,
} from "@/lib/api";
import { formatDurationKo } from "@/lib/format";

const STEPS = ["스크립트", "음성", "이미지", "영상", "렌더", "업로드"] as const;
// 백엔드 step_states 키는 "2"~"7" (숫자 문자열), 프론트 STEPS 인덱스는 0~5
const BACKEND_STEP_NUMS = [2, 3, 4, 5, 6, 7]; // STEPS[0]=step2, STEPS[1]=step3, ...
// 컷 기반 단계인지 (스크립트/음성/이미지/영상 = 인덱스 0~3)
const CUT_BASED_STEPS = new Set([0, 1, 2, 3]);

type StepState = "done" | "active" | "pending" | "failed";

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

function StepChips({ task }: { task: OneClickTask }) {
  return (
    <div className="flex gap-1">
      {STEPS.map((s, i) => {
        const st = stepStatus(task, i);
        return (
          <span
            key={s}
            className={`px-2 py-0.5 rounded text-[10px] font-medium ${
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
  // v1.1.67: 채널별 탭 필터 — 'all' | '1' | '2' | '3' | '4'
  const [channelFilter, setChannelFilter] = useState<"all" | "1" | "2" | "3" | "4">("all");

  const addBusy = (id: string) => setBusyIds((s) => new Set(s).add(id));
  const removeBusy = (id: string) => setBusyIds((s) => { const n = new Set(s); n.delete(id); return n; });

  // v1.1.52: 사용자 편집 중인지 추적 — 폴링이 로컬 변경을 덮어쓰는 것 방지
  const dirtyRef = useRef(false);
  // v1.1.55: save 직후 일정 시간 폴링 덮어쓰기 차단 — save 전에 출발한
  // 폴링 응답이 구 데이터로 덮어쓰는 race condition 방지
  const saveGuardRef = useRef(false);

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
        setQueue(
          (q.items || []).map((it) => ({
            ...it,
            id: it.id || Math.random().toString(36).slice(2, 10),
            channel: it.channel || 1,
          })),
        );
        // v1.1.57: 채널별 시간
        const ct = q.channel_times || {};
        setChannelTimes({ "1": ct["1"] || "", "2": ct["2"] || "", "3": ct["3"] || "", "4": ct["4"] || "" });
      }
      setTasks(t || []);
      setProjects(p || []);
    } catch {
      // ignore polling errors
    }
  }, []);

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
  const completedTasksAll = tasks
    .filter((t) => t.status === "completed")
    .sort((a, b) =>
      new Date(b.finished_at || b.created_at).getTime() -
      new Date(a.finished_at || a.created_at).getTime(),
    );
  const failedTasksAll = tasks.filter((t) => t.status === "failed" || t.status === "cancelled" || t.status === "paused");

  // v1.1.67: 채널 필터 적용본 — 탭 선택에 따라 필터. 'all' 은 그대로 통과.
  const matchesCh = (ch: number | undefined | null) =>
    channelFilter === "all" ? true : (ch || 1) === parseInt(channelFilter);
  const activeTasks = activeTasksAll.filter((t) => matchesCh(t.channel));
  const completedTasks = completedTasksAll.filter((t) => matchesCh(t.channel));
  const failedTasks = failedTasksAll.filter((t) => matchesCh(t.channel));
  const filteredQueue = queue.filter((q) => matchesCh(q.channel));

  // v1.1.67: 각 채널별 건수(탭 배지용). 'all' 은 전체 합.
  const countForCh = (ch: "all" | "1" | "2" | "3" | "4") => {
    if (ch === "all") {
      return activeTasksAll.length + failedTasksAll.length + completedTasksAll.length + queue.length;
    }
    const n = parseInt(ch);
    return (
      activeTasksAll.filter((t) => (t.channel || 1) === n).length +
      failedTasksAll.filter((t) => (t.channel || 1) === n).length +
      completedTasksAll.filter((t) => (t.channel || 1) === n).length +
      queue.filter((q) => (q.channel || 1) === n).length
    );
  };

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
      const res = await oneclickApi.setQueue({ channel_times: ct, items: clean });
      setQueue((res.items || []).map((it) => ({ ...it, id: it.id || Math.random().toString(36).slice(2, 10), channel: it.channel || 1 })));
      setSaved(true);
      dirtyRef.current = false;
      saveGuardRef.current = true;
      setTimeout(() => { saveGuardRef.current = false; }, 6000);
    } catch (e) { setErr((e as Error).message || "삭제 저장 실패"); }
  }, [queue, channelTimes]);
  const addItem = () => {
    // v1.1.68: 현재 선택된 채널 탭에 주제 추가. '전체' 탭일 때만 기본 CH1.
    const newChannel = channelFilter === "all" ? 1 : parseInt(channelFilter);
    setQueue((prev) => [
      ...prev,
      { id: Math.random().toString(36).slice(2, 10), topic: "", template_project_id: null, target_duration: null, channel: newChannel },
    ]);
    setSaved(false);
    dirtyRef.current = true;  // v1.1.52: 폴링 덮어쓰기 방지
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
      const res = await oneclickApi.setQueue({ channel_times: ct, items: clean });
      setQueue((res.items || []).map((it) => ({ ...it, id: it.id || Math.random().toString(36).slice(2, 10), channel: it.channel || 1 })));
      const rct = res.channel_times || {};
      setChannelTimes({ "1": rct["1"] || "", "2": rct["2"] || "", "3": rct["3"] || "", "4": rct["4"] || "" });
      setSaved(true);
      dirtyRef.current = false;
      // v1.1.57: save 전에 출발한 폴링이 구 데이터로 덮어쓰는 것을 방지.
      // 폴링 주기(2초)보다 충분히 긴 보호 기간을 둔다.
      saveGuardRef.current = true;
      setTimeout(() => { saveGuardRef.current = false; }, 6000);
    } catch (e) { setErr((e as Error).message || "저장 실패"); }
    finally { setSaving(false); }
  }, [queue, channelTimes]);

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
  }, [queue, channelTimes, handleSave]);

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
        msg += " 완료 후 자동으로 실행되니 잠시만 기다려 주세요.";
        setErr(msg);
        return true; // 실행 중 — 차단
      }
    } catch { /* 조회 실패 시 그냥 진행 허용 */ }
    return false;
  }, []);

  // 개별 실행 (큐 항목 → prepare → start → 큐에서 제거 후 서버 저장)
  const handleRunItem = useCallback(async (idx: number) => {
    const item = queue[idx];
    if (!(item.topic || "").trim()) { setErr("주제가 비어 있습니다."); return; }
    // v1.1.58: 실행 중인 작업이 있으면 대기 안내
    if (await checkRunningAndWarn()) return;
    const itemId = item.id || String(idx);
    addBusy(itemId);
    setErr(null);
    try {
      // prepare → start
      const prepared = await oneclickApi.prepare({
        topic: item.topic.trim(),
        template_project_id: item.template_project_id || undefined,
        target_duration: item.target_duration || undefined,
      });
      await oneclickApi.start(prepared.task_id);
      // 큐에서 제거 + 서버 저장
      const remaining = queue.filter((_, i) => i !== idx);
      const clean = remaining.map((it) => ({ ...it, topic: (it.topic || "").trim() })).filter((it) => it.topic.length > 0);
      const ct: Record<string, string | null> = {};
      for (const ch of ["1","2","3","4"]) ct[ch] = channelTimes[ch] || null;
      await oneclickApi.setQueue({ channel_times: ct, items: clean });
      setQueue(remaining);
      // v1.1.57: 실행 후 load() 가 큐를 덮어쓰지 않도록 보호
      saveGuardRef.current = true;
      setTimeout(() => { saveGuardRef.current = false; }, 6000);
      await load();
    } catch (e) { setErr((e as Error).message || "실행 실패"); }
    finally { removeBusy(itemId); }
  }, [queue, channelTimes, load, checkRunningAndWarn]);

  // 지금 1건 실행 (큐 맨 위)
  const handleRunNext = useCallback(async () => {
    if (!queue.some((it) => (it.topic || "").trim())) { setErr("큐에 실행할 주제가 없습니다."); return; }
    // v1.1.58: 실행 중인 작업이 있으면 대기 안내
    if (await checkRunningAndWarn()) return;
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
    if (await checkRunningAndWarn()) return;
    addBusy(taskId);
    try {
      await oneclickApi.resume(taskId);
      await load();
    } catch (e) { setErr((e as Error).message || "이어서 하기 실패"); }
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

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 size={20} className="animate-spin text-gray-500" />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-5">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">제작 큐</h1>
        <div className="flex items-center gap-3">
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-1.5 text-xs bg-bg-secondary border border-border text-gray-200 rounded-lg px-3 py-2 hover:bg-bg-tertiary disabled:opacity-40 transition-colors"
          >
            {saving ? <Loader2 size={12} className="animate-spin" /> : saved ? <Check size={12} className="text-accent-success" /> : <Save size={12} />}
            {saved ? "저장됨" : "저장"}
          </button>
          <button
            onClick={handleRunNext}
            disabled={saving || activeTasksAll.length > 0 || queue.length === 0}
            className="flex items-center gap-1.5 text-xs font-semibold bg-accent-primary hover:bg-purple-600 text-white rounded-lg px-4 py-2 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <Play size={12} /> 지금 1건 실행
          </button>
          <button
            onClick={addItem}
            className="flex items-center gap-1.5 text-xs font-semibold bg-accent-success/15 text-accent-success border border-accent-success/30 rounded-lg px-4 py-2 hover:bg-accent-success/25 transition-colors"
          >
            <Plus size={12} /> 주제 추가
          </button>
          {queue.length > 0 && (
            <button
              onClick={async () => {
                setQueue([]);
                try {
                  const ct: Record<string, string | null> = {};
                  for (const ch of ["1","2","3","4"]) ct[ch] = channelTimes[ch] || null;
                  await oneclickApi.setQueue({ channel_times: ct, items: [] });
                  setSaved(true);
                  dirtyRef.current = false;
                } catch (e) { setErr((e as Error).message || "비우기 실패"); }
              }}
              className="flex items-center gap-1.5 text-xs text-gray-400 border border-border rounded-lg px-3 py-2 hover:text-accent-danger hover:border-accent-danger/40 hover:bg-accent-danger/5 transition-colors"
            >
              <Trash2 size={12} /> 큐 비우기
            </button>
          )}
        </div>
      </div>

      {/* 통계 카드 — v1.1.67: 탭에 따라 해당 채널만 카운트 */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: channelFilter === "all" ? "전체 대기" : `CH ${channelFilter} 대기`, value: filteredQueue.length, color: "text-blue-400" },
          { label: "진행 중", value: activeTasks.length, color: "text-amber-400" },
          { label: "완료", value: completedTasks.length, color: "text-accent-success" },
          { label: "실패", value: failedTasks.length, color: "text-accent-danger" },
        ].map((s) => (
          <div key={s.label} className="bg-bg-secondary border border-border rounded-xl p-4 text-center">
            <div className={`text-2xl font-bold ${s.color}`}>{s.value}</div>
            <div className="text-xs text-gray-500 mt-1">{s.label}</div>
          </div>
        ))}
      </div>

      {/* v1.1.57: 채널별 매일 자동 실행 시간 */}
      <div className="bg-bg-secondary border border-border rounded-xl p-4">
        <div className="text-xs font-semibold text-gray-400 mb-3">채널별 매일 자동 실행 시간</div>
        <div className="grid grid-cols-4 gap-3">
          {(["1","2","3","4"] as const).map((ch) => (
            <div key={ch} className="flex items-center gap-2">
              <span className={`text-xs font-bold px-2 py-0.5 rounded ${
                ch === "1" ? "bg-blue-500/20 text-blue-400" :
                ch === "2" ? "bg-green-500/20 text-green-400" :
                ch === "3" ? "bg-amber-500/20 text-amber-400" :
                "bg-purple-500/20 text-purple-400"
              }`}>CH {ch}</span>
              <input
                value={channelTimes[ch] || ""}
                onChange={(e) => {
                  setChannelTimes((prev) => ({ ...prev, [ch]: e.target.value }));
                  setSaved(false);
                  dirtyRef.current = true;
                }}
                placeholder="HH:MM"
                className="flex-1 text-sm bg-bg-primary text-gray-200 border border-border rounded px-2.5 py-1.5 outline-none placeholder:text-gray-600 focus:border-accent-primary/50 w-20"
              />
            </div>
          ))}
        </div>
        <p className="text-[10px] text-gray-600 mt-2">비워두면 해당 채널 자동 실행 꺼짐</p>
      </div>

      {/* 에러 / 대기 안내 */}
      {err && (
        <div className={`flex items-center gap-2 text-xs rounded-lg px-4 py-2.5 ${
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
          className="flex items-center gap-1.5 text-xs font-semibold bg-amber-400/15 text-amber-400 border border-amber-400/30 rounded-lg px-4 py-2.5 hover:bg-amber-400/25 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {recovering ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
          복구
        </button>
      </div>

      {/* 큐 테이블 */}
      <div className="bg-bg-secondary border border-border rounded-xl overflow-hidden">
        {/* 헤더 */}
        {/* v1.1.67: 채널별 탭 필터 — 전체/CH1~4. 각 탭에 건수 배지 표시. */}
        <div className="flex items-center gap-1 px-3 py-2 border-b border-border bg-bg-primary/30 overflow-x-auto">
          {(["all", "1", "2", "3", "4"] as const).map((ch) => {
            const isActive = channelFilter === ch;
            const label = ch === "all" ? "전체" : `CH ${ch}`;
            const count = countForCh(ch);
            const chColor =
              ch === "1"
                ? "text-blue-400 border-blue-500/40 bg-blue-500/10"
                : ch === "2"
                  ? "text-green-400 border-green-500/40 bg-green-500/10"
                  : ch === "3"
                    ? "text-amber-400 border-amber-500/40 bg-amber-500/10"
                    : ch === "4"
                      ? "text-purple-400 border-purple-500/40 bg-purple-500/10"
                      : "text-gray-300 border-border bg-bg-tertiary";
            return (
              <button
                key={ch}
                onClick={() => setChannelFilter(ch)}
                className={`flex items-center gap-1.5 text-xs font-semibold rounded-md px-3 py-1.5 border transition-colors ${
                  isActive
                    ? `${chColor} ring-1 ring-accent-primary`
                    : "text-gray-500 border-transparent hover:text-gray-300 hover:bg-bg-tertiary/50"
                }`}
              >
                <span>{label}</span>
                <span
                  className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                    isActive ? "bg-black/30" : "bg-bg-primary text-gray-600"
                  }`}
                >
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        <div className="flex items-center px-4 py-3 text-[11px] font-semibold text-gray-500 uppercase tracking-wider border-b border-border">
          <span className="w-8 shrink-0">#</span>
          <span className="flex-1 min-w-0">주제</span>
          <span className="hidden md:block w-[260px] shrink-0">단계 진행</span>
          <span className="w-16 shrink-0 text-center">진행률</span>
          <span className="w-[140px] shrink-0 text-center">액션</span>
        </div>

        {filteredQueue.length === 0 && activeTasks.length === 0 && failedTasks.length === 0 && completedTasks.length === 0 ? (
          <div className="text-center text-sm text-gray-500 py-16">
            {channelFilter === "all"
              ? "큐가 비어 있습니다. \"주제 추가\" 버튼으로 시작하세요."
              : `CH ${channelFilter} 에 항목이 없습니다.`}
          </div>
        ) : (
          <>
            {/* ── 진행 중 태스크 ── */}
            {activeTasks.map((t) => {
              // v1.1.55: 큐 항목과 동일한 채널/프리셋 칩 표시
              const ch = t.channel || 0;
              const tmpl = t.template_project_id
                ? projects.find((p) => p.id === t.template_project_id)
                : null;
              const tmplLabel = tmpl ? (tmpl.title || tmpl.topic || tmpl.id) : "기본 설정";
              const chColor =
                ch === 1 ? "bg-blue-500/20 text-blue-400" :
                ch === 2 ? "bg-green-500/20 text-green-400" :
                ch === 3 ? "bg-amber-500/20 text-amber-400" :
                ch === 4 ? "bg-purple-500/20 text-purple-400" :
                "bg-gray-500/20 text-gray-400";
              return (
              <div key={t.task_id} className="border-b border-border/50 bg-accent-primary/[0.03]">
                {/* 상단: 제목 + 전체 % + 중지 */}
                <div className="flex items-center px-4 pt-3 pb-2">
                  <span className="w-8 shrink-0"><Zap size={14} className="text-accent-primary" /></span>
                  <div className="flex-1 min-w-0 pr-3">
                    <span className="text-sm font-medium text-white truncate block">{t.topic || t.title}</span>
                    <div className="flex items-center gap-2 mt-1">
                      {ch > 0 && (
                        <span className={`text-[10px] font-bold rounded px-1.5 py-0.5 ${chColor}`}>
                          CH {ch}
                        </span>
                      )}
                      <span className="text-[10px] text-gray-500 truncate">{tmplLabel}</span>
                      {t.triggered_by === "schedule" && (
                        <span className="text-[10px] text-gray-600">· 스케줄</span>
                      )}
                    </div>
                  </div>
                  <span className="text-sm font-bold text-amber-400 mr-3">{Math.round(t.progress_pct)}%</span>
                  <button
                    onClick={() => handleCancel(t.task_id)}
                    disabled={busyIds.has(t.task_id)}
                    className="flex items-center gap-1 px-3 py-1.5 rounded text-[11px] font-medium text-accent-danger bg-accent-danger/10 border border-accent-danger/30 hover:bg-accent-danger/20 transition-colors disabled:opacity-50"
                  >
                    {busyIds.has(t.task_id) ? <Loader2 size={12} className="animate-spin" /> : <Square size={12} />}
                    중지
                  </button>
                </div>
                {/* 단계별 개별 프로그레스 */}
                <div className="px-4 pl-12 pb-3 grid grid-cols-6 gap-2">
                  {STEPS.map((s, i) => {
                    const st = stepStatus(t, i);
                    const pct = stepProgress(t, i);
                    const bk = String(BACKEND_STEP_NUMS[i]);
                    const cuts = t.completed_cuts_by_step?.[bk] || 0;
                    const total = t.total_cuts || 0;
                    const isActive = st === "active";
                    const isDone = st === "done";
                    const isFailed = st === "failed";
                    const showCuts = CUT_BASED_STEPS.has(i) && total > 0 && (isActive || isDone || isFailed);
                    return (
                      <div key={s} className="min-w-0">
                        <div className="flex items-center justify-between mb-0.5">
                          <span className={`text-[10px] font-medium truncate ${
                            isDone ? "text-accent-success" : isActive ? "text-amber-400" : isFailed ? "text-accent-danger" : "text-gray-600"
                          }`}>
                            {s}
                            {isActive && <Loader2 size={8} className="inline ml-0.5 animate-spin" />}
                          </span>
                          {showCuts && (
                            <span className={`text-[9px] font-mono ${isDone ? "text-accent-success/70" : isActive ? "text-amber-400/70" : "text-accent-danger/70"}`}>
                              {cuts}/{total}
                            </span>
                          )}
                        </div>
                        <ProgressBar
                          pct={pct}
                          color={isDone ? "bg-accent-success" : isActive ? "bg-amber-400" : isFailed ? "bg-accent-danger" : "bg-gray-700"}
                        />
                      </div>
                    );
                  })}
                </div>
              </div>
              );
            })}

            {/* ── 실패/취소 태스크 ── */}
            {failedTasks.slice(0, 10).map((t) => {
              const ch = t.channel || 0;
              const tmpl = t.template_project_id
                ? projects.find((p) => p.id === t.template_project_id)
                : null;
              const tmplLabel = tmpl ? (tmpl.title || tmpl.topic || tmpl.id) : "기본 설정";
              const chColor =
                ch === 1 ? "bg-blue-500/20 text-blue-400" :
                ch === 2 ? "bg-green-500/20 text-green-400" :
                ch === 3 ? "bg-amber-500/20 text-amber-400" :
                ch === 4 ? "bg-purple-500/20 text-purple-400" :
                "bg-gray-500/20 text-gray-400";
              return (
              <div key={t.task_id} className="border-b border-border/50 bg-accent-danger/[0.02]">
                {/* 상단: 제목 + 버튼 */}
                <div className="flex items-center px-4 pt-3 pb-1">
                  <span className="w-8 shrink-0"><AlertTriangle size={14} className="text-accent-danger" /></span>
                  <div className="flex-1 min-w-0 pr-3">
                    <span className="text-sm font-medium text-gray-300 truncate block">{t.topic || t.title}</span>
                    <div className="flex items-center gap-2 mt-1">
                      {ch > 0 && (
                        <span className={`text-[10px] font-bold rounded px-1.5 py-0.5 ${chColor}`}>
                          CH {ch}
                        </span>
                      )}
                      <span className="text-[10px] text-gray-500 truncate">{tmplLabel}</span>
                    </div>
                  </div>
                  <span className="text-xs font-semibold text-accent-danger mr-2">
                    {t.status === "cancelled" ? "취소" : "실패"} · {Math.round(t.progress_pct)}%
                  </span>
                  <div className="flex gap-1">
                    <button
                      onClick={() => handleResume(t.task_id)}
                      disabled={busyIds.has(t.task_id)}
                      className="flex items-center gap-1 px-2.5 py-1.5 rounded text-[11px] font-medium text-accent-primary bg-accent-primary/10 border border-accent-primary/30 hover:bg-accent-primary/20 transition-colors disabled:opacity-50"
                      title="이어서 하기"
                    >
                      {busyIds.has(t.task_id) ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
                      재시도
                    </button>
                    <button
                      onClick={() => handleDeleteTask(t.task_id)}
                      className="p-1.5 rounded text-gray-500 hover:text-accent-danger hover:bg-accent-danger/10 transition-colors"
                      title="삭제"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>
                {/* 단계 칩 */}
                <div className="px-4 pl-12 pb-1">
                  <div className="flex gap-1 flex-wrap">
                    {STEPS.map((s, i) => {
                      const st = stepStatus(t, i);
                      return (
                        <span
                          key={s}
                          className={`px-2 py-0.5 rounded text-[10px] font-medium ${
                            st === "done"
                              ? "bg-accent-success/15 text-accent-success"
                              : st === "active"
                                ? "bg-amber-400/15 text-amber-400 border border-amber-400/40"
                                : st === "failed"
                                  ? "bg-accent-danger/10 text-accent-danger border border-accent-danger/30"
                                  : "bg-bg-primary text-gray-600"
                          }`}
                        >
                          {s}
                        </span>
                      );
                    })}
                  </div>
                </div>
                {/* 에러 메시지 (전체 표시) */}
                {t.error && (
                  <div className="px-4 pl-12 pb-3">
                    <div className="bg-accent-danger/5 border border-accent-danger/20 rounded-lg px-3 py-2 text-[11px] text-accent-danger/80 font-mono whitespace-pre-wrap break-all">
                      {t.error}
                    </div>
                  </div>
                )}
              </div>
              );
            })}

            {/* ── 완료 태스크 ── */}
            {completedTasks.map((t) => {
              const ch = t.channel || 0;
              const tmpl = t.template_project_id
                ? projects.find((p) => p.id === t.template_project_id)
                : null;
              const tmplLabel = tmpl ? (tmpl.title || tmpl.topic || tmpl.id) : "기본 설정";
              const chColor =
                ch === 1 ? "bg-blue-500/20 text-blue-400" :
                ch === 2 ? "bg-green-500/20 text-green-400" :
                ch === 3 ? "bg-amber-500/20 text-amber-400" :
                ch === 4 ? "bg-purple-500/20 text-purple-400" :
                "bg-gray-500/20 text-gray-400";
              return (
              <div key={t.task_id} className="flex items-center px-4 py-3 border-b border-border/50 bg-accent-success/[0.02]">
                <span className="w-8 shrink-0"><CheckCircle2 size={14} className="text-accent-success" /></span>
                <div className="flex-1 min-w-0 pr-3">
                  <span className="text-sm font-medium text-gray-300 truncate block">{t.topic || t.title}</span>
                  <div className="flex items-center gap-2 mt-1">
                    {ch > 0 && (
                      <span className={`text-[10px] font-bold rounded px-1.5 py-0.5 ${chColor}`}>
                        CH {ch}
                      </span>
                    )}
                    <span className="text-[10px] text-gray-500 truncate">{tmplLabel}</span>
                  </div>
                  {t.finished_at && (
                    <span className="text-[11px] text-gray-600">
                      {new Date(t.finished_at).toLocaleString("ko-KR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                    </span>
                  )}
                </div>
                <div className="hidden md:flex w-[260px] shrink-0"><StepChips task={t} /></div>
                <span className="w-16 shrink-0 text-center text-sm font-semibold text-accent-success">완료</span>
                <div className="w-[140px] shrink-0 flex justify-center">
                  <button
                    onClick={() => handleDeleteTask(t.task_id)}
                    disabled={busyIds.has(t.task_id)}
                    className="p-1.5 rounded text-gray-500 hover:text-accent-danger hover:bg-accent-danger/10 transition-colors disabled:opacity-50"
                    title="삭제"
                  >
                    {busyIds.has(t.task_id) ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
                  </button>
                </div>
              </div>
              );
            })}

            {/* ── 대기 큐 ── */}
            {/* v1.1.67: idx 는 원본 queue 배열 기준 유지(updateItem/removeItem/handleRunItem 가 그 idx 에 의존). 필터는 렌더 단계에서 null 반환으로 처리. */}
            {queue.map((item, idx) => {
              if (!matchesCh(item.channel)) return null;
              const itemId = item.id || String(idx);
              const isBusy = busyIds.has(itemId);
              return (
                <div key={itemId} className="flex items-center px-4 py-3.5 border-b border-border/50 hover:bg-white/[0.01] transition-colors">
                  <span className="w-8 shrink-0 text-xs text-gray-600 font-mono">{idx + 1}</span>
                  <div className="flex-1 min-w-0 pr-3">
                    <input
                      value={item.topic}
                      onChange={(e) => updateItem(idx, { topic: e.target.value })}
                      placeholder="주제를 입력하세요"
                      className="w-full text-sm bg-transparent text-gray-200 outline-none placeholder:text-gray-600 focus:text-white"
                    />
                    <div className="flex items-center gap-2 mt-1">
                      <select
                        value={item.channel || 1}
                        onChange={(e) => updateItem(idx, { channel: parseInt(e.target.value) || 1 })}
                        className={`text-[10px] font-bold outline-none cursor-pointer rounded px-1.5 py-0.5 ${
                          (item.channel || 1) === 1 ? "bg-blue-500/20 text-blue-400" :
                          (item.channel || 1) === 2 ? "bg-green-500/20 text-green-400" :
                          (item.channel || 1) === 3 ? "bg-amber-500/20 text-amber-400" :
                          "bg-purple-500/20 text-purple-400"
                        }`}
                      >
                        <option value={1}>CH 1</option>
                        <option value={2}>CH 2</option>
                        <option value={3}>CH 3</option>
                        <option value={4}>CH 4</option>
                      </select>
                      <select
                        value={item.template_project_id || ""}
                        onChange={(e) => updateItem(idx, { template_project_id: e.target.value || null })}
                        className="text-[10px] bg-transparent text-gray-500 outline-none cursor-pointer"
                      >
                        <option value="">기본 설정</option>
                        {projects.map((p) => (
                          <option key={p.id} value={p.id}>{p.title || p.topic || p.id}</option>
                        ))}
                      </select>
                      {item.target_duration && item.target_duration > 0 && (
                        <span className="text-[10px] text-gray-600">
                          <Clock size={9} className="inline mr-0.5" />
                          {formatDurationKo(item.target_duration)}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="hidden md:flex w-[260px] shrink-0 gap-1">
                    {STEPS.map((s) => (
                      <span key={s} className="px-2 py-0.5 rounded text-[10px] font-medium bg-bg-primary text-gray-600">{s}</span>
                    ))}
                  </div>
                  <span className="w-16 shrink-0 text-center text-sm text-gray-600">대기</span>
                  <div className="w-[140px] shrink-0 flex justify-center gap-1.5">
                    <button
                      onClick={() => handleRunItem(idx)}
                      disabled={isBusy || activeTasksAll.length > 0}
                      className="flex items-center gap-1 px-3 py-1.5 rounded text-[11px] font-medium text-accent-success bg-accent-success/10 border border-accent-success/30 hover:bg-accent-success/20 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                      title={activeTasksAll.length > 0 ? "진행 중인 작업 완료 후 실행 가능" : "실행"}
                    >
                      {isBusy ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
                      실행
                    </button>
                    <button
                      onClick={() => removeItem(idx)}
                      className="p-1.5 rounded text-gray-500 hover:text-accent-danger hover:bg-accent-danger/10 transition-colors"
                      title="삭제"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>
              );
            })}
          </>
        )}
      </div>
    </div>
  );
}
