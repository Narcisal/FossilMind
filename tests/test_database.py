import json

import config
import database


def test_open_chat_uses_first_message_as_title():
    assert database.open_chat("c1", "這是一顆黑色有節的石頭，長約五公分") == "這是一顆黑色有節的石頭，長約五..."


def test_open_chat_keeps_title_after_first_exchange():
    database.open_chat("c1", "三葉蟲")
    database.save_exchange("c1", "三葉蟲", "這是三葉蟲的化石", "IDENTIFY")

    assert database.open_chat("c1", "牠吃什麼？") == "三葉蟲..."


def test_save_exchange_round_trip():
    database.open_chat("c1", "三葉蟲")
    database.save_exchange("c1", "三葉蟲", "這是三葉蟲的化石", "IDENTIFY")

    assert database.get_messages("c1") == [
        {"role": "user", "content": "三葉蟲", "intent": None},
        {"role": "assistant", "content": "這是三葉蟲的化石", "intent": "IDENTIFY"},
    ]


def test_identify_context_skips_graph_and_irrelevant_replies():
    """
    回歸測試：畫完演化圖後再追問，背景應該還是鑑定結果，
    而不是「這是……演化關係圖」那句話（舊版只看「最近一則超過 20 字的回覆」會抓錯）。
    """
    database.open_chat("c1", "三葉蟲")
    database.save_exchange("c1", "三葉蟲", "這是三葉蟲 (Trilobite) 的化石，屬於節肢動物門。", "IDENTIFY")
    database.save_exchange("c1", "畫圖", "這是根據目前的鑑定結果，所繪製的親緣演化關係圖：\n\n![演化圖](/graph/x.png)", "GRAPH")
    database.save_exchange("c1", "寫程式", "🦖 術業有專攻，FossilMind 無法回答與化石無關的問題喔！", "IRRELEVANT")

    assert "三葉蟲" in database.get_last_identify_context("c1")


def test_identify_context_uses_most_recent_identification():
    database.open_chat("c1", "三葉蟲")
    database.save_exchange("c1", "三葉蟲", "這是三葉蟲的化石", "IDENTIFY")
    database.save_exchange("c1", "菊石", "這是菊石的化石", "IDENTIFY")

    assert database.get_last_identify_context("c1") == "這是菊石的化石"


def test_identify_context_empty_without_identification():
    database.open_chat("c1", "寫程式")
    database.save_exchange("c1", "寫程式", "🦖 術業有專攻，FossilMind 無法回答與化石無關的問題喔！", "IRRELEVANT")

    assert database.get_last_identify_context("c1") == ""


def test_identify_context_is_per_chat():
    database.open_chat("c1", "三葉蟲")
    database.save_exchange("c1", "三葉蟲", "這是三葉蟲的化石", "IDENTIFY")
    database.open_chat("c2", "畫圖")

    assert database.get_last_identify_context("c2") == ""


def test_legacy_json_is_imported_into_empty_database(isolated_db, monkeypatch):
    legacy = isolated_db / "legacy.json"
    legacy.write_text(json.dumps({"old1": {"title": "舊對話...", "timestamp": 123.0, "messages": [
        {"role": "user", "content": "三葉蟲"},
        {"role": "assistant", "content": "這是一段足夠長的鑑定說明文字，超過二十個字元"},
        {"role": "assistant", "content": "太短"},
    ]}}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(config, "DB_FILE", str(isolated_db / "fresh.db"))
    monkeypatch.setattr(config, "LEGACY_JSON_FILE", str(legacy))

    database.init_db()

    assert len(database.get_messages("old1")) == 3
    # 舊資料沒有 intent，退回「最近一則夠長的回覆」的判斷方式
    assert database.get_last_identify_context("old1") == "這是一段足夠長的鑑定說明文字，超過二十個字元"


def test_legacy_import_runs_only_once(isolated_db, monkeypatch):
    legacy = isolated_db / "legacy.json"
    legacy.write_text(json.dumps({"old1": {"title": "t", "timestamp": 1.0, "messages": [
        {"role": "user", "content": "hi"}]}}), encoding="utf-8")
    monkeypatch.setattr(config, "DB_FILE", str(isolated_db / "fresh.db"))
    monkeypatch.setattr(config, "LEGACY_JSON_FILE", str(legacy))

    database.init_db()
    database.init_db()

    assert len(database.get_messages("old1")) == 1


def test_corrupt_legacy_json_is_skipped_with_warning(isolated_db, monkeypatch, capsys):
    bad = isolated_db / "corrupt.json"
    bad.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(config, "DB_FILE", str(isolated_db / "fresh.db"))
    monkeypatch.setattr(config, "LEGACY_JSON_FILE", str(bad))

    database.init_db()

    # 確認壞掉時至少會印出警告，不是完全靜默吞掉
    assert "Database" in capsys.readouterr().out


def test_graph_round_trip():
    database.save_graph("g1", b"\x89PNG fake bytes")

    assert database.get_graph("g1") == b"\x89PNG fake bytes"
    assert database.get_graph("missing") is None
