import streamlit as st
import pandas as pd
from datetime import datetime

# 導入你的個股邏輯
from stocks import tsmc, yageo, iteq

st.set_page_config(page_title="AI 盤前分析系統", layout="wide", initial_sidebar_state="expanded")

# 介面美化
st.title("📈 台灣半導體/電子盤前分析")
st.caption(f"數據更新時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}")

# 側邊欄設定
st.sidebar.header("分析設定")
selected_targets = st.sidebar.multiselect(
    "選擇追蹤個股",
    options=["tsmc", "yageo", "iteq"],
    default=["tsmc", "yageo", "iteq"],
    format_func=lambda x: {"tsmc":"台積電 (2330)", "yageo":"國巨 (2327)", "iteq":"聯茂 (6213)"}[x]
)

if st.sidebar.button("執行全自動 AI 分析"):
    modules = {"tsmc": tsmc, "yageo": yageo, "iteq": iteq}
    
    # 建立多欄位顯示結果
    cols = st.columns(len(selected_targets))
    
    for idx, target in enumerate(selected_targets):
        with cols[idx]:
            with st.spinner(f"正在計算 {target}..."):
                try:
                    # 執行各模組的分析核心
                    res = modules[target].analyze()
                    pred = res['prediction']
                    
                    # 顯示核心指標 (Metric)
                    color_delta = "normal" if pred['predicted_change_pct'] == 0 else "inverse"
                    st.metric(
                        label=res['stock']['name'],
                        value=f"NT$ {pred['predicted_price_twd']:.1f}",
                        delta=f"{pred['predicted_change_pct']:+.2f}%",
                        delta_color=color_delta
                    )
                    
                    # 顯示信心標籤
                    st.info(f"💡 信心度：{pred['confidence']}")
                    
                    # 顯示關鍵訊號
                    with st.expander("查看分析細節"):
                        st.write("**關鍵訊號：**")
                        for sig in pred.get('key_signals', []):
                            st.write(f"- {sig}")
                        
                        st.write("**市場情緒：**")
                        st.write(res['sentiment']['stock_news']['label'])
                        
                except Exception as e:
                    st.error(f"{target} 分析失敗")
                    st.caption(str(e))

    st.success("✅ 所有分析任務已完成")
else:
    st.info("請點擊左側「執行全自動 AI 分析」開始運算。")

# 顯示 JSON 備份 (模擬你上傳的 summary 檔案內容)
with st.sidebar.expander("開發者調試數據"):
    st.write("此區塊可檢視原始分析結果 JSON")