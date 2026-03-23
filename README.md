# 盤前分析 Agent

美股/日股 → 台股走勢預測（台積電、國巨、聯茂）

---

## 專案結構

```
premarket_agent/
├── .vscode/
│   ├── settings.json     # Python 直譯器、格式化設定
│   └── launch.json       # F5 一鍵執行各個股
├── stocks/
│   ├── tsmc.py           # 台積電 2330（ADR反推 + NVDA/AAPL）
│   ├── yageo.py          # 國巨   2327（村田/TDK/太陽誘電）
│   └── iteq.py           # 聯茂   6213（Resonac/Panasonic）
├── utils/
│   └── fetcher.py        # 共用：get_change / weighted_signal / compute_correlation
├── reports/              # 自動產生的 JSON 報告（git ignore）
├── main.py               # 一鍵執行全部 / 指定個股
├── scheduler.py          # 每日 07:00 自動執行
└── requirements.txt
```

---

## 快速開始

### 1. 建立虛擬環境

```bash
# 在專案根目錄執行
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

### 2. 安裝套件

```bash
pip install -r requirements.txt
```

### 3. 在 VS Code 選擇直譯器

`Ctrl+Shift+P` → `Python: Select Interpreter` → 選 `.venv`

---

## 執行方式

### 方法一：F5 直接執行（推薦）

開啟任一 `.py` 後按 `F5`，從左側下拉選擇要執行的設定：
- `▶ 台積電 TSMC`
- `▶ 國巨 YAGEO`
- `▶ 聯茂 ITEQ`
- `▶ 全部分析 (main)`

### 方法二：終端機

```bash
# 全部個股
python main.py

# 只跑台積電 + 國巨
python main.py --stocks tsmc yageo

# 單一個股
python stocks/tsmc.py
python stocks/yageo.py
python stocks/iteq.py
```

### 方法三：排程器（每日 07:00）

```bash
python scheduler.py
```

---

## 各股分析邏輯

| 個股 | 核心指標 | 其他參考 |
|------|----------|----------|
| 台積電 2330 | ADR (TSM) 折溢價 50% | NVDA 55% + AAPL 45% 客戶訊號 35% |
| 國巨   2327 | 村田製作所 (6981.T) 40% | TDK/太陽誘電/Alps 輔助 |
| 聯茂   6213 | Resonac (4004.T) 40% | Panasonic CCL / AI伺服器需求端 |

### 台積電 ADR 換算公式

```
TSM (USD) ÷ 5 × USD/TWD = 台股理論價 (TWD)
折溢價% = (理論價 - 台股昨收) / 台股昨收 × 100%
```

---

## 新增個股

1. 在 `stocks/` 新增 `xxx.py`，參考 `tsmc.py` 結構
2. 在 `main.py` 的 `STOCK_MODULES` 加入對應條目
3. 在 `.vscode/launch.json` 新增 debug 設定

---

## 報告輸出

每次執行後自動輸出至 `reports/` 目錄：
- `tsmc_YYYYMMDD_HHMM.json`
- `yageo_YYYYMMDD_HHMM.json`
- `iteq_YYYYMMDD_HHMM.json`
- `summary_YYYYMMDD_HHMM.json`（main.py 執行時產生）
