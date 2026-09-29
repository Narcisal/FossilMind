"""首頁設定視窗的後端：/api/llm_config、/api/llm_setup，以及還沒設定時各頁面與 API 的行為。"""
import json

import pytest

import app as app_module
import config
import database
import llm_settings


@pytest.fixture
def unconfigured(monkeypatch):
    """模擬 .env 沒設金鑰、也還沒在首頁設定過的伺服器。"""
    app_module.app.config["TESTING"] = True
    monkeypatch.setattr(app_module.limiter, "enabled", False)
    monkeypatch.setattr(app_module, "expert", None)
    return app_module.app.test_client()


class _FakeExpert:
    """記錄建立時用的參數；_call_llm 的回覆可以用 reply 控制。"""
    created = []
    reply = "OK"

    def __init__(self, api_key=None, api_url=None, model_name=None, api_format=None):
        self.settings = {"api_key": api_key, "api_url": api_url, "model_name": model_name, "api_format": api_format}
        _FakeExpert.created.append(self.settings)

    def _call_llm(self, prompt, temperature=0.7):
        return _FakeExpert.reply

    def determine_intent(self, text):
        return "IRRELEVANT"


@pytest.fixture
def fake_expert(monkeypatch):
    _FakeExpert.created = []
    _FakeExpert.reply = "OK"
    monkeypatch.setattr(app_module, "FossilExpert", _FakeExpert)
    return _FakeExpert


def _settings_on_disk():
    with open(config.SETTINGS_FILE, encoding="utf-8") as f:
        return json.load(f)


# --- 還沒設定時 ---

def test_config_reports_unconfigured_and_lists_providers_without_urls(unconfigured):
    cfg = unconfigured.get("/api/llm_config").get_json()

    assert cfg["configured"] is False
    assert {p["id"] for p in cfg["providers"]} == set(app_module.PROVIDERS)
    # 前端只需要名稱與預設模型，網址不外流
    assert all(set(p) == {"id", "label", "default_model"} for p in cfg["providers"])


@pytest.mark.parametrize("page", ["/chat", "/map"])
def test_pages_redirect_home_until_configured(unconfigured, page):
    res = unconfigured.get(page)

    assert res.status_code == 302
    assert res.headers["Location"].endswith("/")


def test_home_page_is_available_while_unconfigured(unconfigured):
    assert unconfigured.get("/").status_code == 200


def test_chat_api_refuses_until_configured(unconfigured):
    res = unconfigured.post("/chat_api_stream", json={"message": "三葉蟲", "chat_id": "u1"})

    assert res.status_code == 400
    assert "首頁" in res.get_json()["error"]
    assert database.get_messages("u1") == []


def test_map_apis_refuse_until_configured(unconfigured):
    bury = unconfigured.post("/api/bury", json={"lat": 1, "lng": 2, "era": "中生代"}).get_json()
    examine = unconfigured.post("/api/examine", json={"fossil_info": {"found": False}}).get_json()

    assert not bury["success"] and "首頁" in bury["error"]
    assert not examine["success"] and "首頁" in examine["explanation"]


# --- 設定流程 ---

def test_setup_verifies_then_saves_and_everything_starts_working(unconfigured, fake_expert):
    res = unconfigured.post("/api/llm_setup", json={"provider": "gemini", "api_key": "sk-user"})

    assert res.status_code == 200
    assert _settings_on_disk() == {"provider": "gemini", "api_key": "sk-user",
                                   "model": app_module.PROVIDERS["gemini"]["default_model"]}
    # 先用候選設定驗證一次，存好後 get_expert() 再依設定檔建立一次
    assert fake_expert.created[0] == {
        "api_key": "sk-user",
        "api_url": app_module.PROVIDERS["gemini"]["url"],
        "model_name": app_module.PROVIDERS["gemini"]["default_model"],
        "api_format": "openai",
    }
    assert unconfigured.get("/api/llm_config").get_json()["configured"] is True
    assert unconfigured.get("/chat").status_code == 200


def test_setup_accepts_custom_model(unconfigured, fake_expert):
    unconfigured.post("/api/llm_setup", json={"provider": "openai", "api_key": "sk-user", "model": "gpt-custom-1"})

    assert _settings_on_disk()["model"] == "gpt-custom-1"


def test_setup_rejects_key_that_fails_verification(unconfigured, fake_expert):
    """驗證失敗就不存：存了壞掉的設定，使用者又不能在網頁上改，就只能重新 build。"""
    fake_expert.reply = "Error: 401 - API 金鑰無效，或沒有使用這個模型的權限。"

    res = unconfigured.post("/api/llm_setup", json={"provider": "openai", "api_key": "sk-wrong"})

    assert res.status_code == 400
    assert "401" in res.get_json()["error"]
    assert llm_settings.load() is None
    assert unconfigured.get("/api/llm_config").get_json()["configured"] is False


@pytest.mark.parametrize("payload", [
    {"provider": "http://169.254.169.254/", "api_key": "sk-user"},   # 不能自己指定網址
    {"provider": "gemini", "api_key": "   "},                          # 沒填金鑰
    {"provider": "gemini", "api_key": "sk-user", "model": "bad model?x=1"},
])
def test_setup_rejects_invalid_input_without_calling_llm(unconfigured, fake_expert, payload):
    res = unconfigured.post("/api/llm_setup", json=payload)

    assert res.status_code == 400
    assert fake_expert.created == []
    assert llm_settings.load() is None


def test_setup_cannot_be_overwritten_from_the_web(unconfigured, fake_expert):
    """設定只能建立一次；要改只能重新 build 並啟動專案。"""
    unconfigured.post("/api/llm_setup", json={"provider": "gemini", "api_key": "sk-first"})

    res = unconfigured.post("/api/llm_setup", json={"provider": "openai", "api_key": "sk-attacker"})

    assert res.status_code == 409
    assert "重新 build" in res.get_json()["error"]
    assert _settings_on_disk()["api_key"] == "sk-first"


def test_setup_refused_when_env_key_is_configured(monkeypatch):
    """.env 已經設了金鑰（conftest 預設的狀態），網頁上就不能再設定。"""
    app_module.app.config["TESTING"] = True
    monkeypatch.setattr(app_module.limiter, "enabled", False)
    client = app_module.app.test_client()

    assert client.get("/api/llm_config").get_json()["configured"] is True
    res = client.post("/api/llm_setup", json={"provider": "gemini", "api_key": "sk-user"})
    assert res.status_code == 409


def test_other_workers_pick_up_settings_saved_by_another_worker(unconfigured, fake_expert):
    """gunicorn 有多個 worker；在其中一個存的設定，其他 worker 要從設定檔讀得到。"""
    llm_settings.save("openai", "sk-from-other-worker", "gpt-6-luna")

    assert unconfigured.get("/api/llm_config").get_json()["configured"] is True
    assert fake_expert.created[-1]["api_key"] == "sk-from-other-worker"


# --- 設定檔本身 ---

def test_save_refuses_to_overwrite_existing_file():
    llm_settings.save("gemini", "sk-first", "m1")

    with pytest.raises(FileExistsError):
        llm_settings.save("openai", "sk-second", "m2")
    assert llm_settings.load()["api_key"] == "sk-first"


def test_load_ignores_corrupt_or_unknown_settings(isolated_db):
    path = isolated_db / "llm_settings.json"

    path.write_text("{not json", encoding="utf-8")
    assert llm_settings.load() is None

    path.write_text(json.dumps({"provider": "not-a-provider", "api_key": "k", "model": "m"}), encoding="utf-8")
    assert llm_settings.load() is None


def test_setup_key_never_written_to_chat_database(unconfigured, fake_expert, isolated_db):
    unconfigured.post("/api/llm_setup", json={"provider": "gemini", "api_key": "sk-super-secret-value"})
    unconfigured.post("/chat_api_stream", json={"message": "哈囉", "chat_id": "u2"}).get_data()

    assert database.get_messages("u2")
    for f in isolated_db.glob("test.db*"):
        assert b"sk-super-secret-value" not in f.read_bytes()
