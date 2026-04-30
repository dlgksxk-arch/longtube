"use client";

/**
 * v1.1.34 — 딸깍 제작 위젯
 * v1.1.37 — 위치를 Studio 사이드바에서 대시보드 메인으로 이동.
 * v1.1.38 — 매일 HH:MM 자동 실행 스케줄 섹션 추가.
 * v1.1.42 — 인라인 카드 + 자동 스케줄 전면 삭제. 버튼 + "주제/시간 1건 입력"
 *          모달로 재작성.
 * v1.1.43 — 즉시 실행 1건 입력 방식 제거. 이제 모달은 **주제 큐 편집기**.
 *          사용자 요구: "딸깍제작 주제 입력 리스트 만들고 매일 몇시에 시작
 *          할지 입력 할 수 있게해".
 *
 *          UX:
 *            - 버튼 누르면 모달 오픈
 *            - 모달 상단: 매일 실행 시각 (HH:MM 또는 "비활성")
 *            - 모달 본체: 주제 row 리스트. 각 row 마다 주제 / 프리셋 / 길이(분) / [X]
 *              + "주제 추가" 버튼
 *            - 하단: "저장" + "지금 1건 실행"
 *            - 진행 중 태스크가 있으면 상단에 진행 배너 + 중지 버튼
 *            - 큐가 비면 아무것도 안 함 (조용히 대기)
 *
 *          큐 원소 구조:
 *            { id, topic, template_project_id, target_duration(초) | null }
 *
 *          발화 규칙(백엔드):
 *            - 매일 HH:MM 에 큐 맨 위 1건 pop + 실행
 *            - 성공/실패 무관하게 pop-on-start
 *            - 빈 큐면 조용히 대기
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Zap,
  Loader2,
  Check,
  AlertCircle,
  X,
  Clock,
  Plus,
  Play,
  Save,
  Trash2,
  CalendarClock,
} from "lucide-react";
import {
  oneclickApi,
  projectsApi,
  youtubeApi,
  type OneClickTask,
  type OneClickQueueItem,
  type OneClickQueueState,
  type Project,
} from "@/lib/api";
import { formatDurationKo } from "@/lib/format";

function isActiveTask(t: OneClickTask | null): boolean {
  if (!t) return false;
  return (
    t.status === "prepared" ||
    t.status === "queued" ||
    t.status === "running"
  );
}

function genLocalId(): string {
  return Math.random().toString(36).slice(2, 10);
}

function emptyItem(templateId?: string, targetDuration?: number | null): OneClickQueueItem {
  return {
    id: genLocalId(),
    topic: "",
    template_project_id: templateId ?? null,
    target_duration: targetDuration ?? null,
    channel: 1,
    queued_source: "manual",
    queued_at: new Date().toISOString(),
    queued_note: "스튜디오 위젯에서 직접 추가",
  };
}

export default function OneClickWidget() {
  const [open, setOpen] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [items, setItems] = useState<OneClickQueueItem[]>([]);
  // v1.1.57: 채널별 시간
  const [channelTimes, setChannelTimes] = useState<Record<string, string>>({ "1": "", "2": "", "3": "", "4": "" });
  // v1.1.59: 채널별 YouTube 인증 상태 + 채널 정보
  const [channelAuth, setChannelAuth] = useState<Record<string, { authenticated: boolean; title?: string }>>({});
  const [channelAuthBusy, setChannelAuthBusy] = useState<Record<string, boolean>>({});
  const [lastRunDates, setLastRunDates] = useState<Record<string, string | null>>({ "1": null, "2": null, "3": null, "4": null });
  const [task, setTask] = useState<OneClickTask | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ─── 마운트: 프리셋 목록 + 큐 + 활성 태스크 복구 ─────────────────
  useEffect(() => {
    let cancelled = false;
    projectsApi
      .list()
      .then((list) => {
        if (!cancelled) setProjects(list || []);
      })
      .catch(() => {
        if (!cancelled) setProjects([]);
      });
    oneclickApi
      .list()
      .then(({ tasks }) => {
        if (cancelled) return;
        const active = (tasks || []).find((t) =>
          ["prepared", "queued", "running"].includes(t.status),
        );
        if (active) setTask(active);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  // ─── 모달 열 때마다 최신 큐 상태 재로드 ─────────────────────────
  const loadQueue = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const q = await oneclickApi.getQueue();
      const ct = q.channel_times || {};
      setChannelTimes({ "1": ct["1"] || "", "2": ct["2"] || "", "3": ct["3"] || "", "4": ct["4"] || "" });
      const lrd = q.last_run_dates || {};
      setLastRunDates({ "1": lrd["1"] || null, "2": lrd["2"] || null, "3": lrd["3"] || null, "4": lrd["4"] || null });
      // 서버 아이템에 로컬 id 보강
      setItems(
        (q.items || []).map((it) => ({
          ...it,
          id: it.id || genLocalId(),
        })),
      );
    } catch (e) {
      setErr((e as Error).message || "큐 불러오기 실패");
    } finally {
      setLoading(false);
    }
  }, []);

  // ─── 채널별 YouTube 인증 상태 로드 ─────────────────────────────
  const loadChannelAuth = useCallback(async () => {
    const next: Record<string, { authenticated: boolean; title?: string }> = {};
    await Promise.all(
      [1, 2, 3, 4].map(async (ch) => {
        try {
          const s = await youtubeApi.channelAuthStatus(ch);
          next[String(ch)] = { authenticated: !!s.authenticated };
          if (s.authenticated) {
            try {
              const info = await youtubeApi.channelAuthInfo(ch);
              next[String(ch)] = { authenticated: true, title: info.title };
            } catch {
              /* ignore */
            }
          }
        } catch {
          next[String(ch)] = { authenticated: false };
        }
      }),
    );
    setChannelAuth(next);
  }, []);

  const handleChannelAuth = useCallback(
    async (ch: number) => {
      setChannelAuthBusy((p) => ({ ...p, [String(ch)]: true }));
      setErr(null);
      try {
        await youtubeApi.channelAuthenticate(ch);
        await loadChannelAuth();
      } catch (e) {
        setErr(`CH${ch} 인증 실패: ${(e as Error).message || e}`);
      } finally {
        setChannelAuthBusy((p) => ({ ...p, [String(ch)]: false }));
      }
    },
    [loadChannelAuth],
  );

  const handleChannelAuthReset = useCallback(
    async (ch: number) => {
      if (!confirm(`CH${ch} YouTube 인증을 초기화하시겠습니까? 다음 인증 시 계정 선택 팝업이 다시 뜹니다.`)) return;
      setChannelAuthBusy((p) => ({ ...p, [String(ch)]: true }));
      setErr(null);
      try {
        await youtubeApi.channelAuthReset(ch);
        await loadChannelAuth();
      } catch (e) {
        setErr(`CH${ch} 인증 초기화 실패: ${(e as Error).message || e}`);
      } finally {
        setChannelAuthBusy((p) => ({ ...p, [String(ch)]: false }));
      }
    },
    [loadChannelAuth],
  );

  useEffect(() => {
    if (open) {
      void loadQueue();
      void loadChannelAuth();
      setSaved(false);
    }
  }, [open, loadQueue, loadChannelAuth]);

  // ─── 태스크 폴링: running/queued 중이면 2 초마다 갱신 ────────────
  useEffect(() => {
    if (!task) return;
    const done =
      task.status === "completed" ||
      task.status === "failed" ||
      task.status === "cancelled";
    if (done) {
      if (pollTimer.current) {
        clearTimeout(pollTimer.current);
        pollTimer.current = null;
      }
      return;
    }
    pollTimer.current = setTimeout(async () => {
      try {
        const fresh = await oneclickApi.get(task.task_id);
        setTask(fresh);
      } catch (e) {
        console.error("[oneclick] poll failed", e);
      }
    }, 2000);
    return () => {
      if (pollTimer.current) {
        clearTimeout(pollTimer.current);
        pollTimer.current = null;
      }
    };
  }, [task]);

  // ─── 큐 편집 헬퍼 ───────────────────────────────────────────────
  const updateItem = (idx: number, patch: Partial<OneClickQueueItem>) => {
    setItems((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], ...patch };
      return next;
    });
    setSaved(false);
  };
  const removeItem = (idx: number) => {
    setItems((prev) => prev.filter((_, i) => i !== idx));
    setSaved(false);
  };
  const addItem = () => {
    setItems((prev) => [...prev, emptyItem()]);
    setSaved(false);
  };

  // ─── 저장 ───────────────────────────────────────────────────────
  const handleSave = useCallback(async () => {
    // 빈 주제 row 는 저장 시 정리
    const clean = items
      .map((it) => ({
        ...it,
        topic: (it.topic || "").trim(),
      }))
      .filter((it) => it.topic.length > 0);

    // v1.1.57: 채널별 HH:MM 검증
    const ct: Record<string, string | null> = {};
    for (const ch of ["1", "2", "3", "4"]) {
      const val = channelTimes[ch]?.trim() || "";
      if (val) {
        const m = /^(\d{1,2}):(\d{2})$/.exec(val);
        if (!m) {
          setErr(`채널 ${ch} 시간은 HH:MM 형태로 입력해 주세요. 예: 09:00`);
          return;
        }
        const hh = parseInt(m[1], 10);
        const mm = parseInt(m[2], 10);
        if (hh < 0 || hh > 23 || mm < 0 || mm > 59) {
          setErr(`채널 ${ch} 시간 범위를 확인해 주세요 (00:00 ~ 23:59).`);
          return;
        }
        ct[ch] = `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
      } else {
        ct[ch] = null;
      }
    }

    setSaving(true);
    setErr(null);
    try {
      const saved = await oneclickApi.setQueue({
        channel_times: ct,
        items: clean.map((it) => ({
          id: it.id,
          topic: it.topic,
          template_project_id: it.template_project_id || null,
          target_duration: it.target_duration ?? null,
          channel: it.channel || 1,
          queued_source: it.queued_source || "manual",
          queued_at: it.queued_at || new Date().toISOString(),
          queued_note: it.queued_note || "스튜디오 위젯에서 직접 추가",
        })),
      });
      setItems(
        (saved.items || []).map((it) => ({ ...it, id: it.id || genLocalId() })),
      );
      const rct = saved.channel_times || {};
      setChannelTimes({ "1": rct["1"] || "", "2": rct["2"] || "", "3": rct["3"] || "", "4": rct["4"] || "" });
      const rlrd = saved.last_run_dates || {};
      setLastRunDates({ "1": rlrd["1"] || null, "2": rlrd["2"] || null, "3": rlrd["3"] || null, "4": rlrd["4"] || null });
      setSaved(true);
    } catch (e) {
      setErr((e as Error).message || "저장 실패");
    } finally {
      setSaving(false);
    }
  }, [channelTimes, items]);

  // ─── 지금 1건 실행 (pop top) ────────────────────────────────────
  const handleRunNext = useCallback(async () => {
    if (!items.some((it) => (it.topic || "").trim())) {
      setErr("큐에 실행할 주제가 없습니다.");
      return;
    }
    // 저장 안 된 변경이 있으면 먼저 저장해야 서버 큐가 맞음
    await handleSave();
    try {
      const t = await oneclickApi.runQueueNext();
      setTask(t);
      // 서버가 맨 위 1건을 pop 했으므로 UI 큐도 다시 불러옴
      await loadQueue();
    } catch (e) {
      setErr((e as Error).message || "실행 실패");
    }
  }, [items, handleSave, loadQueue]);

  const handleCancel = useCallback(async () => {
    if (!task) return;
    try {
      const t = await oneclickApi.cancel(task.task_id);
      setTask(t);
    } catch (e) {
      setErr((e as Error).message || "취소 실패");
    }
  }, [task]);

  const running = isActiveTask(task);
  const pct = Math.max(0, Math.min(100, task?.progress_pct || 0));

  // ─── 버튼 ───────────────────────────────────────────────────────
  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className={`relative flex items-center gap-2 font-semibold px-4 py-2 rounded-lg text-sm transition-colors ${
          running
            ? "bg-accent-primary/20 border border-accent-primary text-accent-primary"
            : "bg-accent-primary hover:bg-purple-600 text-white"
        }`}
        title={running ? "딸깍 진행 중 — 클릭해 큐/진행 상태 확인" : "딸깍 제작 큐"}
      >
        {running ? (
          <Loader2 size={16} className="animate-spin" />
        ) : (
          <Zap size={16} />
        )}
        딸깍 제작
        {running && (
          <span className="text-[10px] font-normal opacity-80">
            진행 중 {Math.round(pct)}%
          </span>
        )}
      </button>

      {/* ─── 모달 ─────────────────────────────────────────────── */}
      {open && (
        <div
          className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4"
          onClick={() => setOpen(false)}
        >
          <div
            className="bg-bg-primary border border-accent-primary/40 rounded-lg max-w-3xl w-full max-h-[90vh] flex flex-col shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            {/* 헤더 */}
            <div className="flex items-center gap-2 px-5 pt-4 pb-3 border-b border-border flex-shrink-0">
              <div className="w-9 h-9 rounded-full flex items-center justify-center bg-accent-primary/15 border-2 border-accent-primary text-accent-primary">
                <Zap size={16} />
              </div>
              <div className="flex-1">
                <div className="text-base font-semibold text-gray-100">
                  딸깍 제작 큐
                </div>
                <div className="text-[11px] text-gray-500">
                  주제 리스트를 채워 두면 매일 지정한 시각에 맨 위 1건씩 자동 실행합니다.
                </div>
              </div>
              <button
                onClick={() => setOpen(false)}
                className="p-1.5 rounded hover:bg-bg-secondary text-gray-500 hover:text-white"
                title="닫기"
              >
                <X size={16} />
              </button>
            </div>

            {/* 진행 배너 */}
            {running && task && (
              <div className="mx-5 mt-4 rounded border border-accent-primary/40 bg-accent-primary/10 p-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="text-[11px] text-gray-400 mb-0.5">
                      지금 제작 중
                    </div>
                    <div className="text-sm text-gray-100 truncate">
                      {task.topic}
                    </div>
                    {/* v2.1.2: 현재 호출 중인 API/모델 표시 */}
                    {task.current_step && task.models && (() => {
                      const modelMap: Record<number, { label: string; value: string }> = {
                        2: { label: "대본", value: task.models?.script || "" },
                        3: { label: "TTS", value: [task.models?.tts, task.models?.tts_voice].filter(Boolean).join(" / ") },
                        4: { label: "이미지", value: task.models?.image || "" },
                        5: { label: "영상", value: task.models?.video || "" },
                      };
                      const m = modelMap[task.current_step];
                      if (!m || !m.value) return null;
                      return (
                        <div className="mt-1 text-[10px] text-accent-primary/80 font-mono truncate">
                          {m.label}: {m.value}
                        </div>
                      );
                    })()}
                    <div className="mt-2 h-1.5 rounded-full bg-bg-tertiary overflow-hidden">
                      <div
                        className="h-full bg-accent-primary transition-all duration-500"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <div className="mt-1 flex justify-between text-[10px] text-gray-500">
                      <span>
                        {task.current_step_name ||
                          (task.status === "queued" ? "대기 중..." : "실행 중")}
                        {/* 컷 진행 카운터 */}
                        {(task.current_step_completed ?? 0) > 0 && task.current_step_total
                          ? ` (${task.current_step_completed}/${task.current_step_total})`
                          : ""}
                      </span>
                      <span className="font-mono">{pct.toFixed(1)}%</span>
                    </div>
                  </div>
                  <button
                    onClick={handleCancel}
                    className="flex items-center gap-1 text-[11px] bg-bg-tertiary hover:bg-accent-danger/20 hover:border-accent-danger hover:text-accent-danger border border-border text-gray-300 rounded px-2 py-1"
                  >
                    <X size={11} /> 중지
                  </button>
                </div>
                {/* v2.1.2: 제작 로그 */}
                {task.logs && task.logs.length > 0 && (
                  <div className="mt-2 pt-2 border-t border-accent-primary/20 max-h-28 overflow-y-auto">
                    <div className="text-[10px] text-gray-500 mb-1">제작 로그</div>
                    {task.logs.slice(-10).map((log, i) => (
                      <div
                        key={i}
                        className={`text-[10px] font-mono leading-relaxed ${
                          log.level === "error"
                            ? "text-red-400"
                            : log.level === "warn"
                            ? "text-amber-400"
                            : "text-gray-400"
                        }`}
                      >
                        <span className="text-gray-600">{log.ts}</span>{" "}
                        {log.msg}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* v2.1.2: 완료/실패 태스크 로그 (running 아닐 때) */}
            {!running && task && (task.status === "completed" || task.status === "failed" || task.status === "cancelled") && task.logs && task.logs.length > 0 && (
              <div className="mx-5 mt-4 rounded border border-border bg-bg-tertiary/50 p-3">
                <div className="flex items-center justify-between mb-1">
                  <div className="text-[10px] text-gray-500">
                    최근 제작 로그 — {task.topic?.slice(0, 30)}
                    {task.status === "failed" && <span className="ml-1 text-red-400">(실패)</span>}
                    {task.status === "cancelled" && <span className="ml-1 text-amber-400">(취소)</span>}
                    {task.status === "completed" && <span className="ml-1 text-emerald-400">(완료)</span>}
                  </div>
                  <button
                    onClick={() => setTask(null)}
                    className="text-[10px] text-gray-600 hover:text-gray-400"
                  >
                    닫기
                  </button>
                </div>
                <div className="max-h-32 overflow-y-auto">
                  {task.logs.slice(-15).map((log, i) => (
                    <div
                      key={i}
                      className={`text-[10px] font-mono leading-relaxed ${
                        log.level === "error"
                          ? "text-red-400"
                          : log.level === "warn"
                          ? "text-amber-400"
                          : "text-gray-400"
                      }`}
                    >
                      <span className="text-gray-600">{log.ts}</span>{" "}
                      {log.msg}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 본체 — 큐 편집기 */}
            <div className="px-5 py-4 overflow-y-auto flex-1">
              {loading ? (
                <div className="flex items-center gap-2 text-sm text-gray-400 py-10 justify-center">
                  <Loader2 size={14} className="animate-spin" /> 큐 불러오는 중...
                </div>
              ) : (
                <>
                  {/* v1.1.57: 채널별 실행 시각 */}
                  <div className="mb-4 pb-4 border-b border-border">
                    <label className="block text-[11px] text-gray-400 mb-2 flex items-center gap-1">
                      <CalendarClock size={11} /> 채널별 매일 실행 시각
                    </label>
                    <div className="grid grid-cols-2 gap-2">
                      {(["1","2","3","4"] as const).map((ch) => {
                        const color = ch === "1" ? "text-blue-400" : ch === "2" ? "text-green-400" : ch === "3" ? "text-amber-400" : "text-purple-400";
                        return (
                          <div key={ch} className="flex items-center gap-2 bg-bg-tertiary border border-border rounded px-2.5 py-1.5">
                            <span className={`text-[10px] font-bold ${color}`}>CH{ch}</span>
                            <input
                              type="time"
                              value={channelTimes[ch] || ""}
                              onChange={(e) => {
                                setChannelTimes((p) => ({ ...p, [ch]: e.target.value }));
                                setSaved(false);
                              }}
                              className="text-xs bg-transparent text-gray-200 outline-none flex-1"
                            />
                            {lastRunDates[ch] && (
                              <span className="text-[9px] text-gray-600">{lastRunDates[ch]}</span>
                            )}
                          </div>
                        );
                      })}
                    </div>
                    <div className="text-[10px] text-gray-500 mt-1.5">
                      {Object.values(channelTimes).some((v) => !!v)
                        ? "설정된 채널만 매일 해당 시각에 큐 맨 위 1건을 실행합니다."
                        : "시간을 비워 두면 자동 실행이 꺼집니다."}
                    </div>

                    {/* v1.1.59: 채널별 YouTube 인증 */}
                    <div className="mt-3 pt-3 border-t border-border/60">
                      <label className="block text-[11px] text-gray-400 mb-2">
                        채널별 YouTube 계정
                      </label>
                      <div className="grid grid-cols-2 gap-2">
                        {(["1","2","3","4"] as const).map((ch) => {
                          const color = ch === "1" ? "text-blue-400" : ch === "2" ? "text-green-400" : ch === "3" ? "text-amber-400" : "text-purple-400";
                          const a = channelAuth[ch];
                          const busy = !!channelAuthBusy[ch];
                          return (
                            <div key={`auth-${ch}`} className="flex items-center gap-2 bg-bg-tertiary border border-border rounded px-2.5 py-1.5">
                              <span className={`text-[10px] font-bold ${color} shrink-0`}>CH{ch}</span>
                              <div className="flex-1 min-w-0">
                                {a?.authenticated ? (
                                  <div className="text-[10px] text-emerald-400 truncate" title={a.title || "연결됨"}>
                                    ✓ {a.title || "연결됨"}
                                  </div>
                                ) : (
                                  <div className="text-[10px] text-gray-500">미연결</div>
                                )}
                              </div>
                              {a?.authenticated ? (
                                <button
                                  type="button"
                                  disabled={busy}
                                  onClick={() => void handleChannelAuthReset(parseInt(ch, 10))}
                                  className="text-[10px] text-red-400 hover:text-red-300 disabled:opacity-50"
                                  title="인증 초기화"
                                >
                                  {busy ? <Loader2 size={10} className="animate-spin" /> : "초기화"}
                                </button>
                              ) : (
                                <button
                                  type="button"
                                  disabled={busy}
                                  onClick={() => void handleChannelAuth(parseInt(ch, 10))}
                                  className="text-[10px] text-emerald-400 hover:text-emerald-300 disabled:opacity-50"
                                  title="이 채널 계정으로 로그인"
                                >
                                  {busy ? <Loader2 size={10} className="animate-spin" /> : "연결"}
                                </button>
                              )}
                            </div>
                          );
                        })}
                      </div>
                      <div className="text-[10px] text-gray-500 mt-1.5">
                        각 채널의 "연결" 버튼을 누르면 브라우저 팝업이 뜨고, 그 채널로 업로드할 YouTube 계정으로 로그인하시면 됩니다.
                      </div>
                    </div>
                  </div>

                  {/* 주제 row 리스트 */}
                  <div className="text-[11px] text-gray-400 mb-2 flex items-center justify-between">
                    <span>주제 큐 <span className="text-gray-600">(위에서부터 하루 1 건씩 소비)</span></span>
                    <span className="text-gray-600">{items.length} 건</span>
                  </div>

                  {items.length === 0 ? (
                    <div className="text-center text-xs text-gray-500 py-10 border border-dashed border-border rounded">
                      아직 큐가 비어 있습니다. 아래 "주제 추가" 로 시작하세요.
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {items.map((it, idx) => (
                        <QueueRow
                          key={it.id || idx}
                          index={idx}
                          item={it}
                          projects={projects}
                          onChange={(patch) => updateItem(idx, patch)}
                          onRemove={() => removeItem(idx)}
                        />
                      ))}
                    </div>
                  )}

                  <button
                    onClick={addItem}
                    className="mt-3 w-full flex items-center justify-center gap-1.5 text-xs text-gray-300 hover:text-white bg-bg-tertiary hover:bg-bg-secondary border border-dashed border-border rounded py-2 transition-colors"
                  >
                    <Plus size={12} /> 주제 추가
                  </button>

                  {err && (
                    <div className="mt-3 text-xs text-accent-danger flex items-start gap-1">
                      <AlertCircle size={12} className="mt-0.5 flex-shrink-0" />
                      <span>{err}</span>
                    </div>
                  )}
                </>
              )}
            </div>

            {/* 푸터 — 저장 / 지금 실행 */}
            <div className="px-5 py-3 border-t border-border flex items-center gap-2 flex-shrink-0">
              <button
                onClick={handleSave}
                disabled={saving || loading}
                className="flex items-center gap-1.5 text-xs bg-bg-tertiary hover:bg-bg-secondary border border-border text-gray-200 rounded px-3 py-2 disabled:opacity-40"
              >
                {saving ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : saved ? (
                  <Check size={12} className="text-accent-success" />
                ) : (
                  <Save size={12} />
                )}
                {saved ? "저장됨" : "저장"}
              </button>
              <div className="flex-1" />
              <button
                onClick={handleRunNext}
                disabled={saving || loading || running || items.length === 0}
                className="flex items-center gap-1.5 text-xs font-semibold bg-accent-primary hover:bg-purple-600 text-white rounded px-3 py-2 disabled:opacity-40 disabled:cursor-not-allowed"
                title={
                  running
                    ? "이미 실행 중인 태스크가 있습니다"
                    : "큐 맨 위 1건을 지금 바로 실행"
                }
              >
                <Play size={12} /> 지금 1건 실행
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

// ─── 서브 컴포넌트: 큐 row ─────────────────────────────────────────
function QueueRow(props: {
  index: number;
  item: OneClickQueueItem;
  projects: Project[];
  onChange: (patch: Partial<OneClickQueueItem>) => void;
  onRemove: () => void;
}) {
  const { index, item, projects, onChange, onRemove } = props;

  // target_duration 은 초. UI 는 분.
  const durMin =
    item.target_duration && item.target_duration > 0
      ? Math.max(1, Math.round(item.target_duration / 60))
      : "";

  return (
    <div className="flex items-start gap-2 bg-bg-tertiary border border-border rounded p-2">
      <div className="w-6 flex-shrink-0 text-center text-[11px] text-gray-500 font-mono pt-2">
        {index + 1}
      </div>
      <div className="flex-1 min-w-0 space-y-1.5">
        <input
          value={item.topic}
          onChange={(e) => onChange({ topic: e.target.value })}
          placeholder="주제를 입력하세요"
          className="w-full text-sm bg-bg-primary border border-border rounded px-2 py-1.5 text-gray-100 focus:border-accent-primary outline-none"
        />
        <div className="flex items-center gap-2">
          {/* 채널 선택 */}
          <select
            value={item.channel || 1}
            onChange={(e) => onChange({ channel: parseInt(e.target.value, 10) })}
            className="text-[11px] bg-bg-primary border border-border rounded px-1.5 py-1 text-gray-200 focus:border-accent-primary outline-none w-16"
          >
            <option value={1}>CH1</option>
            <option value={2}>CH2</option>
            <option value={3}>CH3</option>
            <option value={4}>CH4</option>
          </select>
          <select
            value={item.template_project_id || ""}
            onChange={(e) => {
              const tid = e.target.value || null;
              const patch: Partial<OneClickQueueItem> = { template_project_id: tid };
              // v1.1.60: 프리셋이 youtube_channel 을 들고 있으면 큐 row 채널을 자동 매핑
              if (tid) {
                const p = projects.find((x) => x.id === tid);
                const cfgCh = (p as unknown as { config?: { youtube_channel?: number | null } } | undefined)
                  ?.config?.youtube_channel;
                if (cfgCh && cfgCh >= 1 && cfgCh <= 4) {
                  patch.channel = cfgCh;
                }
              }
              onChange(patch);
            }}
            className="flex-1 min-w-0 text-[11px] bg-bg-primary border border-border rounded px-2 py-1 text-gray-200 focus:border-accent-primary outline-none"
          >
            <option value="">기본 설정</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.title || p.topic || p.id}
              </option>
            ))}
          </select>
          <div className="flex items-center gap-1 text-[11px] text-gray-500">
            <Clock size={11} />
            <input
              type="number"
              min={1}
              max={180}
              value={durMin}
              placeholder="10"
              onChange={(e) => {
                const v = parseInt(e.target.value, 10);
                onChange({
                  target_duration: Number.isFinite(v) && v > 0 ? v * 60 : null,
                });
              }}
              className="w-14 text-[11px] bg-bg-primary border border-border rounded px-1.5 py-1 text-gray-200 focus:border-accent-primary outline-none"
            />
            <span>분</span>
          </div>
          {item.target_duration && item.target_duration > 0 && (
            <span className="text-[10px] text-gray-600">
              약 {formatDurationKo(item.target_duration)}
            </span>
          )}
        </div>
      </div>
      <button
        onClick={onRemove}
        className="p-1.5 rounded text-gray-500 hover:text-accent-danger hover:bg-accent-danger/10 flex-shrink-0"
        title="이 주제 제거"
      >
        <Trash2 size={13} />
      </button>
    </div>
  );
}
