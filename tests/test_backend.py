import backend
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


class FakeJsonResponse:
    def __init__(self, status_code, body, text=""):
        self.status_code = status_code
        self._body = body
        self.text = text

    def json(self):
        return self._body


def test_call_llm_parses_openai_format(monkeypatch):
    expert = FossilExpert(api_key="k", api_url="https://example.invalid", model_name="m", api_format="openai")
    monkeypatch.setattr(
        "backend.requests.post",
        lambda *a, **k: FakeJsonResponse(200, {"choices": [{"message": {"content": "這是菊石"}}]}),
    )
    assert expert._call_llm("prompt") == "這是菊石"


def test_call_llm_stream_parses_openai_sse(monkeypatch):
    expert = FossilExpert(api_key="k", api_url="https://example.invalid", model_name="m", api_format="openai")
    lines = [
        ": keep-alive comment",
        'data: {"choices": [{"delta": {"role": "assistant"}}]}',
        'data: {"choices": [{"delta": {"content": "菊"}}]}',
        "",
        'data: {"choices": [{"delta": {"content": "石"}}]}',
        'data: {"choices": []}',
        "data: [DONE]",
        'data: {"choices": [{"delta": {"content": "不該出現"}}]}',
    ]
    monkeypatch.setattr("backend.requests.post", lambda *a, **k: FakeStreamResponse(200, lines))

    assert list(expert._call_llm_stream("prompt")) == ["菊", "石"]


def test_request_sends_model_key_and_stream_flag(monkeypatch):
    expert = FossilExpert(api_key="sk-user", api_url="https://example.invalid/v1/chat/completions",
                          model_name="gemini-x", api_format="openai")
    sent = {}

    def fake_post(url, headers, json, timeout, stream):
        sent.update(url=url, auth=headers["Authorization"], model=json["model"], stream=json["stream"])
        return FakeJsonResponse(200, {"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr("backend.requests.post", fake_post)
    expert._call_llm("prompt")

    assert sent == {"url": "https://example.invalid/v1/chat/completions", "auth": "Bearer sk-user",
                    "model": "gemini-x", "stream": False}


def test_auth_error_does_not_echo_provider_response(monkeypatch):
    """有些服務商會在 401 的錯誤訊息裡帶出部分金鑰，這段文字不能顯示給使用者或存進資料庫。"""
    expert = FossilExpert(api_key="sk-secret", api_url="https://example.invalid", model_name="m", api_format="openai")
    monkeypatch.setattr(
        "backend.requests.post",
        lambda *a, **k: FakeJsonResponse(401, {}, text="Incorrect API key provided: sk-sec****ret"),
    )

    result = expert._call_llm("prompt")

    assert result.startswith("Error: 401")
    assert "sk-sec" not in result


# 這是使用者實際遇到的 Gemini 回應：模型忙碌時回傳 503，內容是一個 JSON 陣列
GEMINI_OVERLOADED_BODY = [{"error": {"code": 503, "status": "UNAVAILABLE",
                                     "message": "This model is currently experiencing high demand. "
                                                "Spikes in demand are usually temporary. Please try again later."}}]


def _sequence_post(responses, calls):
    def fake_post(*args, **kwargs):
        calls.append(kwargs.get("stream"))
        return responses[min(len(calls), len(responses)) - 1]
    return fake_post


def test_call_llm_retries_temporary_errors_then_succeeds(monkeypatch):
    expert = FossilExpert(api_key="k", api_url="https://example.invalid", model_name="m", api_format="openai")
    calls = []
    monkeypatch.setattr("backend.requests.post", _sequence_post([
        FakeJsonResponse(503, GEMINI_OVERLOADED_BODY),
        FakeJsonResponse(429, {}),
        FakeJsonResponse(200, {"choices": [{"message": {"content": "這是菊石"}}]}),
    ], calls))

    assert expert._call_llm("prompt") == "這是菊石"
    assert len(calls) == 3


def test_call_llm_gives_up_with_friendly_message_after_retries(monkeypatch):
    expert = FossilExpert(api_key="k", api_url="https://example.invalid", model_name="m", api_format="openai")
    calls = []
    monkeypatch.setattr("backend.requests.post", _sequence_post([FakeJsonResponse(503, GEMINI_OVERLOADED_BODY)], calls))

    result = expert._call_llm("prompt")

    assert len(calls) == 1 + backend.MAX_RETRIES
    assert result.startswith("Error: 503")
    assert "請稍後再試" in result
    assert "UNAVAILABLE" not in result  # 不直接把服務商的原始 JSON 丟給使用者


def test_stream_retries_temporary_errors_before_streaming(monkeypatch):
    expert = FossilExpert(api_key="k", api_url="https://example.invalid", model_name="m", api_format="openai")
    calls = []
    monkeypatch.setattr("backend.requests.post", _sequence_post([
        FakeStreamResponse(503, []),
        FakeStreamResponse(200, ['data: {"choices": [{"delta": {"content": "菊石"}}]}', "data: [DONE]"]),
    ], calls))

    assert list(expert._call_llm_stream("prompt")) == ["菊石"]
    assert calls == [True, True]


def test_client_errors_are_not_retried_and_show_provider_message(monkeypatch):
    """模型名稱打錯這類錯誤重試也沒用，直接回報服務商說的原因。"""
    expert = FossilExpert(api_key="k", api_url="https://example.invalid", model_name="m", api_format="openai")
    calls = []
    monkeypatch.setattr("backend.requests.post", _sequence_post([
        FakeJsonResponse(404, {"error": {"message": "models/gemini-typo is not found"}}),
    ], calls))

    result = expert._call_llm("prompt")

    assert len(calls) == 1
    assert result == "Error: 404 - models/gemini-typo is not found"


def test_retry_delay_honours_short_retry_after_header():
    class R:
        headers = {"Retry-After": "3"}

    class NoHeader:
        pass

    assert backend._retry_delay(R(), 0) == 3
    assert backend._retry_delay(NoHeader(), 0) == 2
    assert backend._retry_delay(NoHeader(), 1) == 4
