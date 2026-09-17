import os
import time
import uuid
import json
import graphviz
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config import SECRET_KEY
from backend import FossilExpert
from database import load_db, save_db, get_last_ai_context
from utils import get_wiki_image, extract_keyword, clean_ai_response

app = Flask(__name__)
app.secret_key = SECRET_KEY

# 每個 LLM 呼叫都有成本，限制單一來源的呼叫頻率，避免額度被打爆
limiter = Limiter(get_remote_address, app=app, default_limits=["60 per hour"])

expert = FossilExpert()

# 頁面路由
@app.route("/")
def index(): return render_template("index.html")

@app.route("/chat")
def chat_page(): return render_template("chat.html")

@app.route("/map")
def map_page(): return render_template("map.html")

# 核心對話 API
@app.route("/chat_api", methods=["POST"])
@limiter.limit("10 per minute")
def chat_api():
    data = request.json
    user_input = data.get("message")
    chat_id = data.get("chat_id")

    if not user_input or not chat_id: return jsonify({"error": "No input"}), 400

    # 1. 讀取/初始化資料庫
    db = load_db()
    if chat_id not in db:
        db[chat_id] = {"title": "新對話", "timestamp": time.time(), "messages": []}
    
    if len(db[chat_id]["messages"]) == 0:
        db[chat_id]["title"] = user_input[:15] + "..."
    db[chat_id]["timestamp"] = time.time()

    # 2. 判斷意圖
    intent = expert.determine_intent(user_input)
    print(f"User Intent: {intent}")

    ai_response_text = ""
    wiki_image_url = None # 圖片很容易找不到，預設 None

    # 3. 執行邏輯 (FSM)
    if intent == "IRRELEVANT":
        ai_response_text = "🦖 術業有專攻，FossilMind 無法回答與化石無關的問題喔！"

    elif intent == "IDENTIFY":
        # A. 鑑定化石
        raw_response = expert.identify_fossil(user_input)
        
        # B. 準備素材：關鍵字、乾淨文字、Wiki圖片
        keyword = extract_keyword(raw_response)
        clean_text = clean_ai_response(raw_response)
        
        # 搜尋圖片 
        search_key = keyword if keyword else user_input
        print(f"Searching Wiki for: {search_key}")
        
        found_img = get_wiki_image(search_key)
        
        # C. 準備演化圖 
        graph_markdown = ""
        if keyword:
            try:
                print("Auto-generating evolution graph...")
                dot_code = expert.generate_evolution_graph(f"Generate phylogeny tree for {keyword}")
                if dot_code and "digraph" in dot_code:
                    filename = f"evo_{uuid.uuid4().hex}"
                    filepath = os.path.join('static', filename)
                    src = graphviz.Source(dot_code)
                    src.format = 'png'
                    src.render(filepath, cleanup=True)
                    
                    graph_url = f"/static/{filename}.png"
                    graph_markdown = f"\n\n### 🧬 親緣演化關係\n![演化圖]({graph_url})"
            except Exception as e:
                print(f"Auto-Graph Error: {e}")

        # D. 組裝回答
        
        split_text = clean_text.split('\n', 1) # 切割第一行標題
        
        img_markdown = f"\n\n![Wiki Image]({found_img})" if found_img else ""
        
        if len(split_text) > 1:
            # 情況 1：有標題 -> 標題 + 圖片 + 剩餘內文 + 演化圖
            ai_response_text = f"{split_text[0]}{img_markdown}\n\n{split_text[1]}{graph_markdown}"
        else:
            # 情況 2：沒標題 -> 圖片 + 全文 + 演化圖
            ai_response_text = f"{img_markdown}\n\n{clean_text}{graph_markdown}"

    elif intent == "GRAPH":
        # 使用者主動要求畫圖
        context = get_last_ai_context(db[chat_id]["messages"])
        if context:
            try:
                dot_code = expert.generate_evolution_graph(context)
                if dot_code and "digraph" in dot_code:
                    filename = f"evo_{uuid.uuid4().hex}"
                    filepath = os.path.join('static', filename)
                    src = graphviz.Source(dot_code)
                    src.format = 'png'
                    src.render(filepath, cleanup=True)
                    
                    wiki_image_url = f"/static/{filename}.png" 
                    ai_response_text = "這是根據目前的鑑定結果，所繪製的親緣演化關係圖："
                else:
                    ai_response_text = "抱歉，生成演化圖時發生錯誤。"
            except Exception as e:
                ai_response_text = "系統繪圖模組發生異常 (Graphviz)。"
        else:
            ai_response_text = "請先讓我鑑定一個化石，我才知道要畫什麼演化圖喔！"

    elif intent == "EXPLAIN":
        context = get_last_ai_context(db[chat_id]["messages"])
        if context:
            ai_response_text = expert.explain_reasoning(context, user_input)
        else:
            ai_response_text = "請先提供化石資訊，我才能為您詳細解釋。"

    # 4. 儲存與回傳
    user_msg = {'role': 'user', 'content': user_input}
    
    # 存進資料庫
    final_content_for_db = ai_response_text
    if wiki_image_url:
        final_content_for_db += f'\n\n![Wiki Image]({wiki_image_url})' 

    ai_msg = {'role': 'assistant', 'content': final_content_for_db}

    db[chat_id]["messages"].append(user_msg)
    db[chat_id]["messages"].append(ai_msg)
    save_db(db)

    return jsonify({
        "response": ai_response_text,     # 包含演化圖 (Markdown)
        "image_url": wiki_image_url,      # 包含 Wiki 圖 (如果有的話)
        "new_title": db[chat_id]["title"]
    })


# 核心對話 API — streaming 版本，解決回覆要等很久才出現文字的問題。
# 保留上面原本的 /chat_api 不動，兩個 route 並存：前端預設用這個，
# 如果 streaming 有問題可以隨時切回非 streaming 版本。
@app.route("/chat_api_stream", methods=["POST"])
@limiter.limit("10 per minute")
def chat_api_stream():
    data = request.json
    user_input = data.get("message")
    chat_id = data.get("chat_id")
    # BYOK：使用者自己貼的金鑰，只在這一次請求裡用，絕對不 log、不存進 chats.json、
    # 不寫進任何檔案。沒有帶這個欄位就沿用伺服器自己的共用金鑰（本機開發情境）。
    user_api_key = (data.get("user_api_key") or "").strip()

    if not user_input or not chat_id:
        return jsonify({"error": "No input"}), 400

    request_expert = FossilExpert(api_key=user_api_key) if user_api_key else expert

    def sse(event, payload):
        return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def generate():
        db = load_db()
        if chat_id not in db:
            db[chat_id] = {"title": "新對話", "timestamp": time.time(), "messages": []}

        if len(db[chat_id]["messages"]) == 0:
            db[chat_id]["title"] = user_input[:15] + "..."
        db[chat_id]["timestamp"] = time.time()

        intent = request_expert.determine_intent(user_input)
        print(f"User Intent (stream): {intent}")

        wiki_image_url = None
        final_text = ""

        try:
            if intent == "IRRELEVANT":
                final_text = "🦖 術業有專攻，FossilMind 無法回答與化石無關的問題喔！"
                yield sse("chunk", {"text": final_text})

            elif intent == "IDENTIFY":
                raw_parts = []
                for piece in request_expert.identify_fossil_stream(user_input):
                    raw_parts.append(piece)
                    yield sse("chunk", {"text": piece})
                raw_response = "".join(raw_parts)

                keyword = extract_keyword(raw_response)
                clean_text = clean_ai_response(raw_response)
                search_key = keyword if keyword else user_input
                found_img = get_wiki_image(search_key)

                graph_markdown = ""
                if keyword:
                    try:
                        dot_code = request_expert.generate_evolution_graph(f"Generate phylogeny tree for {keyword}")
                        if dot_code and "digraph" in dot_code:
                            filename = f"evo_{uuid.uuid4().hex}"
                            filepath = os.path.join('static', filename)
                            src = graphviz.Source(dot_code)
                            src.format = 'png'
                            src.render(filepath, cleanup=True)
                            graph_url = f"/static/{filename}.png"
                            graph_markdown = f"\n\n### 🧬 親緣演化關係\n![演化圖]({graph_url})"
                    except Exception as e:
                        print(f"Auto-Graph Error: {e}")

                split_text = clean_text.split('\n', 1)
                img_markdown = f"\n\n![Wiki Image]({found_img})" if found_img else ""
                if len(split_text) > 1:
                    final_text = f"{split_text[0]}{img_markdown}\n\n{split_text[1]}{graph_markdown}"
                else:
                    final_text = f"{img_markdown}\n\n{clean_text}{graph_markdown}"

                # 逐字串流階段只有原始文字（可能還帶著 [[Wiki: ...]] 標記），
                # 真正的圖片/演化圖要等文字生成完才查得到。這裡送出排版好的
                # 最終定稿版本，前端收到後會整段換掉剛剛逐字顯示的內容。
                yield sse("final", {"text": final_text})

            elif intent == "GRAPH":
                context = get_last_ai_context(db[chat_id]["messages"])
                if context:
                    try:
                        dot_code = request_expert.generate_evolution_graph(context)
                        if dot_code and "digraph" in dot_code:
                            filename = f"evo_{uuid.uuid4().hex}"
                            filepath = os.path.join('static', filename)
                            src = graphviz.Source(dot_code)
                            src.format = 'png'
                            src.render(filepath, cleanup=True)
                            wiki_image_url = f"/static/{filename}.png"
                            final_text = "這是根據目前的鑑定結果，所繪製的親緣演化關係圖："
                        else:
                            final_text = "抱歉，生成演化圖時發生錯誤。"
                    except Exception:
                        final_text = "系統繪圖模組發生異常 (Graphviz)。"
                else:
                    final_text = "請先讓我鑑定一個化石，我才知道要畫什麼演化圖喔！"
                yield sse("chunk", {"text": final_text})

            elif intent == "EXPLAIN":
                context = get_last_ai_context(db[chat_id]["messages"])
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

        # 存進資料庫（跟 /chat_api 的存檔邏輯一致）
        user_msg = {'role': 'user', 'content': user_input}
        final_content_for_db = final_text
        if wiki_image_url:
            final_content_for_db += f'\n\n![Wiki Image]({wiki_image_url})'
        ai_msg = {'role': 'assistant', 'content': final_content_for_db}

        db[chat_id]["messages"].append(user_msg)
        db[chat_id]["messages"].append(ai_msg)
        save_db(db)

        yield sse("done", {"image_url": wiki_image_url, "new_title": db[chat_id]["title"]})

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


# 地圖 API
@app.route("/api/bury", methods=["POST"])
@limiter.limit("10 per minute")
def api_bury():
    data = request.json
    try:
        raw_data = expert.bury_fossil(data.get("lat"), data.get("lng"), data.get("era"))
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
        explanation = expert.dig_fossil(str(data.get("fossil_info")))
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