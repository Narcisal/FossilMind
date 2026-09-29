import json
import os
import sqlite3
import time
from contextlib import contextmanager

import config

# 對話紀錄存在 SQLite。原本整份 chats.json 讀進來、改完再整份寫回去，
# 多個 worker 同時寫會互相覆蓋；SQLite 每次只寫入新增的那幾筆，並由資料庫本身處理鎖。
SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    id        TEXT PRIMARY KEY,
    title     TEXT NOT NULL,
    timestamp REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id    TEXT NOT NULL REFERENCES chats(id),
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    intent     TEXT,  -- AI 回覆是哪種意圖產生的；從舊版 chats.json 匯入的訊息為 NULL
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, id);
CREATE TABLE IF NOT EXISTS graphs (
    id         TEXT PRIMARY KEY,
    png        BLOB NOT NULL,
    created_at REAL NOT NULL
);
"""


@contextmanager
def _connect():
    """開一條連線，區塊正常結束就 commit、出錯就 rollback，最後一定關閉連線。"""
    conn = sqlite3.connect(config.DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db():
    """建立資料表；如果資料庫是空的且有舊版 chats.json，就把舊紀錄匯入。"""
    # gunicorn 的多個 worker 會同時啟動、同時跑到這裡。切換成 WAL 需要獨占鎖，
    # 搶輸的一方會立刻拿到 "database is locked"（不會等 busy timeout），所以稍等後重試。
    for attempt in range(10):
        try:
            with _connect() as conn:
                conn.execute("PRAGMA journal_mode=WAL")  # 讀寫可以同時進行，多個 worker 比較不會互卡
                conn.executescript(SCHEMA)
            break
        except sqlite3.OperationalError as e:
            if "locked" not in str(e) or attempt == 9:
                raise
            time.sleep(0.2 * (attempt + 1))
    if os.path.exists(config.LEGACY_JSON_FILE):
        _import_legacy_json(config.LEGACY_JSON_FILE)


def _import_legacy_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[Database] Failed to import {path}, skipping: {e}")
        return
    with _connect() as conn:
        # 「確認資料庫是空的」跟「寫入」要在同一個獨占交易裡，
        # 否則多個 worker 同時啟動時可能各自匯入一次，資料重複
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT COUNT(*) FROM chats").fetchone()[0] > 0:
            return
        for chat_id, chat in data.items():
            conn.execute(
                "INSERT OR IGNORE INTO chats (id, title, timestamp) VALUES (?, ?, ?)",
                (chat_id, chat.get("title", "新對話"), chat.get("timestamp", time.time())),
            )
            for msg in chat.get("messages", []):
                conn.execute(
                    "INSERT INTO messages (chat_id, role, content, intent, created_at) VALUES (?, ?, ?, NULL, ?)",
                    (chat_id, msg["role"], msg["content"], chat.get("timestamp", time.time())),
                )
    print(f"[Database] Imported {len(data)} chats from {path}")


def open_chat(chat_id, user_input):
    """取得（或建立）這個對話並更新時間戳記，回傳對話標題。還沒有任何訊息時，用使用者的第一句話當標題。"""
    now = time.time()
    title = user_input[:15] + "..."
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO chats (id, title, timestamp) VALUES (?, ?, ?)",
            (chat_id, title, now),
        )
        conn.execute(
            """UPDATE chats SET timestamp = ?,
                   title = CASE WHEN EXISTS (SELECT 1 FROM messages WHERE chat_id = ?) THEN title ELSE ? END
               WHERE id = ?""",
            (now, chat_id, title, chat_id),
        )
        return conn.execute("SELECT title FROM chats WHERE id = ?", (chat_id,)).fetchone()["title"]


def save_exchange(chat_id, user_input, ai_content, intent):
    """把這一輪的使用者訊息與 AI 回覆存進資料庫（同一個 transaction）。"""
    now = time.time()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO messages (chat_id, role, content, intent, created_at) VALUES (?, 'user', ?, NULL, ?)",
            (chat_id, user_input, now),
        )
        conn.execute(
            "INSERT INTO messages (chat_id, role, content, intent, created_at) VALUES (?, 'assistant', ?, ?, ?)",
            (chat_id, ai_content, intent, now),
        )


def get_messages(chat_id):
    with _connect() as conn:
        rows = conn.execute(
            "SELECT role, content, intent FROM messages WHERE chat_id = ? ORDER BY id", (chat_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_last_identify_context(chat_id):
    """
    回傳這個對話最近一次的鑑定結果，給追問 (EXPLAIN) 與畫圖 (GRAPH) 當背景。
    只看 IDENTIFY 產生的回覆，避免抓到「這是演化圖」或拒答訊息這種不含化石資訊的內容。
    舊版匯入的訊息沒有 intent，退回原本「最近一則夠長的 AI 回覆」的判斷方式。
    """
    with _connect() as conn:
        row = conn.execute(
            """SELECT content FROM messages
               WHERE chat_id = ? AND role = 'assistant' AND intent = 'IDENTIFY'
               ORDER BY id DESC LIMIT 1""",
            (chat_id,),
        ).fetchone()
        if row:
            return row["content"]
        rows = conn.execute(
            """SELECT content FROM messages
               WHERE chat_id = ? AND role = 'assistant' AND intent IS NULL
               ORDER BY id DESC""",
            (chat_id,),
        ).fetchall()
    for r in rows:
        if len(r["content"]) > 20:
            return r["content"]
    return ""


def save_graph(graph_id, png_bytes):
    with _connect() as conn:
        conn.execute("INSERT INTO graphs (id, png, created_at) VALUES (?, ?, ?)", (graph_id, png_bytes, time.time()))


def get_graph(graph_id):
    with _connect() as conn:
        row = conn.execute("SELECT png FROM graphs WHERE id = ?", (graph_id,)).fetchone()
    return row["png"] if row else None
