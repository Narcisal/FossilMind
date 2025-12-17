import json
import os
import uuid
from flask import Flask, render_template, request, jsonify
from backend import FossilExpert, API_URL

app = Flask(__name__)
app.secret_key = os.urandom(24)

# 🔑 API KEY
MY_API_KEY = "3dfdd1df4ee04ed8bfc6ba4a68e3577ce2ce2f29690620ae800886061755cafc"
expert = FossilExpert(MY_API_KEY, API_URL, "gpt-oss:20b")

# 設定資料庫檔案 (用一個 JSON 檔來存所有對話)
DB_FILE = "chats.json"

def load_db():
    """讀取所有聊天紀錄"""
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_db(data):
    """儲存所有聊天紀錄"""
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# --- 路由 ---

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/chat")
def chat_page():
    return render_template("chat.html")

# --- API: 取得聊天列表 ---
@app.route("/api/chats", methods=["GET"])
def get_chats():
    db = load_db()
    # 轉換成列表格式回傳：[{id: "...", title: "...", timestamp: ...}]
    chat_list = []
    for chat_id, chat_data in db.items():
        chat_list.append({
            "id": chat_id,
            "title": chat_data.get("title", "未命名對話"),
            "timestamp": chat_data.get("timestamp", 0)
        })
    # 根據時間排序 (新的在上面)
    chat_list.sort(key=lambda x: x["timestamp"], reverse=True)
    return jsonify(chat_list)

# --- API: 建立新聊天 ---
@app.route("/api/chats", methods=["POST"])
def create_chat():
    db = load_db()
    new_id = str(uuid.uuid4())
    import time
    
    # 預設的新聊天結構
    db[new_id] = {
        "title": "新對話",
        "timestamp": time.time(),
        "messages": [] # 空的訊息列表
    }
    save_db(db)
    return jsonify({"id": new_id, "title": "新對話"})

# --- API: 刪除聊天 ---
@app.route("/api/chats/<chat_id>", methods=["DELETE"])
def delete_chat(chat_id):
    db = load_db()
    if chat_id in db:
        del db[chat_id]
        save_db(db)
        return jsonify({"success": True})
    return jsonify({"error": "Chat not found"}), 404

# --- API: 取得特定聊天的訊息 ---
@app.route("/api/chats/<chat_id>/messages", methods=["GET"])
def get_messages(chat_id):
    db = load_db()
    if chat_id in db:
        return jsonify(db[chat_id]["messages"])
    return jsonify([]), 404 # 如果找不到，就回傳空陣列

# --- API: 傳送訊息並存檔 ---
@app.route("/chat_api", methods=["POST"])
def chat_api():
    data = request.json
    user_input = data.get("message")
    chat_id = data.get("chat_id") # 前端必須傳 chat_id 過來

    if not user_input or not chat_id:
        return jsonify({"error": "No input or chat_id"}), 400

    db = load_db()
    
    # 如果這個 chat_id 不存在，先建立它 (防呆)
    if chat_id not in db:
        import time
        db[chat_id] = {"title": "新對話", "timestamp": time.time(), "messages": []}

    # 1. 更新對話標題 (如果是該對話的第一則訊息)
    if len(db[chat_id]["messages"]) == 0:
        # 取前 10 個字當標題
        db[chat_id]["title"] = user_input[:15] + "..."
    
    # 更新時間戳記
    import time
    db[chat_id]["timestamp"] = time.time()

    # 2. 呼叫後端鑑定
    ai_response_text = expert.identify_fossil(user_input)
    
    # 3. 嘗試畫圖 (強制嘗試)
    image_url = None
    if True:
        try:
            dot_code = expert.generate_evolution_graph(ai_response_text)
            if dot_code and "digraph" in dot_code:
                import graphviz
                filename = f"evo_{uuid.uuid4().hex}"
                filepath = os.path.join('static', filename)
                src = graphviz.Source(dot_code)
                src.format = 'png'
                src.render(filepath, cleanup=True)
                image_url = f"/static/{filename}.png"
        except Exception as e:
            print(f"畫圖失敗: {e}")

    # 4. 儲存訊息到 JSON
    user_msg = {'role': 'user', 'content': user_input}
    
    final_content = ai_response_text
    if image_url:
        final_content += f'\n\n<img src="{image_url}" alt="Evolution Graph">'
    
    ai_msg = {'role': 'assistant', 'content': final_content}

    db[chat_id]["messages"].append(user_msg)
    db[chat_id]["messages"].append(ai_msg)
    
    save_db(db)

    return jsonify({
        "response": ai_response_text,
        "image_url": image_url,
        "new_title": db[chat_id]["title"] # 回傳新標題讓前端更新
    })

if __name__ == "__main__":
    if not os.path.exists('static'):
        os.makedirs('static')
    app.run(debug=True, port=5000)