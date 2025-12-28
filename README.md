# FossilMind
an AI agent that help user identify, and learn about simple paleontology.
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
    - **Dual-Agent Architecture**:
        - **Agent 1 (Timekeeper)**：驗證地質年代邏輯（例如：驗證該座標在古生代是否為陸地）。
        - **Agent 2 (Paleontologist)**：根據挖掘結果撰寫科普鑑定報告。

## 🏗️ 系統狀態機圖 (System Logic)

本系統採用中心輻射型狀態機設計，根據使用者的意圖 (Intent) 動態分流至不同工具模組。

```mermaid
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
    - **Dual-Agent Architecture**:
        - **Agent 1 (Timekeeper)**：驗證地質年代邏輯（例如：驗證該座標在古生代是否為陸地）。
        - **Agent 2 (Paleontologist)**：根據挖掘結果撰寫科普鑑定報告。

## 🏗️ 系統狀態機圖 (System Logic)


```mermaid
stateDiagram-v2
    direction TB

    %% 狀態樣式設定
    classDef mainState fill:#f9f,stroke:#333,stroke-width:2px;
    classDef subState fill:#e1f5fe,stroke:#4a6fa5,stroke-width:2px;

    %% 1. 系統啟動
    [*] --> Init : Start Server
    Init --> Idle : System Ready

    %% 2. 待機狀態
    state "Idle (Wait for Input)" as Idle
    class Idle mainState

    %% 3. 意圖分析 (核心)
    state "Intent Analysis" as Analyzer
    class Analyzer mainState

    Idle --> Analyzer : User Message

    %% 4. 功能分流 (分支)
    state "IDENTIFY Mode" as Identify {
        direction TB
        LLM_Identify --> Extract_Keyword
        Extract_Keyword --> Wiki_Search
        Wiki_Search --> Auto_Graph
    }
    class Identify subState

    state "GRAPH Mode" as Graph {
        direction TB
        Check_Context --> Generate_DOT
        Generate_DOT --> Render_PNG
    }
    class Graph subState

    state "EXPLAIN Mode" as Explain {
        Get_Context --> LLM_Reasoning
    }
    class Explain subState
    
    state "IRRELEVANT" as Irrelevant
    class Irrelevant subState

    %% 5. 狀態流轉
    Analyzer --> Identify : intent="IDENTIFY"
    Analyzer --> Graph : intent="GRAPH"
    Analyzer --> Explain : intent="EXPLAIN"
    Analyzer --> Irrelevant : intent="IRRELEVANT"

    %% 6. 回傳結果
    Identify --> Idle : Return JSON
    Graph --> Idle : Return Image
    Explain --> Idle : Return Text
    Irrelevant --> Idle : Return Warning