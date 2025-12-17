import requests
import json
import re

# =============================================================
# 設定區
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
        """內部函式：負責發送 API 請求"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "temperature": temperature
        }
        try:
            # 設定 300 秒 timeout 避免運算過久中斷
            response = requests.post(self.api_url, headers=headers, json=data, timeout=300)
            if response.status_code == 200:
                return response.json().get("message", {}).get("content", "")
            else:
                return f"Error: {response.status_code} - {response.text}"
        except Exception as e:
            return f"Connection Error: {str(e)}"

    def determine_intent(self, user_input):
        """
        Step 1: 感知層 (Perception) - q1
        判斷使用者的意圖是「鑑定」、「畫圖」、「問問題」還是「來亂的」。
        """
        prompt = f"""
        你是一個意圖分類器。請分析使用者的輸入："{user_input}"
        
        請只回傳以下四個關鍵字之一（不要有其他解釋）：
        1. **IDENTIFY** : 如果使用者在描述外觀、特徵，或上傳了圖片的描述 (例如："黑色的石頭，有條紋", "這是什麼", "幫我鑑定")。
        2. **GRAPH** : 如果使用者明確要求看圖、演化樹、親緣關係 (例如："畫出演化圖", "好呀", "給我看圖片", "它是什麼科的", "視覺化")。
        3. **EXPLAIN** : 如果使用者是在針對已知的結果提問，或詢問細節 (例如："為什麼不是恐龍？", "它吃什麼？", "年代多久？")。
        4. **IRRELEVANT** : 如果輸入完全與古生物、化石、地質或生物學**無關** (例如："寫一個 4bit 減法器", "寫程式", "今天天氣", "講笑話", "數學問題")。
        
        Answer:
        """
        response = self._call_llm(prompt, temperature=0.1) 
        intent = response.strip().upper()
        
        # 簡單的關鍵字防呆
        if "GRAPH" in intent: return "GRAPH"
        if "EXPLAIN" in intent: return "EXPLAIN"
        if "IRRELEVANT" in intent: return "IRRELEVANT"
        return "IDENTIFY" 

    def identify_fossil(self, description):
        """
        Step 2: 驗證與鑑定層 (Verification) - q2
        """
        prompt = f"""
        你是一位極度嚴謹的古生物學家。使用者輸入了："{description}"
        
        【🛡️ 安全防護機制 (Safety Guardrail)】
        **請先檢查使用者的輸入內容：**
        如果內容與「古生物、化石、岩石、地質、生物遺骸」**完全無關**（例如：電子電路、程式碼、數學作業、政治、娛樂新聞），
        請**立刻停止鑑定**，不要編造任何學名。
        
        若判定為無關內容，請直接輸出以下 HTML 代碼：
        <div class="message ai">
            <div class="bubble" style="background: #fff3cd; color: #856404; border: 1px solid #ffeeba;">
                <strong>⚠️ 無法識別</strong><br>
                FossilMind 專注於古生物與化石鑑定，無法回答關於其他領域（如電子、程式、數學）的問題。<br>
                請上傳化石照片或描述特徵。
            </div>
        </div>

        ---
        
        只有當確認內容與古生物相關時，才執行以下鑑定任務：
        
        【地質背景過濾機制】
        * 若使用者提到「台灣」、「台南」、「菜寮溪」、「左鎮」，**絕對禁止** 鑑定為恐龍 (Dinosauria)，應優先考慮更新世哺乳類。
        
        【輸出格式】
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
        <p>[簡短特徵描述]。</p>
        """
        return self._call_llm(prompt)

    def explain_reasoning(self, context, question):
        """Step 3: 推理層 (Reasoning)"""
        prompt = f"""
        你是一位古生物科普老師。
        【前情提要】我們剛剛鑑定的化石是：{context}
        【使用者問題】{question}
        請回答問題，若問題與該化石無關，請禮貌引導回化石話題。
        """
        return self._call_llm(prompt)

    def generate_evolution_graph(self, context_text):
        """Step 4: 視覺化層 (Visualization)"""
        prompt = f"""
        你是一位精通 Graphviz DOT 語言的演化生物學家。
        【鑑定結果】"{context_text}"
        請繪製該物種的演化分類分支圖。
        1. 只輸出 digraph 代碼。
        2. 將主角節點設為黃色 (style=filled, fillcolor="#ffeb3b")。
        3. 不要 Markdown。
        """
        result = self._call_llm(prompt)
        clean_code = result.replace("```dot", "").replace("```", "").replace("json", "").strip()
        return clean_code

# 測試用
if __name__ == "__main__":
    expert = FossilExpert()
    print("測試無關話題:", expert.determine_intent("做一個4bit減法器")) # 應該回傳 IRRELEVANT
    print("測試相關話題:", expert.determine_intent("這個牙齒有波浪狀紋路")) # 應該回傳 IDENTIFY