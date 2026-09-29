import os
from dotenv import load_dotenv

load_dotenv()  # 讀取專案根目錄的 .env（該檔案已加進 .gitignore，不會進版控）

API_KEY = os.getenv("FOSSILMIND_API_KEY")
API_URL = os.getenv("FOSSILMIND_API_URL", "https://api-gateway.netdb.csie.ncku.edu.tw/api/chat")
MODEL_NAME = os.getenv("FOSSILMIND_MODEL_NAME", "gpt-oss:20b")

if not API_KEY:
    raise RuntimeError(
        "缺少 FOSSILMIND_API_KEY。請複製 .env.example 為 .env，並填入你自己的金鑰。"
    )

# Docker 部署時可以把這個路徑指到掛載的 volume，容器重建後對話紀錄才不會消失
DB_FILE = os.getenv("FOSSILMIND_DB_FILE", "chats.db")
LEGACY_JSON_FILE = "chats.json"  # 舊版的對話紀錄，資料庫是空的時候會自動匯入
SECRET_KEY = os.urandom(24)