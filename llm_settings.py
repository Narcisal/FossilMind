import json
import os
import tempfile

import config

# 使用者第一次打開首頁時在彈出視窗填的 AI 服務設定（服務、金鑰、模型）。
# 設定只能建立一次：之後網頁上不能修改，要改就刪掉這個檔案（Docker 則是重新 build 並啟動容器）。
# 檔案含有 API 金鑰，已加進 .gitignore 與 .dockerignore。


def load():
    """回傳 {"provider", "api_key", "model"}；還沒設定或檔案內容不合法時回傳 None。"""
    path = config.SETTINGS_FILE
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[Settings] Failed to read {path}: {e}")
        return None
    if data.get("provider") not in config.PROVIDERS or not data.get("api_key") or not data.get("model"):
        print(f"[Settings] Ignoring invalid settings in {path}")
        return None
    return data


def save(provider, api_key, model):
    """
    寫入設定。檔案已經存在時丟出 FileExistsError，不會覆蓋。
    先寫到暫存檔、再用 hard link 放到正式位置：link 在目標已存在時會失敗，
    所以多個 worker 同時送出設定也只會有一個成功，而且其他人不會讀到寫到一半的檔案。
    """
    path = config.SETTINGS_FILE
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".llm_settings.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"provider": provider, "api_key": api_key, "model": model}, f)
        os.chmod(tmp_path, 0o600)  # 只有執行伺服器的帳號能讀
        os.link(tmp_path, path)
    finally:
        os.remove(tmp_path)
