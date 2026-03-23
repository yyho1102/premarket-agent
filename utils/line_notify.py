"""
utils/line_notify.py
LINE Bot 推播模組
使用 LINE Messaging API push_message 推送盤前分析報告

設定步驟：
  1. 前往 https://developers.line.biz/console/
  2. 建立 Provider → 建立 Messaging API Channel
  3. Messaging API tab → 發行 Channel Access Token（長效型）
  4. 用 LINE 掃描 Bot QR Code 加為好友
  5. 取得你的 User ID（Basic settings tab 或用 /getid 指令）
  6. 將 Token 和 User ID 填入 .env
"""

import requests
import json
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_USER_ID              = os.getenv("LINE_USER_ID", "")
LINE_API_URL              = "https://api.line.me/v2/bot/message/push"


# ────────────────────────────────────────────────────────────
# 訊息格式化
# ────────────────────────────────────────────────────────────

def _format_stock_message(stock_key: str, data: dict) -> str:
    """將單一個股資料格式化成 LINE 文字訊息"""
    stock  = data.get("stock", {})
    pred   = data.get("prediction", {})
    chips  = data.get("chips", {})
    sent   = data.get("sentiment", {})
    analyst = data.get("analyst", {})

    name    = stock.get("name", stock_key)
    chg     = pred.get("predicted_change_pct", 0)
    price   = pred.get("predicted_price_twd", "─")
    conf    = pred.get("confidence_pct", 0)
    arrow   = "▲" if chg > 0 else "▼"

    lines = [
        f"{'─'*20}",
        f"📊 {name}  {arrow} {chg:+.2f}%  → TWD {price}",
        f"信心度：{conf}%",
    ]

    # 籌碼
    if chips and chips.get("overall"):
        chips_score = chips.get("chips_score", 0)
        lines.append(f"籌碼：{chips['overall']} ({chips_score:+.1f})")
        for note in chips.get("notes", [])[:2]:
            lines.append(f"  • {note}")

    # 情緒
    if sent and sent.get("combined_label"):
        lines.append(f"情緒：{sent['combined_label']} ({sent.get('combined_score', 0):+.2f})")

    # 分析師
    if analyst and analyst.get("target_mean"):
        upside = analyst.get("upside_pct", 0)
        lines.append(f"分析師：{analyst.get('recommendation', '─')}  目標 {analyst['target_mean']:.0f}  ({upside:+.1f}%)")

    # 風險
    risk_flags = pred.get("risk_flags", [])
    if risk_flags:
        lines.append(f"⚠ {risk_flags[0][:30]}")

    return "\n".join(lines)


def format_full_report(summary: dict) -> list[str]:
    """
    將完整 summary JSON 格式化成多則 LINE 訊息
    LINE 單則訊息上限 5000 字，分多則發送
    回傳：訊息字串列表
    """
    now    = datetime.now().strftime("%m/%d %H:%M")
    stocks = summary.get("stocks", {})

    # 第一則：總覽
    overview_lines = [
        f"🔔 盤前分析報告  {now}",
        f"{'═'*22}",
    ]

    order = ["tsmc", "yageo", "iteq"]
    name_map = {"tsmc": "台積電 2330", "yageo": "國巨 2327", "iteq": "聯茂 6213"}

    for key in order:
        if key not in stocks:
            continue
        pred = stocks[key].get("prediction", {})
        chg  = pred.get("predicted_change_pct", 0)
        price = pred.get("predicted_price_twd", "─")
        conf  = pred.get("confidence_pct", 0)
        arrow = "▲" if chg > 0 else "▼"
        overview_lines.append(
            f"{arrow} {name_map.get(key, key):10s}  {chg:+.2f}%  TWD {price}  ({conf}%)"
        )

    messages = ["\n".join(overview_lines)]

    # 第二則以後：每檔詳細
    for key in order:
        if key in stocks:
            messages.append(_format_stock_message(key, stocks[key]))

    return messages


# ────────────────────────────────────────────────────────────
# 推播函式
# ────────────────────────────────────────────────────────────

def push_message(text: str, user_id: str = "") -> bool:
    """推送單則文字訊息"""
    uid = user_id or LINE_USER_ID
    if not LINE_CHANNEL_ACCESS_TOKEN or not uid:
        print("  [WARN] LINE_CHANNEL_ACCESS_TOKEN 或 LINE_USER_ID 未設定")
        return False

    headers = {
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    body = {
        "to": uid,
        "messages": [{"type": "text", "text": text}],
    }
    try:
        resp = requests.post(LINE_API_URL, headers=headers,
                             data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                             timeout=10)
        if resp.status_code == 200:
            return True
        print(f"  [WARN] LINE API 錯誤 {resp.status_code}: {resp.text[:100]}")
        return False
    except Exception as e:
        print(f"  [WARN] LINE 推播失敗: {e}")
        return False


def push_report(summary: dict, user_id: str = "") -> bool:
    """
    推送完整盤前報告
    自動分成多則訊息發送（總覽 + 每檔詳細）
    """
    messages = format_full_report(summary)
    print(f"\n推播 LINE 報告（共 {len(messages)} 則）...")

    success = True
    for i, msg in enumerate(messages):
        ok = push_message(msg, user_id)
        status = "✓" if ok else "✗"
        print(f"  [{status}] 第 {i+1} 則")
        if not ok:
            success = False

    return success


# ────────────────────────────────────────────────────────────
# 直接執行測試
# ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("LINE Bot 推播測試")
    print(f"Token 設定：{'✓' if LINE_CHANNEL_ACCESS_TOKEN else '✗ 未設定'}")
    print(f"User ID：  {'✓' if LINE_USER_ID else '✗ 未設定'}")

    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_USER_ID:
        print("\n請在 .env 設定：")
        print("  LINE_CHANNEL_ACCESS_TOKEN=你的Token")
        print("  LINE_USER_ID=你的UserID")
    else:
        ok = push_message("✅ 盤前分析 Bot 測試訊息，設定成功！")
        print(f"\n測試結果：{'成功' if ok else '失敗'}")
