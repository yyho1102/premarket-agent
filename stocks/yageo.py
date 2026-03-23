"""
stocks/yageo.py
國巨 (2327) 盤前分析
日本被動元件對標：Resonac (前日立化成)、TDK、太陽誘電、Alps Alpine
"""

import numpy as np
from datetime import datetime
import json, sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.fetcher import get_change, weighted_signal, compute_correlation, get_tw_prev_close
from utils.chips import fetch_chips
from utils.sentiment import analyze_stock_sentiment, sentiment_adjustment
from utils.analyst import fetch_analyst_target

TW_SYMBOL              = "2327.TW"
TW_STOCK_ID            = "2327"
TW_PREV_CLOSE_FALLBACK = 275.0   # TWSE API 失敗時備用，每季確認一次即可

JP_PASSIVE = {
    "6981.T": {"name": "村田製作所 Murata",   "weight": 0.40, "note": "MLCC全球第一，最直接領先指標"},
    "6762.T": {"name": "TDK",                  "weight": 0.25, "note": "電感/電容/磁性元件"},
    "6976.T": {"name": "太陽誘電 Taiyo Yuden", "weight": 0.20, "note": "MLCC第四大，同蘋果供應鏈"},
    "6770.T": {"name": "Alps Alpine",           "weight": 0.15, "note": "電子元件，汽車/IoT"},
}

US_DOWNSTREAM = {
    "AAPL": {"name": "Apple",  "weight": 0.30, "note": "最大MLCC消費端"},
    "NVDA": {"name": "NVIDIA", "weight": 0.25, "note": "AI伺服器需求，鉭電容大客戶"},
    "AMAT": {"name": "AMAT",   "weight": 0.20, "note": "半導體設備"},
    "DELL": {"name": "Dell",   "weight": 0.15, "note": "AI伺服器組裝"},
    "HPQ":  {"name": "HP",     "weight": 0.10, "note": "消費電子需求端"},
}


def analyze() -> dict:
    print("=" * 58)
    print("國巨 (2327) 盤前分析")
    print(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 58)

    print("\n[1/4] 日本被動元件對標...")
    jp_sig = weighted_signal(JP_PASSIVE)
    print(f"  加權均漲跌: {jp_sig['score']:+.2f}%")
    for d in jp_sig["details"]:
        print(f"  {d['name']:22s}: {d['change_pct']:+.2f}%  量比{d['vol_ratio']:.1f}x")

    print("\n[2/4] 美股下游需求端...")
    us_sig = weighted_signal(US_DOWNSTREAM)
    print(f"  加權均漲跌: {us_sig['score']:+.2f}%")

    print("\n[3/4] 原物料...")
    silver = get_change("SI=F")
    silver_chg = silver["change_pct"] if silver else 0.0
    print(f"  白銀: {silver_chg:+.2f}%")

    print(f"\n[4/5] 台股昨收 + 相關係數...")
    tw_prev_close, tw_source = get_tw_prev_close(TW_STOCK_ID, TW_PREV_CLOSE_FALLBACK)
    corr_jp = compute_correlation(TW_SYMBOL, list(JP_PASSIVE.keys()))
    corr_us = compute_correlation(TW_SYMBOL, list(US_DOWNSTREAM.keys()))
    print(f"  國巨昨收: TWD {tw_prev_close:.1f}  [{tw_source}]")
    print(f"  國巨 vs 日本被動元件: {corr_jp:.3f}")
    print(f"  國巨 vs 美股下游:     {corr_us:.3f}")

    # 5. 籌碼
    print("\n[5/5] 籌碼資料（三大法人 + 融資融券）...")
    chips = fetch_chips("2327", "國巨")
    chips_score = chips["chips_score"]
    print(f"  籌碼訊號: {chips['overall']}  (分數 {chips_score:+.1f})")
    for n in chips.get("notes", []):
        print(f"    • {n}")

    # 銀價因子：超過 2% 代表可轉嫁（正向），否則為成本壓力
    silver_factor = 0.3 if silver_chg > 2.0 else (-0.1 * silver_chg)
    chips_adj     = chips_score * 0.3

    # 新聞情緒
    print("\n[6/7] 新聞情緒分析...")
    sentiment  = analyze_stock_sentiment("2327", "國巨")
    sent_score = sentiment["combined_score"]
    sent_adj   = sentiment_adjustment(sent_score)
    print(f"  情緒分數: {sent_score:+.3f}  {sentiment['combined_label']}")
    print(f"  摘要: {sentiment['stock_news'].get('summary', '無')}")

    # 分析師目標價
    print("\n[7/7] 分析師目標價...")
    analyst     = fetch_analyst_target("2327", "國巨")
    upside      = analyst.get("upside_pct") or 0.0
    analyst_adj = 0.2 if analyst["rec_key"] in ("strong_buy","buy") and upside > 10 else \
                 -0.2 if analyst["rec_key"] in ("underperform","sell") else 0.0
    print(f"  評等: {analyst['recommendation']}  空間: {upside:+.1f}%")

    raw_pred = (jp_sig["score"] * 0.50 + us_sig["score"] * 0.35) * 0.65 + silver_factor * 0.10 + chips_adj * 0.03 + sent_adj * 0.01 + analyst_adj * 0.01
    if corr_jp > 0.7:
        raw_pred *= 1.1
    elif corr_jp < 0.4:
        raw_pred *= 0.8

    predicted_chg   = round(raw_pred, 2)
    predicted_price = round(tw_prev_close * (1 + predicted_chg / 100), 0)

    if np.sign(jp_sig["score"]) == np.sign(us_sig["score"]) and abs(jp_sig["score"]) > 1.0:
        confidence, conf_pct = "高", 75
        if np.sign(sent_score) == np.sign(jp_sig["score"]):
            conf_pct = min(conf_pct + 5, 88)
    elif abs(jp_sig["score"]) > 0.5:
        confidence, conf_pct = "中", 55
    else:
        confidence, conf_pct = "低", 35

    top_jp = max(jp_sig["details"], key=lambda x: abs(x["change_pct"]), default=None)
    key_signals = []
    if top_jp:
        key_signals.append(f"{'↑' if top_jp['change_pct'] > 0 else '↓'} {top_jp['name']} {top_jp['change_pct']:+.1f}%")
    if abs(silver_chg) > 1.5:
        key_signals.append(f"銀價 {silver_chg:+.1f}%")
    key_signals.append(f"新聞情緒 {sentiment['combined_label']}（{sent_score:+.2f}）")

    risk_flags = []
    if np.sign(jp_sig["score"]) != np.sign(us_sig["score"]):
        risk_flags.append("日美訊號分歧")
    for r in sentiment["stock_news"].get("risks", []):
        risk_flags.append(f"新聞風險：{r}")

    result = {
        "timestamp":     datetime.now().isoformat(),
        "stock":         {"symbol": TW_SYMBOL, "name": "國巨"},
        "tw_prev_close": tw_prev_close,
        "tw_source":     tw_source,
        "jp_passive":    jp_sig,
        "us_downstream": us_sig,
        "silver_chg":    silver_chg,
        "chips":         chips,
        "sentiment":     sentiment,
        "analyst":       analyst,
        "correlation":   {"jp_6mo": corr_jp, "us_6mo": corr_us},
        "prediction": {
            "predicted_change_pct": predicted_chg,
            "predicted_price_twd":  predicted_price,
            "confidence":           confidence,
            "confidence_pct":       conf_pct,
            "key_signals":          key_signals,
            "risk_flags":           risk_flags,
        },
    }

    arrow = "▲" if predicted_chg > 0 else "▼"
    print(f"\n{'='*58}")
    print(f"國巨預測: {arrow} {predicted_chg:+.2f}%  → TWD {predicted_price:.0f}  ({confidence}信心 {conf_pct}%)")
    return result


if __name__ == "__main__":
    result = analyze()
    os.makedirs("reports", exist_ok=True)
    fname = f"reports/yageo_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n報告輸出: {fname}")
