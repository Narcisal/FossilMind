# 🦕 FossilMind - AI Paleontology Agent
> **TOC 2025 Final Project** | Intelligent Agents with LLMs

**FossilMind** 是一個結合大型語言模型 (LLM) 與視覺化工具的古生物 AI Agent。它不僅能透過自然語言鑑定化石，還能自動檢索維基百科圖片，並生成動態演化樹狀圖，旨在協助使用者探索地球的深層記憶。

##  Key Features

1.  **🔍 智慧化石鑑定 (Identify & RAG)**
    - Agent 能解析使用者對化石外觀的模糊描述，推測學名與年代。
    - **Retrieval-Augmented Generation (RAG)**：鑑定後自動透過 Wiki API 檢索並回傳真實化石照片，解決 LLM 無法提供真實影像的問題。
2.  **🧬 動態演化圖生成 (Graph Visualization)**
    - **Tool Use**: Agent 會根據鑑定結果生成 Graphviz DOT 腳本，並即時渲染出該物種的親緣演化樹 (Phylogenetic Tree)。
3.  **🌍 互動式時空挖掘地圖 (Time-Travel Excavation)**
    - **Dual-Agent Architecture (Innovation)**：
        - **Agent 1 (Timekeeper)**：驗證地質年代邏輯（例如：驗證該座標在古生代是否為陸地）。
        - **Agent 2 (Paleontologist)**：根據挖掘結果撰寫科普鑑定報告。
  
## File Structure

| 檔案 | 說明 |
| :--- | :--- |
| `app.py` | **Controller**: 處理 Flask 路由、圖片組裝與回應邏輯 |
| `backend.py` | **Model**: 封裝 LLM 邏輯、Prompt Engineering 與意圖判斷 |
| `utils.py` | **Tools**: 負責 Wiki API 搜尋、Regex 關鍵字提取與標籤清理 |
| `database.py` | **Data**: 負責 JSON 對話紀錄的讀寫 |
| `config.py` | **Config**: 存放 API Key 與全域設定 |
| `templates/` | 前端 HTML (Chat UI & Leaflet Map) |
| `static/` | 存放 CSS、JS 以及**生成的演化圖** |

---

## ⚙️ 安裝與執行指引 (Installation Guide)

### 1. Prerequisites

* **Python**: 3.9 或以上版本
* **Graphviz**: **必備系統軟體** 
* **Ollama**: 需安裝並執行本地 LLM Server

### 2. System Dependencies

#### A. 安裝 Graphviz

* Windows: [下載安裝檔](https://graphviz.org/download/)
* macOS: `brew install graphviz`
* Linux: `sudo apt-get install graphviz`

#### B. 準備 Ollama 模型
請確認 Ollama 服務已啟動，並下載 `llama3` 模型：
`ollama pull llama3`

### 3. 專案設置
* step 1: 下載專案
`git clone https://github.com/Narcisal/FossilMind.git`

* Step 2: 安裝 Python 套件
`pip install -r requirements.txt`

### 4. 啟動系統 (Run Application)
執行以下指令啟動 Flask 伺服器：
`python app.py`

看到以下訊息代表啟動成功：

`🦕 FossilMind 伺服器啟動中... (http://127.0.0.1:5000)`
`請開啟瀏覽器訪問：http://127.0.0.1:5000`



## FSM

```mermaid
stateDiagram-v2
    direction TB

    %% ==========================================
    %% 樣式定義 (Color Palette)
    %% ==========================================
    classDef server fill:#37474f,stroke:#263238,stroke-width:2px,color:white;
    classDef chatZone fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef mapZone fill:#fff3e0,stroke:#e65100,stroke-width:2px;
    
    classDef llm fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef io fill:#fff8e1,stroke:#fbc02d,stroke-width:1px;
    classDef logic fill:#f3e5f5,stroke:#7b1fa2,stroke-width:1px;
    classDef endpoint fill:#ffccbc,stroke:#d84315,stroke-width:2px;

    %% ==========================================
    %% 系統入口
    %% ==========================================
    [*] --> Server_Listening : python app.py
    state "Flask Server Listening (Port 5000)" as Server_Listening
    class Server_Listening server

    %% ==========================================
    %% 子系統 1: 對話系統 (Chat System)
    %% ==========================================
    state "Chat Subsystem (Detail)" as Chat_System {
        direction TB
        
        state "POST /chat_api" as Chat_EP
        class Chat_EP endpoint
        
        state "Load DB & Init" as DB_Load
        state "Intent Classification" as Intent_Check
        class Intent_Check llm

        Chat_EP --> DB_Load
        DB_Load --> Intent_Check : expert.determine_intent()

        state is_intent <<choice>>
        Intent_Check --> is_intent

        %% 分支 A: IDENTIFY (RAG + Graph)
        state "IDENTIFY Workflow" as ID_Flow {
            direction TB
            state "LLM: Identify Fossil" as L1
            class L1 llm
            state "Regex: Extract Name" as P1
            class P1 logic
            state "API: Wiki Search" as IO1
            class IO1 io
            state "LLM: Gen Evolution Graph" as L2
            class L2 llm
            state "Tool: Render PNG" as IO2
            class IO2 io

            [*] --> L1
            L1 --> P1 : expert.identify_fossil()
            P1 --> IO1 : extract_keyword()
            IO1 --> L2 : Found?
            L2 --> IO2 : expert.generate_evolution_graph()
            IO2 --> [*]
        }

        %% 分支 B: GRAPH
        state "GRAPH Workflow" as Graph_Flow {
            direction TB
            state "Context Check" as C1
            class C1 logic
            state "LLM: Gen DOT" as L3
            class L3 llm
            
            [*] --> C1
            C1 --> L3 : Has Context
            L3 --> [*]
        }

        %% 分支 C: EXPLAIN
        state "EXPLAIN Workflow" as Explain_Flow {
            state "LLM: Reasoning" as L4
            class L4 llm
            [*] --> L4
        }
        
        %% 分支 D: IRRELEVANT
        state "Static Reject" as Reject_Flow

        %% 連接
        is_intent --> ID_Flow : IDENTIFY
        is_intent --> Graph_Flow : GRAPH
        is_intent --> Explain_Flow : EXPLAIN
        is_intent --> Reject_Flow : IRRELEVANT

        %% 結尾
        state "Save Chat History" as Save_DB
        ID_Flow --> Save_DB
        Graph_Flow --> Save_DB
        Explain_Flow --> Save_DB
        Reject_Flow --> Save_DB
    }
    class Chat_System chatZone

    %% ==========================================
    %% 子系統 2: 地圖挖掘系統 (Map Excavation)
    %% ==========================================
    state "Map Excavation System (Detail)" as Map_System {
        direction TB
        
        %% 階段 1: 埋藏判定 (Timekeeper)
        state "Phase 1: Excavation" as Phase1 {
            direction TB
            state "POST /api/bury" as Bury_EP
            class Bury_EP endpoint

            state "Agent 1: The Timekeeper" as Timekeeper_LLM
            class Timekeeper_LLM llm
            
            state "Parse JSON & Clean" as Parse_JSON
            class Parse_JSON logic

            state is_found <<choice>>

            Bury_EP --> Timekeeper_LLM : expert.bury_fossil(lat, lng, era)
            Timekeeper_LLM --> Parse_JSON : Geology Logic Check
            Parse_JSON --> is_found : fossil['found']?

            state "Return: Found Fossil Data" as Ret_Found
            state "Return: Not Found Reason" as Ret_Empty
            
            is_found --> Ret_Found : True
            is_found --> Ret_Empty : False
        }

        %% 階段 2: 鑑定報告 (Paleontologist)
        state "Phase 2: Examination" as Phase2 {
            direction TB
            state "POST /api/examine" as Exam_EP
            class Exam_EP endpoint

            state "Agent 2: The Paleontologist" as Paleo_LLM
            class Paleo_LLM llm

            state "Format HTML Response" as Format_HTML
            class Format_HTML logic

            Exam_EP --> Paleo_LLM : expert.dig_fossil(fossil_data)
            Paleo_LLM --> Format_HTML : Generate Report
            Format_HTML --> [*] : Return JSON
        }
        
        %% 前端邏輯連接
        Ret_Found --> Phase2 : Client triggers Examination
    }
    class Map_System mapZone

    %% ==========================================
    %% 路由分派
    %% ==========================================
    Server_Listening --> Chat_System : /chat_api
    Server_Listening --> Map_System : /api/bury OR /api/examine