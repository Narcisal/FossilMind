from backend import FossilExpert


def make_expert_with_fixed_llm_response(monkeypatch, response_text):
    """建立一個 FossilExpert，並把 _call_llm 換成回傳固定文字，完全不打真的 API。"""
    expert = FossilExpert()
    monkeypatch.setattr(expert, "_call_llm", lambda prompt, temperature=0.7: response_text)
    return expert


def test_determine_intent_graph(monkeypatch):
    expert = make_expert_with_fixed_llm_response(monkeypatch, "GRAPH")
    assert expert.determine_intent("畫一下演化圖") == "GRAPH"


def test_determine_intent_explain(monkeypatch):
    expert = make_expert_with_fixed_llm_response(monkeypatch, "EXPLAIN")
    assert expert.determine_intent("為什麼會滅絕？") == "EXPLAIN"


def test_determine_intent_irrelevant(monkeypatch):
    expert = make_expert_with_fixed_llm_response(monkeypatch, "IRRELEVANT")
    assert expert.determine_intent("寫一個減法器") == "IRRELEVANT"


def test_determine_intent_defaults_to_identify_for_unrecognized_output(monkeypatch):
    # LLM 有時候不會乖乖照格式回答，determine_intent 應該要有合理的預設值而不是壞掉
    expert = make_expert_with_fixed_llm_response(monkeypatch, "嗯我不太確定")
    assert expert.determine_intent("黑色石頭有波浪紋") == "IDENTIFY"


def test_call_llm_reports_http_error_without_raising(monkeypatch):
    """_call_llm 對非 200 回應要回傳可讀訊息，不能整個 crash。"""
    expert = FossilExpert()

    class FakeResponse:
        status_code = 500
        text = "internal error"

    monkeypatch.setattr("backend.requests.post", lambda *a, **k: FakeResponse())

    result = expert._call_llm("test prompt")
    assert "Error" in result
    assert "500" in result


def test_call_llm_reports_connection_error_without_raising(monkeypatch):
    expert = FossilExpert()

    def raise_connection_error(*args, **kwargs):
        raise ConnectionError("network down")

    monkeypatch.setattr("backend.requests.post", raise_connection_error)

    result = expert._call_llm("test prompt")
    assert "Connection Error" in result


class FakeStreamResponse:
    """模擬 Ollama 風格的 NDJSON streaming 回應，用來測試 _call_llm_stream 的解析邏輯。"""

    def __init__(self, status_code, lines):
        self.status_code = status_code
        self._lines = lines
        self.text = "error body"

    def iter_lines(self, decode_unicode=True):
        return iter(self._lines)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_call_llm_stream_yields_each_chunk_in_order(monkeypatch):
    expert = FossilExpert()
    lines = [
        '{"message": {"content": "哈"}, "done": false}',
        '{"message": {"content": "囉"}, "done": false}',
        '{"message": {"content": ""}, "done": true}',
    ]
    monkeypatch.setattr(
        "backend.requests.post",
        lambda *a, **k: FakeStreamResponse(200, lines),
    )

    pieces = list(expert._call_llm_stream("test prompt"))
    assert pieces == ["哈", "囉"]


def test_call_llm_stream_stops_after_done_true(monkeypatch):
    expert = FossilExpert()
    lines = [
        '{"message": {"content": "第一段"}, "done": true}',
        '{"message": {"content": "不該出現"}, "done": false}',
    ]
    monkeypatch.setattr(
        "backend.requests.post",
        lambda *a, **k: FakeStreamResponse(200, lines),
    )

    pieces = list(expert._call_llm_stream("test prompt"))
    assert pieces == ["第一段"]


def test_call_llm_stream_skips_unparseable_lines(monkeypatch):
    expert = FossilExpert()
    lines = [
        "not valid json",
        '{"message": {"content": "還是有內容"}, "done": true}',
    ]
    monkeypatch.setattr(
        "backend.requests.post",
        lambda *a, **k: FakeStreamResponse(200, lines),
    )

    pieces = list(expert._call_llm_stream("test prompt"))
    assert pieces == ["還是有內容"]


def test_call_llm_stream_yields_error_on_non_200(monkeypatch):
    expert = FossilExpert()
    monkeypatch.setattr(
        "backend.requests.post",
        lambda *a, **k: FakeStreamResponse(500, []),
    )

    pieces = list(expert._call_llm_stream("test prompt"))
    assert len(pieces) == 1
    assert "Error" in pieces[0]
    assert "500" in pieces[0]


def test_identify_fossil_stream_reuses_same_prompt_as_non_streaming(monkeypatch):
    expert = FossilExpert()
    seen_prompts = []

    def fake_stream(self, prompt, temperature=0.7):
        seen_prompts.append(prompt)
        yield "chunk"

    def fake_call(self, prompt, temperature=0.7):
        seen_prompts.append(prompt)
        return "full"

    monkeypatch.setattr(FossilExpert, "_call_llm_stream", fake_stream)
    monkeypatch.setattr(FossilExpert, "_call_llm", fake_call)

    list(expert.identify_fossil_stream("黑色石頭有波浪紋"))
    expert.identify_fossil("黑色石頭有波浪紋")

    assert seen_prompts[0] == seen_prompts[1]
