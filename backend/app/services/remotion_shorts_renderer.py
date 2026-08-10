"""Shared Remotion renderer adapter for every LongTube channel."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from app.services.video.subprocess_helper import run_subprocess


SHARED_SHORTS_PIPELINE_ID = "shared-all-channels-3word-captions-v2"


def remotion_shorts_root() -> Path:
    return Path(__file__).resolve().parents[3] / "remotion-shorts"


def _find_node() -> str:
    configured = str(os.environ.get("NODE_BIN") or "").strip().strip('"')
    if configured and Path(configured).is_file():
        return configured
    node = shutil.which("node") or shutil.which("node.exe")
    if node:
        return node
    raise RuntimeError("Remotion shorts renderer requires Node.js, but node was not found")


async def render_remotion_shorts(
    renders: list[dict[str, Any]],
    *,
    manifest_path: Path,
    browser_executable: str | None = None,
) -> None:
    """Render all prepared Shorts through one shared Remotion composition."""
    if not renders:
        return

    for index, item in enumerate(renders, start=1):
        props = item.get("props") if isinstance(item, dict) else None
        if not isinstance(props, dict):
            raise RuntimeError(f"Shared Shorts render {index} is missing props")
        if props.get("pipelineId") != SHARED_SHORTS_PIPELINE_ID:
            raise RuntimeError(
                f"Shared Shorts render {index} has an invalid pipelineId: "
                f"{props.get('pipelineId')!r}"
            )
        if float(props.get("playbackRate") or 0.0) != 1.2:
            raise RuntimeError(f"Shared Shorts render {index} must use 1.2x final playback")
        if not isinstance(props.get("keepSegments"), list) or not props.get("keepSegments"):
            raise RuntimeError(f"Shared Shorts render {index} is missing silence-cut segments")
        if not isinstance(props.get("captionCues"), list) or not props.get("captionCues"):
            raise RuntimeError(f"Shared Shorts render {index} is missing 3-word caption cues")

    root = remotion_shorts_root()
    renderer = root / "render.mjs"
    package_lock = root / "package-lock.json"
    node_modules = root / "node_modules"
    if not renderer.is_file() or not package_lock.is_file():
        raise RuntimeError(f"Remotion shorts renderer is incomplete: {root}")
    if not node_modules.is_dir():
        raise RuntimeError(
            f"Remotion shorts dependencies are missing. Run: npm install --prefix {root}"
        )

    payload = {
        "version": 1,
        "pipeline": SHARED_SHORTS_PIPELINE_ID,
        "browserExecutable": browser_executable,
        "renders": renders,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    cmd = [_find_node(), str(renderer), str(manifest_path)]
    rc, _, stderr = await run_subprocess(
        cmd,
        timeout=3600.0,
        capture_stdout=False,
        capture_stderr=True,
    )
    if rc != 0:
        stderr_text = (stderr or b"").decode(errors="replace")
        detail = stderr_text.strip()[-2000:]
        raise RuntimeError(f"Remotion shorts render failed: {detail}")

    missing = [str(item.get("outputPath")) for item in renders if not Path(str(item.get("outputPath"))).is_file()]
    if missing:
        raise RuntimeError(f"Remotion shorts outputs are missing: {missing}")
