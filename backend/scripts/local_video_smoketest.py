"""Run a small local ComfyUI video model smoke test.

This script is intentionally narrow: it generates one short clip from one
existing LongTube cut image without touching project DB state.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.video.comfyui_service import ComfyUIVideoService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--prompt", default="slow cinematic camera push-in, subtle parallax, natural motion")
    parser.add_argument("--duration", type=float, default=5.0)
    parser.add_argument("--aspect-ratio", default="16:9")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    image = Path(args.image)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    print(json.dumps({
        "event": "start",
        "model": args.model,
        "image": str(image),
        "out": str(out),
        "duration": args.duration,
    }, ensure_ascii=False), flush=True)

    service = ComfyUIVideoService(args.model)
    result = await service.generate(
        image_path=str(image),
        duration=args.duration,
        output_path=str(out),
        aspect_ratio=args.aspect_ratio,
        prompt=args.prompt,
    )

    elapsed = time.perf_counter() - started
    size = Path(result).stat().st_size if Path(result).exists() else 0
    print(json.dumps({
        "event": "done",
        "model": args.model,
        "result": result,
        "elapsed_seconds": round(elapsed, 2),
        "bytes": size,
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
