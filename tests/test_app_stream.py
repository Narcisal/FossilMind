import json

import app as app_module


def make_client(monkeypatch):
    app_module.app.config["TESTING"] = True
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


def test_stream_saves_conversation_to_db(monkeypatch, tmp_path):
    client = make_client(monkeypatch)
    db_file = tmp_path / "chats.json"
    monkeypatch.setattr(app_module, "load_db", lambda: {})
    saved = {}
    monkeypatch.setattr(app_module, "save_db", lambda data: saved.update(data))
    monkeypatch.setattr(app_module.expert, "determine_intent", lambda text: "IRRELEVANT")

    res = client.post("/chat_api_stream", json={"message": "哈囉", "chat_id": "t3"})
    res.get_data()  # 一定要讀取完 response body，streaming generator 才會被完整消費、執行到最後的存檔邏輯

    assert "t3" in saved
    messages = saved["t3"]["messages"]
    assert messages[0] == {"role": "user", "content": "哈囉"}
    assert messages[1]["role"] == "assistant"


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


def test_stream_user_key_never_saved_to_db(monkeypatch):
    """使用者貼的金鑰絕對不能出現在存進 chats.json 的內容裡。"""
    client = make_client(monkeypatch)
    saved = {}
    monkeypatch.setattr(app_module, "load_db", lambda: {})
    monkeypatch.setattr(app_module, "save_db", lambda data: saved.update(data))

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

    assert "sk-super-secret-value" not in json.dumps(saved)


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
