import requests
import json
import re

# =============================================================
# 1. 設定區 (請在這裡填入你的 API 資訊)
# =============================================================
DEFAULT_API_KEY = "3dfdd1df4ee04ed8bfc6ba4a68e3577ce2ce2f29690620ae800886061755cafc" 
API_URL = "https://api-gateway.netdb.csie.ncku.edu.tw/api/chat"
DEFAULT_MODEL = "gpt-oss:20b"
# =============================================================

class FossilExpert:
    def __init__(self, api_key=DEFAULT_API_KEY, api_url=API_URL, model_name=DEFAULT_MODEL):
        self.api_key = api_key
        self.api_url = api_url
        self.model_name = model_name

    def _call_llm(self, prompt, temperature=0.7):
        """內部函式：負責發送 API 请求"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "temperature": temperature # 可調整創造力
        }
        try:
            response = requests.post(self.api_url, headers=headers, json=data, timeout=60)
            if response.status_code == 200:
                return response.json().get("message", {}).get("content", "")
            else:
                return f"Error: {response.status_code} - {response.text}"
        except Exception as e:
            return f"Connection Error: {str(e)}"

    def determine_intent(self, user_input):
        """
        Step 1: 感知層 (Perception) - q1
        判斷使用者的意圖是「鑑定」、「畫圖」還是「問問題」。
        """
        prompt = f"""
        你是一個意圖分類器。請分析使用者的輸入："{user_input}"
        
        請只回傳以下三個關鍵字之一（不要有其他解釋）：
        1. **IDENTIFY** : 如果使用者在描述外觀、特徵，或上傳了圖片的描述 (例如："黑色的石頭，有條紋", "這是什麼", "幫我鑑定")。
        2. **GRAPH** : 如果使用者明確要求看圖、演化樹、親緣關係 (例如："畫出演化圖", "好呀", "給我看圖片", "它是什麼科的", "視覺化")。
        3. **EXPLAIN** : 如果使用者是在針對已知的結果提問，或詢問細節 (例如："為什麼不是恐龍？", "它吃什麼？", "年代多久？")。
        
        Answer:
        """
        response = self._call_llm(prompt, temperature=0.1) # 溫度低一點，讓分類更精確
        
        # 清理回應，確保只拿到關鍵字
        intent = response.strip().upper()
        if "GRAPH" in intent: return "GRAPH"
        if "EXPLAIN" in intent: return "EXPLAIN"
        return "IDENTIFY" # 預設為鑑定

    def identify_fossil(self, description):
        """
        Step 2: 驗證與鑑定層 (Verification) - q2
        """
        prompt = f"""
        你是一位極度嚴謹的古生物學家與分類學家。使用者描述了一個標本：{description}
        
        【地質背景過濾機制】
        * 若使用者提到「台灣」、「台南」、「菜寮溪」、「左鎮」、「澎湖水道」：
          這些地層屬於**更新世 (Pleistocene)**，主要產出哺乳動物（如古菱齒象、四不像鹿、水牛、鯨豚、鯊魚牙）。
          **絕對禁止** 鑑定為恐龍 (Dinosauria)、三葉蟲 (Trilobite) 或菊石 (Ammonite)，因為年代完全不符。
        
        【任務要求】
        請根據描述進行鑑定，若資訊不足可推測最可能的屬 (Genus)。
        請依照以下 HTML 格式輸出 (直接輸出 HTML 代碼，不要用 markdown)：

        <p>這看起來非常像是<strong>[中文俗名] ([學名])</strong> 的化石！</p>
        
        <div class="fossil-card">
            <div class="fossil-header">
                <span>鑑定報告</span>
                <span class="confidence-tag">信心度: [高/中/低]</span>
            </div>
            <div class="fossil-body">
                <div class="info-row"><span class="info-label">學名</span> <span>[學名]</span></div>
                <div class="info-row"><span class="info-label">分類</span> <span>[目] > [科]</span></div>
                <div class="info-row"><span class="info-label">年代</span> <span>[地質年代]</span></div>
                <div class="info-row"><span class="info-label">食性</span> <span>[食性]</span></div>
            </div>
        </div>
        <br>
        <p>[這裡用 50 字以內的簡短文字，描述它的特徵對比或是生態習性]。</p>
        <p style="color: #666; font-size: 0.9em;">(您可以接著問我關於它的細節，或是輸入「畫圖」來看演化關係)</p>
        """
        return self._call_llm(prompt)

    def explain_reasoning(self, context, question):
        """
        Step 3: 推理層 (Reasoning) - q3
        回答使用者的 "Why" 或 "Detail"
        """
        prompt = f"""
        你是一位古生物科普老師。
        
        【前情提要 (Context)】
        我們剛剛鑑定的化石是：{context}
        
        【使用者問題】
        {question}
        
        【任務】
        請根據前情提要回答使用者的問題。回答要簡潔有趣，長度控制在 100 字以內。
        """
        return self._call_llm(prompt)

    def generate_evolution_graph(self, context_text):
        """
        Step 4: 視覺化層 (Visualization) - q4
        輸出 Graphviz DOT 代碼
        """
        prompt = f"""
        你是一位精通 Graphviz DOT 語言的演化生物學家。
        
        【任務目標】
        請根據目前的鑑定結果："{context_text}"，繪製一張該物種的演化分類分支圖 (Cladogram)。
        
        【繪圖規則】
        1. 語法：只輸出 digraph 代碼。
        2. 節點內容：請使用真實的生物學名 (Latin Name) 作為節點 ID，中文名作為 label。
        3. **重要**：請將鑑定結果中的那個物種節點設為 **黃色底色** (style=filled, fillcolor="#ffeb3b") 以便強調。
        4. 結構：從 "Order (目)" -> "Family (科)" -> "Genus (屬)" -> "Species (種)"。
        5. 只輸出程式碼，不要有任何 Markdown 標記 (不要 ```dot)。
        
        【範例結構】
        digraph G {{
            rankdir=LR;
            node [shape=box, style="rounded,filled", fillcolor="white", fontname="Microsoft JhengHei"];
            
            "Proboscidea" [label="長鼻目"];
            "Elephantidae" [label="象科"];
            "Palaeoloxodon" [label="古菱齒象屬"];
            "P_huaihoensis" [label="淮河古菱齒象", fillcolor="#ffeb3b"];
            
            "Proboscidea" -> "Elephantidae";
            "Elephantidae" -> "Palaeoloxodon";
            "Palaeoloxodon" -> "P_huaihoensis";
        }}
        """
        result = self._call_llm(prompt)
        
        # 清除可能殘留的 markdown
        clean_code = result.replace("```dot", "").replace("```", "").replace("json", "").strip()
        return clean_code

# 簡單測試用
if __name__ == "__main__":
    expert = FossilExpert()
    # 測試意圖判斷
    print(expert.determine_intent("畫出演化圖")) # 應該回傳 GRAPH
    print(expert.determine_intent("這是不是恐龍")) # 應該回傳 EXPLAIN 或 IDENTIFY