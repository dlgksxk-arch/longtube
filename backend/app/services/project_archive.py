from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from app.config import RESULT_ARCHIVE_DIR, resolve_project_dir


def archive_uploaded_project(project_id: str, config: dict[str, Any] | None = None) -> dict[str, str | bool]:
    """Move a Studio-verified uploaded project into the completed-result archive."""
    pid = str(project_id or "").strip()
    if not pid:
        return {"archived": False, "reason": "empty_project_id"}

    archive_root = Path(RESULT_ARCHIVE_DIR)
    archive_root.mkdir(parents=True, exist_ok=True)

    dest = (archive_root / pid).resolve()
    src = resolve_project_dir(pid, config=config, create=False).resolve()

    try:
        if src == dest:
            return {"archived": True, "path": str(dest), "reason": "already_archived"}
        if archive_root.resolve() in src.parents:
            return {"archived": True, "path": str(src), "reason": "already_under_archive"}
        if not src.exists():
            if dest.exists():
                return {"archived": True, "path": str(dest), "reason": "archive_exists_source_missing"}
            return {"archived": False, "reason": "source_missing", "source": str(src)}

        final_dest = dest
        if final_dest.exists():
            index = 2
            while True:
                candidate = archive_root / f"{pid}_{index}"
                if not candidate.exists():
                    final_dest = candidate.resolve()
                    break
                index += 1

        shutil.move(str(src), str(final_dest))
        return {"archived": True, "path": str(final_dest), "source": str(src)}
    except Exception as exc:
        return {
            "archived": False,
            "reason": f"{type(exc).__name__}: {exc}",
            "source": str(src),
            "path": str(dest),
        }
