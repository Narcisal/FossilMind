# 🦕 FossilMind - AI Paleontology Agent
> **TOC 2025 Final Project** | Intelligent Agents with LLMs

**FossilMind** 是一個結合大型語言模型 (LLM) 與視覺化工具的古生物 AI Agent。它不僅能透過自然語言鑑定化石，還能自動檢索維基百科圖片，並生成動態演化樹狀圖，旨在協助使用者探索地球的深層記憶。

## 🌟 專案亮點 (Key Features)

1.  **🔍 智慧化石鑑定 (Identify & RAG)**
    - Agent 能解析使用者對化石外觀的模糊描述，推測學名與年代。
    - **Retrieval-Augmented Generation (RAG)**：鑑定後自動透過 Wiki API 檢索並回傳真實化石照片，解決 LLM 無法提供真實影像的問題。
2.  **🧬 動態演化圖生成 (Graph Visualization)**
    - **Tool Use**: Agent 會根據鑑定結果生成 Graphviz DOT 腳本，並即時渲染出該物種的親緣演化樹 (Phylogenetic Tree)。
3.  **🌍 互動式時空挖掘地圖 (Time-Travel Excavation)**
    - **Dual-Agent Architecture (Innovation)**：
        - **Agent 1 (Timekeeper)**：驗證地質年代邏輯（例如：驗證該座標在古生代是否為陸地）。
        - **Agent 2 (Paleontologist)**：根據挖掘結果撰寫科普鑑定報告。

## 🏗️ 系統狀態機圖 (System Logic Diagram)

本系統採用詳細的狀態機流程設計，清楚定義了意圖判斷、工具調用 (Wiki/Graphviz) 與資料庫存取的順序。

```mermaid
stateDiagram-v2
    direction TB

    %% 定義樣式
    classDef startEnd fill:#f96,stroke:#333,stroke-width:2px,color:white;
    classDef process fill:#e1f5fe,stroke:#0277bd,stroke-width:1px;
    classDef llm fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef io fill:#fff3e0,stroke:#ef6c00,stroke-width:1px;
    classDef decision fill:#fce4ec,stroke:#c2185b,stroke-width:1px,shape:rhombus;

    %% 1. 初始化階段
    [*] --> Request_Received : POST /chat_api
    state "Load & Init Session" as Session
    Request_Received --> Session : load_db()
    
    %% 2. 意圖判斷
    state "Intent Classification" as IntentClass
    Session --> IntentClass : expert.determine_intent()
    
    %% 3. 分流決策
    state is_intent <<choice>>
    IntentClass --> is_intent : Return Intent String
    
    %% ==========================================
    %% 分支 A: IDENTIFY (最複雜的邏輯)
    %% ==========================================
    state "IDENTIFY Process" as Identify_Flow {
        direction TB
        
        state "LLM: Identify Fossil" as ID_LLM
        class ID_LLM llm
        
        state "Extract Keyword (Regex)" as Regex
        class Regex process
        
        state "Tool: Wiki Search API" as Wiki
        class Wiki io
        
        state "LLM: Generate DOT Code" as Graph_LLM
        class Graph_LLM llm
        
        state "Tool: Graphviz Render" as Render
        class Render io
        
        [*] --> ID_LLM : expert.identify_fossil()
        ID_LLM --> Regex : extract_keyword()
        Regex --> Wiki : get_wiki_image()
        Wiki --> Graph_LLM : expert.generate_evolution_graph()
        Graph_LLM --> Render : src.render() (Generate PNG)
        Render --> [*] : Append Markdown Image
    }

    %% ==========================================
    %% 分支 B: GRAPH
    %% ==========================================
    state "GRAPH Process" as Graph_Flow {
        direction TB
        state "Context Check" as CtxCheck
        state "LLM: Generate DOT" as G_LLM
        class G_LLM llm
        state "Tool: Render PNG" as G_Render
        class G_Render io
        
        [*] --> CtxCheck : get_last_ai_context()
        CtxCheck --> G_LLM : Context Exists?
        G_LLM --> G_Render : Graphviz Source
    }

    %% ==========================================
    %% 分支 C: EXPLAIN
    %% ==========================================
    state "EXPLAIN Process" as Explain_Flow {
        state "LLM: Reasoning" as E_LLM
        class E_LLM llm
        [*] --> E_LLM : expert.explain_reasoning()
    }

    %% ==========================================
    %% 分支 D: IRRELEVANT
    %% ==========================================
    state "Static Response" as Irrelevant_Flow {
        [*] --> Reject : Return Predefined String
    }

    %% 連接分流
    is_intent --> Identify_Flow : intent == "IDENTIFY"
    is_intent --> Graph_Flow : intent == "GRAPH"
    is_intent --> Explain_Flow : intent == "EXPLAIN"
    is_intent --> Irrelevant_Flow : intent == "IRRELEVANT"

    %% 4. 合併結果
    state "Response Formulation" as Response
    Identify_Flow --> Response : Text + Wiki URL + Graph Path
    Graph_Flow --> Response : Text + Graph Path
    Explain_Flow --> Response : Explanation Text
    Irrelevant_Flow --> Response : Warning Text

    %% 5. 持久化
    state "Save Database" as Save
    class Save io
    Response --> Save : save_db()
    
    %% 6. 結束
    Save --> Return_JSON : jsonify()
    Return_JSON --> [*]
    class Return_JSON startEnd