"""Wan local motion-control helpers.

The goal is not to create a new subject, but to give WanMove a small set of
tracks that nudge already-visible pixels/objects. This keeps motion local and
reduces the "new person/new object" failure mode.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

from PIL import Image


_PERSON_RE = re.compile(
    r"\b(person|people|man|woman|boy|girl|child|character|figure|silhouette|"
    r"scholar|researcher|scientist|student|teacher|worker|human|cartoon|backpack)\b",
    flags=re.IGNORECASE,
)


def _component_bbox(mask: list[list[bool]]) -> tuple[int, int, int, int] | None:
    """Return the best compact vertical foreground component bbox."""
    h = len(mask)
    w = len(mask[0]) if h else 0
    visited = [[False for _ in range(w)] for _ in range(h)]
    best: tuple[float, tuple[int, int, int, int]] | None = None

    for sy in range(h):
        for sx in range(w):
            if visited[sy][sx] or not mask[sy][sx]:
                continue
            stack = [(sx, sy)]
            visited[sy][sx] = True
            min_x = max_x = sx
            min_y = max_y = sy
            area = 0
            while stack:
                x, y = stack.pop()
                area += 1
                if x < min_x:
                    min_x = x
                elif x > max_x:
                    max_x = x
                if y < min_y:
                    min_y = y
                elif y > max_y:
                    max_y = y
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < w and 0 <= ny < h and mask[ny][nx] and not visited[ny][nx]:
                        visited[ny][nx] = True
                        stack.append((nx, ny))

            bw = max_x - min_x + 1
            bh = max_y - min_y + 1
            if area < max(40, int(w * h * 0.002)):
                continue
            if area > int(w * h * 0.35):
                continue
            if bh < h * 0.12 or bw < w * 0.015:
                continue

            vertical_bonus = min(2.0, bh / max(1, bw))
            compactness = area / max(1, bw * bh)
            border_penalty = 0.5 if min_x <= 2 or min_y <= 2 or max_x >= w - 3 or max_y >= h - 3 else 1.0
            score = area * vertical_bonus * compactness * border_penalty
            if best is None or score > best[0]:
                best = (score, (min_x, min_y, max_x, max_y))

    return best[1] if best else None


def _find_foreground_bbox(image_path: str) -> tuple[float, float, float, float]:
    """Find a likely person/foreground bbox in normalized 0..1 coordinates."""
    img = Image.open(image_path).convert("RGB")
    img.thumbnail((320, 320), Image.Resampling.LANCZOS)
    w, h = img.size
    pixels = list(img.getdata())
    lums = [(r + g + b) / 3.0 for r, g, b in pixels]
    sorted_lums = sorted(lums)
    p28 = sorted_lums[min(len(sorted_lums) - 1, max(0, int(len(sorted_lums) * 0.28)))]
    threshold = max(80.0, float(p28))
    dark = [[False for _ in range(w)] for _ in range(h)]
    for y in range(h):
        row = dark[y]
        base = y * w
        for x in range(w):
            row[x] = lums[base + x] < threshold

    # Ignore thin frame/border lines; we want the compact subject/object.
    margin_x = max(2, int(w * 0.015))
    margin_y = max(2, int(h * 0.015))
    for y in range(h):
        for x in range(margin_x):
            dark[y][x] = False
            dark[y][w - 1 - x] = False
    for y in range(margin_y):
        dark[y] = [False for _ in range(w)]
        dark[h - 1 - y] = [False for _ in range(w)]

    bbox = _component_bbox(dark)
    if bbox is None:
        return (0.38, 0.28, 0.62, 0.78)
    x1, y1, x2, y2 = bbox
    pad_x = max(2, int((x2 - x1 + 1) * 0.10))
    pad_y = max(2, int((y2 - y1 + 1) * 0.08))
    x1 = max(0, x1 - pad_x)
    y1 = max(0, y1 - pad_y)
    x2 = min(w - 1, x2 + pad_x)
    y2 = min(h - 1, y2 + pad_y)
    return (x1 / w, y1 / h, x2 / w, y2 / h)


def _track(xs: list[float], ys: list[float]) -> list[dict[str, float]]:
    return [{"x": round(x, 2), "y": round(y, 2)} for x, y in zip(xs, ys)]


def build_wan_track_coords(
    *,
    image_path: str,
    width: int,
    height: int,
    length: int,
    prompt: str = "",
) -> str:
    """Build JSON tracks for WanMoveTracksFromCoords.

    Person-like cuts get planted-feet upper-body sway tracks. Object/abstract
    cuts get a tiny local object/light motion track. Coordinates are output
    resolution pixels, as expected by ComfyUI's WanMove nodes.
    """
    frames = max(5, int(length))
    x1n, y1n, x2n, y2n = _find_foreground_bbox(image_path)
    # WanMove's current ComfyUI implementation downsamples tracks by 8, while
    # Wan2.2 TI2V VAE encodes spatially by 16. Feed half-resolution coords so
    # track indices land inside the encoded latent feature map.
    coord_scale = 0.5
    x1, y1 = x1n * width * coord_scale, y1n * height * coord_scale
    x2, y2 = x2n * width * coord_scale, y2n * height * coord_scale
    bw, bh = max(8.0, x2 - x1), max(8.0, y2 - y1)
    cx = (x1 + x2) / 2.0
    person_like = bool(_PERSON_RE.search(prompt or "")) or bh > bw * 1.35

    tracks: list[list[dict[str, float]]] = []
    phase = [math.sin(math.pi * i / (frames - 1)) for i in range(frames)]

    if person_like:
        # Coordinates are intentionally half-scale for Wan2.2's latent grid.
        # Keep motion above one latent cell, otherwise WanMove becomes static.
        sway = min(22.0, max(14.0, bw * 0.36))
        lift = min(9.0, max(4.0, bh * 0.055))
        anchors = [
            (cx, y1 + bh * 0.18, 0.55, -0.20),  # head/upper silhouette
            (cx - bw * 0.18, y1 + bh * 0.35, 1.15, -0.35),  # backpack/left shoulder
            (cx + bw * 0.14, y1 + bh * 0.40, 0.85, -0.25),  # right shoulder
            (cx, y1 + bh * 0.58, 0.65, -0.15),  # torso
            (cx - bw * 0.18, y2 - bh * 0.04, 0.0, 0.0),  # planted foot anchor
            (cx + bw * 0.16, y2 - bh * 0.04, 0.0, 0.0),  # planted foot anchor
        ]
        for ax, ay, sx, sy in anchors:
            xs = [min(width * coord_scale - 1, max(0, ax + sway * sx * p)) for p in phase]
            ys = [min(height * coord_scale - 1, max(0, ay + lift * sy * p)) for p in phase]
            tracks.append(_track(xs, ys))
    else:
        sway = min(18.0, max(10.0, min(bw, bh) * 0.24))
        anchors = [
            (cx, y1 + bh * 0.35, 1.0, 0.0),
            (cx - bw * 0.18, y1 + bh * 0.55, 0.6, 0.2),
            (cx + bw * 0.18, y1 + bh * 0.55, 0.6, -0.2),
        ]
        for ax, ay, sx, sy in anchors:
            xs = [min(width * coord_scale - 1, max(0, ax + sway * sx * p)) for p in phase]
            ys = [min(height * coord_scale - 1, max(0, ay + sway * sy * p)) for p in phase]
            tracks.append(_track(xs, ys))

    return json.dumps(tracks, separators=(",", ":"))
