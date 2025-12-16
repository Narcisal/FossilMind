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
        """Step 1: 鑑定 (輸出報告) - 嚴格版"""
        prompt = f"""
        你是一位極度嚴謹的古生物學家與分類學家。使用者描述：{description}
        
        【重要警告】
        1. **絕對禁止捏造學名**：你只能提供「真實存在」於科學紀錄與論文中的學名。
        2. **禁止自創命名**：不要根據發現地自己拼湊名字（如不要發明 "Caolinguosaurus" 這種不存在的字）。
        3. **如果特徵模糊**：請回答最接近的「屬 (Genus)」或「科 (Family)」即可，不要強行編造「種 (Species)」。
        4. **地質背景檢核**：若使用者提到「菜寮溪」、「左鎮」等台灣地名，這些地層多為「更新世 (Pleistocene)」，主要出土哺乳類（如古菱齒象、四不像鹿、水牛、獼猴），**絕對不可能**出現恐龍（Dinosauria）。
        
        【任務要求】
        請根據描述進行鑑定，並依照以下格式輸出：
        
        **1. 推測學名與中文俗名**
        * **學名**：(請填寫真實存在的學名，如 *Elaphurus davidianus*, *Palaeoloxodon*。若不確定種名，寫 *sp.*)
        * **中文俗名**：(如 四不像鹿、古菱齒象)
        * **信賴度**：(高/中/低，並說明原因)

        **2. 簡介年代與特徵**
        * **年代**：(如 更新世，約 40萬-1萬年前)
        * **特徵對比**：(說明使用者描述的特徵符合該物種的哪些部分)
        
        **3. 生存環境與習性**
        * (簡述當時的古環境)

        **請直接輸出內容，不要用 ```markdown 包覆代碼塊。**
        """
        return self._call_llm(prompt)

    def generate_evolution_graph(self, analysis_result):
        """Step 2: 畫圖 (輸出 Graphviz DOT 代碼，已套用美學風格)"""
        prompt = f"""
        你是一位精通 Graphviz DOT 語言的演化生物學家。
        
        【任務目標】
        請根據以下的「鑑定報告」，繪製一張該物種的演化分類分支圖 (Cladogram)。
        
        【鑑定報告內容】
        {analysis_result}
        
        【繪圖規則】
        1. 語法：必須使用 valid Graphviz DOT syntax (digraph)。
        2. 節點內容：**嚴格禁止**使用 "Root", "Group A", "Group B" 這種通用詞。必須使用報告中提到的真實學名 (如 "Macaca", "Primates", "Hominidae")。
        3. 結構：從較大的分類單元 (如目、科) 指向較小的分類單元 (屬、種)。
        4. 重點標示：請將鑑定報告中最可能的物種節點設為黃色 (style=filled, fillcolor="yellow")。
        5. 旁系群：若報告中有提到近親，請畫出旁系群分支。
        6. **只輸出程式碼**：不要解釋，不要用 markdown 包覆，直接給出代碼。
        
        【範例結構 (僅供參考格式，不要抄內容)】
        digraph Evolution {{
            rankdir=LR;
            node [shape=box, style=rounded];
            "Primates (靈長目)" -> "Cercopithecidae (科)";
            "Cercopithecidae (科)" -> "Macaca (獼猴屬)";
            "Macaca (獼猴屬)" -> "Macaca cyclopis (台灣獼猴)" [style=filled, fillcolor="yellow"];
        }}
        """
        result = self._call_llm(prompt)
        # 清除 LLM 可能產生的 markdown 符號
        clean_code = result.replace("```dot", "").replace("```", "").strip()
        return clean_code