import json
import os
from config import DB_FILE  

def load_db():
    if not os.path.exists(DB_FILE): return {}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except: return {}

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_last_ai_context(messages):
    for msg in reversed(messages):
        if msg["role"] == "assistant" and len(msg["content"]) > 20:
            return msg["content"]
    return ""