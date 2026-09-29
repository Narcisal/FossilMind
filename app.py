import os
import re
import uuid
import json
import graphviz
from flask import Flask, render_template, request, jsonify, Response, stream_with_context, abort, redirect, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config import SECRET_KEY, API_KEY, PROVIDERS, DEFAULT_PROVIDER
from backend import FossilExpert
import database
import llm_settings
from utils import get_wiki_image, extract_keyword, clean_ai_response

app = Flask(__name__)
app.secret_key = SECRET_KEY

# 每個 LLM 呼叫都有成本，限制單一來源的呼叫頻率，避免額度被打爆
limiter = Limiter(get_remote_address, app=app, default_limits=["60 per hour"])

# AI 服務：.env 有設金鑰就直接用；沒有的話，等使用者在首頁的設定視窗填好（存在 llm_settings.json）
expert = FossilExpert() if API_KEY else None
database.init_db()

NOT_CONFIGURED_MESSAGE = "尚未完成 AI 服務設定，請回到首頁完成設定。"
ALREADY_CONFIGURED_MESSAGE = "AI 服務已經設定過了。如需更改，請重新 build 並啟動專案。"
MODEL_NAME_PATTERN = re.compile(r"[A-Za-z0-9._:/-]{1,100}")


def is_llm_error(text):
    """backend 呼叫 AI 失敗時，回傳的文字一律以 "Error:" 或 "Connection Error:" 開頭。"""
    return text.startswith(("Error:", "Connection Error:"))


def get_expert():
    """
    回傳目前的 AI 服務；還沒設定就回傳 None。
    設定一旦建立就不會再改變（要改只能重新 build 並啟動），所以讀到之後就快取起來。
    每個 gunicorn worker 各自從設定檔讀，其中一個 worker 存好設定後，其他 worker 下次請求就讀得到。
    """
    global expert
    if expert is None:
        settings = llm_settings.load()
        if settings:
            provider = PROVIDERS[settings["provider"]]
            expert = FossilExpert(api_key=settings["api_key"], api_url=provider["url"],
                                  model_name=settings["model"], api_format=provider["format"])
    return expert


# 頁面路由
@app.route("/")
def index(): return render_template("index.html")

# 還沒設定 AI 服務就先回首頁，首頁會跳出設定視窗
@app.route("/chat")
def chat_page():
    if get_expert() is None:
        return redirect(url_for("index"))
    return render_template("chat.html")

@app.route("/map")
def map_page():
    if get_expert() is None:
        return redirect(url_for("index"))
    return render_template("map.html")

@app.route("/api/llm_config")
@limiter.exempt
def llm_config():
    """給首頁的設定視窗用：是否已經設定好、可以選哪些服務。不會回傳金鑰。"""
    return jsonify({
        "configured": get_expert() is not None,
        "default_provider": DEFAULT_PROVIDER,
        "providers": [
            {"id": pid, "label": p["label"], "default_model": p["default_model"]}
            for pid, p in PROVIDERS.items()
        ],
    })

@app.route("/api/llm_setup", methods=["POST"])
@limiter.limit("5 per minute")
def llm_setup():
    """
    首頁設定視窗送出的設定。只能設定一次：已經設定過就拒絕，不能從網頁覆蓋，
    要改只能重新 build 並啟動專案。存之前會先用這組設定實際呼叫一次 AI，
    確認金鑰與模型真的能用，避免存了一組壞掉的設定、卻又無法在網頁上修改。
    """
    if get_expert() is not None:
        return jsonify({"error": ALREADY_CONFIGURED_MESSAGE}), 409

    data = request.json or {}
    provider_id = data.get("provider")
    api_key = (data.get("api_key") or "").strip()
    provider = PROVIDERS.get(provider_id)
    if provider is None:
        return jsonify({"error": "請選擇清單裡的服務。"}), 400
    if not api_key:
        return jsonify({"error": "請填入 API 金鑰。"}), 400
    model = (data.get("model") or "").strip() or provider["default_model"]
    if not MODEL_NAME_PATTERN.fullmatch(model):
        return jsonify({"error": "模型名稱只能包含英數字與 . _ : / - 符號。"}), 400

    candidate = FossilExpert(api_key=api_key, api_url=provider["url"], model_name=model, api_format=provider["format"])
    reply = candidate._call_llm("Reply with the single word OK.", temperature=0.0)
    if is_llm_error(reply):
        return jsonify({"error": f"無法使用這組設定：{reply}"}), 400

    try:
        llm_settings.save(provider_id, api_key, model)
    except FileExistsError:
        return jsonify({"error": ALREADY_CONFIGURED_MESSAGE}), 409
    get_expert()
    return jsonify({"ok": True})

@app.route("/graph/<graph_id>.png")
@limiter.exempt  # 跟 static/ 的圖片一樣不計入限流，限流只是為了保護 LLM 額度
def graph_image(graph_id):
    png = database.get_graph(graph_id)
    if png is None:
        abort(404)
    # 每張圖的 id 都是唯一的、內容不會再變，可以讓瀏覽器長期快取
    return Response(png, mimetype="image/png", headers={"Cache-Control": "public, max-age=31536000, immutable"})

IRRELEVANT_REPLY = "🦖 術業有專攻，FossilMind 無法回答與化石無關的問題喔！"


# 共用工具函式
def render_evolution_graph(dot_code):
    """
    把 DOT 程式碼渲染成 PNG 存進資料庫，回傳圖片網址；不是合法的 digraph 就回傳 None。
    圖片跟對話紀錄放在同一個資料庫，不會在 static/ 底下無限累積檔案，
    容器重建後（資料庫有掛 volume 的話）舊對話裡的圖也不會變成破圖。
    """
    if not dot_code or "digraph" not in dot_code:
        return None
    png = graphviz.Source(dot_code).pipe(format='png')
    graph_id = uuid.uuid4().hex
    database.save_graph(graph_id, png)
    return f"/graph/{graph_id}.png"


def build_identify_response(request_expert, raw_response, user_input):
    """把鑑定的原始回覆組裝成最終版本：標題 + Wiki 圖片 + 內文 + 演化圖。"""
    keyword = extract_keyword(raw_response)
    clean_text = clean_ai_response(raw_response)

    # 圖片很容易找不到，找不到就不放
    search_key = keyword if keyword else user_input
    found_img = get_wiki_image(search_key)

    graph_markdown = ""
    if keyword:
        try:
            dot_code = request_expert.generate_evolution_graph(f"Generate phylogeny tree for {keyword}")
            graph_url = render_evolution_graph(dot_code)
            if graph_url:
                graph_markdown = f"\n\n### 🧬 親緣演化關係\n![演化圖]({graph_url})"
        except Exception as e:
            print(f"Auto-Graph Error: {e}")

    split_text = clean_text.split('\n', 1)  # 切割第一行標題
    img_markdown = f"\n\n![Wiki Image]({found_img})" if found_img else ""
    if len(split_text) > 1:
        # 有標題 -> 標題 + 圖片 + 剩餘內文 + 演化圖
        return f"{split_text[0]}{img_markdown}\n\n{split_text[1]}{graph_markdown}"
    # 沒標題 -> 圖片 + 全文 + 演化圖
    return f"{img_markdown}\n\n{clean_text}{graph_markdown}"


def build_graph_response(request_expert, context):
    """使用者主動要求畫演化圖，回傳 (文字, 圖片網址)。"""
    if not context:
        return "請先讓我鑑定一個化石，我才知道要畫什麼演化圖喔！", None
    try:
        graph_url = render_evolution_graph(request_expert.generate_evolution_graph(context))
    except Exception as e:
        print(f"Graph Error: {e}")
        return "系統繪圖模組發生異常 (Graphviz)。", None
    if not graph_url:
        return "抱歉，生成演化圖時發生錯誤。", None
    return "這是根據目前的鑑定結果，所繪製的親緣演化關係圖：", graph_url


# 核心對話 API（streaming，避免回覆要等很久才出現文字）
@app.route("/chat_api_stream", methods=["POST"])
@limiter.limit("10 per minute")
def chat_api_stream():
    data = request.json
    user_input = data.get("message")
    chat_id = data.get("chat_id")

    if not user_input or not chat_id:
        return jsonify({"error": "No input"}), 400

    request_expert = get_expert()
    if request_expert is None:
        return jsonify({"error": NOT_CONFIGURED_MESSAGE}), 400

    def sse(event, payload):
        return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def generate():
        title = database.open_chat(chat_id, user_input)

        # 判斷意圖 (FSM)
        intent = request_expert.determine_intent(user_input)
        print(f"User Intent: {intent}")

        image_url = None
        final_text = ""

        try:
            if intent == "IRRELEVANT":
                final_text = IRRELEVANT_REPLY
                yield sse("chunk", {"text": final_text})

            elif intent == "IDENTIFY":
                raw_parts = []
                for piece in request_expert.identify_fossil_stream(user_input):
                    raw_parts.append(piece)
                    yield sse("chunk", {"text": piece})

                # 逐字串流階段只有原始文字（可能還帶著 [[Wiki: ...]] 標記），
                # 真正的圖片/演化圖要等文字生成完才查得到。這裡送出排版好的
                # 最終定稿版本，前端收到後會整段換掉剛剛逐字顯示的內容。
                raw_response = "".join(raw_parts)
                if is_llm_error(raw_response):
                    # AI 服務出錯（忙碌、額度用完等）：不去找圖、不畫演化圖，也不把這段錯誤
                    # 當成鑑定結果存起來，否則之後追問時會被拿去當背景
                    final_text = f"⚠️ {raw_response}"
                    intent = "ERROR"
                else:
                    final_text = build_identify_response(request_expert, raw_response, user_input)
                yield sse("final", {"text": final_text})

            elif intent == "GRAPH":
                context = database.get_last_identify_context(chat_id)
                final_text, image_url = build_graph_response(request_expert, context)
                yield sse("chunk", {"text": final_text})

            elif intent == "EXPLAIN":
                context = database.get_last_identify_context(chat_id)
                if context:
                    raw_parts = []
                    for piece in request_expert.explain_reasoning_stream(context, user_input):
                        raw_parts.append(piece)
                        yield sse("chunk", {"text": piece})
                    final_text = "".join(raw_parts)
                else:
                    final_text = "請先提供化石資訊，我才能為您詳細解釋。"
                    yield sse("chunk", {"text": final_text})
        except Exception as e:
            # 串流中途出錯也要讓前端知道，不能悶不吭聲斷線
            print(f"Stream Error: {e}")
            yield sse("chunk", {"text": f"\n\n⚠️ 發生錯誤：{str(e)}"})
            final_text = final_text or "（回覆中斷）"

        content_for_db = final_text + (f"\n\n![演化圖]({image_url})" if image_url else "")
        database.save_exchange(chat_id, user_input, content_for_db, intent)
        yield sse("done", {"image_url": image_url, "new_title": title})

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


# 地圖 API
@app.route("/api/bury", methods=["POST"])
@limiter.limit("10 per minute")
def api_bury():
    data = request.json
    try:
        request_expert = get_expert()
        if request_expert is None:
            return jsonify({"success": False, "error": NOT_CONFIGURED_MESSAGE})
        raw_data = request_expert.bury_fossil(data.get("lat"), data.get("lng"), data.get("era"))
        if is_llm_error(raw_data):
            # LLM 呼叫失敗（例如金鑰無效），直接把原因告訴使用者，不要變成看不懂的 JSON 解析錯誤
            return jsonify({"success": False, "error": raw_data})
        clean_json = raw_data.replace("```json", "").replace("```", "").strip()
        return jsonify({"success": True, "fossil": json.loads(clean_json)})
    except Exception as e:
        print(f"Bury Error: {e}") # 除錯用
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/examine", methods=["POST"])
@limiter.limit("10 per minute")
def api_examine():
    data = request.json
    try:
        request_expert = get_expert()
        if request_expert is None:
            return jsonify({"success": False, "explanation": NOT_CONFIGURED_MESSAGE})
        explanation = request_expert.dig_fossil(str(data.get("fossil_info")))
        if is_llm_error(explanation):
            # 不要把錯誤訊息當成鑑定報告寫進挖掘日誌
            return jsonify({"success": False, "explanation": explanation})
        return jsonify({"success": True, "explanation": explanation.replace("```html", "").replace("```", "").strip()})
    except Exception as e:
        print(f"Examine Error: {e}")
        return jsonify({"success": False, "explanation": "通訊錯誤"})

if __name__ == "__main__":
    if not os.path.exists('static'): os.makedirs('static')
    print("FossilMind 伺服器啟動中... (http://127.0.0.1:5000)")
    # debug 模式預設關閉，避免部署時不小心開著 Werkzeug 除錯主控台（有 RCE 風險）。
    # 本機開發需要時，在啟動前設 FLASK_DEBUG=true
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug_mode, port=5000)