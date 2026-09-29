import os
import tempfile

import pytest

# 測試環境不需要真的金鑰 —— config.py 只是要求「有值」，實際呼叫 LLM 的地方
# 在測試裡全部被 mock 掉，不會真的發送任何請求。這行必須在任何 import config
# （或間接 import 到 config 的模組，如 backend / app）之前執行。
os.environ.setdefault("FOSSILMIND_API_KEY", "test-dummy-key-not-a-real-secret")
# app.py 在 import 時就會初始化資料庫，這裡先指到暫存位置，避免在專案資料夾裡產生 chats.db
os.environ.setdefault("FOSSILMIND_DB_FILE", os.path.join(tempfile.mkdtemp(), "import-time.db"))


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """每個測試都用一個全新的空資料庫，彼此不會互相影響，也不會碰到真正的對話紀錄。"""
    import config
    import database

    monkeypatch.setattr(config, "DB_FILE", str(tmp_path / "test.db"))
    monkeypatch.setattr(config, "LEGACY_JSON_FILE", str(tmp_path / "chats.json"))
    database.init_db()
    return tmp_path
