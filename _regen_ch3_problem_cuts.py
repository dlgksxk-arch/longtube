import asyncio
import sys
import traceback
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

from app.models.database import SessionLocal  # noqa: E402
from app.routers.image import generate_one_image  # noqa: E402


PROJECT_ID = "V3_CH3_EP75_2606292227021801c7"
DEFAULT_CUTS = [29, 47, 63, 84, 90, 93, 94, 96, 110, 112, 123, 125, 129, 144]


async def main() -> int:
    cuts = [int(value) for value in sys.argv[1:]] if len(sys.argv) > 1 else DEFAULT_CUTS
    failed: list[int] = []
    for idx, cut_number in enumerate(cuts, 1):
        print(f"[regen] {idx}/{len(cuts)} cut_{cut_number} start", flush=True)
        db = SessionLocal()
        try:
            result = await generate_one_image(PROJECT_ID, cut_number, db)
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
