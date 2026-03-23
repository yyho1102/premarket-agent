"""
utils/chips.py
模組 3：三大法人動向 + 融資融券

資料來源（依優先順序）：
  1. TWSE OpenAPI  — openapi.twse.com.tw（上市股）
  2. TPEx OpenAPI  — www.tpex.org.tw/openapi（上櫃股）
  3. FinMind API   — api.finmindtrade.com（備援，需免費註冊）

資料更新時間：
  三大法人：每日 16:00 後
  融資融券：每日 20:00 後
"""

import requests
import time
from datetime import datetime, date

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# TWSE/TPEx 憑證缺少 Subject Key Identifier，Python 3.14+ 驗證更嚴格
# 關閉 SSL 驗證（僅限政府開放資料 API，無安全疑慮）
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
VERIFY_SSL = False

# ────────────────────────────────────────────────────────────
# 判斷上市 / 上櫃
# ────────────────────────────────────────────────────────────

def _is_otc(stock_id: str) -> bool:
    """
    簡易判斷：上櫃股（TPEx）通常以 6、4、3 開頭
    上市股（TWSE）通常以 1、2 開頭
    例外個股可手動覆蓋
    """
    OTC_PREFIXES = ("6", "4", "3", "8", "9")
    return stock_id.startswith(OTC_PREFIXES)


# ────────────────────────────────────────────────────────────
# TWSE OpenAPI — 三大法人（上市）
# ────────────────────────────────────────────────────────────

def _fetch_twse_institutional(stock_id: str) -> dict | None:
    """
    優先 TWSE T86，失敗時 fallback 到 FinMind
    """
    # 先試 TWSE T86
    url = "https://openapi.twse.com.tw/v1/fund/T86"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12, verify=VERIFY_SSL)
        resp.raise_for_status()
        text = resp.text.strip()
        if text and text != "[]":
            data = resp.json()
            for row in data:
                code = str(row.get("證券代號", row.get("Code", "")))
                if code == stock_id:
                    return _parse_twse_inst(row)
    except Exception as e:
        print(f"  [WARN] TWSE T86 失敗: {e}")

    # T86 無資料或失敗 → FinMind 備援
    return _fetch_tpex_institutional(stock_id)


def _parse_twse_inst(row: dict) -> dict:
    def n(k, *alt):
        for key in (k, *alt):
            v = row.get(key, "")
            try:
                return int(str(v).replace(",", "").replace("+", "").strip() or "0")
            except:
                pass
        return 0

    # TWSE T86 實際欄位名（中文）
    foreign = n("外資及陸資(不含外資自營商)買賣超股數",
                "Foreign_Investor_Buy_Sell", "外陸資買賣超股數(不含外資自營商)")
    trust   = n("投信買賣超股數",
                "Investment_Trust_Buy_Sell")
    dealer  = n("自營商買賣超股數(自行買賣)",
                "Dealer_Buy_Sell", "自營商買賣超股數")
    total   = n("三大法人買賣超股數") or (foreign + trust + dealer)

    return {
        "foreign_net": foreign,
        "trust_net":   trust,
        "dealer_net":  dealer,
        "total_net":   total,
        "signal":      _inst_signal(foreign, trust, total),
        "source":      "TWSE",
    }


# ────────────────────────────────────────────────────────────
# TPEx OpenAPI — 三大法人（上櫃）
# ────────────────────────────────────────────────────────────

# ────────────────────────────────────────────────────────────
# TPEx — 改用 FinMind API（上櫃股，免費無需 Token）
# ────────────────────────────────────────────────────────────

def _fetch_tpex_institutional(stock_id: str) -> dict | None:
    """
    FinMind API: TaiwanStockInstitutionalInvestorsBuySell
    上市 + 上櫃都支援，免費不需 Token
    """
    from datetime import date, timedelta
    today = date.today().strftime("%Y-%m-%d")
    # 取最近 3 天確保有資料
    start = (date.today() - timedelta(days=5)).strftime("%Y-%m-%d")
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset":    "TaiwanStockInstitutionalInvestorsBuySell",
        "data_id":    stock_id,
        "start_date": start,
        "end_date":   today,
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=12)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            return None
        # 取最新一天，彙總三大法人
        latest_date = max(r["date"] for r in data)
        rows = [r for r in data if r["date"] == latest_date]
        foreign = trust = dealer = 0
        for r in rows:
            name = r.get("name", "")
            net  = int(str(r.get("buy", 0)).replace(",", "") or 0) - \
                   int(str(r.get("sell", 0)).replace(",", "") or 0)
            if "外資" in name or "Foreign" in name:
                foreign += net
            elif "投信" in name or "Investment" in name:
                trust += net
            elif "自營" in name or "Dealer" in name:
                dealer += net
        total = foreign + trust + dealer
        return {
            "foreign_net": foreign,
            "trust_net":   trust,
            "dealer_net":  dealer,
            "total_net":   total,
            "signal":      _inst_signal(foreign, trust, total),
            "source":      "FinMind",
            "date":        latest_date,
        }
    except Exception as e:
        print(f"  [WARN] FinMind 三大法人失敗: {e}")
        return None


def _fetch_tpex_margin(stock_id: str) -> dict | None:
    """
    FinMind API: TaiwanStockMarginPurchaseShortSale
    上市 + 上櫃都支援，免費不需 Token
    """
    from datetime import date, timedelta
    today = date.today().strftime("%Y-%m-%d")
    start = (date.today() - timedelta(days=5)).strftime("%Y-%m-%d")
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset":    "TaiwanStockMarginPurchaseShortSale",
        "data_id":    stock_id,
        "start_date": start,
        "end_date":   today,
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=12)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            return None
        row = sorted(data, key=lambda x: x["date"])[-1]  # 最新一天
        margin_bal   = int(str(row.get("MarginPurchaseBalance",   0)).replace(",","") or 0)
        margin_chg   = int(str(row.get("MarginPurchaseTodayBalance", 0)).replace(",","") or 0) - \
                       int(str(row.get("MarginPurchaseYesterdayBalance", 0)).replace(",","") or 0)
        short_bal    = int(str(row.get("ShortSaleBalance",        0)).replace(",","") or 0)
        short_chg    = int(str(row.get("ShortSaleTodayBalance",   0)).replace(",","") or 0) - \
                       int(str(row.get("ShortSaleYesterdayBalance", 0)).replace(",","") or 0)
        margin_limit = int(str(row.get("MarginPurchaseLimit",     1)).replace(",","") or 1)
        margin_usage = round(margin_bal / margin_limit * 100, 1) if margin_limit > 0 else 0.0
        ratio        = round(short_bal  / margin_bal  * 100, 1) if margin_bal   > 0 else 0.0
        return {
            "margin_balance": margin_bal,
            "margin_change":  margin_chg,
            "margin_usage":   margin_usage,
            "short_balance":  short_bal,
            "short_change":   short_chg,
            "short_ratio":    ratio,
            "signal":         _margin_signal(margin_chg, short_chg, ratio),
        }
    except Exception as e:
        print(f"  [WARN] FinMind 融資融券失敗: {e}")
        return None


# ────────────────────────────────────────────────────────────
# TWSE OpenAPI — 融資融券（上市）
# ────────────────────────────────────────────────────────────

def _fetch_twse_margin(stock_id: str) -> dict | None:
    """優先 TWSE MI_MARGN，失敗時 fallback 到 FinMind"""
    url = "https://openapi.twse.com.tw/v1/marginShortSales/MI_MARGN"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12, verify=VERIFY_SSL)
        resp.raise_for_status()
        text = resp.text.strip()
        if text and text != "[]":
            data = resp.json()
            for row in data:
                code = str(row.get("股票代號", row.get("Code", "")))
                if code == stock_id:
                    return _parse_margin(row)
    except Exception as e:
        print(f"  [WARN] TWSE MI_MARGN 失敗: {e}")

    # 備援 FinMind
    return _fetch_tpex_margin(stock_id)


# ────────────────────────────────────────────────────────────
# TPEx OpenAPI — 融資融券（上櫃）
# ────────────────────────────────────────────────────────────

def _parse_margin(row: dict) -> dict:
    def n(*keys):
        for k in keys:
            v = row.get(k, "")
            try:
                return int(str(v).replace(",", "").strip() or "0")
            except:
                pass
        return 0

    # TWSE 實際欄位名（中文）
    margin_bal   = n("融資今日餘額", "MarginPurchaseBalance",  "MarginBalance")
    margin_chg_p = n("融資買進",     "MarginPurchaseBuy")
    margin_chg_s = n("融資賣出",     "MarginPurchaseSell")
    margin_chg   = margin_chg_p - margin_chg_s   # 今日淨增減
    margin_limit = n("融資限額",     "MarginPurchaseLimit",    "MarginQuota")
    short_bal    = n("融券今日餘額", "ShortSaleBalance",       "ShortBalance")
    short_chg_p  = n("融券賣出",     "ShortSaleSell")
    short_chg_s  = n("融券買進",     "ShortSaleBuy")
    short_chg    = short_chg_p - short_chg_s     # 今日淨增減

    margin_usage = round(margin_bal / margin_limit * 100, 1) if margin_limit > 0 else 0.0
    ratio        = round(short_bal  / margin_bal  * 100, 1) if margin_bal   > 0 else 0.0

    return {
        "margin_balance": margin_bal,
        "margin_change":  margin_chg,
        "margin_usage":   margin_usage,
        "short_balance":  short_bal,
        "short_change":   short_chg,
        "short_ratio":    ratio,
        "signal":         _margin_signal(margin_chg, short_chg, ratio),
    }


# ────────────────────────────────────────────────────────────
# 訊號判斷
# ────────────────────────────────────────────────────────────

def _inst_signal(foreign: int, trust: int, total: int) -> str:
    if total > 0 and foreign > 0 and trust > 0:
        return "三大齊買（強多）"
    if total > 0 and foreign > 0:
        return "外資主導買超"
    if total > 0 and trust > 0:
        return "投信主導買超"
    if total < 0 and foreign < 0 and trust < 0:
        return "三大齊賣（強空）"
    if total < 0 and foreign < 0:
        return "外資主導賣超"
    if total < 0 and trust < 0:
        return "投信主導賣超"
    if foreign > 0 and trust < 0:
        return "外資買、投信賣（分歧）"
    if foreign < 0 and trust > 0:
        return "外資賣、投信買（分歧）"
    return "偏中性"


def _margin_signal(margin_chg: int, short_chg: int, ratio: float) -> str:
    if margin_chg > 0 and short_chg < 0:
        return "融資增、融券減（偏多）"
    if margin_chg < 0 and short_chg > 0:
        return "融資減、融券增（偏空）"
    if ratio > 25:
        return f"券資比 {ratio}%（空壓大）"
    if ratio > 15:
        return f"券資比 {ratio}%（偏高注意）"
    if margin_chg > 0:
        return "融資持續增加（注意追價）"
    if short_chg > 0:
        return "融券持續增加（空方布局）"
    return "融資融券平穩"


# ────────────────────────────────────────────────────────────
# 整合：完整籌碼分析
# ────────────────────────────────────────────────────────────

def fetch_chips(stock_id: str, stock_name: str = "") -> dict:
    """
    取得個股完整籌碼資料（三大法人 + 融資融券）
    自動判斷上市/上櫃，選擇對應 API
    """
    print(f"  取得籌碼：{stock_id} {stock_name}")
    is_otc = _is_otc(stock_id)
    market = "上櫃(TPEx)" if is_otc else "上市(TWSE)"

    # 三大法人
    if is_otc:
        inst = _fetch_tpex_institutional(stock_id)
    else:
        inst = _fetch_twse_institutional(stock_id)

    time.sleep(0.5)

    # 融資融券
    if is_otc:
        margin = _fetch_tpex_margin(stock_id)
    else:
        margin = _fetch_twse_margin(stock_id)

    # 籌碼綜合評分
    chips_score = 0.0
    notes       = []

    if inst:
        if inst["foreign_net"] > 0:
            chips_score += 2.0
            notes.append(f"外資買超 {inst['foreign_net']:,} 股")
        elif inst["foreign_net"] < 0:
            chips_score -= 2.0
            notes.append(f"外資賣超 {abs(inst['foreign_net']):,} 股")

        if inst["trust_net"] > 0:
            chips_score += 1.0
            notes.append(f"投信買超 {inst['trust_net']:,} 股")
        elif inst["trust_net"] < 0:
            chips_score -= 1.0
            notes.append(f"投信賣超 {abs(inst['trust_net']):,} 股")

        if inst["dealer_net"] > 0:
            chips_score += 0.5
        elif inst["dealer_net"] < 0:
            chips_score -= 0.5

    if margin:
        if margin["margin_change"] > 0:
            chips_score -= 0.5     # 融資增加 = 散戶追高，輕微負向
            notes.append(f"融資增 {margin['margin_change']:,} 張")
        elif margin["margin_change"] < 0:
            chips_score += 0.3     # 融資減少 = 去槓桿，輕微正向
        if margin["short_change"] > 0:
            chips_score -= 1.0
            notes.append(f"融券增 {margin['short_change']:,} 張")
        if margin["short_ratio"] > 25:
            notes.append(f"⚠ 券資比 {margin['short_ratio']}%（偏高）")
        elif margin["short_ratio"] > 15:
            notes.append(f"券資比 {margin['short_ratio']}%（注意）")

    # 整體訊號
    if chips_score >= 2.5:
        overall = "籌碼強烈偏多"
    elif chips_score >= 1.0:
        overall = "籌碼偏多"
    elif chips_score <= -2.5:
        overall = "籌碼強烈偏空"
    elif chips_score <= -1.0:
        overall = "籌碼偏空"
    else:
        overall = "籌碼中性"

    return {
        "stock_id":      stock_id,
        "stock_name":    stock_name,
        "market":        market,
        "institutional": inst,
        "margin":        margin,
        "chips_score":   round(chips_score, 1),
        "overall":       overall,
        "notes":         notes,
        "updated_at":    datetime.now().isoformat(),
    }


# ────────────────────────────────────────────────────────────
# 直接執行測試
# ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("模組 3：三大法人 + 融資融券測試")
    print(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"注意：資料需在 16:00（三大法人）/ 20:00（融資融券）後才有")
    print("=" * 55)

    stocks = [
        ("2330", "台積電"),   # 上市
        ("2327", "國巨"),     # 上市
        ("6213", "聯茂電子"), # 上櫃
    ]

    for sid, sname in stocks:
        print(f"\n{'─'*45}")
        r = fetch_chips(sid, sname)
        print(f"  市場：{r['market']}")

        inst = r["institutional"]
        if inst:
            print(f"  外資：{inst['foreign_net']:+,} 股")
            print(f"  投信：{inst['trust_net']:+,} 股")
            print(f"  自營：{inst['dealer_net']:+,} 股")
            print(f"  訊號：{inst['signal']}")
        else:
            print("  三大法人：尚無資料（可能未到 16:00 或 API 暫停）")

        mgn = r["margin"]
        if mgn:
            print(f"  融資：{mgn['margin_balance']:,} 張（{mgn['margin_change']:+,}）  使用率 {mgn['margin_usage']}%")
            print(f"  融券：{mgn['short_balance']:,} 張（{mgn['short_change']:+,}）  券資比 {mgn['short_ratio']}%")
            print(f"  訊號：{mgn['signal']}")
        else:
            print("  融資融券：尚無資料（可能未到 20:00 或 API 暫停）")

        print(f"  籌碼評分：{r['chips_score']:+.1f}  →  {r['overall']}")
        for n in r["notes"]:
            print(f"    • {n}")