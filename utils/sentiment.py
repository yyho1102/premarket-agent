"""
utils/sentiment.py
模組 2：市場情緒分析

資料來源：
  1. Yahoo Finance RSS — 個股新聞（穩定，無需登入）
  2. Google News RSS   — 中文台股新聞關鍵字搜尋
  3. Claude API        — 新聞情緒分類 + 摘要

流程：
  抓 RSS 新聞 → Claude 分析情緒 → 輸出分數 + 摘要
"""

import requests
import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()  # 載入 .env 的 ANTHROPIC_API_KEY
from anthropic import Anthropic
from anthropic.types import TextBlock

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

client = Anthropic()


# ────────────────────────────────────────────────────────────
# ────────────────────────────────────────────────────────────
# 新聞抓取：yfinance（主要）+ Google News RSS（備用）
# ────────────────────────────────────────────────────────────

def fetch_yfinance_news(stock_id: str, limit: int = 15) -> list[dict]:
    """
    用 yfinance 抓個股新聞（新版 SDK 格式：item["content"]["title"]）
    """
    import yfinance as yf
    symbol = f"{stock_id}.TW"
    try:
        ticker = yf.Ticker(symbol)
        raw    = ticker.news or []
        cutoff = datetime.now() - timedelta(hours=48)
        news   = []

        for item in raw[:limit * 2]:
            # 新版 yfinance SDK 結構：item["content"]["title"]
            content = item.get("content") or item  # 相容新舊格式
            title   = (content.get("title") or item.get("title") or "").strip()
            if not title:
                continue

            pub_str = content.get("pubDate") or content.get("displayTime") or ""
            try:
                pub_dt = datetime.strptime(pub_str[:19], "%Y-%m-%dT%H:%M:%S")
            except Exception:
                pub_dt = datetime.now()

            if pub_dt < cutoff:
                continue

            url = ""
            click = content.get("clickThroughUrl") or content.get("canonicalUrl")
            if isinstance(click, dict):
                url = click.get("url", "")

            news.append({
                "title":    title,
                "summary":  content.get("summary", "")[:100],
                "pub_time": pub_dt.strftime("%m/%d %H:%M"),
                "url":      url,
            })
            if len(news) >= limit:
                break

        return news
    except Exception as e:
        print(f"  [WARN] yfinance news {stock_id}: {e}")
        return []


def fetch_google_news_rss(query: str, limit: int = 10) -> list[dict]:
    """Google News RSS 搜尋中文台股新聞"""
    try:
        resp = requests.get(
            "https://news.google.com/rss/search",
            params={"q": f"{query} 股票", "hl": "zh-TW", "gl": "TW", "ceid": "TW:zh-Hant"},
            headers=HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        return _parse_rss(resp.content, limit)
    except Exception as e:
        print(f"  [WARN] Google News RSS {query}: {e}")
        return []


def _parse_rss(content: bytes, limit: int) -> list[dict]:
    """解析 RSS XML，回傳最近 48hr 的新聞"""
    news   = []
    cutoff = datetime.now() - timedelta(hours=48)
    try:
        # Google News RSS 有 namespace，用 str 解析較安全
        text = content.decode("utf-8", errors="ignore")
        root = ET.fromstring(text)
        # 嘗試各種路徑
        items = root.findall(".//item")

        for item in items:
            title   = (item.findtext("title") or "").strip()
            pub_str = item.findtext("pubDate") or ""
            link    = item.findtext("link")    or ""
            desc    = (item.findtext("description") or "").strip()

            if not title:
                continue

            pub_dt = _parse_date(pub_str)
            if pub_dt and pub_dt < cutoff:
                continue

            news.append({
                "title":    title,
                "summary":  desc[:100],
                "pub_time": pub_dt.strftime("%m/%d %H:%M") if pub_dt else "未知",
                "url":      link,
            })
            if len(news) >= limit:
                break

    except ET.ParseError as e:
        print(f"  [WARN] RSS 解析失敗: {e}")
    return news


def _parse_date(date_str: str) -> datetime | None:
    """解析多種 RSS 日期格式"""
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.replace(tzinfo=None)
        except ValueError:
            continue
    return None


# ────────────────────────────────────────────────────────────
# Claude 情緒分析
# ────────────────────────────────────────────────────────────

def analyze_sentiment(
    news_list: list[dict],
    context:   str = "台股市場",
    max_news:  int = 20,
) -> dict:
    """
    使用 Claude API 分析新聞情緒，API 不可用時自動切換規則式分析
    回傳：{"score", "label", "summary", "key_news", "risks", "news_count"}
    """
    if not news_list:
        return _empty_sentiment()

    news_slice = news_list[:max_news]

    # 先嘗試 Claude API
    result = _analyze_with_claude(news_slice, context)
    if result:
        return result

    # Claude 不可用 → 規則式備援
    print(f"  [INFO] 切換規則式情緒分析")
    return _analyze_with_rules(news_slice)


def _analyze_with_claude(news_slice: list[dict], context: str) -> dict | None:
    """Claude API 分析，失敗回傳 None"""
    titles = "\n".join(
        f"[{i+1}] ({n['pub_time']}) {n['title']}"
        for i, n in enumerate(news_slice)
    )
    prompt = f"""你是一位專業的台股盤前分析師。
以下是 {context} 的最新新聞標題（最近48小時）：

{titles}

請分析整體市場情緒，以 JSON 格式回覆：
{{
  "score": <-1.0到1.0的浮點數，-1極空、0中性、+1極多>,
  "label": <"強烈偏多"|"偏多"|"中性偏多"|"中性"|"中性偏空"|"偏空"|"強烈偏空">,
  "summary": "<2-3句話概括今日市場情緒>",
  "key_news": ["<最重要新聞1>", "<最重要新聞2>", "<最重要新聞3>"],
  "risks": ["<風險訊號1>", "<風險訊號2>"]
}}
只回傳 JSON，不要其他文字。"""

    try:
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        text = next(
            (block.text for block in resp.content if isinstance(block, TextBlock)), ""
        ).strip()
        text   = text.replace("```json", "").replace("```", "").strip()
        result = json.loads(text)
        result["news_count"] = len(news_slice)
        result["method"] = "claude"
        return result
    except Exception:
        return None


# 正向關鍵字
_BULL_WORDS = [
    "漲停", "大漲", "創高", "突破", "上攻", "買超", "法人買", "外資買",
    "獲利", "營收創高", "展望正向", "訂單暢旺", "優於預期", "上調目標",
    "AI需求", "伺服器", "漲價", "供不應求", "回升", "反彈", "強勢",
    "surge", "rally", "beat", "upgrade", "bullish", "growth",
]
# 負向關鍵字
_BEAR_WORDS = [
    "跌停", "大跌", "破底", "下殺", "賣超", "外資賣", "法人賣",
    "虧損", "營收衰退", "展望保守", "下調目標", "不如預期", "裁員",
    "供過於求", "庫存", "降價", "貿易戰", "關稅", "制裁", "下修",
    "drop", "fall", "miss", "downgrade", "bearish", "loss", "war",
]


def _analyze_with_rules(news_slice: list[dict]) -> dict:
    """規則式情緒分析（不需要 API）"""
    bull_count = 0
    bear_count = 0
    key_news   = []

    for n in news_slice:
        title = n["title"].lower()
        b = sum(1 for w in _BULL_WORDS if w.lower() in title)
        e = sum(1 for w in _BEAR_WORDS if w.lower() in title)
        bull_count += b
        bear_count += e
        if b > 0 or e > 0:
            key_news.append(n["title"])

    total = bull_count + bear_count
    if total == 0:
        score = 0.0
    else:
        score = round((bull_count - bear_count) / (total + len(news_slice) * 0.3), 3)
        score = max(-1.0, min(1.0, score))

    risks = []
    if bear_count > bull_count * 2:
        risks.append("負面新聞比例偏高")

    return {
        "score":      score,
        "label":      _score_to_label(score),
        "summary":    f"規則式分析：{len(news_slice)} 篇新聞，正向 {bull_count} 則，負向 {bear_count} 則",
        "key_news":   key_news[:3],
        "risks":      risks,
        "news_count": len(news_slice),
        "method":     "rules",
    }


def _empty_sentiment() -> dict:
    return {
        "score": 0.0, "label": "中性（無資料）",
        "summary": "無法取得新聞資料",
        "key_news": [], "risks": [], "news_count": 0,
    }


# ────────────────────────────────────────────────────────────
# 整合：個股 + 大盤情緒
# ────────────────────────────────────────────────────────────

def analyze_stock_sentiment(stock_id: str, stock_name: str) -> dict:
    """個股情緒：yfinance news（主要）+ Google News RSS（補充）"""
    print(f"  抓取新聞：{stock_id} {stock_name}")

    # yfinance 新聞（主要，走官方 SDK）
    yf_news = fetch_yfinance_news(stock_id, limit=12)
    time.sleep(0.3)

    # Google News 中文補充
    google_news = fetch_google_news_rss(stock_name, limit=8)

    # 合併去重（標題前20字）
    seen, all_news = set(), []
    for n in yf_news + google_news:
        key = n["title"][:20]
        if key not in seen:
            seen.add(key)
            all_news.append(n)

    print(f"  yfinance {len(yf_news)} 篇 / Google {len(google_news)} 篇 / 合併 {len(all_news)} 篇")

    stock_sent = analyze_sentiment(all_news, context=f"{stock_name}({stock_id})", max_news=15) \
                 if all_news else _empty_sentiment()

    time.sleep(0.3)
    market_news = fetch_google_news_rss("台股 大盤", limit=8)
    market_sent = analyze_sentiment(market_news, context="台股大盤", max_news=8) \
                  if market_news else _empty_sentiment()

    combined_score = round(stock_sent["score"] * 0.7 + market_sent["score"] * 0.3, 3)

    return {
        "stock_id":       stock_id,
        "stock_name":     stock_name,
        "stock_news":     stock_sent,
        "market_news":    market_sent,
        "combined_score": combined_score,
        "combined_label": _score_to_label(combined_score),
    }


def analyze_market_sentiment() -> dict:
    """大盤整體情緒"""
    print("  抓取大盤新聞...")
    news   = fetch_google_news_rss("台股 大盤 外資", limit=20)
    result = analyze_sentiment(news, context="台股大盤", max_news=20)
    result["fetched_at"] = datetime.now().isoformat()
    return result


def _score_to_label(score: float) -> str:
    if score >= 0.6:  return "強烈偏多"
    if score >= 0.3:  return "偏多"
    if score >= 0.1:  return "中性偏多"
    if score > -0.1:  return "中性"
    if score > -0.3:  return "中性偏空"
    if score > -0.6:  return "偏空"
    return "強烈偏空"


def sentiment_adjustment(sentiment_score: float) -> float:
    """情緒分數 → 預測幅度調整值（%）"""
    return round(sentiment_score * 0.5, 3)


# ────────────────────────────────────────────────────────────
# 直接執行測試
# ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("模組 2：市場情緒分析測試")
    print(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 55)

    stocks  = [("2330", "台積電"), ("2327", "國巨"), ("6213", "聯茂電子")]
    results = {}

    for sid, sname in stocks:
        print(f"\n{'─'*40}")
        r = analyze_stock_sentiment(sid, sname)
        results[sid] = r
        print(f"  個股: {r['stock_news']['score']:+.3f}  {r['stock_news']['label']}")
        print(f"  大盤: {r['market_news']['score']:+.3f}  {r['market_news']['label']}")
        print(f"  綜合: {r['combined_score']:+.3f}  {r['combined_label']}")
        print(f"  摘要: {r['stock_news'].get('summary', '無')}")
        for n in r["stock_news"].get("key_news", [])[:2]:
            print(f"    • {n}")
        time.sleep(1)

    with open("sentiment_test.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\n輸出：sentiment_test.json")