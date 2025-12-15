import requests
import json

# =============================================================
# 🚨 1. 設定區 (請在這裡填入你的 API 資訊)
# =============================================================
# ⚠️ 注意：你的 API KEY 不應該直接寫在程式碼裡，之後我們用 Streamlit 的密碼輸入框處理。
# 這裡先寫死方便測試，但正式提交前建議刪除或用環境變數取代。
DEFAULT_API_KEY = "3dfdd1df4ee04ed8bfc6ba4a68e3577ce2ce2f29690620ae800886061755cafc" 
API_URL = "https://api-gateway.netdb.csie.ncku.edu.tw/api/chat"
DEFAULT_MODEL = "gpt-oss:20b"
# =============================================================

class FossilExpert:
    def __init__(self, api_key=DEFAULT_API_KEY, api_url=API_URL, model_name=DEFAULT_MODEL):
        self.api_key = api_key
        self.api_url = api_url
        self.model_name = model_name

    def _call_llm(self, prompt):
        """內部函式：負責發送 API 请求"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False
        }
        try:
            response = requests.post(self.api_url, headers=headers, json=data, timeout=60)
            if response.status_code == 200:
                return response.json().get("message", {}).get("content", "")
            else:
                return f"Error: {response.status_code} - {response.text}"
        except Exception as e:
            return f"Connection Error: {str(e)}"

    def identify_fossil(self, description):
        """Step 1: 鑑定 (輸出報告)"""
        prompt = f"""
        你是一位專業古生物學家。使用者描述：{description}
        請根據描述：
        1. 推測學名與中文俗名。
        2. 簡單介紹年代與特徵。
        3. 用 Markdown 格式排版，重點文字加粗。
        """
        return self._call_llm(prompt)

    def generate_evolution_graph(self, fossil_info):
        """Step 2: 畫圖 (輸出 Graphviz DOT 代碼，已套用美學風格)"""
        prompt = f"""
        基於此資訊：{fossil_info}
        請幫我畫出一個「演化分支圖 (Phylogenetic Tree)」，使用 Graphviz DOT 語言。
        
        **美學設計要求 (請嚴格遵守)：**
        1. **版面：** 使用 `rankdir=LR` (由左至右)，`splines=ortho` (折線風格)。
        2. **節點：** 使用 `shape=box`，設定 `style="filled,rounded"`。填滿顏色使用淡綠色 (`#E0F2F1`)。
        3. **目標強調：** 最終的化石節點請用 **金黃色 (`#FFD700`)** 強調顯示。
        4. **結構：** 必須包含 1~2 個旁系群 (Sister Groups) 以展現分支感。
        5. **只輸出程式碼：** 不要任何解釋，前後不要有 ```dot 符號。
        """
        result = self._call_llm(prompt)
        # 清除 LLM 可能產生的 markdown 符號
        clean_code = result.replace("```dot", "").replace("```", "").strip()
        return clean_code