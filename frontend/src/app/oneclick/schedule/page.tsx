"use client";

/**
 * v1.1.49 — 딸깍 대시보드 > 스케줄
 * 월간 캘린더 (완료/진행중/예약 표시) + 예정 업로드 리스트 + 매일 실행 시간 설정
 */
import { useCallback, useEffect, useState } from "react";
import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Clock,
  Loader2,
  Save,
  Check,
  Pencil,
} from "lucide-react";
import {
  oneclickApi,
  type OneClickTask,
  type OneClickQueueItem,
  type OneClickQueueState,
} from "@/lib/api";

const DAYS_KO = ["일", "월", "화", "수", "목", "금", "토"];

export default function SchedulePage() {
  const [queue, setQueue] = useState<OneClickQueueState | null>(null);
  const [tasks, setTasks] = useState<OneClickTask[]>([]);
  const [loading, setLoading] = useState(true);
  // v1.1.57: 채널별 시간
  const [channelTimes, setChannelTimes] = useState<Record<string, string>>({ "1": "", "2": "", "3": "", "4": "" });
  const [editingTime, setEditingTime] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  // 캘린더 상태
  const now = new Date();
  const [viewYear, setViewYear] = useState(now.getFullYear());
  const [viewMonth, setViewMonth] = useState(now.getMonth()); // 0-based

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [q, { tasks: t }] = await Promise.all([
        oneclickApi.getQueue(),
        oneclickApi.list(),
      ]);
      setQueue(q);
      const ct = q.channel_times || {};
      setChannelTimes({ "1": ct["1"] || "", "2": ct["2"] || "", "3": ct["3"] || "", "4": ct["4"] || "" });
      setTasks(t || []);
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // 캘린더 데이터
  const firstDay = new Date(viewYear, viewMonth, 1).getDay();
  const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
  const today = new Date();
  const isCurrentMonth =
    viewYear === today.getFullYear() && viewMonth === today.getMonth();

  // 완료/실패 태스크를 날짜별 맵핑
  const dayStatusMap = new Map<
    number,
    "completed" | "failed" | "running" | "scheduled"
  >();
  // v1.1.60: 날짜별 채널 번호 집합 — 캘린더 셀에 "CH1, CH3" 처럼 표시
  const dayChannelsMap = new Map<number, Set<number>>();
  const addDayChannel = (day: number, ch: number | null | undefined) => {
    if (!ch) return;
    let set = dayChannelsMap.get(day);
    if (!set) {
      set = new Set();
      dayChannelsMap.set(day, set);
    }
    set.add(ch);
  };
  for (const t of tasks) {
    const d = t.finished_at
      ? new Date(t.finished_at)
      : t.started_at
        ? new Date(t.started_at)
        : new Date(t.created_at);
    if (d.getFullYear() === viewYear && d.getMonth() === viewMonth) {
      const day = d.getDate();
      if (t.status === "completed") dayStatusMap.set(day, "completed");
      else if (t.status === "failed") dayStatusMap.set(day, "failed");
      else if (["running", "queued", "prepared"].includes(t.status))
        dayStatusMap.set(day, "running");
      addDayChannel(day, (t as { channel?: number | null }).channel);
    }
  }

  // v1.1.58: 채널별 병행 스케줄 — 각 채널이 하루에 1건씩 독립 소비
  const hasAnySchedule = Object.values(queue?.channel_times || {}).some((v) => !!v);
  const activeChannelKeys = Object.entries(queue?.channel_times || {})
    .filter(([, v]) => !!v)
    .map(([k]) => parseInt(k, 10));

  if (hasAnySchedule && queue && queue.items.length > 0) {
    // 채널별로 아이템 분리
    const itemsByChannel: Record<number, typeof queue.items> = {};
    for (const ch of activeChannelKeys) itemsByChannel[ch] = [];
    for (const item of queue.items) {
      const ch = item.channel || 1;
      if (itemsByChannel[ch]) itemsByChannel[ch].push(item);
    }

    const activeTasks = tasks.filter((t) =>
      ["running", "queued", "prepared"].includes(t.status),
    );
    const todayBusy = activeTasks.length > 0 || dayStatusMap.has(today.getDate());

    // 각 채널의 아이템을 날짜에 매핑
    for (const ch of activeChannelKeys) {
      const chItems = itemsByChannel[ch] || [];
      let schedDate = new Date(today);
      if (todayBusy) schedDate.setDate(schedDate.getDate() + 1);
      for (let i = 0; i < chItems.length; i++) {
        if (
          schedDate.getFullYear() === viewYear &&
          schedDate.getMonth() === viewMonth
        ) {
          const d = schedDate.getDate();
          if (!dayStatusMap.has(d)) {
            dayStatusMap.set(d, "scheduled");
          }
          addDayChannel(d, ch);
        }
        schedDate.setDate(schedDate.getDate() + 1);
      }
    }
  }

  const prevMonth = () => {
    if (viewMonth === 0) {
      setViewYear(viewYear - 1);
      setViewMonth(11);
    } else {
      setViewMonth(viewMonth - 1);
    }
  };
  const nextMonth = () => {
    if (viewMonth === 11) {
      setViewYear(viewYear + 1);
      setViewMonth(0);
    } else {
      setViewMonth(viewMonth + 1);
    }
  };

  // 시간 저장
  const handleSaveTime = async () => {
    if (!queue) return;
    setSaving(true);
    try {
      const ct: Record<string, string | null> = {};
      for (const ch of ["1","2","3","4"]) ct[ch] = channelTimes[ch] || null;
      const res = await oneclickApi.setQueue({
        channel_times: ct,
        items: queue.items,
      });
      setQueue(res);
      const rct = res.channel_times || {};
      setChannelTimes({ "1": rct["1"] || "", "2": rct["2"] || "", "3": rct["3"] || "", "4": rct["4"] || "" });
      setSaved(true);
      setEditingTime(false);
      setTimeout(() => setSaved(false), 2000);
    } catch {}
    setSaving(false);
  };

  // v1.1.58: 예정 리스트 — 채널 병행 방식
  const upcomingList: {
    date: string;
    sortKey: number;  // 정렬용 타임스탬프
    topic: string;
    status: string;
    color: string;
    channel: number;
  }[] = [];
  if (queue?.items) {
    const activeTasks = tasks.filter((t) =>
      ["running", "queued", "prepared"].includes(t.status),
    );
    // 활성 태스크 먼저
    for (const t of activeTasks) {
      upcomingList.push({
        date: "오늘",
        sortKey: 0,
        topic: t.topic || t.title,
        status: "제작 중",
        color: "text-amber-400 bg-amber-400/15",
        channel: (t as any).channel || 1,
      });
    }

    // 채널별로 아이템 분리 후 날짜 할당
    const todayBusy = activeTasks.length > 0 || dayStatusMap.has(today.getDate());
    const itemsByChannel: Record<number, typeof queue.items> = {};
    for (const ch of activeChannelKeys) itemsByChannel[ch] = [];
    for (const item of queue.items) {
      const ch = item.channel || 1;
      if (itemsByChannel[ch]) itemsByChannel[ch].push(item);
    }

    for (const ch of activeChannelKeys) {
      const chItems = itemsByChannel[ch] || [];
      let d = new Date(today);
      if (todayBusy) d.setDate(d.getDate() + 1);
      for (const item of chItems) {
        const label =
          d.toDateString() === today.toDateString()
            ? "오늘"
            : `${d.getMonth() + 1}/${d.getDate()} (${DAYS_KO[d.getDay()]})`;
        upcomingList.push({
          date: label,
          sortKey: d.getTime() + ch,  // 같은 날이면 채널 번호순
          topic: item.topic,
          status: "대기",
          color: "text-blue-400 bg-blue-400/15",
          channel: item.channel || 1,
        });
        d.setDate(d.getDate() + 1);
      }
    }

    // 날짜순 정렬 (같은 날이면 채널 번호순)
    upcomingList.sort((a, b) => a.sortKey - b.sortKey);
  }

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
        <h1 className="text-xl font-bold text-white">스케줄</h1>
        <div className="flex items-center gap-3">
          {editingTime ? (
            <div className="flex items-center gap-2 bg-bg-secondary border border-border rounded-lg px-3 py-1.5">
              <Clock size={14} className="text-gray-500" />
              {(["1","2","3","4"] as const).map((ch) => (
                <div key={ch} className="flex items-center gap-1">
                  <span className={`text-[10px] font-bold ${
                    ch==="1"?"text-blue-400":ch==="2"?"text-green-400":ch==="3"?"text-amber-400":"text-purple-400"
                  }`}>{ch}</span>
                  <input
                    type="time"
                    value={channelTimes[ch] || ""}
                    onChange={(e) => setChannelTimes((p) => ({...p, [ch]: e.target.value}))}
                    className="text-xs bg-transparent text-white outline-none w-[70px]"
                  />
                </div>
              ))}
              <button
                onClick={handleSaveTime}
                disabled={saving}
                className="flex items-center gap-1 text-[10px] bg-accent-primary text-white rounded px-2 py-1"
              >
                {saving ? <Loader2 size={10} className="animate-spin" /> : <Save size={10} />}
                저장
              </button>
              <button onClick={() => setEditingTime(false)} className="text-gray-500 hover:text-gray-300">✕</button>
            </div>
          ) : (
            <button
              onClick={() => setEditingTime(true)}
              className="flex items-center gap-2 bg-bg-secondary border border-border rounded-lg px-3 py-2 hover:bg-bg-tertiary transition-colors"
            >
              <Clock size={14} className="text-gray-500" />
              <span className="text-xs text-gray-400">채널별 실행:</span>
              <span className="text-sm font-bold text-accent-primary">
                {hasAnySchedule ? Object.entries(queue?.channel_times || {}).filter(([,v])=>!!v).map(([k,v])=>`CH${k} ${v}`).join(" / ") : "꺼짐"}
              </span>
              <Pencil size={10} className="text-gray-500" />
            </button>
          )}
        </div>
      </div>

      {/* 본체: 캘린더 + 예정 리스트 */}
      <div className="grid grid-cols-[1fr_360px] gap-5">
        {/* 캘린더 */}
        <div className="bg-bg-secondary border border-border rounded-xl p-5">
          <div className="flex items-center gap-4 mb-5">
            <button
              onClick={prevMonth}
              className="p-1.5 rounded-lg hover:bg-bg-tertiary text-gray-400 transition-colors"
            >
              <ChevronLeft size={18} />
            </button>
            <h2 className="text-lg font-bold text-white">
              {viewYear}년 {viewMonth + 1}월
            </h2>
            <button
              onClick={nextMonth}
              className="p-1.5 rounded-lg hover:bg-bg-tertiary text-gray-400 transition-colors"
            >
              <ChevronRight size={18} />
            </button>
          </div>

          {/* 요일 헤더 */}
          <div className="grid grid-cols-7 gap-1.5 mb-2">
            {DAYS_KO.map((d, i) => (
              <div
                key={d}
                className={`text-center text-[11px] font-semibold py-1.5 ${
                  i === 0
                    ? "text-accent-danger"
                    : i === 6
                      ? "text-blue-400"
                      : "text-gray-600"
                }`}
              >
                {d}
              </div>
            ))}
          </div>

          {/* 날짜 그리드 */}
          <div className="grid grid-cols-7 gap-1.5">
            {/* 빈 칸 */}
            {Array.from({ length: firstDay }).map((_, i) => (
              <div key={`e-${i}`} className="h-[72px]" />
            ))}
            {/* 날짜 */}
            {Array.from({ length: daysInMonth }).map((_, i) => {
              const day = i + 1;
              const isToday = isCurrentMonth && day === today.getDate();
              const status = dayStatusMap.get(day);
              const channels = Array.from(dayChannelsMap.get(day) || []).sort();
              const chColor = (c: number) =>
                c === 1 ? "text-blue-400 bg-blue-400/15"
                  : c === 2 ? "text-green-400 bg-green-400/15"
                  : c === 3 ? "text-amber-400 bg-amber-400/15"
                  : "text-purple-400 bg-purple-400/15";
              return (
                <div
                  key={day}
                  className={`h-[72px] rounded-lg p-2 ${
                    isToday
                      ? "bg-accent-primary/10 border border-accent-primary/40"
                      : status === "completed"
                        ? "bg-accent-success/[0.05]"
                        : "bg-bg-primary/50"
                  }`}
                >
                  <div
                    className={`text-xs ${
                      isToday
                        ? "text-accent-primary font-bold"
                        : "text-gray-300 font-medium"
                    }`}
                  >
                    {day}
                  </div>
                  {status === "completed" && (
                    <div className="text-[9px] text-accent-success font-medium mt-1">
                      ✓ 완료
                    </div>
                  )}
                  {status === "failed" && (
                    <div className="text-[9px] text-accent-danger font-medium mt-1">
                      ✕ 실패
                    </div>
                  )}
                  {status === "running" && (
                    <div className="text-[9px] text-amber-400 font-medium mt-1">
                      ▶ 진행 중
                    </div>
                  )}
                  {/* v1.1.60: 예약됨 라벨 대신 채널 번호 뱃지 표시 */}
                  {channels.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {channels.map((c) => (
                        <span
                          key={c}
                          className={`text-[9px] font-bold px-1 py-0.5 rounded ${chColor(c)}`}
                        >
                          CH{c}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* 예정된 업로드 */}
        <div className="bg-bg-secondary border border-border rounded-xl p-5">
          <h3 className="text-sm font-bold text-white mb-4 pb-3 border-b border-border">
            예정된 업로드
          </h3>
          {upcomingList.length === 0 ? (
            <div className="text-xs text-gray-500 text-center py-10">
              예정된 항목이 없습니다.
            </div>
          ) : (
            <div className="space-y-3">
              {upcomingList.map((item, i) => (
                <div
                  key={i}
                  className="bg-bg-primary/50 rounded-lg p-3"
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-[11px] text-gray-400 font-semibold">
                      {item.date}
                    </span>
                    <span
                      className={`text-[10px] font-medium px-2 py-0.5 rounded ${item.color}`}
                    >
                      {item.status}
                    </span>
                  </div>
                  <div className="text-xs text-gray-200 font-medium">
                    {item.topic}
                  </div>
                  {hasAnySchedule && (
                    <div className="text-[10px] text-gray-600 mt-1">
                      <span className={`font-bold ${
                        item.channel === 1 ? "text-blue-400" : item.channel === 2 ? "text-green-400" :
                        item.channel === 3 ? "text-amber-400" : "text-purple-400"
                      }`}>CH{item.channel}</span> 업로드 예정
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
