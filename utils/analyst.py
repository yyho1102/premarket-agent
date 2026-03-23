"""
utils/analyst.py
模組 4：分析師目標價

資料來源：
  yfinance .info 欄位（Yahoo Finance 彙整的分析師共識）
  涵蓋：共識目標價、最高/最低目標、建議評等、分析師人數

欄位說明：
  targetMeanPrice   — 平均目標價
  targetHighPrice   — 最高目標價
  targetLowPrice    — 最低目標價
  targetMedianPrice — 中位目標價
  recommendationKey — 建議（strong_buy / buy / hold / sell）
  numberOfAnalystOpinions — 分析師人數
"""

import yfinance as yf
from datetime import datetime


# 建議評等中文對照
RECOMMEND_MAP = {
    "strong_buy":  "強力買進",
    "buy":         "買進",
    "hold":        "持有",
    "underperform":"表現落後",
    "sell":        "賣出",
}


def fetch_analyst_target(stock_id: str, stock_name: str = "") -> dict:
    """
    取得個股分析師目標價與評等
    stock_id: "2330"（自動補 .TW）或 "TSM"（美股ADR）
    """
    # 判斷是否需要補 .TW
    symbol = stock_id if stock_id.isalpha() else f"{stock_id}.TW"

    print(f"  分析師目標價：{symbol} {stock_name}")
    try:
        info = yf.Ticker(symbol).info

        mean_price   = info.get("targetMeanPrice")
        high_price   = info.get("targetHighPrice")
        low_price    = info.get("targetLowPrice")
        median_price = info.get("targetMedianPrice")
        rec_key      = info.get("recommendationKey", "")
        n_analysts   = info.get("numberOfAnalystOpinions", 0)
        current      = info.get("currentPrice") or info.get("regularMarketPrice")

        # 換算上下空間 %
        upside = None
        if mean_price and current and current > 0:
            upside = round((mean_price - current) / current * 100, 1)

        rec_zh = RECOMMEND_MAP.get(rec_key, rec_key)

        result = {
            "stock_id":       stock_id,
            "stock_name":     stock_name,
            "symbol":         symbol,
            "current_price":  current,
            "target_mean":    mean_price,
            "target_high":    high_price,
            "target_low":     low_price,
            "target_median":  median_price,
            "upside_pct":     upside,
            "recommendation": rec_zh,
            "rec_key":        rec_key,
            "n_analysts":     n_analysts,
            "signal":         _analyst_signal(rec_key, upside),
            "fetched_at":     datetime.now().isoformat(),
        }

        print(f"  目標均價: {mean_price}  ({upside:+.1f}% 空間)" if upside else f"  目標均價: {mean_price}")
        print(f"  評等: {rec_zh}  分析師: {n_analysts} 位")
        print(f"  區間: {low_price} ~ {high_price}")

        return result

    except Exception as e:
        print(f"  [WARN] {symbol} 分析師目標價失敗: {e}")
        return _empty_analyst(stock_id, stock_name)


def _analyst_signal(rec_key: str, upside: float | None) -> str:
    """綜合評等 + 上漲空間產生訊號"""
    if rec_key in ("strong_buy", "buy"):
        if upside and upside > 20:
            return "分析師強烈看多（大幅折價）"
        return "分析師看多"
    if rec_key == "hold":
        if upside and upside > 10:
            return "持有但仍有上漲空間"
        if upside and upside < -5:
            return "持有但已超漲"
        return "分析師中性"
    if rec_key in ("underperform", "sell"):
        return "分析師看空"
    return "評等未知"


def _empty_analyst(stock_id: str, stock_name: str) -> dict:
    return {
        "stock_id": stock_id, "stock_name": stock_name,
        "symbol": f"{stock_id}.TW",
        "current_price": None, "target_mean": None,
        "target_high": None, "target_low": None,
        "target_median": None, "upside_pct": None,
        "recommendation": "無資料", "rec_key": "",
        "n_analysts": 0, "signal": "無分析師資料",
        "fetched_at": datetime.now().isoformat(),
    }


# ────────────────────────────────────────────────────────────
# 直接執行測試
# ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("模組 4：分析師目標價測試")
    print(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 55)

    stocks = [
        ("2330", "台積電"),
        ("2327", "國巨"),
        ("6213", "聯茂電子"),
        ("TSM",  "台積電 ADR"),   # 美股 ADR 分析師更多
    ]

    for sid, sname in stocks:
        print(f"\n{'─'*45}")
        r = fetch_analyst_target(sid, sname)
        if r["target_mean"]:
            print(f"  上漲空間: {r['upside_pct']:+.1f}%")
            print(f"  訊號: {r['signal']}")
