"""
utils/fetcher.py
共用資料擷取工具 - 所有股票模組共用
"""

import yfinance as yf
import pandas as pd
import numpy as np
import requests
from datetime import datetime
import warnings

warnings.filterwarnings("ignore")

# TWSE / TPEx 即時行情 API
_MIS_URL  = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
_MIS_HEADERS = {"User-Agent": "Mozilla/5.0"}


def get_tw_close(stock_id: str) -> float | None:
    """
    從 TWSE MIS API 取得台股「昨收價」（y 欄位）
    支援上市（tse_XXXX.tw）與上櫃（otc_XXXX.tw）

    上市：2330、2327 等 4 碼
    上櫃：6213 等 4 碼開頭為 6/5 者

    回傳昨收價 float，失敗回傳 None
    """
    # 判斷上市 or 上櫃
    if stock_id.startswith("6") or stock_id.startswith("5"):
        ex = "otc"
    else:
        ex = "tse"

    ex_ch = f"{ex}_{stock_id}.tw"
    try:
        resp = requests.get(
            _MIS_URL,
            params={"ex_ch": ex_ch, "json": "1", "delay": "0"},
            headers=_MIS_HEADERS,
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        arr  = data.get("msgArray", [])
        if not arr:
            return None
        row = arr[0]
        y   = row.get("y", "-")   # y = 昨收價
        if y == "-" or y == "":
            return None
        return round(float(y), 2)
    except Exception as e:
        print(f"  [WARN] TWSE MIS {stock_id}: {e}")
        return None


def get_tw_prev_close(stock_id: str, fallback: float) -> tuple[float, str]:
    """
    自動取得台股昨收價，失敗時使用 fallback 值
    回傳 (昨收價, 來源說明)

    用法：
        tw_prev_close, tw_source = get_tw_prev_close("2327", 275.0)
    """
    price = get_tw_close(stock_id)
    if price and abs(price - fallback) / fallback < 0.30:
        # TWSE 回傳值與 fallback 差距在 30% 以內 → 採用 TWSE
        return price, "TWSE MIS"
    elif price:
        # 差距過大（可能 fallback 過時）→ 仍採用 TWSE，但警告
        print(f"  [INFO] {stock_id} TWSE={price:.1f} vs fallback={fallback:.1f}，採用 TWSE")
        return price, "TWSE MIS（fallback差異大）"
    else:
        # TWSE 失敗 → 用 fallback
        return fallback, "fallback（TWSE失敗）"


def get_change(symbol: str) -> dict | None:
    """
    取得單一股票最新漲跌幅、量比、收盤價

    Returns:
        {
            "change_pct": float,   # 漲跌幅 %
            "latest":    float,   # 最新收盤
            "prev":      float,   # 昨日收盤
            "vol_ratio": float,   # 量比（今日 / 90日均量）
        }
        或 None（取得失敗）
    """
    try:
        ticker = yf.Ticker(symbol)
        hist   = ticker.history(period="5d")
        if len(hist) < 2:
            return None
        c   = hist["Close"]
        v   = hist["Volume"]
        latest = float(c.iloc[-1])
        prev   = float(c.iloc[-2])
        chg    = (latest - prev) / prev * 100

        hist90 = ticker.history(period="3mo")
        avg_v  = float(hist90["Volume"].mean()) if len(hist90) > 5 else float(v.mean())
        vr     = float(v.iloc[-1]) / avg_v if avg_v > 0 else 1.0

        return {
            "change_pct": round(chg,    3),
            "latest":     round(latest, 4),
            "prev":       round(prev,   4),
            "vol_ratio":  round(vr,     2),
        }
    except Exception as e:
        print(f"  [WARN] {symbol}: {e}")
        return None


def weighted_signal(peer_group: dict) -> dict:
    """
    計算一組股票的加權平均訊號

    peer_group 格式：
        { "NVDA": {"name": "NVIDIA", "weight": 0.6, "note": "..."}, ... }

    Returns:
        { "score": float, "details": [...] }
    """
    details      = []
    weighted_sum = 0.0
    total_w      = 0.0

    for sym, cfg in peer_group.items():
        d = get_change(sym)
        if d is None:
            continue
        w = cfg.get("weight", 1.0)
        weighted_sum += d["change_pct"] * w
        total_w      += w
        details.append({
            "symbol":     sym,
            "name":       cfg.get("name", sym),
            "change_pct": d["change_pct"],
            "vol_ratio":  d["vol_ratio"],
            "weight":     w,
            "note":       cfg.get("note", ""),
        })

    score = weighted_sum / total_w if total_w > 0 else 0.0
    return {"score": round(score, 3), "details": details}


def compute_correlation(symbol_a: str, symbols_b: list[str], period: str = "6mo") -> float:
    """
    計算 symbol_a 與 symbols_b 群組的 6 個月歷史相關係數

    Returns:
        float：相關係數 (-1 ~ 1)，失敗時回傳 0.5
    """
    try:
        all_syms = [symbol_a] + symbols_b
        prices   = yf.download(all_syms, period=period, auto_adjust=True, progress=False)
        if isinstance(prices.columns, pd.MultiIndex):
            prices = prices["Close"]
        returns  = prices.pct_change().dropna()
        if symbol_a not in returns.columns:
            return 0.5
        b_cols = [s for s in symbols_b if s in returns.columns]
        if not b_cols:
            return 0.5
        corr = returns[symbol_a].corr(returns[b_cols].mean(axis=1))
        return round(float(corr) if not np.isnan(corr) else 0.5, 3)
    except:
        return 0.5


def get_usdtwd() -> float:
    """取得即時 USD/TWD 匯率，失敗時回傳預設值 31.5"""
    d = get_change("TWD=X")
    return round(d["latest"], 3) if d else 31.5


def classify_signal(score: float) -> str:
    """將分數轉成文字訊號"""
    if score >  1.5: return "強多"
    if score >  0.3: return "弱多"
    if score < -1.5: return "強空"
    if score < -0.3: return "弱空"
    return "中性"
