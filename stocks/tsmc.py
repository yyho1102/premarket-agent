"""
stocks/tsmc.py
台積電 (2330) 盤前分析
核心方法：ADR 反推 + NVIDIA / Apple 客戶訊號 + 匯率換算

【折溢價計算說明】
  盤前執行時台股尚未開盤，yfinance 的 2330.TW 只有「上一個交易日收盤」。
  正確做法：用「ADR 昨收（prev）折合台幣」當基準，
  再比較「ADR 今收（latest）折合台幣」，得出漲跌幅即為今日預期缺口。
  公式：premium_pct = ADR 自身 change_pct（已是前後兩日 USD 價差）
        再加上當日匯率變動修正。
"""

import numpy as np
from datetime import datetime
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.fetcher import get_change, weighted_signal, compute_correlation, get_usdtwd
from utils.chips import fetch_chips
from utils.sentiment import analyze_stock_sentiment, sentiment_adjustment
from utils.analyst import fetch_analyst_target

# ── 設定 ────────────────────────────────────────────────────
ADR_SYMBOL = "TSM"
TW_SYMBOL  = "2330.TW"
ADR_RATIO  = 5          # 1 ADR = 5 股普通股

KEY_CUSTOMERS = {
    "NVDA": {"name": "NVIDIA",  "weight": 0.55, "note": "AI加速器最大客戶，HPC晶圓佔營收 ~35%"},
    "AAPL": {"name": "Apple",   "weight": 0.45, "note": "手機/M系列最大客戶，蘋果佔營收 ~25%"},
}

AUX_REFS = {
    "AMD":  {"name": "AMD",      "weight": 0.30, "note": "GPU/CPU 全委外台積電"},
    "AVGO": {"name": "Broadcom", "weight": 0.25, "note": "ASIC / 網通晶片"},
    "QCOM": {"name": "Qualcomm", "weight": 0.25, "note": "手機 AP 主力客戶"},
    "^SOX": {"name": "費城半導體", "weight": 0.20, "note": "大盤情緒參考"},
}


# ── 分析 ────────────────────────────────────────────────────
def analyze() -> dict:
    print("=" * 60)
    print("台積電 (2330) 盤前分析")
    print(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # 1. ADR + 匯率
    print("\n[1/4] ADR (TSM) + USD/TWD...")
    adr_data = get_change(ADR_SYMBOL)
    tw_data  = get_change(TW_SYMBOL)
    usdtwd   = get_usdtwd()

    if not adr_data:
        raise RuntimeError("無法取得 ADR 資料，請確認網路連線")

    adr_latest = adr_data["latest"]   # ADR 今收 (USD)
    adr_prev   = adr_data["prev"]     # ADR 昨收 (USD)
    adr_chg    = adr_data["change_pct"]

    # ── 台股昨收：從 TWSE MIS API 自動取得 ─────────────────────
    from utils.fetcher import get_tw_prev_close
    TW_PREV_CLOSE_FALLBACK = 1840.0   # TWSE API 失敗時備用，每季確認一次即可
    tw_prev_close, tw_source = get_tw_prev_close("2330", TW_PREV_CLOSE_FALLBACK)

    # ── ADR 缺口計算 ─────────────────────────────────────────
    # ADR 自身漲跌幅 = 最直接的台股開盤缺口預測
    premium_pct = adr_chg
    implied_twd = adr_latest / ADR_RATIO * usdtwd   # ADR今收反推台幣（供參考）
    premium_twd = tw_prev_close * premium_pct / 100

    print(f"  TSM ADR 昨收: USD {adr_prev:.2f}")
    print(f"  TSM ADR 今收: USD {adr_latest:.2f}  ({adr_chg:+.2f}%)")
    print(f"  USD/TWD     : {usdtwd:.3f}")
    print(f"  台積電昨收  : TWD {tw_prev_close:.1f}  [{tw_source}]")
    print(f"  ADR反推台幣 : TWD {implied_twd:.1f}  (僅參考，勿直接比較)")
    print(f"  ★ 預期缺口  : {premium_pct:+.2f}%  ({premium_twd:+.1f} TWD)")

    # 2. 關鍵客戶
    print("\n[2/4] 關鍵客戶 NVDA + AAPL...")
    cust_sig = weighted_signal(KEY_CUSTOMERS)
    for d in cust_sig["details"]:
        print(f"  {d['name']:8s}: {d['change_pct']:+.2f}%  量比{d['vol_ratio']:.1f}x")

    # 3. 輔助參考
    print("\n[3/4] 輔助參考...")
    aux_sig = weighted_signal(AUX_REFS)
    for d in aux_sig["details"]:
        print(f"  {d['name']:10s}: {d['change_pct']:+.2f}%")

    # 4. 相關係數
    print("\n[4/5] 歷史相關係數 (6個月)...")
    corr_cust = compute_correlation(TW_SYMBOL, list(KEY_CUSTOMERS.keys()))
    corr_aux  = compute_correlation(TW_SYMBOL, [s for s in AUX_REFS if not s.startswith("^")])
    print(f"  台積電 vs 客戶群: {corr_cust:.3f}")
    print(f"  台積電 vs 輔助群: {corr_aux:.3f}")

    # 5. 籌碼：三大法人 + 融資融券
    print("\n[5/6] 籌碼資料（三大法人 + 融資融券）...")
    chips = fetch_chips("2330", "台積電")
    chips_score = chips["chips_score"]
    print(f"  籌碼訊號: {chips['overall']}  (分數 {chips_score:+.1f})")
    for n in chips.get("notes", []):
        print(f"    • {n}")

    # 6. 新聞情緒分析
    print("\n[6/7] 新聞情緒分析...")
    sentiment  = analyze_stock_sentiment("2330", "台積電")
    sent_score = sentiment["combined_score"]
    sent_adj   = sentiment_adjustment(sent_score)
    print(f"  情緒分數: {sent_score:+.3f}  {sentiment['combined_label']}")
    print(f"  摘要: {sentiment['stock_news'].get('summary', '無')}")
    for n in sentiment["stock_news"].get("key_news", [])[:2]:
        print(f"    • {n}")

    # 7. 分析師目標價
    print("\n[7/7] 分析師目標價...")
    analyst = fetch_analyst_target("TSM", "台積電ADR")   # ADR 分析師覆蓋度更高
    upside  = analyst.get("upside_pct") or 0.0
    # 目標價上漲空間 > 20% 且評等偏多 → 輕微正向加分
    analyst_adj = 0.0
    if analyst["rec_key"] in ("strong_buy", "buy") and upside > 10:
        analyst_adj = 0.2
    elif analyst["rec_key"] in ("underperform", "sell"):
        analyst_adj = -0.2
    print(f"  評等: {analyst['recommendation']}  目標均價: {analyst.get('target_mean')}  空間: {upside:+.1f}%")

    # ── 預測公式 ──
    # ADR 49% + 客戶 32% + 輔助 9% + 籌碼 4% + 情緒 4% + 分析師 2%
    customer_signal = cust_sig["score"] * 0.55
    aux_signal      = aux_sig["score"]  * 0.50
    chips_adj       = chips_score * 0.3

    predicted_chg = (
        premium_pct     * 0.49 +
        customer_signal * 0.32 +
        aux_signal      * 0.09 +
        chips_adj       * 0.04 +
        sent_adj        * 0.04 +
        analyst_adj     * 0.02
    )
    predicted_price = round(tw_prev_close * (1 + predicted_chg / 100), 0)

    # 信心度（情緒與ADR同向則提升信心）
    if np.sign(premium_pct) == np.sign(cust_sig["score"]) and abs(premium_pct) > 1.0:
        confidence, conf_pct = "高", 80
        if np.sign(sent_score) == np.sign(premium_pct):
            conf_pct = min(conf_pct + 5, 90)   # 情緒同向，信心+5%
    elif abs(premium_pct) > 0.5:
        confidence, conf_pct = "中", 60
    else:
        confidence, conf_pct = "低", 38

    key_signals = [
        f"ADR 缺口 {premium_pct:+.2f}%（昨收 TWD {tw_prev_close:.0f} → 預測 TWD {predicted_price:.0f}）",
        f"{'↑' if cust_sig['score'] > 0 else '↓'} NVDA+AAPL 加權 {cust_sig['score']:+.2f}%",
        f"新聞情緒 {sentiment['combined_label']}（{sent_score:+.2f}）",
    ]
    risk_flags = []
    if np.sign(premium_pct) != np.sign(cust_sig["score"]):
        risk_flags.append("ADR 與客戶訊號方向分歧，注意匯率干擾")
    if abs(premium_pct) < 0.5:
        risk_flags.append("ADR 漲跌幅小，今日可能盤整")
    for r in sentiment["stock_news"].get("risks", []):
        risk_flags.append(f"新聞風險：{r}")

    result = {
        "timestamp":  datetime.now().isoformat(),
        "stock":      {"symbol": "2330.TW", "name": "台積電"},
        "adr": {
            "price_usd":   adr_latest,
            "prev_usd":    adr_prev,
            "change_pct":  adr_chg,
            "vol_ratio":   adr_data["vol_ratio"],
            "usdtwd":      usdtwd,
            "implied_twd": round(implied_twd, 1),
            "premium_pct": round(premium_pct, 2),
            "premium_twd": round(premium_twd, 1),
        },
        "tw_prev_close": tw_prev_close,
        "tw_source":     tw_source,
        "key_customers": cust_sig,
        "aux_refs":      aux_sig,
        "chips":         chips,
        "sentiment":     sentiment,
        "analyst":       analyst,
        "correlation":   {"customers": corr_cust, "aux": corr_aux},
        "prediction": {
            "predicted_change_pct": round(predicted_chg, 2),
            "predicted_price_twd":  predicted_price,
            "confidence":           confidence,
            "confidence_pct":       conf_pct,
            "key_signals":          key_signals,
            "risk_flags":           risk_flags,
        },
    }

    arrow = "▲" if predicted_chg > 0 else "▼"
    print(f"\n{'='*60}")
    print(f"台積電預測: {arrow} {predicted_chg:+.2f}%  → TWD {predicted_price:.0f}")
    print(f"信心度: {confidence} ({conf_pct}%)")
    return result


if __name__ == "__main__":
    result = analyze()
    os.makedirs("reports", exist_ok=True)
    fname = f"reports/tsmc_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n報告輸出: {fname}")
