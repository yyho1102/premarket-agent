"""
utils/fetcher.py
共用資料擷取工具 - 終極穩定版
"""

import yfinance as yf
import pandas as pd
import numpy as np
import requests
from datetime import datetime
from typing import Any, cast, Optional
import warnings

warnings.filterwarnings("ignore")

_MIS_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
_MIS_HEADERS = {"User-Agent": "Mozilla/5.0"}

def get_tw_close(stock_id: str) -> tuple[Optional[float], str]:
    """取得台股價格 (優先 MIS, 備援 yfinance)"""
    ex = "otc" if stock_id.startswith(("6", "5")) else "tse"
    ex_ch = f"{ex}_{stock_id}.tw"
    
    try:
        resp = requests.get(_MIS_URL, params={"ex_ch": ex_ch, "json": "1"}, headers=_MIS_HEADERS, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            msg = data.get("msgArray", [])
            if msg:
                p_str = msg[0].get("z") if msg[0].get("z") != "-" else msg[0].get("y")
                if p_str and p_str != "-":
                    return float(p_str), "TWSE_MIS"
    except: pass

    try:
        ticker = yf.Ticker(f"{stock_id}.TW")
        hist = ticker.history(period="2d")
        if hist is not None and not hist.empty:
            return float(hist['Close'].iloc[-1]), "yfinance"
    except: pass

    return None, "none"

def get_usdtwd() -> float:
    try:
        df = yf.download("TWD=X", period="1d", progress=False)
        if df is not None and not df.empty:
            return float(df["Close"].iloc[-1])
        return 32.5
    except: return 32.5

def get_change(symbol: str, period: str = "2d") -> dict[str, Any]:
    try:
        ticker = yf.Ticker(symbol)
        h = ticker.history(period=period)
        if h is None or len(h) < 2: 
            return {"change_pct": 0.0, "vol_ratio": 1.0, "last_close": 0.0}
        
        p_close, c_close = h["Close"].iloc[-2], h["Close"].iloc[-1]
        return {
            "change_pct": round(((c_close - p_close) / p_close * 100), 2),
            "vol_ratio": round((h["Volume"].iloc[-1] / h["Volume"].mean()), 2),
            "last_close": round(float(c_close), 2)
        }
    except: return {"change_pct": 0.0, "vol_ratio": 1.0, "last_close": 0.0}

def weighted_signal(targets: dict[str, Any], period: str = "2d") -> dict[str, Any]:
    total_w, w_sum, details = 0.0, 0.0, []
    for sym, cfg in targets.items():
        w = cfg.get("weight", 0.0)
        d = get_change(sym, period)
        total_w += w
        w_sum += d["change_pct"] * w
        details.append({"symbol": sym, "change_pct": d["change_pct"], "weight": w})
    return {"score": round(w_sum / total_w, 3) if total_w > 0 else 0.0, "details": details}

def compute_correlation(symbol_a: str, symbols_b: list[str], period: str = "6mo") -> float:
    """計算相關係數 - 徹底修正 Pylance 報錯"""
    try:
        all_syms = [symbol_a] + symbols_b
        # 移除明確的 pd.DataFrame 宣告，改用類型檢查
        raw_df = yf.download(all_syms, period=period, auto_adjust=True, progress=False)
        
        if raw_df is None or (isinstance(raw_df, pd.DataFrame) and raw_df.empty):
            return 0.5
            
        df = cast(pd.DataFrame, raw_df)

        # 處理 yfinance 多股票時的 MultiIndex
        if isinstance(df.columns, pd.MultiIndex):
            prices = cast(pd.DataFrame, df["Close"])
        else:
            prices = df

        if prices is None or prices.empty:
            return 0.5

        returns = cast(pd.DataFrame, prices.pct_change().dropna())
        
        # 檢查欄位是否存在
        col_names = [str(c) for c in returns.columns]
        if symbol_a not in col_names:
            return 0.5
            
        valid_b = [s for s in symbols_b if s in col_names]
        if not valid_b:
            return 0.5
            
        target_series = cast(pd.Series, returns[symbol_a])
        b_group_df = cast(pd.DataFrame, returns[valid_b])
        
        # 使用字串 'columns' 避免 axis=1 的型別爭議
        avg_b_returns = b_group_df.mean(axis='columns') 
        
        corr_val = target_series.corr(avg_b_returns)
        
        if np.isnan(corr_val):
            return 0.5
            
        return round(float(corr_val), 3)
    except Exception as e:
        print(f"Correlation Error: {e}")
        return 0.5