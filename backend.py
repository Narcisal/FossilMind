import requests
import json
import re
import time
from config import API_KEY, API_URL, MODEL_NAME, API_FORMAT

# 暫時性的錯誤：請求太頻繁（429）、服務商忙碌或暫時故障（5xx）。等一下再試通常就會成功
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 2


def _retry_delay(response, attempt):
    """服務商有用 Retry-After 指定等待秒數（而且不會太久）就照它，否則依序等 2、4 秒。"""
    retry_after = (getattr(response, "headers", None) or {}).get("Retry-After", "")
    if retry_after.isdigit() and int(retry_after) <= 10:
        return int(retry_after)
    return 2 ** (attempt + 1)


def _provider_detail(response):
    """從服務商的錯誤回應裡取出人看得懂的那句話（例如模型不存在），取不到就用原始內容的開頭。"""
    try:
        body = response.json()
        if isinstance(body, list) and body:
            body = body[0]
        error = body.get("error", body) if isinstance(body, dict) else body
        message = error.get("message") if isinstance(error, dict) else error
        if isinstance(message, str) and message:
            return message
    except Exception:
        pass
    return (getattr(response, "text", "") or "")[:300]


def _error_message(response):
    """
    把失敗的回應轉成要顯示給使用者的訊息，一律以 "Error: <狀態碼>" 開頭（呼叫端靠這個判斷失敗）。
    這段文字會顯示在網頁上、也會存進對話紀錄，所以不直接轉貼服務商的原始 JSON。
    """
    status = response.status_code
    if status in (401, 403):
        # 不附上服務商的內容：有些服務商會在錯誤訊息裡帶出部分金鑰
        return f"Error: {status} - API 金鑰無效，或沒有使用這個模型的權限。"
    if status == 429:
        return f"Error: {status} - AI 服務的請求太頻繁或額度已用完，請稍後再試。"
    if status >= 500:
        return f"Error: {status} - AI 服務目前忙碌或暫時無法使用，請稍後再試。"
    return f"Error: {status} - {_provider_detail(response)}"


class FossilExpert:
    """
    api_format 決定請求與回應的格式：
    - "ollama"：NCKU gateway 與本機 Ollama。非串流回傳 {"message": {"content": ...}}，
      串流回傳逐行 NDJSON，每行是 {"message": {"content": "..."}, "done": bool}。
    - "openai"：OpenAI 相容的 chat completions（OpenAI、Gemini 等）。非串流回傳
      {"choices": [{"message": {"content": ...}}]}，串流是 SSE，每行 "data: {...}"，以 "data: [DONE]" 結束。
    """

    def __init__(self, api_key=API_KEY, api_url=API_URL, model_name=MODEL_NAME, api_format=API_FORMAT):
        self.api_key = api_key
        self.api_url = api_url
        self.model_name = model_name
        self.api_format = api_format

    def _request(self, prompt, temperature, stream):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "stream": stream,
            "temperature": temperature
        }
        return requests.post(self.api_url, headers=headers, json=data, timeout=300, stream=stream)

    def _request_with_retry(self, prompt, temperature, stream):
        """遇到暫時性錯誤時自動重試，最多 MAX_RETRIES 次；最後一次的回應不論成功與否都交給呼叫端處理。"""
        for attempt in range(MAX_RETRIES + 1):
            response = self._request(prompt, temperature, stream)
            if response.status_code not in RETRYABLE_STATUS or attempt == MAX_RETRIES:
                return response
            delay = _retry_delay(response, attempt)
            print(f"[LLM] HTTP {response.status_code}, retrying in {delay}s ({attempt + 1}/{MAX_RETRIES})")
            if hasattr(response, "close"):
                response.close()
            time.sleep(delay)

    def _call_llm(self, prompt, temperature=0.7):
        """內部函式：負責發送 API 請求"""
        try:
            response = self._request_with_retry(prompt, temperature, stream=False)
            if response.status_code != 200:
                return _error_message(response)
            body = response.json()
            if self.api_format == "openai":
                return (body.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            return body.get("message", {}).get("content", "")
        except Exception as e:
            return f"Connection Error: {str(e)}"

    def _call_llm_stream(self, prompt, temperature=0.7):
        """內部函式：streaming 版本，逐段 yield 文字片段。"""
        try:
            with self._request_with_retry(prompt, temperature, stream=True) as response:
                if response.status_code != 200:
                    yield _error_message(response)
                    return
                # 串流回應常常沒標 charset，requests 會把每行當成 bytes；統一用 UTF-8 解碼
                response.encoding = "utf-8"
                for line in response.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    if self.api_format == "openai":
                        if not line.startswith("data:"):
                            continue
                        payload = line[len("data:"):].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            chunk = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        piece = ((chunk.get("choices") or [{}])[0].get("delta") or {}).get("content")
                        if piece:
                            yield piece
                    else:
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        piece = chunk.get("message", {}).get("content", "")
                        if piece:
                            yield piece
                        if chunk.get("done"):
                            break
        except Exception as e:
            yield f"Connection Error: {str(e)}"

    def determine_intent(self, user_input):
        """
        Step 1: 感知層 (Perception)
        加強對「名詞直接輸入」的判定，避免卡在上一輪話題。
        """
        prompt = f"""
        你是一個意圖分類器。請分析使用者輸入："{user_input}"
        
        請只回傳以下四個關鍵字之一（不要有其他解釋）：
        1. **IDENTIFY** : 
           - 使用者在描述外觀、特徵 (e.g. "黑色石頭", "像大象的骨頭")。
           - 或者使用者**直接輸入一個物種名稱** (e.g. "古菱齒象", "暴龍", "海神三葉蟲")，這代表他想查這個物種。
           - 或者明確要求鑑定 (e.g. "這是什麼").
           
        2. **GRAPH** : 
           - 使用者明確要求看圖、演化樹、親緣關係 (e.g. "畫圖", "演化圖", "視覺化").

        3. **EXPLAIN** : 
           - 使用者針對**已知結果**提問細節 (e.g. "為什麼？", "它吃什麼？", "年代多久？", "真的嗎？").
           - 注意：如果輸入是一個全新的名詞（與上下文無關），請優先歸類為 IDENTIFY。

        4. **IRRELEVANT** : 完全無關的話題 (e.g. "寫程式", "今天天氣").
        
        Answer:
        """
        response = self._call_llm(prompt, temperature=0.0) # 避免胡言亂語
        intent = response.strip().upper()
        
        if "GRAPH" in intent: return "GRAPH"
        if "EXPLAIN" in intent: return "EXPLAIN"
        if "IRRELEVANT" in intent: return "IRRELEVANT"
        return "IDENTIFY"

    def _identify_fossil_prompt(self, description):
        return f"""
        你是一位極度嚴謹的古生物學家。使用者輸入了："{description}"
        
        【安全防護機制】
        **請先檢查使用者的輸入內容：**
        如果內容與「古生物、化石、岩石、地質、生物遺骸」**完全無關**（例如：電子電路、程式碼、數學作業、政治、娛樂新聞），
        請**立刻停止鑑定**，不要編造任何學名。
        
        若判定為無關內容，請直接輸出以下 HTML 代碼：
        <div class="message ai">
            <div class="bubble" style="background: #fff3cd; color: #856404; border: 1px solid #ffeeba;">
                <strong>⚠️ 無法識別</strong><br>
                FossilMind 專注於古生物與化石鑑定，無法回答關於其他領域（如電子、程式、數學）的問題。<br>
                請輸入化石特徵描述。
            </div>
        </div>

        ---
        
        只有當確認內容與古生物相關時，才執行以下鑑定任務：

        ⚠️ **極重要指令**：
        在回答的**最後一行**，請務必加上一個搜尋標籤，格式為：`[[Wiki: 學名或最通用的英文俗名]]`。
        這個標籤是用來在維基百科找圖的，所以請給出最容易找到圖片的關鍵字 (例如：`[[Wiki: Triceratops]]` 或 `[[Wiki: Ammonite]]`)。
        
        【地質背景過濾機制】
        * 需貼近真實地裡形成所造成的化石種類。若是在該地並未有發現到該世代的化石，請不要輕易編造學名或不該存在的化石。
        * e.g. 若使用者提到「台灣」、「台南」、「菜寮溪」、「左鎮」，**絕對應** 優先考慮新生代哺乳類。
        
        【輸出格式】
        請依照以下 HTML 格式輸出 (直接輸出 HTML 代碼，不要用 markdown)：

        <p><strong>[中文俗名] ([學名])</strong> 的化石！</p>
        
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

    def identify_fossil(self, description):
        """Step 2: 驗證與鑑定層 (Verification)"""
        return self._call_llm(self._identify_fossil_prompt(description))

    def identify_fossil_stream(self, description):
        """Step 2 的 streaming 版本，逐段回傳文字。"""
        yield from self._call_llm_stream(self._identify_fossil_prompt(description))

    def _explain_reasoning_prompt(self, context, question):
        return f"""
        你是一位極度嚴謹的古生物學家。
        【前情提要】我們剛剛鑑定的化石是：{context}
        【使用者問題】{question}
        請回答問題，若問題與該化石無關，請禮貌引導回化石話題。
        """

    def explain_reasoning(self, context, question):
        """Step 3: 推理層 (Reasoning)"""
        return self._call_llm(self._explain_reasoning_prompt(context, question))

    def explain_reasoning_stream(self, context, question):
        """Step 3 的 streaming 版本，逐段回傳文字。"""
        yield from self._call_llm_stream(self._explain_reasoning_prompt(context, question))

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


    def bury_fossil(self, lat, lng, era):
        """
        AI #1: 埋藏者 (The Timekeeper) - 嚴格地質版
        如果是後來才形成的島嶼 (如台灣)，在古老年代必須判定為「不存在」。
        """
        prompt = f"""
        你是時間守護者。使用者在座標 ({lat}, {lng}) 進行挖掘。
        目標年代：{era}。
        
        【任務：嚴格地質檢核】
        請判斷「現代的這個地點」在「{era}」是否存在？
        
        ⚠️ **最重要的判斷標準 (Strict Rules)**：
        1. **新生地質區**：如果該地點是現代才形成的島嶼或陸地 (例如：**台灣**、夏威夷、冰島、日本列島大部分)，而在目標年代 (如中生代、古生代) 尚未透過造山運動形成，**請直接判定為 found: false**。
        2. **理由 (Reason)**：必須明確寫出「當時台灣島尚未形成」或「該板塊還在深海/地函中」。
        3. **例外**：只有在點擊「大陸板塊核心」(如歐亞大陸內部、美洲大陸) 且當時真的是海洋時，才允許發現海洋生物。

        ⚠️ **針對「台灣 (Taiwan)」與類似島嶼的特殊規則**：
        1. **古生代 (Paleozoic) 與 中生代 (Mesozoic)**：
        - 狀態：**found: false**。
        - 理由：當時台灣島尚未形成，位於深海或地殼隱沒帶，無陸地生物。
        2. **新生代 (Cenozoic)**：
        - 狀態：**found: true** (機率極高)。
        - 早期 (Paleogene)：多為 **海相化石** (貝類、有孔蟲、海膽)。
        - 晚期 (Neogene/Quaternary)：台灣島浮出水面，且冰河期有陸橋連接亞洲大陸。可發現 **大型哺乳類** (古菱齒象、犀牛、鹿) 或 **人類遺骸** (如左鎮人)。

        【嚴格學名規範 (CRITICAL)】
        1. **絕對禁止捏造學名**：你提供的 `name_latin` 必須是古生物學界公認、真實存在的物種。
        2. **寧缺勿濫**：若你不確定該地點的特定「種 (Species)」，請**只提供「屬 (Genus)」名**，並加上 "sp." (例如：使用 "Palaeoloxodon sp." 而非胡亂拼湊的 "Mammut primigenium")。
        3. **分類準確性**：不要將不同屬的特徵混用 (例如：不要把長毛象的種名安在古菱齒象的屬名上)。
        
        【決策邏輯】
        * 情況 A (地質不存在)：點擊台灣/夏威夷 + 中生代/古生代 -> **found: false** (理由：島嶼未誕生)。
        * 情況 B (環境不對)：點擊內陸沙漠 + 尋找水生生物 -> **found: false**。
        * 情況 C (成功)：點擊古大陸板塊 -> **found: true**。
        
        【⚠️ 強制語言規範】
        1. 必須使用 **繁體中文 (Taiwan)**。
        2. 絕對禁止簡體字。
        
        【輸出格式 (JSON)】
        {{
            "found": boolean,
            "reason": "若 false，請解釋地質原因 (例如: 當時台灣島尚未因板塊擠壓而浮出水面，該處為深海)",
            "location": "地點名稱 (如: 遠古太平洋深處)",
            "terrain": "地形描述 (如: 深海 / 地殼下)",
            "name_zh": "物種中文名 (若 false 留空)",
            "name_latin": "學名 (若 false 留空)",
            "type": "分類 (若 false 留空)",
            "environment": "古代環境",
            "description": "簡述"
        }}
        """
        return self._call_llm(prompt, temperature=0.7)

    def dig_fossil(self, fossil_data):
        """
        AI #2: 鑑定師 (The Paleontologist)
        根據挖掘結果進行講解 (成功恭喜，失敗則科普)。
        """
        prompt = f"""
        你是一位嚴謹的古生物學家。這是剛出土的探勘結果：
        
        {fossil_data}
        
        【任務】
        請判斷 JSON 資料中的 "found" 欄位：
        
        **情況 A：如果有挖到 (found: true)**
        請用專業、略微興喜的口吻撰寫鑑定報告：
        1. 發現了什麼物種。
        2. 介紹該物種的習性。
        3. 描述當時這個地點的環境樣貌。
        4. 介紹該生物將來的命運 (例如於何時繁盛、消亡等等)。
        
        **情況 B：如果沒挖到 (found: false)**
        請用遺憾但富含教育意義的口吻解釋：
        1. 告訴使用者這裡為什麼沒有化石 (引用 reason 欄位)。
        2. 科普一下當時這個地點的地質狀態 (例如：當時台灣還在海底，或者是火山還沒噴發)。
        3. 鼓勵使用者去別的地方試試看。
        
        【強制語言規範】
        1. **全程使用繁體中文 (Traditional Chinese, Taiwan)**。
        2. 輸出格式為 HTML (不包含 ```html 標記)。

        【輸出格式規範】
        1. 只輸出報告的內文段落，直接從內容開始寫。
        2. **不要**加報告標題、撰寫人、鑑定日期、署名、編號或任何頁首頁尾資訊
           （網頁上已經會顯示物種名稱，這些資訊是多餘的）。
        3. **不要**輸出 <html>、<head>、<title>、<body> 等整頁的標籤，只用 <p>、<ul>、<li>、<strong> 這類內文標籤。
        """
        return self._call_llm(prompt)
    
# # 測試用
# if __name__ == "__main__":
#     expert = FossilExpert()
#     print("測試無關話題:", expert.determine_intent("做一個4bit減法器")) # 應該回傳 IRRELEVANT
#     print("測試相關話題:", expert.determine_intent("這個牙齒有波浪狀紋路")) # 應該回傳 IDENTIFY