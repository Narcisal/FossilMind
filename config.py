import os
from dotenv import load_dotenv

load_dotenv()  # 讀取專案根目錄的 .env（該檔案已加進 .gitignore，不會進版控）

# AI 服務的設定有兩種來源：
# 1. 這裡的環境變數（.env）——有設 FOSSILMIND_API_KEY 就直接使用，首頁不會跳出設定視窗。
# 2. 沒設的話，第一次打開首頁會跳出視窗讓使用者填，存進 SETTINGS_FILE（見 llm_settings.py）。
API_KEY = os.getenv("FOSSILMIND_API_KEY") or None
API_URL = os.getenv("FOSSILMIND_API_URL", "https://api-gateway.netdb.csie.ncku.edu.tw/api/chat")
MODEL_NAME = os.getenv("FOSSILMIND_MODEL_NAME", "gpt-oss:20b")
# 共用金鑰那個服務的 API 格式："ollama"（NCKU gateway、本機 Ollama）或 "openai"（OpenAI 相容的 chat completions）
API_FORMAT = os.getenv("FOSSILMIND_API_FORMAT", "ollama")

# 首頁設定視窗可以選的服務。網址寫死在伺服器這邊，不讓使用者自己填網址：
# 否則伺服器會被拿來替使用者連到任意位址（包括伺服器所在的內部網路），也就是 SSRF。
PROVIDERS = {
    "ncku": {
        "label": "NCKU 課程 API",
        "url": "https://api-gateway.netdb.csie.ncku.edu.tw/api/chat",
        "format": "ollama",
        "default_model": "gpt-oss:20b",
    },
    "openai": {
        "label": "OpenAI",
        "url": "https://api.openai.com/v1/chat/completions",
        "format": "openai",
        "default_model": "gpt-6-luna",
    },
    "gemini": {
        "label": "Google Gemini",
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "format": "openai",
        "default_model": "gemini-3.8-flash",
    },
}
DEFAULT_PROVIDER = "ncku"  # 設定視窗預設選的服務

# 開發用：設了這個環境變數，設定視窗才會多一個「本機 Ollama」選項（Ollama 不檢查金鑰，隨便填都能用）。
# 正式部署不要設。Docker 裡要連到主機上的 Ollama，網址用 http://host.docker.internal:11434/api/chat
LOCAL_OLLAMA_URL = os.getenv("FOSSILMIND_LOCAL_OLLAMA_URL")
if LOCAL_OLLAMA_URL:
    PROVIDERS["local"] = {
        "label": "本機 Ollama（開發用）",
        "url": LOCAL_OLLAMA_URL,
        "format": "ollama",
        "default_model": os.getenv("FOSSILMIND_LOCAL_OLLAMA_MODEL", "qwen3:4b"),
    }

# 首頁設定視窗存下來的設定檔
SETTINGS_FILE = os.getenv("FOSSILMIND_SETTINGS_FILE", "llm_settings.json")

# Docker 部署時可以把這個路徑指到掛載的 volume，容器重建後對話紀錄才不會消失
DB_FILE = os.getenv("FOSSILMIND_DB_FILE", "chats.db")
LEGACY_JSON_FILE = "chats.json"  # 舊版的對話紀錄，資料庫是空的時候會自動匯入
SECRET_KEY = os.urandom(24)