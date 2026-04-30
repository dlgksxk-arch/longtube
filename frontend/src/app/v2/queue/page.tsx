/**
 * /v2/queue — 딸깍 제작 큐 (기획 §11).
 *
 * v2.2.0:
 *   - 채널 탭 (전체/CH1~CH4) 필터
 *   - "추가" 모달: 프리셋 드롭다운 + EP.XX read-only (preview-episode)
 *     + 멀티라인 주제 textarea
 *   - 리스트 행: EP.XX · 주제 · 상태 · 삭제
 */
"use client";

import { useCallback, useEffect, useId, useMemo, useState } from "react";
import { channelColor } from "@/lib/channelColor";
import { v2Url } from "@/lib/v2Api";
import {
  Modal,
  ConfirmDialog,
  EmptyState,
  LoadingState,
  ErrorState,
  StatusDot,
  V2Button,
} from "@/components/v2";

interface QueueItem {
  id: number;
  preset_id: number;
  channel_id: number;
  episode_no: number | null;
  topic_raw: string;
  topic_polished: string | null;
  status: string;
  scheduled_at: string | null;
  created_at: string | null;
}

/** `datetime-local` input 이 쓰는 형식 `YYYY-MM-DDTHH:MM` (로컬). */
function toLocalInputValue(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** 로컬 `datetime-local` 입력값을 ISO 문자열로. 빈 문자열이면 null. */
function fromLocalInputValue(v: string): string | null {
  if (!v) return null;
  const d = new Date(v); // `YYYY-MM-DDTHH:MM` 은 로컬로 파싱됨.
  if (Number.isNaN(d.getTime())) return null;
  return d.toISOString();
}

/** "MM-DD HH:MM" 표시용. */
function fmtScheduled(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

interface PresetRow {
  id: number;
  channel_id: number;
  form_type: "딸깍폼" | "테스트폼";
  name: string;
  full_name: string;
}

type TabKey = "all" | 1 | 2 | 3 | 4;

const TABS: TabKey[] = ["all", 1, 2, 3, 4];

function statusTone(s: string): { dot: "ok" | "idle" | "fail" | "warn"; label: string } {
  if (s === "running") return { dot: "warn", label: "진행 중" };
  if (s === "done" || s === "success") return { dot: "ok", label: "완료" };
  if (s === "failed" || s === "error") return { dot: "fail", label: "실패" };
  if (s === "scheduled") return { dot: "idle", label: "예약" };
  return { dot: "idle", label: "대기" };
}

export default function V2QueuePage() {
  const idp = useId();
  const [items, setItems] = useState<QueueItem[] | null>(null);
  const [presets, setPresets] = useState<PresetRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState<TabKey>("all");

  // 추가 모달.
  const [addOpen, setAddOpen] = useState(false);
  const [addPresetId, setAddPresetId] = useState<number | null>(null);
  const [addTopic, setAddTopic] = useState("");
  const [addPreviewEp, setAddPreviewEp] = useState<number | null>(null);
  const [addSubmitting, setAddSubmitting] = useState(false);
  const [addErr, setAddErr] = useState<string | null>(null);

  // 삭제 확인.
  const [delTarget, setDelTarget] = useState<QueueItem | null>(null);

  // 예약 편집 모달.
  const [schedTarget, setSchedTarget] = useState<QueueItem | null>(null);
  const [schedValue, setSchedValue] = useState<string>("");
  const [schedSubmitting, setSchedSubmitting] = useState(false);
  const [schedErr, setSchedErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const [qRes, pRes] = await Promise.all([
        fetch(v2Url("/v2/queue/")),
        fetch(v2Url("/v2/presets/")),
      ]);
      if (!qRes.ok) throw new Error(`queue HTTP ${qRes.status}`);
      if (!pRes.ok) throw new Error(`presets HTTP ${pRes.status}`);
      setItems(await qRes.json());
      setPresets(await pRes.json());
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(() => {
    if (!items) return [];
    if (tab === "all") return items;
    return items.filter((i) => i.channel_id === tab);
  }, [items, tab]);

  // 모달에서 프리셋을 고를 때마다 EP 미리보기를 새로고침한다.
  const selectedPreset = useMemo(
    () => presets?.find((p) => p.id === addPresetId) ?? null,
    [presets, addPresetId],
  );
  useEffect(() => {
    setAddPreviewEp(null);
    if (!addOpen || !selectedPreset) return;
    if (selectedPreset.form_type !== "딸깍폼") {
      // 테스트폼은 EP 없음.
      return;
    }
    let cancelled = false;
    fetch(v2Url(`/v2/queue/preview-episode/${selectedPreset.channel_id}`))
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j) => {
        if (!cancelled) setAddPreviewEp(j.next_episode_no);
      })
      .catch(() => {
        if (!cancelled) setAddPreviewEp(null);
      });
    return () => {
      cancelled = true;
    };
  }, [addOpen, selectedPreset]);

  const openAdd = () => {
    setAddPresetId(null);
    setAddTopic("");
    setAddPreviewEp(null);
    setAddErr(null);
    setAddOpen(true);
  };

  const submitAdd = async () => {
    if (!addPresetId || !addTopic.trim()) return;
    setAddSubmitting(true);
    setAddErr(null);
    try {
      const res = await fetch(v2Url("/v2/queue/"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          preset_id: addPresetId,
          topic_raw: addTopic,
        }),
      });
      if (!res.ok) {
        const txt = await res.text();
        throw new Error(`HTTP ${res.status} ${txt}`);
      }
      setAddOpen(false);
      await load();
    } catch (e) {
      setAddErr(e instanceof Error ? e.message : String(e));
    } finally {
      setAddSubmitting(false);
    }
  };

  const doDelete = async () => {
    if (!delTarget) return;
    try {
      const res = await fetch(v2Url(`/v2/queue/${delTarget.id}`), {
        method: "DELETE",
      });
      if (!res.ok && res.status !== 204) {
        throw new Error(`HTTP ${res.status}`);
      }
      setDelTarget(null);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setDelTarget(null);
    }
  };

  const openSchedule = (q: QueueItem) => {
    setSchedTarget(q);
    setSchedValue(toLocalInputValue(q.scheduled_at));
    setSchedErr(null);
  };

  const submitSchedule = async (clear: boolean) => {
    if (!schedTarget) return;
    setSchedSubmitting(true);
    setSchedErr(null);
    try {
      const body = {
        scheduled_at: clear ? null : fromLocalInputValue(schedValue),
      };
      if (!clear && !body.scheduled_at) {
        throw new Error("예약 시각을 입력해 주세요.");
      }
      const res = await fetch(v2Url(`/v2/queue/${schedTarget.id}/schedule`), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const txt = await res.text();
        throw new Error(`HTTP ${res.status} ${txt}`);
      }
      setSchedTarget(null);
      await load();
    } catch (e) {
      setSchedErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSchedSubmitting(false);
    }
  };

  return (
    <div className="p-6 space-y-5">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-gray-100">제작 큐</h1>
          <p className="text-sm text-gray-500 mt-1">
            채널별 독립, 하루 1개 소비. EP.XX는 큐 추가 시점에 자동 확정됩니다.
          </p>
        </div>
        <V2Button variant="primary" onClick={openAdd}>
          + 추가
        </V2Button>
      </header>

      {/* 채널 탭 -------------------------------------------------------- */}
      <div className="flex items-center gap-1 border-b border-border">
        {TABS.map((t) => {
          const active = tab === t;
          const label = t === "all" ? "전체" : `CH${t}`;
          return (
            <button
              key={String(t)}
              type="button"
              onClick={() => setTab(t)}
              className={`px-3 py-1.5 text-sm border-b-2 -mb-px ${
                active
                  ? "border-sky-400 text-sky-200"
                  : "border-transparent text-gray-400 hover:text-gray-200"
              }`}
            >
              {label}
            </button>
          );
        })}
      </div>

      {err && <ErrorState message={err} onRetry={load} />}
      {!err && !items && <LoadingState />}

      {!err && items && filtered.length === 0 && (
        <EmptyState
          title="큐가 비어 있습니다"
          description='상단 "+ 추가" 버튼으로 제작 항목을 넣어 주세요.'
        />
      )}

      {!err && items && filtered.length > 0 && (
        <ul className="space-y-2">
          {filtered.map((q) => {
            const c = channelColor(q.channel_id);
            const tone = statusTone(q.status);
            const firstLine = q.topic_raw.split("\n")[0]?.slice(0, 120) ?? "";
            return (
              <li
                key={q.id}
                className="rounded-lg border border-border bg-bg-secondary px-4 py-3 flex items-center gap-3"
              >
                <span
                  className={`px-2 py-0.5 rounded-md text-xs font-semibold ${c.bgSoft} ${c.text} border ${c.border} shrink-0`}
                >
                  CH{q.channel_id}
                </span>
                <span className="px-2 py-0.5 rounded-md text-xs font-semibold bg-bg-tertiary text-gray-100 border border-border shrink-0">
                  {q.episode_no ? `EP.${String(q.episode_no).padStart(2, "0")}` : "—"}
                </span>
                <p className="flex-1 text-sm text-gray-100 truncate" title={firstLine}>
                  {firstLine}
                </p>
                {q.scheduled_at && (
                  <span
                    className="px-2 py-0.5 rounded-md text-[11px] font-mono tabular-nums bg-amber-500/10 text-amber-200 border border-amber-500/30 shrink-0"
                    title={new Date(q.scheduled_at).toLocaleString()}
                  >
                    {fmtScheduled(q.scheduled_at)}
                  </span>
                )}
                <StatusDot status={tone.dot} label={tone.label} />
                <V2Button
                  variant="ghost"
                  size="sm"
                  onClick={() => openSchedule(q)}
                  disabled={
                    q.status === "running" ||
                    q.status === "done" ||
                    q.status === "failed"
                  }
                >
                  {q.scheduled_at ? "예약 수정" : "예약"}
                </V2Button>
                <V2Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setDelTarget(q)}
                >
                  삭제
                </V2Button>
              </li>
            );
          })}
        </ul>
      )}

      {/* 추가 모달 ------------------------------------------------------ */}
      <Modal
        open={addOpen}
        onClose={() => !addSubmitting && setAddOpen(false)}
        title="큐에 추가"
        widthClass="w-[560px]"
        footer={
          <>
            <V2Button
              variant="secondary"
              onClick={() => setAddOpen(false)}
              disabled={addSubmitting}
            >
              취소
            </V2Button>
            <V2Button
              variant="primary"
              onClick={submitAdd}
              disabled={!addPresetId || !addTopic.trim() || addSubmitting}
              loading={addSubmitting}
            >
              추가
            </V2Button>
          </>
        }
      >
        <div className="space-y-4 text-sm">
          <div>
            <label
              htmlFor={`${idp}-preset`}
              className="block text-xs text-gray-400 mb-1"
            >
              프리셋
            </label>
            <select
              id={`${idp}-preset`}
              value={addPresetId ?? ""}
              onChange={(e) =>
                setAddPresetId(e.target.value ? Number(e.target.value) : null)
              }
              className="w-full bg-bg-tertiary border border-border rounded-md px-3 py-2 text-sm text-gray-100"
            >
              <option value="">— 프리셋을 선택하세요 —</option>
              {(presets ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.full_name}
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label
                htmlFor={`${idp}-ch`}
                className="block text-xs text-gray-400 mb-1"
              >
                채널
              </label>
              <input
                id={`${idp}-ch`}
                type="text"
                readOnly
                value={selectedPreset ? `CH${selectedPreset.channel_id}` : "—"}
                className="w-full bg-bg-primary border border-border rounded-md px-3 py-2 text-sm text-gray-400"
              />
            </div>
            <div>
              <label
                htmlFor={`${idp}-ep`}
                className="block text-xs text-gray-400 mb-1"
              >
                EP.XX (자동)
              </label>
              <input
                id={`${idp}-ep`}
                type="text"
                readOnly
                value={
                  !selectedPreset
                    ? "—"
                    : selectedPreset.form_type !== "딸깍폼"
                    ? "테스트폼은 EP 없음"
                    : addPreviewEp !== null
                    ? `EP.${String(addPreviewEp).padStart(2, "0")}`
                    : "계산 중..."
                }
                className="w-full bg-bg-primary border border-border rounded-md px-3 py-2 text-sm text-gray-400"
              />
            </div>
          </div>

          <div>
            <label
              htmlFor={`${idp}-topic`}
              className="block text-xs text-gray-400 mb-1"
            >
              주제 (멀티라인 자유 입력)
            </label>
            <textarea
              id={`${idp}-topic`}
              value={addTopic}
              onChange={(e) => setAddTopic(e.target.value)}
              rows={8}
              className="w-full bg-bg-tertiary border border-border rounded-md px-3 py-2 text-sm text-gray-100 font-mono"
              placeholder={
                "Ep.01 주제 - …\n첫대사 - …\n핵심소재 - …\n(원하는 만큼)"
              }
            />
            <p className="mt-1 text-xs text-gray-500">
              검증 없음. 첫 줄 제목 부분만 의미 보존 다듬기가 적용됩니다.
            </p>
          </div>

          {addErr && (
            <p
              role="alert"
              className="text-xs text-red-300 bg-red-500/10 border border-red-500/40 rounded-md px-3 py-2"
            >
              {addErr}
            </p>
          )}
        </div>
      </Modal>

      <ConfirmDialog
        open={!!delTarget}
        title="큐에서 삭제할까요?"
        description={
          delTarget
            ? `CH${delTarget.channel_id} ${
                delTarget.episode_no
                  ? `EP.${String(delTarget.episode_no).padStart(2, "0")}`
                  : "(테스트폼)"
              } 항목을 제거합니다.`
            : ""
        }
        confirmLabel="삭제"
        danger
        onConfirm={doDelete}
        onCancel={() => setDelTarget(null)}
      />

      {/* 예약 편집 모달 ----------------------------------------------- */}
      <Modal
        open={!!schedTarget}
        onClose={() => !schedSubmitting && setSchedTarget(null)}
        title={
          schedTarget?.scheduled_at ? "예약 수정" : "예약 시각 지정"
        }
        widthClass="w-[420px]"
        footer={
          <>
            <V2Button
              variant="secondary"
              onClick={() => setSchedTarget(null)}
              disabled={schedSubmitting}
            >
              취소
            </V2Button>
            {schedTarget?.scheduled_at && (
              <V2Button
                variant="danger"
                onClick={() => submitSchedule(true)}
                disabled={schedSubmitting}
                loading={schedSubmitting}
              >
                예약 해제
              </V2Button>
            )}
            <V2Button
              variant="primary"
              onClick={() => submitSchedule(false)}
              disabled={!schedValue || schedSubmitting}
              loading={schedSubmitting}
            >
              저장
            </V2Button>
          </>
        }
      >
        <div className="space-y-3 text-sm">
          {schedTarget && (
            <p className="text-xs text-gray-400">
              CH{schedTarget.channel_id}
              {schedTarget.episode_no
                ? ` · EP.${String(schedTarget.episode_no).padStart(2, "0")}`
                : " · (테스트폼)"}
            </p>
          )}
          <div>
            <label
              htmlFor={`${idp}-sched`}
              className="block text-xs text-gray-400 mb-1"
            >
              실행 예정 시각 (로컬)
            </label>
            <input
              id={`${idp}-sched`}
              type="datetime-local"
              value={schedValue}
              onChange={(e) => setSchedValue(e.target.value)}
              className="w-full bg-bg-tertiary border border-border rounded-md px-3 py-2 text-sm text-gray-100"
            />
            <p className="mt-1 text-xs text-gray-500">
              저장 시 상태가 &apos;pending&apos; → &apos;scheduled&apos; 로 승격됩니다.
              해제하면 다시 &apos;pending&apos; 으로 돌아갑니다. 달력(
              <span className="text-sky-300">/v2/schedule</span>) 에서 미래
              예약으로 표시됩니다.
            </p>
          </div>
          {schedErr && (
            <p
              role="alert"
              className="text-xs text-red-300 bg-red-500/10 border border-red-500/40 rounded-md px-3 py-2"
            >
              {schedErr}
            </p>
          )}
        </div>
      </Modal>
    </div>
  );
}
