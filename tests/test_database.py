import json
import importlib

import config
import database


def test_save_and_load_round_trip(tmp_path, monkeypatch):
    db_file = tmp_path / "chats.json"
    monkeypatch.setattr(config, "DB_FILE", str(db_file))
    monkeypatch.setattr(database, "DB_FILE", str(db_file))

    data = {"chat1": {"title": "測試", "timestamp": 123.0, "messages": []}}
    database.save_db(data)

    loaded = database.load_db()
    assert loaded == data


def test_load_db_returns_empty_dict_when_file_missing(tmp_path, monkeypatch):
    missing_file = tmp_path / "does_not_exist.json"
    monkeypatch.setattr(database, "DB_FILE", str(missing_file))

    assert database.load_db() == {}


def test_load_db_returns_empty_dict_on_corrupt_json(tmp_path, monkeypatch, capsys):
    bad_file = tmp_path / "corrupt.json"
    bad_file.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(database, "DB_FILE", str(bad_file))

    result = database.load_db()

    assert result == {}
    # 確認壞掉時至少會印出警告，不是完全靜默吞掉
    assert "Database" in capsys.readouterr().out


def test_get_last_ai_context_finds_most_recent_long_assistant_message():
    messages = [
        {"role": "user", "content": "這是什麼"},
        {"role": "assistant", "content": "太短"},
        {"role": "assistant", "content": "這是一段足夠長的鑑定說明文字，超過二十個字元"},
    ]
    assert database.get_last_ai_context(messages) == "這是一段足夠長的鑑定說明文字，超過二十個字元"


def test_get_last_ai_context_returns_empty_string_when_none_found():
    messages = [{"role": "user", "content": "哈囉"}]
    assert database.get_last_ai_context(messages) == ""
