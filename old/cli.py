import requests
import json
import os

# ==========================================
# 1. 設定區 (請修改這裡)
# ==========================================
API_KEY = "3dfdd1df4ee04ed8bfc6ba4a68e3577ce2ce2f29690620ae800886061755cafc" 
API_URL = "https://api-gateway.netdb.csie.ncku.edu.tw/api/chat"

MODEL_NAME = "gpt-oss:20b" 

# ==========================================
# 2. 工具函式 (Tools)
# ==========================================

def call_llm(prompt):
    """傳送文字給 LLM 並取得回覆"""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    # 準備訊息 payload
    data = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "stream": False
    }

    try:
        # 發送 POST 請求
        print("   (等待 API 回應中...)")
        response = requests.post(API_URL, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            # 成功！解析 JSON
            return response.json().get("message", {}).get("content", "")
        else:
            print(f"❌ API 錯誤 ({response.status_code}): {response.text}")
            return None
    except Exception as e:
        print(f"❌ 連線錯誤: {e}")
        return None

# ==========================================
# 3. 核心邏輯 (Workflow)
# ==========================================

def step_1_identify_from_text(user_description):
    """第一階段：根據使用者的文字描述進行鑑定"""
    print("\n🦖 --- Step 1: 正在根據你的描述進行鑑定... ---")
    
    prompt = f"""
    你是一位專業的古生物學家。使用者描述了一個化石特徵：
    「{user_description}」

    請根據這個描述：
    1. 推測這可能是什麼生物 (給出學名與中文俗名)。
    2. 簡單介紹它的生存年代與特徵。
    
    請用繁體中文回答，語氣專業但親切。
    """
    
    result = call_llm(prompt)
    return result

def step_2_visualize_from_text(identification_result):
    """第二階段：根據鑑定結果生成「美觀版」演化分支圖"""
    print("\n🌳 --- Step 2: 正在生成演化分支圖 (套用教科書風格)... ---")
    
    # 這裡的 Prompt 是關鍵：我們要求它畫出「旁系群 (Sister Groups)」並設定美學
    prompt = f"""
    基於以下古生物資訊：
    {identification_result}

    請幫我畫出一個「演化分支圖 (Phylogenetic Tree)」，使用 Graphviz DOT 語言。
    
    **美學設計要求 (請嚴格遵守)：**
    1. **版面：** 使用 `rankdir=LR` (由左至右)。
    2. **線條：** 設定 `splines=ortho` (折線風格)，讓圖表看起來像科學圖鑑。
    3. **節點 (Nodes)：** - 使用 `shape=box`，但是設定 `style="filled,rounded"` (圓角矩形)。
       - 填滿顏色使用淡米色 (`#F5F5DC`) 或淡綠色 (`#E0F2F1`)。
       - 字體使用 `fontname="Arial"` 或 `Sans-Serif`。
    4. **目標強調：** 最終的化石節點 (你的鑑定結果)，請用 **金黃色 (`#FFD700`)** 或 **深綠色** 強調顯示。
    5. **結構：** 必須包含 1~2 個旁系群 (Sister Groups) 以展現分支感。
    6. **只輸出程式碼：** 不要任何解釋，前後不要有 ```dot 符號。
    """
    
    dot_code = call_llm(prompt)
    return dot_code

# ==========================================
# 4. 主程式 (CLI 入口)
# ==========================================

if __name__ == "__main__":
    print("=== FossilMind CLI (Text Mode) v1.0 ===")
    print("請輸入化石的特徵描述，我來幫你鑑定！")
    print("範例：一個螺旋狀的貝殼，殼很厚，是在白堊紀地層發現的。")
    print("---------------------------------------------------")
    
    while True:
        user_input = input("\n請輸入描述 (或輸入 q 離開): ").strip()
        
        if user_input.lower() == 'q':
            print("👋 掰掰！")
            break
            
        if not user_input:
            continue

        # --- 執行 Workflow ---
        
        # 1. 鑑定
        identity_info = step_1_identify_from_text(user_input)
        
        if identity_info:
            print("\n✅ 鑑定報告：")
            print("=========================================")
            print(identity_info)
            print("=========================================")
            
            # 2. 畫圖 (詢問使用者是否要產生圖表代碼)
            ask_graph = input("\n❓ 是否要生成演化圖代碼？(y/n): ").lower()
            if ask_graph == 'y':
                graph_code = step_2_visualize_from_text(identity_info)
                
                if graph_code:
                    # 清洗代碼 (去掉 markdown 符號)
                    clean_code = graph_code.replace("```dot", "").replace("```", "").strip()
                    
                    print("\n✅ Graphviz 代碼如下：")
                    print("-----------------------------")
                    print(clean_code)
                    print("-----------------------------")
                    print("💡 提示：你可以把這段代碼貼到 https://dreampuf.github.io/GraphvizOnline 查看結果。")