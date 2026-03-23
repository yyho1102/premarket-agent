import streamlit as st
import pandas as pd
from datetime import datetime
import os

# 匯入你的個股模組
from stocks import tsmc, yageo, iteq
from utils.line_notify import push_report

# 網頁設定
st.set_page_config(page_title="台股盤前 AI 分析", layout="wide")

st.title("📈 盤前分析 Agent 儀表板")
st.sidebar.header("控制面板")

# 選擇要分析的股票
options = {
    "台積電 (2330)": tsmc,
    "國巨 (2327)": yageo,
    "聯茂 (6213)": iteq
}
selected_stocks = st.sidebar.multiselect("選擇分析對象", list(options.keys()), default=list(options.keys()))
send_line = st.sidebar.checkbox("完成後發送 LINE 通知", value=False)

if st.sidebar.button("開始執行 AI 分析"):
    results = {}
    
    for name in selected_stocks:
        with st.status(f"正在分析 {name}...", expanded=True) as status:
            try:
                # 執行各模組的 analyze() 函式
                module = options[name]
                res = module.analyze()
                results[name] = res
                
                # 顯示預測結果
                pred = res['prediction']
                color = "green" if pred['predicted_change_pct'] > 0 else "red"
                st.write(f"預測漲跌: :{color}[{pred['predicted_change_pct']:+.2f}%]")
                st.write(f"信心等級: {pred['confidence']}")
                status.update(label=f"{name} 分析完成！", state="complete")
            except Exception as e:
                st.error(f"{name} 分析出錯: {e}")
                status.update(label=f"{name} 失敗", state="error")

    # 顯示總覽卡片
    if results:
        st.divider()
        st.subheader("📊 分析總覽")
        cols = st.columns(len(results))
        for i, (name, data) in enumerate(results.items()):
            with cols[i]:
                p = data['prediction']
                st.metric(name, f"{p['predicted_price_twd']:.1f}", f"{p['predicted_change_pct']:+.2f}%")
                st.caption(f"信心度: {p['confidence']}")

        # LINE 推播邏輯
        if send_line:
            # 轉換格式以符合你的 push_report
            summary = {"timestamp": datetime.now().isoformat(), "stocks": results}
            if push_report(summary):
                st.toast("LINE 推播成功！")
            else:
                st.toast("LINE 推播失敗，請檢查 Token。")

    # 顯示詳細 JSON 內容 (選配)
    with st.expander("查看原始數據"):
        st.json(results)