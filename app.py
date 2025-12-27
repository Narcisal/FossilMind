import json
import os
import uuid
import time
import graphviz
from flask import Flask, render_template, request, jsonify
from backend import FossilExpert, API_URL

app = Flask(__name__)
app.secret_key = os.urandom(24)

# 🔑 API KEY
MY_API_KEY = "3dfdd1df4ee04ed8bfc6ba4a68e3577ce2ce2f29690620ae800886061755cafc"
expert = FossilExpert(MY_API_KEY, API_URL, "gpt-oss:20b")

# 設定資料庫檔案
DB_FILE = "chats.json"

def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_last_ai_context(messages):
    """從歷史訊息中抓取 AI 最後一次的鑑定內容作為 Context"""
    for msg in reversed(messages):
        if msg["role"] == "assistant" and len(msg["content"]) > 20:
            return msg["content"]
    return ""

# ==========================================
# 🌐 路由 (Routes)
# ==========================================

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/chat")
def chat_page():
    return render_template("chat.html")

# 👇 修正重點：地圖路由要放在這裡 (app.run 之前)
@app.route("/map")
def map_page():
    return render_template("map.html")

# ==========================================
# 💬 API: 聊天記錄管理
# ==========================================

@app.route("/api/chats", methods=["GET"])
def get_chats():
    db = load_db()
    chat_list = []
    for chat_id, chat_data in db.items():
        chat_list.append({
            "id": chat_id,
            "title": chat_data.get("title", "未命名對話"),
            "timestamp": chat_data.get("timestamp", 0)
        })
    chat_list.sort(key=lambda x: x["timestamp"], reverse=True)
    return jsonify(chat_list)

@app.route("/api/chats", methods=["POST"])
def create_chat():
    db = load_db()
    new_id = str(uuid.uuid4())
    db[new_id] = {
        "title": "新對話",
        "timestamp": time.time(),
        "messages": []
    }
    save_db(db)
    return jsonify({"id": new_id, "title": "新對話"})

@app.route("/api/chats/<chat_id>", methods=["DELETE"])
def delete_chat(chat_id):
    db = load_db()
    if chat_id in db:
        del db[chat_id]
        save_db(db)
        return jsonify({"success": True})
    return jsonify({"error": "Chat not found"}), 404

@app.route("/api/chats/<chat_id>/messages", methods=["GET"])
def get_messages(chat_id):
    db = load_db()
    if chat_id in db:
        return jsonify(db[chat_id]["messages"])
    return jsonify([]), 404

# ==========================================
# 🧠 API: 核心 AI 邏輯
# ==========================================

# 1. 對話鑑定 API
@app.route("/chat_api", methods=["POST"])
def chat_api():
    data = request.json
    user_input = data.get("message")
    chat_id = data.get("chat_id")

    if not user_input or not chat_id:
        return jsonify({"error": "No input or chat_id"}), 400

    db = load_db()
    
    if chat_id not in db:
        db[chat_id] = {"title": "新對話", "timestamp": time.time(), "messages": []}

    if len(db[chat_id]["messages"]) == 0:
        db[chat_id]["title"] = user_input[:15] + "..."
    db[chat_id]["timestamp"] = time.time()

    # --- FSM Router ---
    intent = expert.determine_intent(user_input)
    print(f"User Intent: {intent}")

    ai_response_text = ""
    image_url = None

    if intent == "IRRELEVANT":
        ai_response_text = "🦖 術業有專攻，FossilMind 無法回答與化石無關的問題喔！"

    elif intent == "IDENTIFY":
        ai_response_text = expert.identify_fossil(user_input)

    elif intent == "GRAPH":
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
                    
                    image_url = f"/static/{filename}.png"
                    ai_response_text = "這是根據目前的鑑定結果，所繪製的親緣演化關係圖："
                else:
                    ai_response_text = "抱歉，生成演化圖時發生錯誤，無法解析資料結構。"
            except Exception as e:
                print(f"Graph Error: {e}")
                ai_response_text = "系統繪圖模組發生異常，請確認伺服器是否安裝 Graphviz。"
        else:
            ai_response_text = "請先讓我鑑定一個化石，我才知道要畫什麼演化圖喔！(無前文)"

    elif intent == "EXPLAIN":
        context = get_last_ai_context(db[chat_id]["messages"])
        if context:
            ai_response_text = expert.explain_reasoning(context, user_input)
        else:
            ai_response_text = "請先提供化石資訊或照片，我才能為您詳細解釋。"

    # --- 儲存與回傳 ---
    user_msg = {'role': 'user', 'content': user_input}
    
    final_content = ai_response_text
    if image_url:
        final_content += f'\n\n<div style="text-align:center;"><img src="{image_url}" alt="Evolution Graph" style="max-width:100%; border-radius:8px; margin-top:10px;"></div>'
    
    ai_msg = {'role': 'assistant', 'content': final_content}

    db[chat_id]["messages"].append(user_msg)
    db[chat_id]["messages"].append(ai_msg)
    
    save_db(db)

    return jsonify({
        "response": ai_response_text,
        "image_url": image_url,
        "new_title": db[chat_id]["title"]
    })

# 2. 挖掘 API Part 1: AI #1 埋藏者 (Timekeeper)
@app.route("/api/bury", methods=["POST"])
def api_bury():
    data = request.json
    lat = data.get("lat")
    lng = data.get("lng")
    era = data.get("era")
    
    try:
        # AI #1 思考中...
        raw_data = expert.bury_fossil(lat, lng, era)
        clean_json = raw_data.replace("```json", "").replace("```", "").strip()
        fossil_info = json.loads(clean_json)
        return jsonify({"success": True, "fossil": fossil_info})
    except Exception as e:
        print(f"Bury Error: {e}")
        return jsonify({"success": False, "error": str(e)})

# 3. 挖掘 API Part 2: AI #2 鑑定師 (Paleontologist)
@app.route("/api/examine", methods=["POST"])
def api_examine():
    data = request.json
    fossil_info = data.get("fossil_info") # 接收 Part 1 的結果
    
    try:
        # AI #2 思考中...
        explanation = expert.dig_fossil(str(fossil_info))
        
        # 👇 新增這行：暴力清除 Markdown 標記
        clean_explanation = explanation.replace("```html", "").replace("```", "").strip()
        
        return jsonify({"success": True, "explanation": clean_explanation})
    except Exception as e:
        return jsonify({"success": False, "explanation": "通訊錯誤，無法生成詳細報告。"})

# ==========================================
# 🚀 啟動伺服器 (這個必須永遠在最後面)
# ==========================================
if __name__ == "__main__":
    if not os.path.exists('static'):
        os.makedirs('static')
    print("🦕 FossilMind 伺服器啟動中...")
    print("🌍 地圖功能已就緒: http://127.0.0.1:5000/map")
    app.run(debug=True, port=5000)