"""잔액 원장 실측 조사 스크립트 (v1.1.64 진단용).

실행:  cd backend && python scripts/inspect_spend_ledger.py

출력:
  - 원장 총 레코드 수 / 날짜 범위
  - 프로바이더별 레코드 수 + 누적 USD
  - kind(llm/image/tts/video) 분포
  - model_id 별 top 10
  - api_balances.json 현재 상태 + set_at 이후 감산 계산 재현
  - set_at 이전 지출(감산 제외된 '숨은 지출') 합계
  - 최근 20 개 레코드 원문
"""
from __future__ import annotations
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# backend/app/config.py 의 DATA_DIR 로직과 동일하게 해석
ROOT = Path(__file__).resolve().parents[1]  # backend/
sys.path.insert(0, str(ROOT))
try:
    from app.config import DATA_DIR
except Exception:
    DATA_DIR = Path(os.getenv("DATA_DIR", r"C:\Users\Jevis\Desktop\longtube_net\projects"))

LOG_FILE = Path(DATA_DIR) / "api_spend_log.jsonl"
BAL_FILE = Path(DATA_DIR) / "api_balances.json"


def _fmt_money(v: float) -> str:
    return f"${v:,.4f}"


def load_ledger() -> list[dict]:
    out: list[dict] = []
    if not LOG_FILE.exists():
        print(f"[!] 원장 파일 없음: {LOG_FILE}")
        return out
    with LOG_FILE.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception as e:
                print(f"[!] line {i} parse error: {e}")
    return out


def load_balances() -> dict:
    if not BAL_FILE.exists():
        print(f"[!] 잔액 파일 없음: {BAL_FILE}")
        return {}
    return json.loads(BAL_FILE.read_text(encoding="utf-8"))


def iso_lt(a: str, b: str) -> bool:
    try:
        return a < b
    except Exception:
        return False


def main() -> None:
    print("=" * 72)
    print(f"DATA_DIR : {DATA_DIR}")
    print(f"LOG_FILE : {LOG_FILE}  (exists={LOG_FILE.exists()})")
    print(f"BAL_FILE : {BAL_FILE}  (exists={BAL_FILE.exists()})")
    print("=" * 72)

    records = load_ledger()
    print(f"\n[1] 원장 총 레코드 수: {len(records)}")
    if not records:
        print("    (원장 비어있음)")

    if records:
        ts_list = sorted(r.get("ts", "") for r in records if r.get("ts"))
        print(f"    날짜 범위: {ts_list[0]}  →  {ts_list[-1]}")

    # 프로바이더별
    by_prov_cnt = Counter()
    by_prov_sum = defaultdict(float)
    by_kind_cnt = Counter()
    by_kind_sum = defaultdict(float)
    by_model_cnt = Counter()
    by_model_sum = defaultdict(float)
    for r in records:
        prov = r.get("provider") or "(none)"
        amt = float(r.get("amount_usd") or 0.0)
        kind = r.get("kind") or "(none)"
        model = r.get("model") or "(none)"
        by_prov_cnt[prov] += 1
        by_prov_sum[prov] += amt
        by_kind_cnt[kind] += 1
        by_kind_sum[kind] += amt
        by_model_cnt[model] += 1
        by_model_sum[model] += amt

    print("\n[2] 프로바이더별 누적 지출:")
    for prov, cnt in sorted(by_prov_cnt.items(), key=lambda x: -by_prov_sum[x[0]]):
        print(f"    {prov:20s}  레코드 {cnt:5d}건   누적 {_fmt_money(by_prov_sum[prov])}")

    print("\n[3] kind 별 분포:")
    for kind, cnt in by_kind_cnt.most_common():
        print(f"    {kind:8s}  {cnt:5d}건   누적 {_fmt_money(by_kind_sum[kind])}")

    print("\n[4] model_id top 15 (지출액 기준):")
    top = sorted(by_model_sum.items(), key=lambda x: -x[1])[:15]
    for model, total in top:
        print(f"    {model:40s}  {by_model_cnt[model]:5d}건   {_fmt_money(total)}")

    # 잔액 파일 대조
    balances = load_balances()
    print(f"\n[5] 잔액 파일({BAL_FILE.name}) 상태:")
    if not balances:
        print("    (비어있음)")
    for prov, entry in balances.items():
        unit = entry.get("unit") or "USD"
        initial = float(entry.get("initial_amount", entry.get("amount", 0)) or 0)
        set_at = entry.get("set_at") or ""
        low_th = entry.get("low_threshold")
        # 원장에서 set_at 이후 합계
        spent_after = 0.0
        spent_before = 0.0
        for r in records:
            if r.get("provider") != prov:
                continue
            amt = float(r.get("amount_usd") or 0.0)
            ts = r.get("ts") or ""
            if set_at and ts < set_at:
                spent_before += amt
            else:
                spent_after += amt
        rem = max(0.0, initial - spent_after) if unit.upper() == "USD" else initial
        low_flag = "⚠ LOW" if (low_th is not None and rem < float(low_th)) else ""
        print(f"\n    ── {prov} ──")
        print(f"      unit          : {unit}")
        print(f"      initial       : {_fmt_money(initial) if unit.upper()=='USD' else f'{initial:,.2f} {unit}'}")
        print(f"      set_at        : {set_at or '(없음)'}")
        print(f"      spent_after   : {_fmt_money(spent_after)}  ← 대시보드가 빼는 값")
        print(f"      spent_before  : {_fmt_money(spent_before)}  ← set_at 이전(감산에서 제외된 숨은 지출)")
        print(f"      remaining     : {_fmt_money(rem) if unit.upper()=='USD' else f'{rem:,.2f} {unit}'}  {low_flag}")
        if low_th is not None:
            print(f"      low_threshold : {low_th}")

    # 미매핑 provider 감지 (registry provider 토큰 → 원장에 안 들어간 케이스 추정은 불가 — 여긴 생략)
    # 대신 ALLOWED_PROVIDERS 외 provider 가 원장에 있으면 표시
    allowed = {"Anthropic", "OpenAI", "ElevenLabs", "fal.ai", "xAI (Grok)"}
    unknown = {p for p in by_prov_cnt if p not in allowed}
    if unknown:
        print(f"\n[6] 화이트리스트 외 provider 감지: {sorted(unknown)}")
        for p in sorted(unknown):
            print(f"    {p:20s}  {by_prov_cnt[p]}건  {_fmt_money(by_prov_sum[p])}")
    else:
        print("\n[6] 화이트리스트 외 provider 없음 (정상)")

    # 최근 20 개
    print("\n[7] 최근 20 개 레코드 (ts 내림차순):")
    for r in sorted(records, key=lambda x: x.get("ts", ""), reverse=True)[:20]:
        print(f"    {r.get('ts','')} | {r.get('provider',''):12s} | {r.get('kind',''):6s} | "
              f"{_fmt_money(float(r.get('amount_usd') or 0)):>10s} | {r.get('model','')[:28]:28s} | "
              f"{r.get('note','')[:30]}")

    print("\n" + "=" * 72)
    print("끝.")


if __name__ == "__main__":
    main()
