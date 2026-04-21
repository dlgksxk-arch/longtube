"""FFmpeg local video generation (Ken Burns effect)"""
import asyncio
import os
from typing import Optional
from app.services.video.base import BaseVideoService
from app.services.video.subprocess_helper import run_subprocess, find_ffmpeg


def _resolve_ffmpeg_cmd(cmd: list[str]) -> list[str]:
    """Replace the leading bare 'ffmpeg' token with an absolute resolved path."""
    if cmd and cmd[0] in ("ffmpeg", "ffmpeg.exe"):
        return [find_ffmpeg()] + list(cmd[1:])
    return cmd


class FFmpegService(BaseVideoService):
    def __init__(self):
        self.model_id = "ffmpeg-kenburns"
        self.display_name = "FFmpeg Ken Burns"

    @staticmethod
    async def _run_ffmpeg(cmd: list[str], timeout: float = 300.0) -> str:
        """Run ffmpeg in a worker thread (bypasses Windows asyncio subprocess limit)."""
        cmd = _resolve_ffmpeg_cmd(cmd)
        print(f"[ffmpeg] running: {os.path.basename(cmd[0])} {' '.join(cmd[1:4])} ... ({len(cmd)} args)")
        try:
            rc, _, stderr = await run_subprocess(
                cmd, timeout=timeout, capture_stdout=False, capture_stderr=True
            )
        except FileNotFoundError as e:
            raise RuntimeError(f"FFmpeg binary not executable: {e}")
        except asyncio.TimeoutError:
            raise RuntimeError(f"FFmpeg timed out after {int(timeout)}s")
        if rc != 0:
            err_text = (stderr or b"").decode(errors="replace")[-800:]
            raise RuntimeError(f"FFmpeg failed (code {rc}): {err_text}")
        return ""

    async def generate(
        self,
        image_path: str,
        audio_path: Optional[str] = None,
        duration: float = 5.0,
        output_path: str = "",
        aspect_ratio: str = "16:9",
        prompt: str = "",
    ) -> str:
        """이미지 + Ken Burns 줌 효과 → 영상 클립 (오디오 있으면 포함)"""
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")

        frames = int(duration * 30)

        # Output resolution from aspect_ratio
        if aspect_ratio == "9:16":
            resolution = "1080x1920"
            up_w = 1620  # 1.5x for zoom headroom
        elif aspect_ratio == "1:1":
            resolution = "1080x1080"
            up_w = 1620
        else:
            resolution = "1920x1080"
            up_w = 2880  # 1.5x for zoom headroom, instead of 8000

        has_audio = bool(audio_path and os.path.exists(audio_path))

        # Ken Burns zoom filter — scaled down for speed (was 8000, caused 60s+/cut)
        vf = (
            f"[0:v]scale={up_w}:-1,zoompan=z='min(zoom+0.0015,1.225)':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={frames}:s={resolution}:fps=30[v]"
        )

        if has_audio:
            # v1.1.45: 영상 길이는 `duration` 으로 고정. 오디오가 더 짧으면
            # `apad` 로 무음을 꼬리에 붙이고, 더 길면 `-t duration` 으로 잘라낸다.
            # -shortest 는 음성 길이에 맞춰 영상을 축소시키므로 사용하지 않는다.
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", image_path,
                "-i", audio_path,
                "-filter_complex", vf,
                "-map", "[v]", "-map", "1:a",
                "-af", "apad",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-c:a", "aac", "-b:a", "192k",
                "-t", str(duration),
                "-pix_fmt", "yuv420p",
                output_path,
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", image_path,
                "-filter_complex", vf,
                "-map", "[v]",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-t", str(duration),
                "-pix_fmt", "yuv420p",
                output_path,
            ]

        # 3 minute per-cut timeout — should be plenty even for slow boxes
        await self._run_ffmpeg(cmd, timeout=180.0)
        return output_path

    @staticmethod
    async def merge_videos(video_paths: list[str], output_path: str) -> str:
        """여러 영상 클립을 하나로 병합 (stream copy — very fast)"""
        # v1.1.55 hotfix: 빈 리스트 또는 존재하지 않는 파일만 있으면 즉시 에러
        valid_paths = [p for p in video_paths if os.path.exists(p) and os.path.getsize(p) > 0]
        if not valid_paths:
            missing = [p for p in video_paths if not os.path.exists(p)]
            raise RuntimeError(
                f"merge_videos: 유효한 영상 클립이 없습니다. "
                f"전달된 {len(video_paths)}개 중 존재하지 않는 파일: {missing[:5]}"
            )
        concat_file = output_path.replace(".mp4", "_concat.txt")
        with open(concat_file, "w", encoding="utf-8") as f:
            for vp in valid_paths:
                abs_p = os.path.abspath(vp).replace("\\", "/").replace("'", r"\'")
                f.write(f"file '{abs_p}'\n")

        # Stream copy first (fast). Clips already use same codec so this works.
        cmd = _resolve_ffmpeg_cmd([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", concat_file,
            "-c", "copy",
            output_path,
        ])

        print(f"[ffmpeg] merging {len(video_paths)} clips → {output_path} (bin={os.path.basename(cmd[0])})")
        try:
            rc, _, stderr = await run_subprocess(
                cmd, timeout=300.0, capture_stdout=False, capture_stderr=True
            )
        except asyncio.TimeoutError:
            raise RuntimeError("FFmpeg merge timed out")
        except FileNotFoundError as e:
            raise RuntimeError(f"FFmpeg binary not executable: {e}")

        try:
            os.remove(concat_file)
        except:
            pass

        if rc != 0:
            err_text = (stderr or b"").decode(errors="replace")[-800:]
            raise RuntimeError(f"FFmpeg merge failed: {err_text}")
        return output_path

    @staticmethod
    async def probe_duration(video_path: str) -> float:
        """ffprobe 로 영상 길이(초) 조회. 실패 시 0.0 반환."""
        try:
            ffbin = find_ffmpeg()
        except RuntimeError:
            return 0.0
        ffprobe = ffbin.replace("ffmpeg.exe", "ffprobe.exe").replace("ffmpeg", "ffprobe")
        if not os.path.exists(ffprobe):
            return 0.0
        try:
            rc, stdout, _ = await run_subprocess(
                [ffprobe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", video_path],
                timeout=30.0,
                capture_stdout=True,
                capture_stderr=False,
            )
        except Exception:
            return 0.0
        if rc != 0:
            return 0.0
        txt = (stdout or b"").decode(errors="replace").strip()
        try:
            return float(txt) if txt else 0.0
        except ValueError:
            return 0.0

    @staticmethod
    async def ensure_min_duration(
        input_path: str,
        output_path: str,
        min_seconds: float = 5.0,
        resolution: str = "1920x1080",
    ) -> str:
        """입력 영상이 ``min_seconds`` 보다 짧으면 영상/음성 모두 루프해서 정확히
        ``min_seconds`` 로 맞춘 파일을 ``output_path`` 에 쓴다. 이미 충분히 길면
        재인코딩해서 output_path 에 복사 (다음 단계와 코덱을 통일하기 위해).
        """
        dur = await FFmpegService.probe_duration(input_path)
        need_loop = dur > 0 and dur < min_seconds - 0.05

        # ★ v1.1.30: ffmpeg 의 pad 필터는 ``w:h:x:y`` 형식만 받는다. scale 은
        # ``1920x1080`` 같은 "size" 지름길을 eval 전에 특수 처리하지만 pad 는
        # 그냥 expression 으로 파싱해서 ``Invalid chars 'x1080'`` 로 터진다.
        # 그래서 pad 용으로는 반드시 ``WxH`` → ``W:H`` 로 분리한 문자열을 쓴다.
        pad_wh = resolution.replace("x", ":")
        vf = (
            f"scale={resolution}:force_original_aspect_ratio=decrease,"
            f"pad={pad_wh}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30"
        )

        if need_loop:
            # -stream_loop -1 로 무한 반복 후 -t 로 정확히 min_seconds 길이 만큼 잘라낸다.
            # 영상/오디오 모두 같은 입력이라 자연스럽게 함께 반복됨.
            cmd = [
                "ffmpeg", "-y",
                "-stream_loop", "-1", "-i", input_path,
                "-t", f"{min_seconds:.3f}",
                "-vf", vf,
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                output_path,
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-vf", vf,
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                output_path,
            ]
        await FFmpegService._run_ffmpeg(cmd, timeout=300.0)
        return output_path

    @staticmethod
    async def add_fade_in_out(
        input_path: str,
        output_path: str,
        fade_seconds: float = 2.0,
        resolution: str = "1920x1080",
    ) -> str:
        """입력 영상에 앞 ``fade_seconds`` 초 페이드 인, 뒤 ``fade_seconds`` 초
        페이드 아웃 효과를 주고 해상도/fps 도 표준화해서 저장.
        """
        dur = await FFmpegService.probe_duration(input_path)
        if dur <= 0:
            dur = fade_seconds * 2 + 0.5  # guess
        fade_out_start = max(0.0, dur - fade_seconds)
        # v1.1.30: pad 필터는 WxH 지름길을 안 받아서 ``1920:1080`` 로 분리.
        pad_wh = resolution.replace("x", ":")
        vf = (
            f"scale={resolution}:force_original_aspect_ratio=decrease,"
            f"pad={pad_wh}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,"
            f"fade=t=in:st=0:d={fade_seconds},"
            f"fade=t=out:st={fade_out_start}:d={fade_seconds}"
        )
        af = (
            f"afade=t=in:st=0:d={fade_seconds},"
            f"afade=t=out:st={fade_out_start}:d={fade_seconds}"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-vf", vf,
            "-af", af,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            output_path,
        ]
        await FFmpegService._run_ffmpeg(cmd, timeout=300.0)
        return output_path

    @staticmethod
    async def merge_videos_reencode(
        video_paths: list[str],
        output_path: str,
        resolution: str = "1920x1080",
    ) -> str:
        """여러 영상 클립을 재인코딩 concat 으로 이어붙임.

        각 클립의 코덱/해상도가 다를 수 있을 때 사용. 모두 같은 표준 규격으로
        맞춰 인코딩한 뒤 concat filter 로 이어붙인다.
        """
        if not video_paths:
            raise RuntimeError("merge_videos_reencode: empty input list")

        inputs: list[str] = []
        for vp in video_paths:
            inputs += ["-i", vp]

        n = len(video_paths)
        # v1.1.30: pad 필터는 WxH 지름길을 안 받아서 ``1920:1080`` 로 분리.
        pad_wh = resolution.replace("x", ":")
        filter_parts = []
        for i in range(n):
            filter_parts.append(
                f"[{i}:v]scale={resolution}:force_original_aspect_ratio=decrease,"
                f"pad={pad_wh}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v{i}];"
            )
            filter_parts.append(f"[{i}:a]aresample=48000[a{i}];")
        concat_inputs = "".join(f"[v{i}][a{i}]" for i in range(n))
        filter_parts.append(f"{concat_inputs}concat=n={n}:v=1:a=1[v][a]")
        filter_complex = "".join(filter_parts)

        cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            output_path,
        ]
        await FFmpegService._run_ffmpeg(cmd, timeout=600.0)
        return output_path

    @staticmethod
    async def merge_with_crossfade(
        video_a: str,
        video_b: str,
        output_path: str,
        fade_seconds: float = 0.5,
        resolution: str = "1920x1080",
    ) -> str:
        """두 영상을 xfade 크로스페이드로 이어붙임 (v1.1.55).

        video_a 의 마지막 ``fade_seconds`` 와 video_b 의 첫 ``fade_seconds`` 가
        겹치면서 자연스럽게 전환된다.
        """
        dur_a = await FFmpegService.probe_duration(video_a)
        if dur_a <= fade_seconds:
            # a 가 너무 짧으면 크로스페이드 불가 → 단순 concat
            return await FFmpegService.merge_videos_reencode(
                [video_a, video_b], output_path, resolution=resolution,
            )
        offset = max(0.0, dur_a - fade_seconds)
        pad_wh = resolution.replace("x", ":")
        filter_complex = (
            f"[0:v]scale={resolution}:force_original_aspect_ratio=decrease,"
            f"pad={pad_wh}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[va];"
            f"[1:v]scale={resolution}:force_original_aspect_ratio=decrease,"
            f"pad={pad_wh}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[vb];"
            f"[va][vb]xfade=transition=fade:duration={fade_seconds}:offset={offset}[v];"
            f"[0:a][1:a]acrossfade=d={fade_seconds}[a]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", video_a,
            "-i", video_b,
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            output_path,
        ]
        await FFmpegService._run_ffmpeg(cmd, timeout=600.0)
        return output_path

    @staticmethod
    async def prepend_silent_fade_in(
        input_path: str,
        output_path: str,
        silent_seconds: float = 0.5,
        fade_seconds: float = 0.15,
        resolution: str = "1920x1080",
    ) -> str:
        """영상 맨 앞에 ``silent_seconds`` 초의 무음 + 정지 프레임을 붙이고,
        그 중 처음 ``fade_seconds`` 초 동안 검정→첫 프레임 페이드 인 한다.

        v1.1.71: 롱폼 시작의 "재생 누르자마자 바로 본문이 때리는" 어색함을
        완화. 0.5 초 뜸을 들여 시청자가 화면에 안착하도록 유도.

        비디오: `tpad=start_duration=SILENT:start_mode=clone` 로 첫 프레임을
        앞으로 SILENT 초만큼 복제 + `fade=t=in:st=0:d=FADE` 로 검정→프레임
        페이드. FADE 이후 (SILENT - FADE) 초는 첫 프레임 그대로 정지.
        오디오: `adelay=MS|MS` 로 전단에 MS 만큼 무음을 삽입 (오디오 delay).
        """
        pad_wh = resolution.replace("x", ":")
        adelay_ms = int(round(silent_seconds * 1000))
        vf = (
            f"scale={resolution}:force_original_aspect_ratio=decrease,"
            f"pad={pad_wh}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,"
            f"tpad=start_duration={silent_seconds}:start_mode=clone,"
            f"fade=t=in:st=0:d={fade_seconds}"
        )
        af = f"adelay={adelay_ms}|{adelay_ms}"
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-vf", vf,
            "-af", af,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            output_path,
        ]
        await FFmpegService._run_ffmpeg(cmd, timeout=600.0)
        return output_path

    @staticmethod
    async def burn_subtitles(video_path: str, subtitle_path: str, output_path: str) -> str:
        """영상에 자막 삽입"""
        # libass on Windows resolves the ASS file path relative to cwd. Pass
        # the subtitle path with escaped separators to keep ffmpeg happy.
        sub_escaped = subtitle_path.replace("\\", "/").replace(":", r"\:")
        cmd = _resolve_ffmpeg_cmd([
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", f"ass='{sub_escaped}'",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "copy",
            output_path,
        ])

        print(f"[ffmpeg] burning subtitles → {output_path} (bin={os.path.basename(cmd[0])})")
        try:
            rc, _, stderr = await run_subprocess(
                cmd, timeout=600.0, capture_stdout=True, capture_stderr=True
            )
        except FileNotFoundError as e:
            raise RuntimeError(f"FFmpeg binary not executable: {e}")

        if rc != 0:
            err_text = (stderr or b"").decode(errors="replace")[:800]
            raise RuntimeError(f"FFmpeg subtitle burn failed: {err_text}")
        return output_path


# --------------------------------------------------------------------------- #
# v1.1.40 — Static (무효과) 폴백 서비스
# --------------------------------------------------------------------------- #
#
# 사용자 요청: "나머지(영상 제작 대상 미선택 컷)에 Ken Burns 효과 넣지 말라고".
# 기존 폴백은 FFmpegService (= Ken Burns 줌인). 이걸 대체할 "효과 없음" 서비스.
# 정지 이미지를 오디오 길이만큼 그대로 보여주기만 하면 됨 — 가장 저렴 + 가장
# 빠름. zoompan 필터를 빼고 scale/pad 만 태워서 해상도를 정상화한다.
# --------------------------------------------------------------------------- #


class FFmpegStaticService(BaseVideoService):
    """정지 이미지 + 오디오 = 효과 없는 영상 클립. 0원, 0 모션."""

    def __init__(self):
        self.model_id = "ffmpeg-static"
        self.display_name = "FFmpeg Static (no motion)"

    async def generate(
        self,
        image_path: str,
        audio_path: Optional[str] = None,
        duration: float = 5.0,
        output_path: str = "",
        aspect_ratio: str = "16:9",
        prompt: str = "",
    ) -> str:
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")

        # 출력 해상도
        if aspect_ratio == "9:16":
            resolution = "1080x1920"
        elif aspect_ratio == "1:1":
            resolution = "1080x1080"
        else:
            resolution = "1920x1080"

        # 이미지가 출력 종횡비와 달라도 letterbox/pillarbox 로 맞춰 넣는다.
        # pad 필터는 "WxH" 지름길을 안 받으므로 ``W:H`` 로 분리 (v1.1.30 참고).
        pad_wh = resolution.replace("x", ":")
        vf = (
            f"scale={resolution}:force_original_aspect_ratio=decrease,"
            f"pad={pad_wh}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p"
        )

        has_audio = bool(audio_path and os.path.exists(audio_path))
        if has_audio:
            # v1.1.45: -shortest 대신 apad + -t 로 영상 길이를 정확히 `duration` 으로 고정
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", image_path,
                "-i", audio_path,
                "-vf", vf,
                "-af", "apad",
                "-map", "0:v", "-map", "1:a",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-c:a", "aac", "-b:a", "192k",
                "-t", str(duration),
                "-pix_fmt", "yuv420p",
                output_path,
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", image_path,
                "-vf", vf,
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-t", str(duration),
                "-pix_fmt", "yuv420p",
                output_path,
            ]

        await FFmpegService._run_ffmpeg(cmd, timeout=180.0)
        return output_path
