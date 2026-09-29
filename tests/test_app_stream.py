import json
import shutil

import app as app_module
import database
import pytest


def make_client(monkeypatch):
    app_module.app.config["TESTING"] = True
    # 限流是「每分鐘 10 次」，整個測試檔的請求加起來會超過，第 11 個開始會被擋成 429
    monkeypatch.setattr(app_module.limiter, "enabled", False)
    return app_module.app.test_client()


def parse_sse(raw_text):
    """把 SSE 原始文字拆成 [(event, data_dict), ...] 方便斷言。"""
    events = []
    for block in raw_text.strip().split("\n\n"):
        if not block.strip():
            continue
        event_line, data_line = block.split("\n", 1)
        event = event_line.removeprefix("event: ")
        data = json.loads(data_line.removeprefix("data: "))
        events.append((event, data))
    return events


def test_stream_irrelevant_intent_returns_single_chunk_then_done(monkeypatch):
    client = make_client(monkeypatch)
    monkeypatch.setattr(app_module.expert, "determine_intent", lambda text: "IRRELEVANT")

    res = client.post("/chat_api_stream", json={"message": "寫個減法器", "chat_id": "t1"})

    assert res.status_code == 200
    assert res.mimetype == "text/event-stream"
    events = parse_sse(res.get_data(as_text=True))

    assert events[0][0] == "chunk"
    assert "無法回答" in events[0][1]["text"]
    assert events[-1][0] == "done"


def test_stream_identify_intent_streams_chunks_then_final(monkeypatch):
    client = make_client(monkeypatch)
    monkeypatch.setattr(app_module.expert, "determine_intent", lambda text: "IDENTIFY")
    monkeypatch.setattr(
        app_module.expert,
        "identify_fossil_stream",
        lambda desc: iter(["這是", "三葉蟲", "[[Wiki: Trilobite]]"]),
    )
    monkeypatch.setattr(app_module, "get_wiki_image", lambda q: None)
    # 回應裡有 [[Wiki: Trilobite]]，extract_keyword 會抓到 keyword，
    # 程式碼就會呼叫 generate_evolution_graph 畫演化圖——這裡沒 mock 掉的話
    # 會真的打一次網路請求到 LLM API，讓這個「單元測試」變成會受網路環境影響。
    monkeypatch.setattr(
        app_module.expert,
        "generate_evolution_graph",
        lambda prompt: "",
    )

    res = client.post("/chat_api_stream", json={"message": "黑色有節的石頭", "chat_id": "t2"})
    events = parse_sse(res.get_data(as_text=True))

    chunk_events = [e for e in events if e[0] == "chunk"]
    final_events = [e for e in events if e[0] == "final"]
    done_events = [e for e in events if e[0] == "done"]

    assert [e[1]["text"] for e in chunk_events] == ["這是", "三葉蟲", "[[Wiki: Trilobite]]"]
    assert len(final_events) == 1
    # 最終版本要把 [[Wiki: ...]] 標記清掉，不該出現在使用者看到的最終文字裡
    assert "[[Wiki" not in final_events[0][1]["text"]
    assert "這是三葉蟲" in final_events[0][1]["text"]
    assert len(done_events) == 1


def test_stream_saves_conversation_to_db(monkeypatch):
    client = make_client(monkeypatch)
    monkeypatch.setattr(app_module.expert, "determine_intent", lambda text: "IRRELEVANT")

    res = client.post("/chat_api_stream", json={"message": "哈囉", "chat_id": "t3"})
    res.get_data()  # 一定要讀取完 response body，streaming generator 才會被完整消費、執行到最後的存檔邏輯

    messages = database.get_messages("t3")
    assert messages[0] == {"role": "user", "content": "哈囉", "intent": None}
    assert messages[1]["role"] == "assistant"
    assert messages[1]["intent"] == "IRRELEVANT"


def test_stream_missing_input_returns_400(monkeypatch):
    client = make_client(monkeypatch)
    res = client.post("/chat_api_stream", json={"message": "", "chat_id": "t4"})
    assert res.status_code == 400


def test_stream_uses_user_supplied_key_when_provided(monkeypatch):
    """BYOK：帶了 user_api_key 就該用一個新的 FossilExpert 實例，且用那把金鑰。"""
    client = make_client(monkeypatch)
    created_with = []

    class FakeExpert:
        def __init__(self, api_key=None, api_url=None, model_name=None):
            created_with.append(api_key)

        def determine_intent(self, text):
            return "IRRELEVANT"

    monkeypatch.setattr(app_module, "FossilExpert", FakeExpert)

    res = client.post(
        "/chat_api_stream",
        json={"message": "哈囉", "chat_id": "t6", "user_api_key": "sk-user-own-key"},
    )
    res.get_data()

    assert created_with == ["sk-user-own-key"]


def test_stream_falls_back_to_shared_expert_without_user_key(monkeypatch):
    """沒帶 user_api_key 時應該沿用共用的 expert，而不是每次都重新建立一個。"""
    client = make_client(monkeypatch)
    monkeypatch.setattr(app_module.expert, "determine_intent", lambda text: "IRRELEVANT")

    calls = []
    original_init = app_module.FossilExpert.__init__

    def spy_init(self, *a, **k):
        calls.append(k.get("api_key"))
        return original_init(self, *a, **k)

    monkeypatch.setattr(app_module.FossilExpert, "__init__", spy_init)

    res = client.post("/chat_api_stream", json={"message": "哈囉", "chat_id": "t7"})
    res.get_data()

    # 沒有 user_api_key 就不該建立任何新的 FossilExpert 實例
    assert calls == []


def test_stream_user_key_never_saved_to_db(monkeypatch, isolated_db):
    """使用者貼的金鑰絕對不能出現在資料庫檔案裡。"""
    client = make_client(monkeypatch)

    class FakeExpert:
        def __init__(self, api_key=None, api_url=None, model_name=None):
            pass

        def determine_intent(self, text):
            return "IRRELEVANT"

    monkeypatch.setattr(app_module, "FossilExpert", FakeExpert)

    res = client.post(
        "/chat_api_stream",
        json={"message": "哈囉", "chat_id": "t8", "user_api_key": "sk-super-secret-value"},
    )
    res.get_data()

    assert database.get_messages("t8")  # 確認這輪對話確實有存
    for f in isolated_db.glob("test.db*"):
        assert b"sk-super-secret-value" not in f.read_bytes()


def test_stream_llm_exception_is_reported_not_raised(monkeypatch):
    client = make_client(monkeypatch)
    monkeypatch.setattr(app_module.expert, "determine_intent", lambda text: "IDENTIFY")

    def broken_stream(desc):
        yield "部分內容"
        raise RuntimeError("模擬中途斷線")

    monkeypatch.setattr(app_module.expert, "identify_fossil_stream", broken_stream)

    res = client.post("/chat_api_stream", json={"message": "測試", "chat_id": "t5"})
    events = parse_sse(res.get_data(as_text=True))

    # 不應該讓整個 request 直接 500，而是把錯誤訊息當成一段內容送出，並仍然收到 done
    assert events[-1][0] == "done"
    assert any("錯誤" in e[1]["text"] for e in events if e[0] == "chunk" and "text" in e[1])


def _seed_identified_fossil(chat_id):
    database.open_chat(chat_id, "三葉蟲")
    database.save_exchange(chat_id, "三葉蟲", "這是三葉蟲 (Trilobite) 的化石，屬於節肢動物門。", "IDENTIFY")


def test_stream_graph_without_context_asks_to_identify_first(monkeypatch):
    client = make_client(monkeypatch)
    monkeypatch.setattr(app_module.expert, "determine_intent", lambda text: "GRAPH")

    res = client.post("/chat_api_stream", json={"message": "畫圖", "chat_id": "t9"})
    events = parse_sse(res.get_data(as_text=True))

    assert "請先讓我鑑定" in events[0][1]["text"]
    assert events[-1] == ("done", {"image_url": None, "new_title": "畫圖..."})


def test_stream_graph_with_context_returns_image_and_saves_it(monkeypatch):
    client = make_client(monkeypatch)
    _seed_identified_fossil("t9")
    monkeypatch.setattr(app_module.expert, "determine_intent", lambda text: "GRAPH")
    monkeypatch.setattr(app_module.expert, "generate_evolution_graph", lambda ctx: "digraph { a -> b }")
    monkeypatch.setattr(app_module, "render_evolution_graph", lambda dot: "/graph/test.png")

    res = client.post("/chat_api_stream", json={"message": "畫演化圖", "chat_id": "t9"})
    events = parse_sse(res.get_data(as_text=True))

    assert events[-1][1]["image_url"] == "/graph/test.png"
    assert "/graph/test.png" in database.get_messages("t9")[-1]["content"]


def test_stream_explain_uses_previous_answer_as_context(monkeypatch):
    client = make_client(monkeypatch)
    _seed_identified_fossil("t9")
    monkeypatch.setattr(app_module.expert, "determine_intent", lambda text: "EXPLAIN")
    received = {}

    def fake_explain(context, question):
        received["context"] = context
        yield "牠吃浮游生物"

    monkeypatch.setattr(app_module.expert, "explain_reasoning_stream", fake_explain)

    res = client.post("/chat_api_stream", json={"message": "牠吃什麼？", "chat_id": "t9"})
    events = parse_sse(res.get_data(as_text=True))

    assert "三葉蟲" in received["context"]
    assert events[0] == ("chunk", {"text": "牠吃浮游生物"})


def test_render_evolution_graph_rejects_non_digraph():
    assert app_module.render_evolution_graph("") is None
    assert app_module.render_evolution_graph("Error: 500 - gateway down") is None


def test_stream_explain_after_graph_still_uses_identification(monkeypatch):
    """回歸測試：先鑑定、再畫圖、再追問，追問的背景要是鑑定結果，不是畫圖那句話。"""
    client = make_client(monkeypatch)
    _seed_identified_fossil("t10")
    database.save_exchange("t10", "畫圖", "這是根據目前的鑑定結果，所繪製的親緣演化關係圖：\n\n![演化圖](/graph/x.png)", "GRAPH")
    monkeypatch.setattr(app_module.expert, "determine_intent", lambda text: "EXPLAIN")
    received = {}

    def fake_explain(context, question):
        received["context"] = context
        yield "牠吃浮游生物"

    monkeypatch.setattr(app_module.expert, "explain_reasoning_stream", fake_explain)

    client.post("/chat_api_stream", json={"message": "牠吃什麼？", "chat_id": "t10"}).get_data()

    assert "三葉蟲" in received["context"]
    assert "演化關係圖" not in received["context"]


@pytest.mark.skipif(shutil.which("dot") is None, reason="需要系統安裝 Graphviz（CI 有裝）")
def test_render_evolution_graph_stores_png_and_serves_it(monkeypatch):
    client = make_client(monkeypatch)

    url = app_module.render_evolution_graph('digraph { "Arthropoda" -> "Trilobita" }')

    assert url.startswith("/graph/") and url.endswith(".png")
    res = client.get(url)
    assert res.status_code == 200
    assert res.mimetype == "image/png"
    assert res.data.startswith(b"\x89PNG")


def test_unknown_graph_returns_404(monkeypatch):
    client = make_client(monkeypatch)
    assert client.get("/graph/does-not-exist.png").status_code == 404


class _KeyRecordingExpert:
    created_with = []

    def __init__(self, api_key=None, api_url=None, model_name=None):
        _KeyRecordingExpert.created_with.append(api_key)

    def bury_fossil(self, lat, lng, era):
        return '{"found": false, "reason": "test"}'

    def dig_fossil(self, info):
        return "<p>report</p>"


def test_map_apis_use_user_supplied_key(monkeypatch):
    client = make_client(monkeypatch)
    _KeyRecordingExpert.created_with = []
    monkeypatch.setattr(app_module, "FossilExpert", _KeyRecordingExpert)

    bury = client.post("/api/bury", json={"lat": 1, "lng": 2, "era": "中生代", "user_api_key": "sk-user"}).get_json()
    examine = client.post("/api/examine", json={"fossil_info": {"found": False}, "user_api_key": "sk-user"}).get_json()

    assert bury["success"] and examine["success"]
    assert _KeyRecordingExpert.created_with == ["sk-user", "sk-user"]


def test_map_apis_fall_back_to_shared_expert(monkeypatch):
    client = make_client(monkeypatch)
    _KeyRecordingExpert.created_with = []
    monkeypatch.setattr(app_module, "FossilExpert", _KeyRecordingExpert)
    monkeypatch.setattr(app_module.expert, "bury_fossil", lambda lat, lng, era: '{"found": false}')

    res = client.post("/api/bury", json={"lat": 1, "lng": 2, "era": "中生代"}).get_json()

    assert res["success"]
    assert _KeyRecordingExpert.created_with == []
