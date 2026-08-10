import asyncio
import sys
import traceback
from pathlib import Path


for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

from app.models.database import SessionLocal  # noqa: E402
from app.routers.image import generate_one_image  # noqa: E402


async def main() -> int:
    if len(sys.argv) < 3:
        print("usage: python _regen_project_cuts.py PROJECT_ID CUT [CUT ...]", flush=True)
        return 2
    project_id = sys.argv[1]
    cuts = [int(value) for value in sys.argv[2:]]
    failed: list[int] = []
    for idx, cut_number in enumerate(cuts, 1):
        print(f"[regen] {idx}/{len(cuts)} {project_id} cut_{cut_number} start", flush=True)
        db = SessionLocal()
        try:
            result = await generate_one_image(project_id, cut_number, db)
            print(f"[regen] cut_{cut_number} ok {result}", flush=True)
        except Exception as exc:
            failed.append(cut_number)
            print(f"[regen] cut_{cut_number} failed: {type(exc).__name__}: {exc}", flush=True)
            print(traceback.format_exc(), flush=True)
        finally:
            db.close()
    if failed:
        print(f"[regen] failed cuts: {failed}", flush=True)
        return 1
    print("[regen] all requested cuts completed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
