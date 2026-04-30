/**
 * v2 전용 fetch 헬퍼.
 *
 * 기존 `src/lib/api.ts` 의 BASE_URL 유도 규칙과 100% 동일하게 맞춘다.
 *   1) NEXT_PUBLIC_API_BASE (빌드 타임)
 *   2) window.location.hostname + :8000/api  (LAN/로컬 공용)
 *   3) http://127.0.0.1:8000/api (SSR/폴백)
 *
 * localhost 는 Windows IPv6 해석 흔들림을 피하려고 127.0.0.1 로 고정한다.
 *
 * v2 라우터는 `/api/v2/...` 아래에 있으므로, 이 헬퍼가 반환하는 base 에
 * `/v2/...` 를 이어 붙이면 된다.
 */
const _envApi = process.env.NEXT_PUBLIC_API_BASE;
const _envAsset = process.env.NEXT_PUBLIC_ASSET_BASE;

function _deriveAssetBase(): string {
  if (_envAsset) return _envAsset.replace(/\/$/, "");
  if (typeof window !== "undefined" && window.location?.hostname) {
    const hostname =
      window.location.hostname === "localhost" ? "127.0.0.1" : window.location.hostname;
    return `${window.location.protocol}//${hostname}:8000`;
  }
  return "http://127.0.0.1:8000";
}

function _deriveApiBase(): string {
  if (_envApi) return _envApi.replace(/\/$/, "");
  return `${_deriveAssetBase()}/api`;
}

export const V2_API_BASE = _deriveApiBase();

/** `/v2/keys/` 같은 상대 경로를 받아 절대 URL 로 만든다. */
export function v2Url(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${V2_API_BASE}${p}`;
}

/** 정적 에셋(업로드된 인터루드 영상 등) 접근 기준 URL.
 * 백엔드가 `/assets/**` 로 DATA_DIR 을 서빙하므로, 쿼리 응답의 상대 경로
 * `"presets/1/interlude/opening.mp4"` 를 여기에 이어붙이면 된다.
 */
export function assetUrl(relPath: string): string {
  if (!relPath) return "";
  if (/^https?:\/\//i.test(relPath)) return relPath;
  const base = V2_API_BASE.replace(/\/api$/, "");
  const p = relPath.startsWith("/") ? relPath : `/${relPath}`;
  return `${base}/assets${p}`;
}

// ---------------------------------------------------------------------------
// v2.4.0 — 프리셋 인터루드 (오프닝/인터미션/엔딩) 영상 업로드 API
// ---------------------------------------------------------------------------

export type InterludeKind = "opening" | "intermission" | "ending";

export interface InterludeEntry {
  video_path: string | null;
  filename: string | null;
  size_bytes: number | null;
  duration: number | null;
  source: string | null;
}

export interface InterludeState {
  preset_id: number;
  opening: InterludeEntry;
  intermission: InterludeEntry;
  ending: InterludeEntry;
  intermission_every_sec: number;
}

/** 한 프리셋의 인터루드 파일 + 설정을 가져온다. */
export async function getPresetInterludes(
  presetId: number,
): Promise<InterludeState> {
  const res = await fetch(v2Url(`/v2/presets/${presetId}/interlude`));
  if (!res.ok) throw new Error(`GET interlude HTTP ${res.status}`);
  return (await res.json()) as InterludeState;
}

/** 인터미션 주기(초) 업데이트. 1 ≤ every_sec ≤ 1800. */
export async function updatePresetInterludeConfig(
  presetId: number,
  intermissionEverySec: number,
): Promise<InterludeState> {
  const res = await fetch(
    v2Url(`/v2/presets/${presetId}/interlude/config`),
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ intermission_every_sec: intermissionEverySec }),
    },
  );
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`PUT interlude/config HTTP ${res.status} ${t}`);
  }
  return (await res.json()) as InterludeState;
}

/** multipart 업로드 — 한 kind 의 파일 하나. 성공 시 새 entry 반환. */
export async function uploadPresetInterlude(
  presetId: number,
  kind: InterludeKind,
  file: File,
): Promise<InterludeEntry> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(
    v2Url(`/v2/presets/${presetId}/interlude/upload/${kind}`),
    { method: "POST", body: fd },
  );
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`POST interlude/upload/${kind} HTTP ${res.status} ${t}`);
  }
  return (await res.json()) as InterludeEntry;
}

/** 해당 kind 의 업로드 파일 + config 엔트리 제거. 204 응답 기대. */
export async function deletePresetInterlude(
  presetId: number,
  kind: InterludeKind,
): Promise<void> {
  const res = await fetch(
    v2Url(`/v2/presets/${presetId}/interlude/${kind}`),
    { method: "DELETE" },
  );
  if (!res.ok && res.status !== 204) {
    const t = await res.text();
    throw new Error(`DELETE interlude/${kind} HTTP ${res.status} ${t}`);
  }
}

export const presetInterludeApi = {
  get: getPresetInterludes,
  updateConfig: updatePresetInterludeConfig,
  upload: uploadPresetInterlude,
  remove: deletePresetInterlude,
};
