import streamlit as st
import graphviz
from backend import FossilExpert, API_URL  # 從 backend 匯入邏輯

# =========================================================
# 🔑 API KEY 設定區 (已寫死)
# =========================================================
MY_API_KEY = "3dfdd1df4ee04ed8bfc6ba4a68e3577ce2ce2f29690620ae800886061755cafc"
# =========================================================

# --- 1. 頁面設定 ---
st.set_page_config(page_title="FossilMind 古生物鑑定師", page_icon="🦖", layout="wide")

st.markdown("""
<style>
    .stButton>button { width: 100%; border-radius: 20px; }
</style>
""", unsafe_allow_html=True)

# --- 2. 側邊欄：設定區 ---
with st.sidebar:
    st.title("⚙️ 設定")
    
    # 保留模型選擇功能
    model_name = st.selectbox("選擇模型 (Model)", ["gpt-oss:20b", "gpt-oss:120b", "gemma3:4b"], index=0)
    
    st.divider()
    st.info("💡 提示：若感覺回答怪怪的，可以切換成 120b (較聰明但較慢) 試試看。")

# --- 3. 主畫面 ---
st.title("🦖 FossilMind 古生物鑑定師")
st.markdown("---")

# 建立兩欄佈局
col_input, col_result = st.columns([1, 1.5])

with col_input:
    st.subheader("1. 輸入化石特徵描述")
    user_desc = st.text_area("請盡可能詳盡地描述化石...", height=150, 
                            placeholder="例如：一個螺旋狀的貝殼，殼很厚，是在白堊紀地層發現的。")
    
    analyze_btn = st.button("🔍 開始鑑定與分析", type="primary")

# --- 4. 邏輯串接 ---
if "result_text" not in st.session_state:
    st.session_state.result_text = None
if "graph_code" not in st.session_state:
    st.session_state.graph_code = None

if analyze_btn:
    if not user_desc:
        st.warning("請先輸入化石的特徵描述喔！")
    else:
        # 使用寫死的 Key 和使用者選的模型
        expert = FossilExpert(MY_API_KEY, API_URL, model_name)
        
        with col_result:
            # Step 1: 鑑定
            with st.spinner("⏳ Step 1/2: 正在諮詢古生物學家 (LLM 鑑定)..."):
                st.session_state.result_text = expert.identify_fossil(user_desc)
            
            # 檢查是否有 API 錯誤
            if st.session_state.result_text.startswith(("Error:", "Connection Error:")):
                st.error(f"API 呼叫失敗：{st.session_state.result_text}")
                st.session_state.result_text = None 
            else:
                # Step 2: 畫圖
                with st.spinner("⏳ Step 2/2: 正在繪製演化分支圖..."):
                    st.session_state.graph_code = expert.generate_evolution_graph(st.session_state.result_text)

# --- 5. 顯示結果 ---
with col_result:
    if st.session_state.result_text:
        st.subheader("2. 鑑定報告與演化分析")
        
        with st.expander("📄 化石鑑定報告", expanded=True):
            st.markdown(st.session_state.result_text)
            
        if st.session_state.graph_code and not st.session_state.graph_code.startswith("Error"):
            st.markdown("---")
            st.markdown("#### 🌳 演化分類分支圖")
            try:
                st.graphviz_chart(st.session_state.graph_code, use_container_width=True) 
            except Exception as e:
                st.warning("圖表代碼生成有誤，無法渲染。")
                with st.expander("查看原始代碼"):
                    st.code(st.session_state.graph_code)