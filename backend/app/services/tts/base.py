"""Base TTS service interface"""
import os
import subprocess
from abc import ABC, abstractmethod
from typing import Optional


def _resolve_bins() -> tuple:
    """find_ffmpeg() 로 ffmpeg/ffprobe 절대경로를 구한다.
    Windows 에서 bare 'ffmpeg' 호출이 안 되므로 반드시 필요.
    """
    from app.services.video.subprocess_helper import find_ffmpeg
    ffbin = find_ffmpeg()
    # ffprobe 는 ffmpeg 옆에 같이 있다
    ffprobe = ffbin.replace("ffmpeg.exe", "ffprobe.exe").replace("ffmpeg", "ffprobe")
    if not os.path.exists(ffprobe):
        ffprobe = "ffprobe"  # fallback to PATH
    return ffbin, ffprobe


class BaseTTSService(ABC):
    model_id: str
    display_name: str

    @abstractmethod
    async def generate(self, text: str, voice_id: str, output_path: str, speed: float = 1.0, voice_settings: Optional[dict] = None) -> dict:
        """텍스트 → 음성 파일 생성. Returns {"path": str, "duration": float}"""
        pass

    @abstractmethod
    async def list_voices(self) -> list[dict]:
        """사용 가능한 보이스 목록 반환"""
        pass

    @staticmethod
    def enforce_max_duration(path: str, current_dur: float, max_dur: float) -> float:
        """v1.1.49: 음성이 max_dur 를 초과하면 FFmpeg 로 보정한다.

        전략 (3단계 방어):
        1) atempo 배속 (ratio ≤ 1.35) — 자연스러운 속도 조절
        2) atempo 1.35x + 하드컷 (ratio > 1.35) — 속도 올리고 잘라내기
        3) 위 둘 다 실패하면 순수 하드컷 (-t max_dur) — 최후의 보루

        Returns: 처리 후 실제 duration.
        """
        try:
            ffbin, ffprobe_bin = _resolve_bins()
        except Exception as e:
            print(f"[TTS] ⚠ ffmpeg 를 찾을 수 없어서 enforce 불가: {e}")
            return current_dur

        ratio = current_dur / max_dur
        tmp_path = path + ".tmp.mp3"

        def _measure(p: str) -> float:
            """ffprobe 로 duration 측정. 실패 시 -1."""
            try:
                r = subprocess.run(
                    [ffprobe_bin, "-v", "quiet", "-show_entries", "format=duration",
                     "-of", "csv=p=0", p],
                    capture_output=True, text=True, timeout=10,
                )
                if r.stdout.strip():
                    return float(r.stdout.strip())
            except Exception:
                pass
            return -1.0

        def _try_ffmpeg(cmd: list[str]) -> bool:
            """FFmpeg 실행 후 tmp_path 유효성 검사."""
            try:
                proc = subprocess.run(cmd, capture_output=True, timeout=30)
                if proc.returncode != 0:
                    stderr_msg = (proc.stderr or b"")[:300]
                    print(f"[TTS] ffmpeg returncode={proc.returncode}: {stderr_msg}")
                    return False
                if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 100:
                    return True
            except Exception as e:
                print(f"[TTS] ffmpeg failed: {e}")
            return False

        def _apply_and_measure() -> float:
            """tmp_path → path 교체 후 duration 반환."""
            os.replace(tmp_path, path)
            new_dur = _measure(path)
            if new_dur > 0:
                print(f"[TTS] duration enforced: {current_dur:.1f}s → {new_dur:.1f}s (ratio={ratio:.2f})")
                return new_dur
            return max_dur  # 측정 실패 시 max_dur 로 간주 (파일 자체는 교체됨)

        try:
            # ── 1단계: atempo 배속 ──
            if ratio <= 1.35:
                tempo = round(ratio, 3)
                if _try_ffmpeg([ffbin, "-y", "-i", path,
                                "-filter:a", f"atempo={tempo}",
                                "-vn", tmp_path]):
                    return _apply_and_measure()

            # ── 2단계: 1.35x + 하드컷 ──
            if _try_ffmpeg([ffbin, "-y", "-i", path,
                            "-filter:a", "atempo=1.35",
                            "-t", str(max_dur),
                            "-vn", tmp_path]):
                return _apply_and_measure()

            # ── 3단계: 순수 하드컷 (최후의 보루) ──
            print(f"[TTS] atempo 실패, 하드컷 적용: {current_dur:.1f}s → {max_dur}s")
            if _try_ffmpeg([ffbin, "-y", "-i", path,
                            "-t", str(max_dur),
                            "-vn", tmp_path]):
                return _apply_and_measure()

            print(f"[TTS] ⚠ 모든 enforce 시도 실패! 원본 유지: {current_dur:.1f}s")
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

        return current_dur

    @staticmethod
    def enforce_min_duration(path: str, current_dur: float, min_dur: float) -> float:
        """v1.1.53: 음성이 min_dur 미만이면 FFmpeg atempo 감속으로 늘린다.

        예: 3초 음성 → min_dur=4.0 → atempo=0.75 (3/4=0.75) → ~4초로 늘어남.
        atempo 범위: [0.5, 1.0]. 0.5 미만이면 감속 한계로 간주.
        """
        if current_dur >= min_dur or current_dur <= 0:
            return current_dur

        try:
            ffbin, ffprobe_bin = _resolve_bins()
        except Exception as e:
            print(f"[TTS] ⚠ ffmpeg 를 찾을 수 없어서 min enforce 불가: {e}")
            return current_dur

        # atempo = current / target → 값이 1 미만이면 감속(늘어남)
        tempo = current_dur / min_dur
        tempo = max(0.5, round(tempo, 3))  # 0.5 이하로는 안 내림 (품질 문제)
        tmp_path = path + ".tmp_slow.mp3"

        try:
            proc = subprocess.run(
                [ffbin, "-y", "-i", path,
                 "-filter:a", f"atempo={tempo}",
                 "-vn", tmp_path],
                capture_output=True, timeout=30,
            )
            if proc.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 100:
                os.replace(tmp_path, path)
                # 측정
                try:
                    r = subprocess.run(
                        [ffprobe_bin, "-v", "quiet", "-show_entries", "format=duration",
                         "-of", "csv=p=0", path],
                        capture_output=True, text=True, timeout=10,
                    )
                    new_dur = float(r.stdout.strip()) if r.stdout.strip() else min_dur
                except Exception:
                    new_dur = min_dur
                print(f"[TTS] min duration enforced: {current_dur:.1f}s → {new_dur:.1f}s (atempo={tempo})")
                return new_dur
            else:
                stderr_msg = (proc.stderr or b"")[:300]
                print(f"[TTS] ⚠ min enforce 실패 (returncode={proc.returncode}): {stderr_msg}")
        except Exception as e:
            print(f"[TTS] ⚠ min enforce ffmpeg 오류: {e}")
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

        return current_dur
