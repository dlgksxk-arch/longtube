/**
 * /v2/presets — 프리셋 목록 (기획 §9).
 *
 * v2.3.0: 디자인 크리틱 결과 카드 정보 밀도를 복원한다.
 *   - 카드 1장에 채널 배지, 이름, 풀네임, 영상 길이, 언어 배지,
 *     모델 체인, 편당/월 추정 비용, 수정일, modified 뱃지, 편집 CTA.
 *   - 카드 크기: 2열 grid, min-h 180, rounded-xl, padding comfortable.
 *   - 모든 버튼은 V2Button 을 사용한다.
 *
 * v2.2.0 와의 차이:
 *   - 인라인 button 클래스 전부 V2Button 으로 교체.
 *   - config 메타(길이/비용/모델)를 presetMeta 헬퍼로 파싱.
 *   - 폼 label 에 htmlFor 를 붙여 접근성 향상.
 *   - 모달 내부 label/라디오는 고유 id 로 연결.
 */
"use client";

import Link from "next/link";
import { useEffect, useId, useMemo, useState } from "react";
import { channelColor } from "@/lib/channelColor";
import { v2Url } from "@/lib/v2Api";
import { fmtKrw, fmtUpdatedAt, parsePresetMeta } from "@/lib/presetMeta";
import {
  EmptyState,
  LoadingState,
  ErrorState,
  StatusDot,
  Modal,
  ConfirmDialog,
  V2Button,
} from "@/components/v2";

interface PresetRow {
  id: number;
  channel_id: number;
  form_type: "딸깍폼" | "테스트폼";
  name: string;
  full_name: string;
  is_modified: boolean;
  config?: Record<string, unknown>;
  updated_at?: string;
}

const CHANNELS = [1, 2, 3, 4] as const;
type ChannelId = (typeof CHANNELS)[number];
type InitMode = "A" | "B" | "C";

export default function V2PresetsPage() {
  const [rows, setRows] = useState<PresetRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // 초기화 모달 상태.
  const [initOpen, setInitOpen] = useState(false);
  const [initTargetCh, setInitTargetCh] = useState<ChannelId>(1);
  const [initMode, setInitMode] = useState<InitMode>("A");
  const [initName, setInitName] = useState("");
  const [initSourceId, setInitSourceId] = useState<number | null>(null);
  const [initSubmitting, setInitSubmitting] = useState(false);
  const [initErr, setInitErr] = useState<string | null>(null);

  // 2차 확인(ConfirmDialog).
  const [confirmOpen, setConfirmOpen] = useState(false);

  // 접근성: 폼 label/input 연결용 id prefix (React 18 useId).
  const idp = useId();

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(v2Url("/v2/presets/"));
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setRows(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const byChannel = (ch: number) =>
    (rows ?? []).find((r) => r.channel_id === ch && r.form_type === "딸깍폼");
  const testPresets = useMemo(
    () => (rows ?? []).filter((r) => r.form_type === "테스트폼"),
    [rows],
  );
  const otherChannelDdalkkaks = useMemo(
    () =>
      (rows ?? []).filter(
        (r) => r.form_type === "딸깍폼" && r.channel_id !== initTargetCh,
      ),
    [rows, initTargetCh],
  );

  const openInit = (ch: ChannelId) => {
    setInitTargetCh(ch);
    setInitMode("A");
    setInitName(`CH${ch} 기본`);
    setInitSourceId(null);
    setInitErr(null);
    setInitOpen(true);
  };

  /** 실제로 서버에 POST — 모달 내부 2차 확인 후 호출. */
  const submitInit = async () => {
    setInitSubmitting(true);
    setInitErr(null);
    try {
      let sourceConfig: Record<string, unknown> = {};
      if ((initMode === "B" || initMode === "C") && initSourceId !== null) {
        const src = await fetch(v2Url(`/v2/presets/${initSourceId}`));
        if (!src.ok) throw new Error(`소스 읽기 실패 HTTP ${src.status}`);
        const j = await src.json();
        sourceConfig = j.config ?? {};
      }
      const res = await fetch(v2Url("/v2/presets/"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          channel_id: initTargetCh,
          form_type: "딸깍폼",
          name: initName.trim() || `CH${initTargetCh} 기본`,
          config: sourceConfig,
        }),
      });
      if (!res.ok) {
        const txt = await res.text();
        throw new Error(`HTTP ${res.status} ${txt}`);
      }
      setInitOpen(false);
      setConfirmOpen(false);
      await load();
    } catch (e) {
      setInitErr(e instanceof Error ? e.message : String(e));
    } finally {
      setInitSubmitting(false);
    }
  };

  const canSubmit =
    !!initName.trim() &&
    (initMode === "A" ||
      ((initMode === "B" || initMode === "C") && initSourceId !== null));

  return (
    <div className="p-6 space-y-6">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-gray-100">프리셋</h1>
          <p className="text-sm text-gray-500 mt-1">
            채널 4개 딸깍폼 + 테스트폼. 단일 진실원.
          </p>
        </div>
      </header>

      {loading && <LoadingState message="프리셋을 불러오는 중입니다..." />}
      {error && <ErrorState message={error} onRetry={load} />}

      {!loading && !error && (
        <>
          {/* ─────────────────────────────────────── 채널별 딸깍폼 ── */}
          <section>
            <h2 className="text-gray-200 mb-3">채널별 딸깍폼</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {CHANNELS.map((ch) => {
                const c = channelColor(ch);
                const found = byChannel(ch);
                if (!found) {
                  return (
                    <EmptyChannelCard
                      key={ch}
                      ch={ch}
                      onInit={() => openInit(ch)}
                    />
                  );
                }
                const m = parsePresetMeta(found.config);
                return (
                  <article
                    key={ch}
                    className={`rounded-xl border ${c.border} ${c.bgSoft} p-5 flex flex-col gap-3`}
                    aria-labelledby={`${idp}-ch${ch}-title`}
                  >
                    {/* 헤더 — 채널 배지 + 상태 + modified */}
                    <div className="flex items-center gap-2">
                      <span
                        className={`px-2 py-0.5 rounded-md text-xs font-semibold ${c.bgSoft} ${c.text} border ${c.border}`}
                      >
                        CH{ch}
                      </span>
                      <span className="px-2 py-0.5 rounded-md text-xs bg-bg-tertiary text-gray-300 border border-border">
                        딸깍폼
                      </span>
                      {m.language && (
                        <span className="px-2 py-0.5 rounded-md text-xs bg-bg-tertiary text-gray-300 border border-border">
                          {m.language}
                        </span>
                      )}
                      {found.is_modified && (
                        <span className="px-2 py-0.5 rounded-md text-xs bg-amber-500/15 text-amber-300 border border-amber-500/30">
                          modified
                        </span>
                      )}
                      <span className="ml-auto">
                        <StatusDot status="ok" />
                      </span>
                    </div>

                    {/* 이름 */}
                    <div>
                      <h3
                        id={`${idp}-ch${ch}-title`}
                        className="text-gray-100 truncate"
                      >
                        {found.name}
                      </h3>
                      <p className="text-xs text-gray-500 truncate mt-0.5">
                        {found.full_name}
                      </p>
                    </div>

                    {/* meta grid — 영상 길이 / 편당 / 월 / 모델 */}
                    <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                      <MetaItem label="영상 길이" value={m.durationLabel ?? "—"} />
                      <MetaItem label="편당 비용" value={fmtKrw(m.perEpisodeKrw)} />
                      <MetaItem
                        label="월 추정"
                        value={fmtKrw(m.monthlyKrw)}
                      />
                      <MetaItem
                        label="모델 체인"
                        value={m.modelChain ?? "—"}
                        mono
                      />
                    </dl>

                    {/* 푸터 — 수정일 + CTA */}
                    <div className="mt-auto pt-2 flex items-center justify-between border-t border-border">
                      <span className="text-xs text-gray-500">
                        수정 {fmtUpdatedAt(found.updated_at)}
                      </span>
                      <Link href={`/v2/presets/${found.id}`} tabIndex={-1}>
                        <V2Button variant="primary" size="sm">
                          편집
                        </V2Button>
                      </Link>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>

          {/* ─────────────────────────────────────── 테스트폼 ──── */}
          <section>
            <h2 className="text-gray-200 mb-3">테스트폼</h2>
            {testPresets.length === 0 ? (
              <EmptyState
                title="테스트폼이 없습니다"
                description="v2.3.0: 프리셋 편집에서 새 테스트폼을 만들 수 있습니다."
              />
            ) : (
              <ul className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {testPresets.map((p) => {
                  const c = channelColor(p.channel_id);
                  const m = parsePresetMeta(p.config);
                  return (
                    <li
                      key={p.id}
                      className="rounded-xl border border-border bg-bg-secondary p-5 flex flex-col gap-3"
                    >
                      <div className="flex items-center gap-2">
                        <span
                          className={`px-2 py-0.5 rounded-md text-xs font-semibold ${c.bgSoft} ${c.text} border ${c.border}`}
                        >
                          CH{p.channel_id}
                        </span>
                        <span className="px-2 py-0.5 rounded-md text-xs bg-bg-tertiary text-gray-300 border border-border">
                          테스트폼
                        </span>
                        {m.language && (
                          <span className="px-2 py-0.5 rounded-md text-xs bg-bg-tertiary text-gray-300 border border-border">
                            {m.language}
                          </span>
                        )}
                      </div>
                      <div>
                        <h3 className="text-gray-100 truncate">{p.name}</h3>
                        <p className="text-xs text-gray-500 truncate mt-0.5">
                          {p.full_name}
                        </p>
                      </div>
                      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                        <MetaItem label="영상" value={m.durationLabel ?? "—"} />
                        <MetaItem label="편당" value={fmtKrw(m.perEpisodeKrw)} />
                      </dl>
                      <div className="mt-auto pt-2 flex items-center justify-between border-t border-border">
                        <span className="text-xs text-gray-500">
                          수정 {fmtUpdatedAt(p.updated_at)}
                        </span>
                        <Link href={`/v2/presets/${p.id}`} tabIndex={-1}>
                          <V2Button variant="secondary" size="sm">
                            편집
                          </V2Button>
                        </Link>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </>
      )}

      {/* ─────────────────────── 초기화 3-way 모달 (§9.2) ────────────────── */}
      <Modal
        open={initOpen}
        onClose={() => !initSubmitting && setInitOpen(false)}
        title={`CH${initTargetCh} 딸깍폼 초기화`}
        widthClass="w-[560px]"
        footer={
          <>
            <V2Button
              variant="secondary"
              onClick={() => setInitOpen(false)}
              disabled={initSubmitting}
            >
              취소
            </V2Button>
            <V2Button
              variant="primary"
              onClick={() => setConfirmOpen(true)}
              disabled={!canSubmit || initSubmitting}
              loading={initSubmitting}
            >
              만들기
            </V2Button>
          </>
        }
      >
        <div className="space-y-4 text-sm">
          <div>
            <label
              htmlFor={`${idp}-init-ch`}
              className="block text-xs text-gray-400 mb-1"
            >
              채널
            </label>
            <select
              id={`${idp}-init-ch`}
              value={initTargetCh}
              onChange={(e) =>
                setInitTargetCh(Number(e.target.value) as ChannelId)
              }
              className="w-full bg-bg-tertiary border border-border rounded-md px-3 py-2 text-sm text-gray-100"
            >
              {CHANNELS.map((ch) => (
                <option key={ch} value={ch}>
                  CH{ch}
                </option>
              ))}
            </select>
          </div>

          <fieldset className="space-y-2">
            <legend className="text-xs text-gray-400 mb-1">생성 방식</legend>

            <InitModeRadio
              id={`${idp}-mode-A`}
              name={`${idp}-init-mode`}
              checked={initMode === "A"}
              onChange={() => {
                setInitMode("A");
                setInitSourceId(null);
              }}
              title="A. 빈 프리셋으로 생성"
              hint="모든 섹션이 기본값으로 초기화됩니다."
            />

            <InitModeRadio
              id={`${idp}-mode-B`}
              name={`${idp}-init-mode`}
              checked={initMode === "B"}
              onChange={() => {
                setInitMode("B");
                setInitSourceId(null);
              }}
              title="B. 다른 CH 딸깍폼에서 복사"
            >
              {initMode === "B" &&
                (otherChannelDdalkkaks.length === 0 ? (
                  <p className="text-xs text-gray-500 mt-1">
                    복사할 수 있는 다른 채널 딸깍폼이 없습니다.
                  </p>
                ) : (
                  <select
                    aria-label="소스 딸깍폼 선택"
                    value={initSourceId ?? ""}
                    onChange={(e) =>
                      setInitSourceId(
                        e.target.value ? Number(e.target.value) : null,
                      )
                    }
                    className="mt-2 w-full bg-bg-primary border border-border rounded-md px-2 py-1.5 text-sm text-gray-100"
                  >
                    <option value="">— 소스를 선택하세요 —</option>
                    {otherChannelDdalkkaks.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.full_name}
                      </option>
                    ))}
                  </select>
                ))}
            </InitModeRadio>

            <InitModeRadio
              id={`${idp}-mode-C`}
              name={`${idp}-init-mode`}
              checked={initMode === "C"}
              onChange={() => {
                setInitMode("C");
                setInitSourceId(null);
              }}
              title="C. 테스트폼에서 복사"
            >
              {initMode === "C" &&
                (testPresets.length === 0 ? (
                  <p className="text-xs text-gray-500 mt-1">
                    복사할 수 있는 테스트폼이 없습니다.
                  </p>
                ) : (
                  <select
                    aria-label="소스 테스트폼 선택"
                    value={initSourceId ?? ""}
                    onChange={(e) =>
                      setInitSourceId(
                        e.target.value ? Number(e.target.value) : null,
                      )
                    }
                    className="mt-2 w-full bg-bg-primary border border-border rounded-md px-2 py-1.5 text-sm text-gray-100"
                  >
                    <option value="">— 소스를 선택하세요 —</option>
                    {testPresets.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.full_name}
                      </option>
                    ))}
                  </select>
                ))}
            </InitModeRadio>
          </fieldset>

          <div>
            <label
              htmlFor={`${idp}-init-name`}
              className="block text-xs text-gray-400 mb-1"
            >
              이름 (사용자 부분)
            </label>
            <input
              id={`${idp}-init-name`}
              type="text"
              value={initName}
              onChange={(e) => setInitName(e.target.value)}
              maxLength={64}
              className="w-full bg-bg-tertiary border border-border rounded-md px-3 py-2 text-sm text-gray-100"
              placeholder="예: 10분역공"
            />
            <p className="mt-1 text-xs text-gray-500">
              풀네임:{" "}
              <span className="text-gray-400">
                CH{initTargetCh}-딸깍폼-{initName.trim() || "…"}
              </span>
            </p>
          </div>

          {initErr && (
            <p
              role="alert"
              className="text-xs text-red-300 bg-red-500/10 border border-red-500/40 rounded-md px-3 py-2"
            >
              {initErr}
            </p>
          )}
        </div>
      </Modal>

      <ConfirmDialog
        open={confirmOpen}
        title="진짜 실행할까요?"
        description={
          initMode === "A"
            ? `CH${initTargetCh} 에 새 딸깍폼 "${initName.trim()}" 을 생성합니다.`
            : `CH${initTargetCh} 에 선택한 소스 내용을 복사해 딸깍폼 "${initName.trim()}" 을 생성합니다.`
        }
        confirmLabel="실행"
        cancelLabel="취소"
        onConfirm={submitInit}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}

/* ========================================================================= */
/* 서브 컴포넌트들                                                            */
/* ========================================================================= */

function MetaItem({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex flex-col min-w-0">
      <dt className="text-xs text-gray-500">{label}</dt>
      <dd
        className={`text-sm text-gray-200 truncate ${
          mono ? "font-mono text-[13px]" : ""
        }`}
        title={value}
      >
        {value}
      </dd>
    </div>
  );
}

function EmptyChannelCard({
  ch,
  onInit,
}: {
  ch: ChannelId;
  onInit: () => void;
}) {
  const c = channelColor(ch);
  return (
    <article
      className={`rounded-xl border border-dashed ${c.border} bg-bg-secondary/40 p-5 min-h-[220px] flex flex-col`}
      aria-label={`CH${ch} 딸깍폼 없음`}
    >
      <div className="flex items-center gap-2">
        <span
          className={`px-2 py-0.5 rounded-md text-xs font-semibold ${c.bgSoft} ${c.text} border ${c.border}`}
        >
          CH{ch}
        </span>
        <span className="px-2 py-0.5 rounded-md text-xs bg-bg-tertiary text-gray-300 border border-border">
          딸깍폼
        </span>
        <span className="ml-auto">
          <StatusDot status="idle" />
        </span>
      </div>
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <p className="text-sm text-gray-400">아직 딸깍폼이 없습니다.</p>
          <p className="text-xs text-gray-500 mt-1">
            초기화로 이 채널의 기본 프리셋을 만드세요.
          </p>
        </div>
      </div>
      <div className="pt-2 flex justify-end">
        <V2Button variant="primary" size="sm" onClick={onInit}>
          초기화
        </V2Button>
      </div>
    </article>
  );
}

function InitModeRadio({
  id,
  name,
  checked,
  onChange,
  title,
  hint,
  children,
}: {
  id: string;
  name: string;
  checked: boolean;
  onChange: () => void;
  title: string;
  hint?: string;
  children?: React.ReactNode;
}) {
  return (
    <label
      htmlFor={id}
      className={`flex items-start gap-3 p-3 rounded-md border cursor-pointer transition-colors ${
        checked
          ? "border-sky-500/60 bg-sky-500/10"
          : "border-border bg-bg-tertiary/50 hover:bg-bg-tertiary"
      }`}
    >
      <input
        id={id}
        type="radio"
        name={name}
        className="mt-1 accent-sky-500"
        checked={checked}
        onChange={onChange}
      />
      <div className="flex-1 min-w-0">
        <p className="text-gray-100">{title}</p>
        {hint && <p className="text-xs text-gray-500 mt-0.5">{hint}</p>}
        {children}
      </div>
    </label>
  );
}
