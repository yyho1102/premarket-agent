"""
main.py
盤前分析 Agent - 一鍵執行全部個股分析
用法：python main.py
      python main.py --stocks tsmc yageo   # 只跑指定個股
      python main.py --no-line             # 不推播 LINE
"""

import json
import os
import sys
import argparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# 個股模組
from stocks import tsmc, yageo, iteq
from utils.line_notify import push_report

STOCK_MODULES = {
    "tsmc":  {"module": tsmc,  "name": "台積電 2330"},
    "yageo": {"module": yageo, "name": "國巨   2327"},
    "iteq":  {"module": iteq,  "name": "聯茂   6213"},
}


def run_all(targets: list[str] | None = None, send_line: bool = True) -> dict:
    targets = targets or list(STOCK_MODULES.keys())
    results = {}

    print("=" * 65)
    print(f"  盤前分析 Agent  |  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  執行個股：{', '.join(targets)}")
    print("=" * 65)

    # 平行執行（加快速度）
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(STOCK_MODULES[t]["module"].analyze): t
            for t in targets if t in STOCK_MODULES
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as e:
                print(f"\n[ERROR] {key}: {e}")
                results[key] = {"error": str(e)}

    # 摘要列印
    print("\n" + "=" * 65)
    print("  ── 盤前摘要 ──")
    for key, r in results.items():
        name = STOCK_MODULES[key]["name"]
        if "error" in r:
            print(f"  {name}: 分析失敗 - {r['error']}")
            continue
        pred  = r.get("prediction", {})
        chg   = pred.get("predicted_change_pct", 0)
        conf  = pred.get("confidence", "─")
        arrow = "▲" if chg > 0 else "▼"
        print(f"  {name}: {arrow} {chg:+.2f}%  （{conf}信心）")
    print("=" * 65)

    # 儲存報告
    os.makedirs("reports", exist_ok=True)
    fname   = f"reports/summary_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    summary = {"timestamp": datetime.now().isoformat(), "stocks": results}
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n  報告儲存: {fname}")

    # LINE 推播
    if send_line:
        push_report(summary)

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="盤前分析 Agent")
    parser.add_argument(
        "--stocks", nargs="*",
        choices=list(STOCK_MODULES.keys()),
        help="指定要分析的個股 (預設全部)",
    )
    parser.add_argument(
        "--no-line", action="store_true",
        help="不推播 LINE（僅儲存報告）",
    )
    args = parser.parse_args()
    run_all(args.stocks, send_line=not args.no_line)
