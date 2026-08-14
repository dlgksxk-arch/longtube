"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import {
  ArrowLeft,
  Clapperboard,
  Eye,
  FileAudio,
  FileJson,
  FileText,
  Film,
  HardDrive,
  Image as ImageIcon,
  Loader2,
  MousePointer2,
  Save,
  SlidersHorizontal,
  Subtitles,
  Tags,
  WandSparkles,
  X,
} from "lucide-react";
import {
  movieReviewApi,
  movieReviewArtifactUrl,
  type MovieReviewJob,
  type MoviePreviewShortsLayout,
} from "@/lib/api";

function formatDuration(seconds: number) {
  const total = Math.max(0, Math.round(seconds || 0));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remain = total % 60;
  return hours
    ? `${hours}:${String(minutes).padStart(2, "0")}:${String(remain).padStart(2, "0")}`
    : `${minutes}:${String(remain).padStart(2, "0")}`;
}

function fileName(path: string) {
  return String(path || "").split(/[\\/]/).filter(Boolean).pop() || path;
}

function movieTitleName(title: string) {
  return String(title || "").split(/[|｜]/, 1)[0].trim() || "영화 제목";
}

type PreviewTarget = {
  kind: string;
  path: string;
};

function previewMode(target: PreviewTarget): "video" | "audio" | "image" | "text" {
  const extension = target.path.split(".").pop()?.toLowerCase() || "";
  if (target.kind === "video") return "video";
  if (target.kind === "audio") return "audio";
  if (target.kind === "thumbnail" || ["jpg", "jpeg", "png", "webp", "gif"].includes(extension)) return "image";
  return "text";
}

function ArtifactPreviewModal({ job, target, onClose }: { job: MovieReviewJob; target: PreviewTarget; onClose: () => void }) {
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const mode = previewMode(target);
  const url = movieReviewArtifactUrl(job.job_id, target.kind);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [onClose]);

  useEffect(() => {
    if (mode !== "text") return;
    const controller = new AbortController();
    setLoading(true);
    setPreviewError("");
    fetch(url, { credentials: "include", signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`자료를 불러오지 못했습니다. (${response.status})`);
        const raw = await response.text();
        const isJson = target.path.toLowerCase().endsWith(".json") || ["metadata", "meta-tags-json", "research-metadata", "preview-script", "upload-metadata"].includes(target.kind);
        if (!isJson) return raw;
        try {
          return JSON.stringify(JSON.parse(raw), null, 2);
        } catch {
          return raw;
        }
      })
      .then(setContent)
      .catch((caught) => {
        if (caught instanceof DOMException && caught.name === "AbortError") return;
        setPreviewError(caught instanceof Error ? caught.message : String(caught));
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [mode, target.kind, target.path, url]);

  return (
    <div role="dialog" aria-modal="true" aria-label={`${fileName(target.path)} 미리보기`} className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm" onClick={onClose}>
      <section className="flex max-h-[92vh] w-full max-w-6xl flex-col overflow-hidden rounded-2xl border border-white/15 bg-bg-secondary shadow-2xl" onClick={(event) => event.stopPropagation()}>
        <header className="flex items-center gap-3 border-b border-white/10 px-5 py-4">
          <Eye size={18} className="shrink-0 text-accent-primary" />
          <h2 className="min-w-0 flex-1 truncate text-sm font-black text-white" title={target.path}>{fileName(target.path)}</h2>
          <button type="button" onClick={onClose} aria-label="미리보기 닫기" className="rounded-lg p-2 text-gray-400 hover:bg-white/10 hover:text-white"><X size={19} /></button>
        </header>
        <div className="min-h-0 flex-1 overflow-auto bg-black/40 p-4 lg:p-6">
          {mode === "video" && <video controls autoPlay className="mx-auto max-h-[76vh] w-full bg-black" src={url} />}
          {mode === "audio" && <div className="flex min-h-[220px] items-center justify-center"><audio controls autoPlay className="w-full max-w-3xl" src={url} /></div>}
          {mode === "image" && <img src={url} alt={fileName(target.path)} className="mx-auto max-h-[76vh] max-w-full object-contain" />}
          {mode === "text" && loading && <div className="flex min-h-[300px] items-center justify-center text-gray-400"><Loader2 size={24} className="animate-spin" /></div>}
          {mode === "text" && previewError && <div className="p-6 text-center text-red-300">{previewError}</div>}
          {mode === "text" && !loading && !previewError && <pre className="whitespace-pre-wrap break-words font-mono text-sm leading-6 text-gray-200">{content}</pre>}
        </div>
      </section>
    </div>
  );
}

function ArtifactRow({ job, kind, path, icon: Icon, onPreview }: { job: MovieReviewJob; kind: string; path: string; icon: typeof Film; onPreview: (target: PreviewTarget) => void }) {
  if (!path) return null;
  return (
    <button type="button" onClick={() => onPreview({ kind, path })} className="flex w-full items-center gap-3 rounded-xl border border-border bg-bg-primary/60 px-4 py-3 text-left text-sm text-gray-300 hover:border-accent-primary/50 hover:text-white">
      <Icon size={17} className="shrink-0 text-accent-primary" />
      <span className="min-w-0 flex-1 truncate">{fileName(path)}</span>
      <Eye size={15} className="shrink-0" />
    </button>
  );
}

type LayoutNumberKey = {
  [Key in keyof MoviePreviewShortsLayout]: MoviePreviewShortsLayout[Key] extends number ? Key : never;
}[keyof MoviePreviewShortsLayout];

type LayoutColorKey = {
  [Key in keyof MoviePreviewShortsLayout]: MoviePreviewShortsLayout[Key] extends string ? Key : never;
}[keyof MoviePreviewShortsLayout];

function LayoutNumberField({ label, field, value, min, max, suffix = "px", onChange }: {
  label: string;
  field: LayoutNumberKey;
  value: MoviePreviewShortsLayout;
  min: number;
  max: number;
  suffix?: string;
  onChange: (next: MoviePreviewShortsLayout) => void;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-bold text-gray-400">{label}</span>
      <div className="flex items-center rounded-lg border border-border bg-bg-primary/70 focus-within:border-accent-primary/60">
        <input
          type="number"
          min={min}
          max={max}
          value={value[field]}
          onChange={(event) => onChange({ ...value, [field]: Number(event.target.value) })}
          className="min-w-0 flex-1 bg-transparent px-3 py-2 text-sm font-bold text-white outline-none"
        />
        <span className="pr-3 text-xs text-gray-600">{suffix}</span>
      </div>
    </label>
  );
}

function LayoutColorField({ label, field, value, onChange }: {
  label: string;
  field: LayoutColorKey;
  value: MoviePreviewShortsLayout;
  onChange: (next: MoviePreviewShortsLayout) => void;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-bold text-gray-400">{label}</span>
      <div className="flex items-center gap-2 rounded-lg border border-border bg-bg-primary/70 px-2 py-1.5 focus-within:border-accent-primary/60">
        <input type="color" value={value[field]} onChange={(event) => onChange({ ...value, [field]: event.target.value })} className="h-7 w-9 cursor-pointer border-0 bg-transparent p-0" />
        <input value={value[field]} maxLength={7} onChange={(event) => onChange({ ...value, [field]: event.target.value })} className="min-w-0 flex-1 bg-transparent font-mono text-xs font-bold uppercase text-white outline-none" />
      </div>
    </label>
  );
}

type LayoutTextLayer = "hero" | "caption" | "movieTitle" | "channel";

const LAYOUT_TEXT_LAYERS: { key: LayoutTextLayer; label: string }[] = [
  { key: "hero", label: "히어로" },
  { key: "caption", label: "자막" },
  { key: "movieTitle", label: "영화 제목" },
  { key: "channel", label: "우리 채널명" },
];

function ShortsLayoutModal({ job, onClose, onSave }: {
  job: MovieReviewJob;
  onClose: () => void;
  onSave: (layout: MoviePreviewShortsLayout) => Promise<void>;
}) {
  const [layout, setLayout] = useState<MoviePreviewShortsLayout>({ ...job.shorts_layout });
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [previewCard, setPreviewCard] = useState(false);
  const [selectedLayer, setSelectedLayer] = useState<LayoutTextLayer>("hero");
  const previewCanvasRef = useRef<HTMLDivElement>(null);
  const textDragState = useRef<{ layer: LayoutTextLayer; x: number; y: number } | null>(null);
  const intertitleDragOffset = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !saving) onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [onClose, saving]);

  const submit = async () => {
    setSaving(true);
    setSaveError("");
    try {
      await onSave(layout);
      onClose();
    } catch (caught) {
      setSaveError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSaving(false);
    }
  };

  const percent = (value: number) => `${(value / layout.canvas_height) * 100}%`;
  const layerPosition = (layer: LayoutTextLayer, value: MoviePreviewShortsLayout) => {
    if (layer === "hero") return { x: value.title_center_x, y: value.title_top };
    if (layer === "caption") return { x: value.caption_center_x, y: value.caption_top };
    if (layer === "movieTitle") return { x: value.movie_title_center_x, y: value.movie_title_top };
    return { x: value.channel_center_x, y: value.channel_top };
  };
  const beginTextDrag = (layer: LayoutTextLayer, event: ReactPointerEvent<HTMLDivElement>) => {
    const bounds = previewCanvasRef.current?.getBoundingClientRect();
    if (!bounds) return;
    setSelectedLayer(layer);
    const pointerX = ((event.clientX - bounds.left) / bounds.width) * layout.canvas_width;
    const pointerY = ((event.clientY - bounds.top) / bounds.height) * layout.canvas_height;
    const current = layerPosition(layer, layout);
    textDragState.current = {
      layer,
      x: pointerX - current.x,
      y: pointerY - current.y,
    };
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {}
  };
  const moveTextLayer = (layer: LayoutTextLayer, event: ReactPointerEvent<HTMLDivElement>) => {
    const drag = textDragState.current;
    if (!drag || drag.layer !== layer) return;
    const bounds = previewCanvasRef.current?.getBoundingClientRect();
    if (!bounds) return;
    const pointerX = ((event.clientX - bounds.left) / bounds.width) * layout.canvas_width;
    const pointerY = ((event.clientY - bounds.top) / bounds.height) * layout.canvas_height;
    const x = Math.round(Math.max(80, Math.min(1000, pointerX - drag.x)));
    const requestedY = pointerY - drag.y;
    setLayout((current) => ({
      ...current,
      ...(layer === "hero"
        ? { title_center_x: x, title_top: Math.round(Math.max(0, Math.min(320, requestedY))) }
        : layer === "caption"
          ? { caption_center_x: x, caption_top: Math.round(Math.max(current.video_top + current.video_height, Math.min(1600, requestedY))) }
          : layer === "movieTitle"
            ? { movie_title_center_x: x, movie_title_top: Math.round(Math.max(1200, Math.min(1760, requestedY))) }
            : { channel_center_x: x, channel_top: Math.round(Math.max(1200, Math.min(1830, requestedY))) }),
    }));
  };
  const endTextDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    try {
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
    } catch {}
    textDragState.current = null;
  };
  const layerClass = (layer: LayoutTextLayer) =>
    `touch-none select-none rounded-sm ${selectedLayer === layer ? "ring-2 ring-cyan-400 ring-offset-1 ring-offset-black/40" : "hover:ring-1 hover:ring-white/60"}`;
  const beginIntertitleDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    const bounds = previewCanvasRef.current?.getBoundingClientRect();
    if (!bounds) return;
    intertitleDragOffset.current = {
      x: ((event.clientX - bounds.left) / bounds.width) * layout.canvas_width - layout.intertitle_text_center_x,
      y: ((event.clientY - bounds.top) / bounds.height) * layout.canvas_height - layout.intertitle_text_top,
    };
    try { event.currentTarget.setPointerCapture(event.pointerId); } catch {}
  };
  const moveIntertitle = (event: ReactPointerEvent<HTMLDivElement>) => {
    const offset = intertitleDragOffset.current;
    const bounds = previewCanvasRef.current?.getBoundingClientRect();
    if (!offset || !bounds) return;
    const x = ((event.clientX - bounds.left) / bounds.width) * layout.canvas_width - offset.x;
    const y = ((event.clientY - bounds.top) / bounds.height) * layout.canvas_height - offset.y;
    setLayout((current) => ({
      ...current,
      intertitle_text_center_x: Math.round(Math.max(80, Math.min(1000, x))),
      intertitle_text_top: Math.round(Math.max(120, Math.min(1680, y))),
    }));
  };
  const endIntertitleDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    intertitleDragOffset.current = null;
    try {
      if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    } catch {}
  };
  const movieDisplayTitle = movieTitleName(job.title);
  return (
    <div role="dialog" aria-modal="true" aria-label="숏츠 화면 레이아웃 설정" className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 p-3 backdrop-blur-sm lg:p-6" onClick={() => !saving && onClose()}>
      <section className="flex max-h-[94vh] w-full max-w-6xl flex-col overflow-hidden rounded-2xl border border-white/15 bg-bg-secondary shadow-2xl" onClick={(event) => event.stopPropagation()}>
        <header className="flex items-center gap-3 border-b border-white/10 px-5 py-4">
          <SlidersHorizontal size={19} className="text-accent-primary" />
          <div className="min-w-0 flex-1">
            <h2 className="text-base font-black text-white">숏츠 화면 레이아웃 설정</h2>
            <p className="mt-0.5 text-xs text-gray-500">이 수집 자료의 Remotion 1080×1920 예고 숏츠에 저장됩니다.</p>
          </div>
          <button type="button" onClick={onClose} disabled={saving} aria-label="레이아웃 설정 닫기" className="rounded-lg p-2 text-gray-400 hover:bg-white/10 hover:text-white disabled:opacity-40"><X size={19} /></button>
        </header>

        <div className="grid min-h-0 flex-1 overflow-auto lg:grid-cols-[340px_minmax(0,1fr)]">
          <div className="border-b border-white/10 bg-black/20 p-5 lg:border-b-0 lg:border-r">
            <div className="mb-3 flex items-center justify-between">
              <span className="text-xs font-black text-gray-300">실시간 미리보기</span>
              <div className="flex rounded-lg border border-border bg-bg-primary p-1 text-[11px] font-black">
                <button type="button" onClick={() => setPreviewCard(false)} className={`rounded px-2 py-1 ${!previewCard ? "bg-accent-primary text-white" : "text-gray-500"}`}>영상 화면</button>
                <button type="button" onClick={() => setPreviewCard(true)} className={`rounded px-2 py-1 ${previewCard ? "bg-accent-primary text-white" : "text-gray-500"}`}>타이핑 화면</button>
              </div>
            </div>
            <div className="mb-3 grid grid-cols-2 gap-1.5">
              {LAYOUT_TEXT_LAYERS.map((layer) => (
                <button
                  key={layer.key}
                  type="button"
                  onClick={() => { setPreviewCard(false); setSelectedLayer(layer.key); }}
                  className={`rounded-lg border px-2 py-2 text-xs font-black ${selectedLayer === layer.key && !previewCard ? "border-cyan-400 bg-cyan-400/15 text-cyan-200" : "border-border bg-bg-primary/60 text-gray-500 hover:text-white"}`}
                >
                  {layer.label}
                </button>
              ))}
            </div>
            <div ref={previewCanvasRef} className="mx-auto aspect-[9/16] w-full max-w-[270px] overflow-hidden rounded-lg border border-white/15 shadow-xl" style={{ position: "relative", backgroundColor: previewCard ? layout.intertitle_background_color : layout.background_color }}>
              {previewCard ? (
                <div
                  data-testid="layout-layer-intertitle-caption"
                  className="absolute w-[90%] touch-none select-none rounded-sm px-5 text-center font-black ring-2 ring-cyan-400 ring-offset-1 ring-offset-black/40 active:cursor-grabbing"
                  style={{ left: `${(layout.intertitle_text_center_x / layout.canvas_width) * 100}%`, transform: "translateX(-50%)", top: percent(layout.intertitle_text_top), color: layout.intertitle_text_color, fontSize: layout.intertitle_font_size / 4, lineHeight: 1.2, WebkitTextStroke: `${layout.intertitle_outline_width / 4}px ${layout.intertitle_outline_color}`, cursor: "grab" }}
                  onPointerDown={beginIntertitleDrag}
                  onPointerMove={moveIntertitle}
                  onPointerUp={endIntertitleDrag}
                >
                  작품의 핵심을<br />3컷마다 설명합니다.
                </div>
              ) : (
                <>
                  <div
                    data-testid="layout-layer-hero"
                    className={`absolute w-full px-2 text-center font-black leading-[1.03] text-white active:cursor-grabbing ${layerClass("hero")}`}
                    style={{ left: `${(layout.title_center_x / layout.canvas_width) * 100}%`, transform: "translateX(-50%)", top: percent(layout.title_top), fontSize: layout.title_font_size / 4, WebkitTextStroke: "2px #000", cursor: "grab" }}
                    onPointerDown={(event) => beginTextDrag("hero", event)}
                    onPointerMove={(event) => moveTextLayer("hero", event)}
                    onPointerUp={endTextDrag}
                  >
                    {(job.hero_copy?.lines || ["오늘의 영화 예고", "핵심 장면 공개", "지금 시작합니다"]).map((line, index) => <div key={`${line}-${index}`} style={{ color: index === 1 ? layout.title_accent_color : "#ffffff" }}>{line}</div>)}
                  </div>
                  <div className="absolute left-0 w-full overflow-hidden bg-black bg-cover bg-center" style={{ top: percent(layout.video_top), height: percent(layout.video_height), backgroundImage: job.thumbnail_path ? `url(${movieReviewArtifactUrl(job.job_id, "thumbnail")})` : undefined }}>
                    {!job.thumbnail_path && <div className="flex h-full items-center justify-center text-xs text-gray-600">영상 표현 구간</div>}
                  </div>
                  <div
                    data-testid="layout-layer-caption"
                    className={`absolute flex w-[90%] items-center justify-center text-center font-black text-white active:cursor-grabbing ${layerClass("caption")}`}
                    style={{ left: `${(layout.caption_center_x / layout.canvas_width) * 100}%`, transform: "translateX(-50%)", top: percent(layout.caption_top), minHeight: "9.9%", fontSize: layout.caption_font_size / 4, WebkitTextStroke: `${layout.caption_outline_width / 4}px ${layout.caption_outline_color}`, cursor: "grab" }}
                    onPointerDown={(event) => beginTextDrag("caption", event)}
                    onPointerMove={(event) => moveTextLayer("caption", event)}
                    onPointerUp={endTextDrag}
                  >
                    <span className="rounded px-2 py-1" style={{ backgroundColor: `${layout.caption_background_color}${Math.round(layout.caption_background_opacity * 2.55).toString(16).padStart(2, "0")}` }}>대사 싱크 자막</span>
                  </div>
                  <div
                    data-testid="layout-layer-movie-title"
                    className={`absolute w-[90%] text-center font-black active:cursor-grabbing ${layerClass("movieTitle")}`}
                    style={{ left: `${(layout.movie_title_center_x / layout.canvas_width) * 100}%`, transform: "translateX(-50%)", top: percent(layout.movie_title_top), fontSize: layout.movie_title_font_size / 4, color: layout.movie_title_color, WebkitTextStroke: `${layout.movie_title_outline_width / 4}px ${layout.movie_title_outline_color}`, cursor: "grab" }}
                    onPointerDown={(event) => beginTextDrag("movieTitle", event)}
                    onPointerMove={(event) => moveTextLayer("movieTitle", event)}
                    onPointerUp={endTextDrag}
                  >
                    {movieDisplayTitle}
                  </div>
                  <div
                    data-testid="layout-layer-channel"
                    className={`absolute w-[90%] text-center font-black active:cursor-grabbing ${layerClass("channel")}`}
                    style={{ left: `${(layout.channel_center_x / layout.canvas_width) * 100}%`, transform: "translateX(-50%)", top: percent(layout.channel_top), fontSize: layout.channel_font_size / 4, color: layout.channel_color, cursor: "grab" }}
                    onPointerDown={(event) => beginTextDrag("channel", event)}
                    onPointerMove={(event) => moveTextLayer("channel", event)}
                    onPointerUp={endTextDrag}
                  >
                    우리 채널명
                  </div>
                </>
              )}
            </div>
          </div>

          <div className="space-y-6 p-5 lg:p-6">
            <section>
              <h3 className="mb-1 text-sm font-black text-white">텍스트 레이어 선택</h3>
              <p className="mb-3 flex items-center gap-1.5 text-xs text-cyan-300"><MousePointer2 size={13} /> 분류를 선택한 뒤 미리보기 문구를 마우스로 끌어 이동합니다.</p>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {LAYOUT_TEXT_LAYERS.map((layer) => (
                  <button
                    key={layer.key}
                    type="button"
                    onClick={() => { setPreviewCard(false); setSelectedLayer(layer.key); }}
                    className={`rounded-xl border px-3 py-3 text-xs font-black ${selectedLayer === layer.key ? "border-cyan-400 bg-cyan-400/15 text-cyan-200" : "border-border bg-bg-primary/60 text-gray-500 hover:text-white"}`}
                  >
                    {layer.label}
                  </button>
                ))}
              </div>
              <div className="mt-4 rounded-xl border border-border bg-bg-primary/35 p-4">
                <div className="mb-3 text-xs font-black text-white">{LAYOUT_TEXT_LAYERS.find((layer) => layer.key === selectedLayer)?.label} 설정</div>
                {selectedLayer === "hero" && (
                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                    <LayoutNumberField label="가운데 위치 X" field="title_center_x" value={layout} min={80} max={1000} onChange={setLayout} />
                    <LayoutNumberField label="위치 Y" field="title_top" value={layout} min={0} max={320} onChange={setLayout} />
                    <LayoutNumberField label="글자 크기" field="title_font_size" value={layout} min={48} max={140} onChange={setLayout} />
                    <LayoutColorField label="강조 색상" field="title_accent_color" value={layout} onChange={setLayout} />
                  </div>
                )}
                {selectedLayer === "caption" && (
                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                    <LayoutNumberField label="가운데 위치 X" field="caption_center_x" value={layout} min={80} max={1000} onChange={setLayout} />
                    <LayoutNumberField label="위치 Y" field="caption_top" value={layout} min={900} max={1600} onChange={setLayout} />
                    <LayoutNumberField label="글자 크기" field="caption_font_size" value={layout} min={42} max={100} onChange={setLayout} />
                    <LayoutNumberField label="배경 투명도" field="caption_background_opacity" value={layout} min={0} max={100} suffix="%" onChange={setLayout} />
                    <LayoutColorField label="배경 색상" field="caption_background_color" value={layout} onChange={setLayout} />
                    <LayoutNumberField label="외곽선 굵기" field="caption_outline_width" value={layout} min={0} max={15} onChange={setLayout} />
                    <LayoutColorField label="외곽선 색상" field="caption_outline_color" value={layout} onChange={setLayout} />
                  </div>
                )}
                {selectedLayer === "movieTitle" && (
                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                    <LayoutNumberField label="가운데 위치 X" field="movie_title_center_x" value={layout} min={80} max={1000} onChange={setLayout} />
                    <LayoutNumberField label="위치 Y" field="movie_title_top" value={layout} min={1200} max={1760} onChange={setLayout} />
                    <LayoutNumberField label="글자 크기" field="movie_title_font_size" value={layout} min={36} max={96} onChange={setLayout} />
                    <LayoutColorField label="글자 색상" field="movie_title_color" value={layout} onChange={setLayout} />
                    <LayoutNumberField label="외곽선 굵기" field="movie_title_outline_width" value={layout} min={0} max={12} onChange={setLayout} />
                    <LayoutColorField label="외곽선 색상" field="movie_title_outline_color" value={layout} onChange={setLayout} />
                  </div>
                )}
                {selectedLayer === "channel" && (
                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                    <LayoutNumberField label="가운데 위치 X" field="channel_center_x" value={layout} min={80} max={1000} onChange={setLayout} />
                    <LayoutNumberField label="위치 Y" field="channel_top" value={layout} min={1200} max={1830} onChange={setLayout} />
                    <LayoutNumberField label="글자 크기" field="channel_font_size" value={layout} min={42} max={120} onChange={setLayout} />
                    <LayoutColorField label="글자 색상" field="channel_color" value={layout} onChange={setLayout} />
                  </div>
                )}
              </div>
            </section>
            <section>
              <h3 className="mb-3 text-sm font-black text-white">영상 표현 구간</h3>
              <div className="grid gap-3 sm:grid-cols-3">
                <LayoutNumberField label="위치 Y" field="video_top" value={layout} min={280} max={700} onChange={setLayout} />
                <LayoutNumberField label="높이" field="video_height" value={layout} min={480} max={1050} onChange={setLayout} />
                <LayoutColorField label="화면 배경" field="background_color" value={layout} onChange={setLayout} />
              </div>
            </section>
            <section>
              <h3 className="mb-1 text-sm font-black text-white">설명 카드 자막</h3>
              <p className="mb-3 flex items-center gap-1.5 text-xs text-cyan-300"><MousePointer2 size={13} /> 타이핑 화면을 선택하면 자막을 직접 드래그할 수 있습니다.</p>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                <LayoutColorField label="배경 색상" field="intertitle_background_color" value={layout} onChange={setLayout} />
                <LayoutNumberField label="가운데 위치 X" field="intertitle_text_center_x" value={layout} min={80} max={1000} onChange={setLayout} />
                <LayoutNumberField label="위치 Y" field="intertitle_text_top" value={layout} min={120} max={1680} onChange={setLayout} />
                <LayoutColorField label="글자 색상" field="intertitle_text_color" value={layout} onChange={setLayout} />
                <LayoutNumberField label="글자 크기" field="intertitle_font_size" value={layout} min={42} max={120} onChange={setLayout} />
                <LayoutNumberField label="외곽선 굵기" field="intertitle_outline_width" value={layout} min={0} max={15} onChange={setLayout} />
                <LayoutColorField label="외곽선 색상" field="intertitle_outline_color" value={layout} onChange={setLayout} />
              </div>
            </section>
            {saveError && <div className="rounded-lg border border-red-400/30 bg-red-400/10 px-4 py-3 text-sm text-red-300">{saveError}</div>}
          </div>
        </div>

        <footer className="flex justify-end gap-2 border-t border-white/10 px-5 py-4">
          <button type="button" onClick={onClose} disabled={saving} className="rounded-xl border border-border px-5 py-2.5 text-sm font-black text-gray-300 hover:bg-white/5 disabled:opacity-40">취소</button>
          <button type="button" onClick={() => void submit()} disabled={saving} className="inline-flex items-center gap-2 rounded-xl bg-accent-primary px-5 py-2.5 text-sm font-black text-white hover:opacity-90 disabled:opacity-50">{saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />} 설정 저장</button>
        </footer>
      </section>
    </div>
  );
}

function ThumbnailFrameModal({ job, onClose, onSave }: {
  job: MovieReviewJob;
  onClose: () => void;
  onSave: (timeSeconds: number) => Promise<void>;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const initialTime = Math.max(0, Number(job.thumbnail_time_seconds ?? Math.min(3, Math.max(0, job.duration_seconds - 0.1))));
  const [selectedTime, setSelectedTime] = useState(initialTime);
  const [duration, setDuration] = useState(Math.max(0, job.duration_seconds));
  const [timelineFrames, setTimelineFrames] = useState<{ time: number; image: string }[]>([]);
  const [timelineLoading, setTimelineLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const scrubbingRef = useRef(false);
  const manualSeekTargetRef = useRef<number | null>(initialTime);
  const videoUrl = movieReviewArtifactUrl(job.job_id, "video");

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !saving) onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [onClose, saving]);

  useEffect(() => {
    let cancelled = false;
    const source = document.createElement("video");
    source.preload = "auto";
    source.muted = true;
    source.playsInline = true;
    source.src = videoUrl;

    const waitFor = (eventName: "loadedmetadata" | "loadeddata" | "seeked") => new Promise<void>((resolve, reject) => {
      const done = () => { cleanup(); resolve(); };
      const failed = () => { cleanup(); reject(new Error("타임라인 프레임을 불러오지 못했습니다.")); };
      const cleanup = () => {
        source.removeEventListener(eventName, done);
        source.removeEventListener("error", failed);
      };
      source.addEventListener(eventName, done, { once: true });
      source.addEventListener("error", failed, { once: true });
    });

    const buildFilmstrip = async () => {
      setTimelineLoading(true);
      try {
        if (source.readyState < 1) await waitFor("loadedmetadata");
        if (source.readyState < 2) await waitFor("loadeddata");
        const sourceDuration = Number.isFinite(source.duration) ? source.duration : job.duration_seconds;
        if (!sourceDuration || sourceDuration <= 0) return;
        const frameCount = 12;
        const canvas = document.createElement("canvas");
        canvas.width = 240;
        canvas.height = 135;
        const context = canvas.getContext("2d");
        if (!context) return;
        const frames: { time: number; image: string }[] = [];
        for (let index = 0; index < frameCount; index += 1) {
          if (cancelled) return;
          const time = Math.min(sourceDuration - 0.05, (sourceDuration * index) / Math.max(1, frameCount - 1));
          if (Math.abs(source.currentTime - time) > 0.02) {
            source.currentTime = Math.max(0, time);
            await waitFor("seeked");
          }
          context.drawImage(source, 0, 0, canvas.width, canvas.height);
          frames.push({ time, image: canvas.toDataURL("image/jpeg", 0.72) });
          if (!cancelled) setTimelineFrames([...frames]);
        }
      } catch {
        if (!cancelled) setTimelineFrames([]);
      } finally {
        if (!cancelled) setTimelineLoading(false);
        source.removeAttribute("src");
        source.load();
      }
    };
    void buildFilmstrip();
    return () => {
      cancelled = true;
      source.removeAttribute("src");
      source.load();
    };
  }, [job.duration_seconds, videoUrl]);

  const seek = (next: number) => {
    const maximum = Math.max(0, duration - 0.05);
    const value = Math.max(0, Math.min(maximum, next));
    setSelectedTime(value);
    if (videoRef.current) {
      videoRef.current.pause();
      manualSeekTargetRef.current = value;
      videoRef.current.currentTime = value;
    }
  };
  const seekFromTimelinePointer = (event: ReactPointerEvent<HTMLDivElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width));
    seek(ratio * Math.max(0, duration - 0.05));
  };
  const beginTimelineScrub = (event: ReactPointerEvent<HTMLDivElement>) => {
    scrubbingRef.current = true;
    videoRef.current?.pause();
    try { event.currentTarget.setPointerCapture(event.pointerId); } catch {}
    seekFromTimelinePointer(event);
  };
  const moveTimelineScrub = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!scrubbingRef.current) return;
    seekFromTimelinePointer(event);
  };
  const endTimelineScrub = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (scrubbingRef.current) seekFromTimelinePointer(event);
    scrubbingRef.current = false;
    try {
      if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    } catch {}
  };
  const submit = async () => {
    setSaving(true);
    setSaveError("");
    try {
      await onSave(selectedTime);
      onClose();
    } catch (caught) {
      setSaveError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div role="dialog" aria-modal="true" aria-label="영상에서 썸네일 선택" className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm" onClick={() => !saving && onClose()}>
      <section className="flex max-h-[92vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-white/15 bg-bg-secondary shadow-2xl" onClick={(event) => event.stopPropagation()}>
        <header className="flex items-center gap-3 border-b border-white/10 px-5 py-4">
          <ImageIcon size={19} className="text-accent-primary" />
          <div className="min-w-0 flex-1">
            <h2 className="text-base font-black text-white">영상에서 썸네일 선택</h2>
            <p className="mt-0.5 text-xs text-gray-500">프레임 타임라인을 좌우로 드래그해 원하는 장면을 선택합니다.</p>
          </div>
          <button type="button" onClick={onClose} disabled={saving} aria-label="썸네일 선택 닫기" className="rounded-lg p-2 text-gray-400 hover:bg-white/10 hover:text-white disabled:opacity-40"><X size={19} /></button>
        </header>
        <div className="min-h-0 flex-1 overflow-auto p-5 lg:p-6">
          <video
            ref={videoRef}
            controls
            preload="metadata"
            className="aspect-video w-full bg-black"
            src={videoUrl}
            onLoadedMetadata={(event) => {
              const loadedDuration = Number.isFinite(event.currentTarget.duration) ? event.currentTarget.duration : job.duration_seconds;
              setDuration(loadedDuration);
              const next = Math.min(initialTime, Math.max(0, loadedDuration - 0.05));
              manualSeekTargetRef.current = next;
              event.currentTarget.currentTime = next;
              setSelectedTime(next);
            }}
            onTimeUpdate={(event) => {
              if (manualSeekTargetRef.current != null) return;
              if (!scrubbingRef.current) setSelectedTime(event.currentTarget.currentTime);
            }}
            onSeeked={(event) => {
              const target = manualSeekTargetRef.current;
              if (target != null && Math.abs(event.currentTarget.currentTime - target) > 0.15) return;
              setSelectedTime(event.currentTarget.currentTime);
              manualSeekTargetRef.current = null;
            }}
          />
          <div className="mt-5 rounded-xl border border-border bg-bg-primary/60 p-4">
            <div className="mb-3 flex items-center justify-between text-sm">
              <span className="font-black text-white">장면 선택 타임라인</span>
              <span className="font-mono font-black text-accent-primary">{selectedTime.toFixed(1)}초 / {duration.toFixed(1)}초</span>
            </div>
            <div
              data-testid="thumbnail-filmstrip-timeline"
              className="relative h-24 touch-none overflow-hidden rounded-lg border border-white/15 bg-black"
              onPointerDown={beginTimelineScrub}
              onPointerMove={moveTimelineScrub}
              onPointerUp={endTimelineScrub}
              onPointerCancel={endTimelineScrub}
            >
              <div className="absolute inset-0 flex">
                {timelineFrames.length ? timelineFrames.map((frame, index) => (
                  <img key={`${frame.time}-${index}`} src={frame.image} alt="" className="h-full min-w-0 flex-1 object-cover" />
                )) : Array.from({ length: 12 }, (_, index) => <div key={index} className="h-full flex-1 border-r border-white/5 bg-white/5" />)}
              </div>
              {timelineLoading && <div className="absolute inset-0 flex items-center justify-center bg-black/55 text-xs font-bold text-gray-300"><Loader2 size={15} className="mr-2 animate-spin" /> 영상 프레임 구성 중</div>}
              <div className="pointer-events-none absolute inset-y-0 left-0 bg-cyan-400/10" style={{ width: `${duration > 0 ? (selectedTime / duration) * 100 : 0}%` }} />
              <div className="pointer-events-none absolute inset-y-0 w-0.5 bg-cyan-300 shadow-[0_0_10px_rgba(103,232,249,.95)]" style={{ left: `${duration > 0 ? (selectedTime / duration) * 100 : 0}%` }}>
                <div className="absolute left-1/2 top-1 -translate-x-1/2 rounded bg-cyan-300 px-1.5 py-0.5 font-mono text-[10px] font-black text-black">{selectedTime.toFixed(1)}s</div>
              </div>
              <input
                aria-label="썸네일 장면 타임라인"
                type="range"
                min={0}
                max={Math.max(0, duration - 0.05)}
                step={0.1}
                value={Math.min(selectedTime, Math.max(0, duration - 0.05))}
                onPointerDown={() => { scrubbingRef.current = true; videoRef.current?.pause(); }}
                onInput={(event) => seek(Number(event.currentTarget.value))}
                onChange={(event) => seek(Number(event.currentTarget.value))}
                onPointerUp={(event) => { seek(Number(event.currentTarget.value)); scrubbingRef.current = false; }}
                className="absolute inset-0 h-full w-full cursor-ew-resize opacity-0"
              />
            </div>
            <div className="mt-3 grid grid-cols-6 gap-1.5">
              {[-10, -1, -0.1, 0.1, 1, 10].map((amount) => (
                <button key={amount} type="button" onClick={() => seek(selectedTime + amount)} className="rounded-lg border border-border bg-bg-secondary px-2 py-2 text-xs font-black text-gray-300 hover:border-cyan-400/40 hover:text-white">
                  {amount > 0 ? "+" : ""}{amount}초
                </button>
              ))}
            </div>
            <div className="mt-3 flex items-center gap-3">
              <label htmlFor="thumbnail-time-seconds" className="text-xs font-bold text-gray-500">정확한 시점</label>
              <input id="thumbnail-time-seconds" aria-label="썸네일 선택 시간 초" type="number" min={0} max={Math.max(0, duration - 0.05)} step={0.1} value={selectedTime.toFixed(1)} onChange={(event) => seek(Number(event.target.value))} className="w-28 rounded-lg border border-border bg-bg-secondary px-3 py-2 font-mono text-sm font-black text-white outline-none focus:border-cyan-400/60" />
              <span className="text-xs text-gray-600">초</span>
            </div>
          </div>
          {saveError && <div className="mt-4 rounded-lg border border-red-400/30 bg-red-400/10 px-4 py-3 text-sm text-red-300">{saveError}</div>}
        </div>
        <footer className="flex justify-end gap-2 border-t border-white/10 px-5 py-4">
          <button type="button" onClick={onClose} disabled={saving} className="rounded-xl border border-border px-5 py-2.5 text-sm font-black text-gray-300 hover:bg-white/5 disabled:opacity-40">취소</button>
          <button type="button" onClick={() => void submit()} disabled={saving || !job.video_path || duration <= 0} className="inline-flex items-center gap-2 rounded-xl bg-accent-primary px-5 py-2.5 text-sm font-black text-white hover:opacity-90 disabled:opacity-50">{saving ? <Loader2 size={16} className="animate-spin" /> : <ImageIcon size={16} />} 이 장면을 썸네일로 저장</button>
        </footer>
      </section>
    </div>
  );
}

export default function MovieReviewWorkPage({ params }: { params: { jobId: string } }) {
  const [job, setJob] = useState<MovieReviewJob | null>(null);
  const [error, setError] = useState("");
  const [generating, setGenerating] = useState(false);
  const [previewTarget, setPreviewTarget] = useState<PreviewTarget | null>(null);
  const [layoutOpen, setLayoutOpen] = useState(false);
  const [thumbnailOpen, setThumbnailOpen] = useState(false);

  const load = useCallback(() => {
    return movieReviewApi.getJob(params.jobId)
      .then(setJob)
      .catch((caught) => setError(caught instanceof Error ? caught.message : String(caught)));
  }, [params.jobId]);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 2500);
    return () => window.clearInterval(timer);
  }, [load]);

  const generatePreview = async () => {
    setGenerating(true);
    setError("");
    try {
      const updated = await movieReviewApi.generatePreview(params.jobId);
      setJob(updated);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setGenerating(false);
    }
  };

  const saveShortsLayout = async (layout: MoviePreviewShortsLayout) => {
    const updated = await movieReviewApi.updateShortsLayout(params.jobId, layout);
    setJob(updated);
  };

  const saveThumbnailFrame = async (timeSeconds: number) => {
    const updated = await movieReviewApi.selectThumbnailFrame(params.jobId, timeSeconds);
    setJob(updated);
  };

  if (error) {
    return <div className="p-8 text-red-300">{error}</div>;
  }
  if (!job) {
    return <div className="flex h-full items-center justify-center text-gray-500"><Loader2 size={26} className="animate-spin" /></div>;
  }

  return (
    <div className="mx-auto w-full max-w-[1500px] px-4 py-5 lg:px-8 lg:py-8">
      <Link href="/oneclick/movie-review" className="inline-flex items-center gap-2 text-sm font-bold text-gray-400 hover:text-white"><ArrowLeft size={17} /> 수집 작업 게시판</Link>

      <header className="mt-5 flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <div className="rounded-xl bg-accent-primary/15 p-2.5 text-accent-primary"><Clapperboard size={24} /></div>
          <div className="min-w-0">
            <div className="text-xs font-black text-accent-primary">영화 예고 · {job.sequence_number}번</div>
            <h1 className="mt-1 truncate text-2xl font-black text-white lg:text-3xl">{job.title}</h1>
            <p className="mt-2 text-sm text-gray-500">{job.channel || "채널 정보 없음"} · {formatDuration(job.duration_seconds)} · {job.video_id}</p>
          </div>
        </div>
        <span className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-3 py-1.5 text-xs font-black text-emerald-300">수집 자료 연결 완료</span>
      </header>

      <div className="mt-7 grid gap-6 xl:grid-cols-[minmax(0,1.55fr)_minmax(340px,.75fr)]">
        <section className="overflow-hidden rounded-2xl border border-border bg-black shadow-2xl shadow-black/20">
          {job.video_path ? (
            <video controls preload="metadata" poster={job.thumbnail_path ? movieReviewArtifactUrl(job.job_id, "thumbnail") : undefined} className="aspect-video w-full bg-black" src={movieReviewArtifactUrl(job.job_id, "video")} />
          ) : (
            <div className="flex aspect-video items-center justify-center text-gray-700"><Film size={48} /></div>
          )}
          <div className="border-t border-white/10 bg-bg-secondary px-5 py-4">
            <div className="text-sm font-black text-white">원본 영상 확인</div>
            <div className="mt-1 text-xs text-gray-500">작품 기본 조사, 수집 메타데이터, 실제 자막을 함께 사용해 예고 대본을 구성합니다.</div>
          </div>
        </section>

        <aside className="space-y-5">
          <section className="rounded-2xl border border-border bg-bg-secondary p-5">
            <h2 className="text-base font-black text-white">작업 정보</h2>
            <dl className="mt-4 grid grid-cols-[100px_minmax(0,1fr)] gap-y-3 text-sm">
              <dt className="text-gray-500">순번</dt><dd className="font-bold text-gray-200">{job.sequence_number}</dd>
              <dt className="text-gray-500">폴더</dt><dd className="truncate font-bold text-gray-200" title={job.output_dir}>{job.folder_name}</dd>
              <dt className="text-gray-500">자막</dt><dd className="font-bold text-gray-200">{job.subtitle_paths.length}개</dd>
              <dt className="text-gray-500">메타태그</dt><dd className="font-bold text-gray-200">{job.tag_count}개</dd>
              <dt className="text-gray-500">작업 ID</dt><dd className="truncate text-xs text-gray-400">{job.job_id}</dd>
            </dl>
            <div className="mt-4 flex items-center gap-2 rounded-lg border border-border bg-bg-primary/60 px-3 py-2 text-xs text-gray-500" title={job.output_dir}><HardDrive size={14} className="shrink-0" /><span className="truncate">{job.output_dir}</span></div>
            <button
              type="button"
              onClick={() => void generatePreview()}
              disabled={generating || job.running || !job.subtitle_paths.length}
              className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-accent-primary px-4 py-3 text-sm font-black text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {generating || job.status === "generating_preview" ? <Loader2 size={17} className="animate-spin" /> : <WandSparkles size={17} />}
              {job.preview_script_path ? "예고 대본 다시 생성" : "예고 대본·업로드 메타 생성"}
            </button>
            <button
              type="button"
              onClick={() => setLayoutOpen(true)}
              className="mt-2 inline-flex w-full items-center justify-center gap-2 rounded-xl border border-accent-primary/40 bg-accent-primary/10 px-4 py-3 text-sm font-black text-accent-primary hover:bg-accent-primary/15"
            >
              <SlidersHorizontal size={17} /> 화면 레이아웃 설정
            </button>
            <button
              type="button"
              onClick={() => setThumbnailOpen(true)}
              disabled={!job.video_path || job.running}
              className="mt-2 inline-flex w-full items-center justify-center gap-2 rounded-xl border border-border bg-bg-primary/60 px-4 py-3 text-sm font-black text-gray-200 hover:border-accent-primary/40 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
            >
              <ImageIcon size={17} /> 영상에서 썸네일 선택
            </button>
            {job.thumbnail_source === "video_frame" && job.thumbnail_time_seconds != null && <div className="mt-2 text-center text-xs font-bold text-emerald-300">선택 프레임 {formatDuration(job.thumbnail_time_seconds)}</div>}
            {job.status === "generating_preview" && <div className="mt-2 text-center text-xs text-cyan-300">{job.message}</div>}
          </section>

          <section className="rounded-2xl border border-border bg-bg-secondary p-5">
            <h2 className="text-base font-black text-white">수집 자료</h2>
            <div className="mt-4 space-y-2">
              <ArtifactRow job={job} kind="video" path={job.video_path} icon={Film} onPreview={setPreviewTarget} />
              <ArtifactRow job={job} kind="audio" path={job.audio_path} icon={FileAudio} onPreview={setPreviewTarget} />
              <ArtifactRow job={job} kind="thumbnail" path={job.thumbnail_path} icon={ImageIcon} onPreview={setPreviewTarget} />
              <ArtifactRow job={job} kind="metadata" path={job.metadata_path} icon={FileJson} onPreview={setPreviewTarget} />
              <ArtifactRow job={job} kind="meta-tags-json" path={job.meta_tags_path} icon={Tags} onPreview={setPreviewTarget} />
              <ArtifactRow job={job} kind="meta-tags-text" path={job.meta_tags_text_path} icon={FileText} onPreview={setPreviewTarget} />
              {job.subtitle_paths.map((path, index) => <ArtifactRow key={path} job={job} kind={`subtitle-${index}`} path={path} icon={Subtitles} onPreview={setPreviewTarget} />)}
              <ArtifactRow job={job} kind="research-metadata" path={job.research_metadata_path || ""} icon={FileJson} onPreview={setPreviewTarget} />
              <ArtifactRow job={job} kind="preview-script" path={job.preview_script_path || ""} icon={WandSparkles} onPreview={setPreviewTarget} />
              <ArtifactRow job={job} kind="preview-script-md" path={job.preview_script_markdown_path || ""} icon={FileText} onPreview={setPreviewTarget} />
              <ArtifactRow job={job} kind="upload-metadata" path={job.upload_metadata_path || ""} icon={Tags} onPreview={setPreviewTarget} />
            </div>
          </section>
        </aside>
      </div>
      {previewTarget && <ArtifactPreviewModal job={job} target={previewTarget} onClose={() => setPreviewTarget(null)} />}
      {layoutOpen && <ShortsLayoutModal job={job} onClose={() => setLayoutOpen(false)} onSave={saveShortsLayout} />}
      {thumbnailOpen && <ThumbnailFrameModal job={job} onClose={() => setThumbnailOpen(false)} onSave={saveThumbnailFrame} />}
    </div>
  );
}
