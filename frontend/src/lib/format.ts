// v1.1.33: 공용 포맷 헬퍼
// 백엔드 estimation_service.format_duration_ko 와 동일한 규칙을 유지한다.

/**
 * 초 단위 숫자를 한국어 표기로 포맷.
 *
 * - 60초 미만: "45초"
 * - 60초 이상 3600초 미만: "27분" / "27분 12초"
 * - 3600초 이상: "3시간" / "3시간 12분"
 */
export function formatDurationKo(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return "-";
  const s = Math.round(Number(seconds));
  if (s < 60) return `${s}초`;
  const m = Math.floor(s / 60);
  const sec = s % 60;
  if (m < 60) return sec === 0 ? `${m}분` : `${m}분 ${sec}초`;
  const h = Math.floor(m / 60);
  const mm = m % 60;
  return mm === 0 ? `${h}시간` : `${h}시간 ${mm}분`;
}

/**
 * v1.1.35: 원화 포맷. "12,345원".
 */
export function formatKrw(amount: number | null | undefined): string {
  if (amount === null || amount === undefined || Number.isNaN(amount)) return "-원";
  const n = Math.round(Number(amount));
  return `${n.toLocaleString("ko-KR")}원`;
}

/**
 * v1.1.35: 비용 tier → 색상 클래스 매핑.
 * Tailwind 유틸리티만 사용 (프로젝트 theme 에 맞춘 accent-* 색).
 */
export function costTierClasses(tier?: string): {
  text: string;
  bg: string;
  border: string;
  label: string;
} {
  if (tier === "expensive") {
    return {
      text: "text-accent-danger",
      bg: "bg-accent-danger/10",
      border: "border-accent-danger/50",
      label: "비쌈",
    };
  }
  if (tier === "normal") {
    return {
      text: "text-accent-warning",
      bg: "bg-accent-warning/10",
      border: "border-accent-warning/50",
      label: "중간",
    };
  }
  return {
    text: "text-accent-success",
    bg: "bg-accent-success/10",
    border: "border-accent-success/50",
    label: "저렴",
  };
}
