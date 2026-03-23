"""
scheduler.py
盤前分析排程器
週一至週五 07:30 + 07:50 各執行一次並推播 LINE
08:00 自動結束程式（讓工作排程器在 08:05 執行關機）
"""

import schedule
import time
import logging
import sys
from datetime import datetime
from main import run_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler("premarket.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)


def is_weekday() -> bool:
    return datetime.now().weekday() < 5


def job(label: str):
    if not is_weekday():
        logging.info(f"[{label}] 今日為假日，跳過")
        return
    logging.info(f"[{label}] 盤前分析啟動")
    try:
        run_all(send_line=True)
        logging.info(f"[{label}] 完成，LINE 已推播")
    except Exception as e:
        logging.error(f"[{label}] 失敗: {e}", exc_info=True)


def auto_exit():
    """08:00 自動結束，讓排程器在 08:05 執行關機"""
    logging.info("08:00 任務結束，程式自動退出")
    sys.exit(0)


if __name__ == "__main__":
    logging.info("排程器啟動  週一至週五 07:30 / 07:50 / 08:00退出")

    schedule.every().day.at("07:30").do(job,       label="07:30")
    schedule.every().day.at("07:50").do(job,       label="07:50")
    schedule.every().day.at("08:00").do(auto_exit)

    # 開發測試：立即執行一次，取消下方注解
    # job("手動測試")

    while True:
        schedule.run_pending()
        time.sleep(30)