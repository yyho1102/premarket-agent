"""
stocks/iteq.py
聯茂電子 (6213) 盤前分析
日本材料商對標：Resonac (前日立化成)、Panasonic、住友電木、三井化學
"""

import numpy as np
from datetime import datetime
import json, sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.fetcher import get_change, weighted_signal, compute_correlation, get_tw_prev_close
from utils.chips import fetch_chips
from utils.sentiment import analyze_stock_sentiment, sentiment_adjustment
from utils.analyst import fetch_analyst_target

TW_SYMBOL              = "6213.TW"
TW_STOCK_ID            = "6213"
TW_PREV_CLOSE_FALLBACK = 143.5   # TWSE API 失敗時備用，每季確認一次即可

JP_MATERIALS = {
    "4004.T": {"name": "Resonac（前日立化成）", "weight": 0.40, "note": "PCB層壓材料＆半導體後工程材料，使用者指定核心對標"},
    "6752.T": {"name": "Panasonic Holdings",    "weight": 0.25, "note": "Megtron高速CCL，與聯茂搶同一客戶"},
    "4203.T": {"name": "住友電木",               "weight": 0.20, "note": "半導體封裝材料＆PCB基板樹脂"},
    "4183.T": {"name": "三井化學",               "weight": 0.15, "note": "CCL上游環氧樹脂供應商"},
}

US_AI_SERVER = {
    "NVDA": {"name": "NVIDIA",           "weight": 0.35, "note": "AI加速器最大買家，高階CCL需求直接指標"},
    "AVGO": {"name": "Broadcom",          "weight": 0.25, "note": "ASIC晶片＆800G交換器PCB大客戶"},
    "MSFT": {"name": "Microsoft",         "weight": 0.20, "note": "Azure資料中心擴張"},
    "DELL": {"name": "Dell Technologies", "weight": 0.20, "note": "AI伺服器組裝出貨"},
}


def analyze() -> dict:
    print("=" * 58)
    print("聯茂電子 (6213) 盤前分析")
    print(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 58)

    print("\n[1/4] 日本電子材料商（Resonac/Panasonic/住友電木）...")
    jp_sig = weighted_signal(JP_MATERIALS)
    print(f"  加權均漲跌: {jp_sig['score']:+.2f}%")
    for d in jp_sig["details"]:
        print(f"  {d['name']:22s}: {d['change_pct']:+.2f}%  量比{d['vol_ratio']:.1f}x")

    print("\n[2/4] 美股 AI 伺服器需求端...")
    us_sig = weighted_signal(US_AI_SERVER)
    print(f"  加權均漲跌: {us_sig['score']:+.2f}%")

    print("\n[3/4] 原物料（銅/美元）...")
    copper = get_change("HG=F")
    usd    = get_change("DX-Y.NYB")
    copper_chg = copper["change_pct"] if copper else 0.0
    usd_chg    = usd["change_pct"]    if usd    else 0.0
    print(f"  銅價: {copper_chg:+.2f}%  美元: {usd_chg:+.2f}%")

    print(f"\n[4/5] 台股昨收 + 相關係數...")
    tw_prev_close, tw_source = get_tw_prev_close(TW_STOCK_ID, TW_PREV_CLOSE_FALLBACK)
    corr_resonac = compute_correlation(TW_SYMBOL, ["4004.T"])
    corr_jp      = compute_correlation(TW_SYMBOL, list(JP_MATERIALS.keys()))
    corr_us      = compute_correlation(TW_SYMBOL, list(US_AI_SERVER.keys()))
    print(f"  聯茂昨收: TWD {tw_prev_close:.1f}  [{tw_source}]")
    print(f"  聯茂 vs Resonac（核心）: {corr_resonac:.3f}")
    print(f"  聯茂 vs 日本材料商:     {corr_jp:.3f}")
    print(f"  聯茂 vs AI伺服器需求:  {corr_us:.3f}")

    # 5. 籌碼
    print("\n[5/5] 籌碼資料（三大法人 + 融資融券）...")
    chips = fetch_chips("6213", "聯茂電子")
    chips_score = chips["chips_score"]
    print(f"  籌碼訊號: {chips['overall']}  (分數 {chips_score:+.1f})")
    for n in chips.get("notes", []):
        print(f"    • {n}")

    # Resonac 單獨加成
    resonac_d = next((d for d in jp_sig["details"] if d["symbol"] == "4004.T"), None)
    resonac_boost = resonac_d["change_pct"] * 0.10 if resonac_d and abs(resonac_d["change_pct"]) > 1.5 else 0.0

    copper_factor = -0.15 * copper_chg if abs(copper_chg) < 3 else 0.0
    usd_factor    = 0.05 * usd_chg
    chips_adj     = chips_score * 0.3

    raw_pred = (
        jp_sig["score"] * 0.45 +
        us_sig["score"] * 0.40 +
        copper_factor   * 0.08 +
        usd_factor      * 0.04 +
        chips_adj       * 0.03 +
        resonac_boost
    ) * 0.65

    if corr_resonac > 0.65:
        raw_pred *= 1.1
    elif corr_resonac < 0.35:
        raw_pred *= 0.8

    # 新聞情緒
    print("\n[6/7] 新聞情緒分析...")
    sentiment  = analyze_stock_sentiment("6213", "聯茂電子")
    sent_score = sentiment["combined_score"]
    sent_adj   = sentiment_adjustment(sent_score)
    raw_pred  += sent_adj * 0.01
    print(f"  情緒分數: {sent_score:+.3f}  {sentiment['combined_label']}")
    print(f"  摘要: {sentiment['stock_news'].get('summary', '無')}")

    # 分析師目標價
    print("\n[7/7] 分析師目標價...")
    analyst     = fetch_analyst_target("6213", "聯茂電子")
    upside      = analyst.get("upside_pct") or 0.0
    analyst_adj = 0.2 if analyst["rec_key"] in ("strong_buy","buy") and upside > 10 else \
                 -0.2 if analyst["rec_key"] in ("underperform","sell") else 0.0
    raw_pred   += analyst_adj * 0.01
    print(f"  評等: {analyst['recommendation']}  空間: {upside:+.1f}%")

    predicted_chg   = round(raw_pred, 2)
    predicted_price = round(tw_prev_close * (1 + predicted_chg / 100), 0)

    if np.sign(jp_sig["score"]) == np.sign(us_sig["score"]) and abs(jp_sig["score"]) > 1.0 and abs(us_sig["score"]) > 0.8:
        confidence, conf_pct = "高", 78
        if np.sign(sent_score) == np.sign(jp_sig["score"]):
            conf_pct = min(conf_pct + 5, 88)
    elif abs(jp_sig["score"]) > 0.5 or abs(us_sig["score"]) > 0.5:
        confidence, conf_pct = "中", 58
    else:
        confidence, conf_pct = "低", 35

    key_signals = []
    if resonac_d:
        key_signals.append(f"{'↑' if resonac_d['change_pct'] > 0 else '↓'} Resonac {resonac_d['change_pct']:+.1f}%")
    top_us = max(us_sig["details"], key=lambda x: abs(x["change_pct"]), default=None)
    if top_us:
        key_signals.append(f"{'↑' if top_us['change_pct'] > 0 else '↓'} {top_us['name']} {top_us['change_pct']:+.1f}%")
    key_signals.append(f"新聞情緒 {sentiment['combined_label']}（{sent_score:+.2f}）")

    risk_flags = []
    if np.sign(jp_sig["score"]) != np.sign(us_sig["score"]):
        risk_flags.append("材料商與需求端訊號分歧")
    for r in sentiment["stock_news"].get("risks", []):
        risk_flags.append(f"新聞風險：{r}")

    result = {
        "timestamp":     datetime.now().isoformat(),
        "stock":         {"symbol": TW_SYMBOL, "name": "聯茂電子"},
        "tw_prev_close": tw_prev_close,
        "tw_source":     tw_source,
        "jp_materials":  jp_sig,
        "us_ai":         us_sig,
        "materials":     {"copper_chg": copper_chg, "usd_chg": usd_chg},
        "chips":         chips,
        "sentiment":     sentiment,
        "analyst":       analyst,
        "correlation":   {"resonac_6mo": corr_resonac, "jp_6mo": corr_jp, "us_6mo": corr_us},
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
    print(f"聯茂預測: {arrow} {predicted_chg:+.2f}%  → TWD {predicted_price:.0f}  ({confidence}信心 {conf_pct}%)")
    return result


if __name__ == "__main__":
    result = analyze()
    os.makedirs("reports", exist_ok=True)
    fname = f"reports/iteq_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n報告輸出: {fname}")
