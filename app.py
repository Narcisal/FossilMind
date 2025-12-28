import json
import os
import uuid
import time
import re
import requests # 👈 新增這個來抓 Wiki 圖片
import graphviz
from flask import Flask, render_template, request, jsonify
from backend import FossilExpert, API_URL

app = Flask(__name__)
app.secret_key = os.urandom(24)

# ==========================================
# 🔑 設定區
# ==========================================
MY_API_KEY = "3dfdd1df4ee04ed8bfc6ba4a68e3577ce2ce2f29690620ae800886061755cafc"
expert = FossilExpert(MY_API_KEY, API_URL, "gpt-oss:20b")

DB_FILE = "chats.json"

# ==========================================
# 🛠️ 輔助工具：Wiki 圖片抓取
# ==========================================
def get_wiki_image(query):
    """搜尋維基百科並回傳第一張圖片的 URL"""
    try:
        # 1. 搜尋頁面 ID
        search_url = "https://en.wikipedia.org/w/api.php"
        search_params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "format": "json",
            "origin": "*"
        }
        search_res = requests.get(search_url, params=search_params, timeout=3).json()
        
        if not search_res.get("query", {}).get("search"):
            return None # 沒找到
        
        title = search_res["query"]["search"][0]["title"]

        # 2. 抓取該頁面的圖片
        img_url = "https://en.wikipedia.org/w/api.php"
        img_params = {
            "action": "query",
            "titles": title,
            "prop": "pageimages",
            "format": "json",
            "pithumbsize": 500, # 圖片大小
            "origin": "*"
        }
        img_res = requests.get(img_url, params=img_params, timeout=3).json()
        
        pages = img_res.get("query", {}).get("pages", {})
        for page_id in pages:
            if "thumbnail" in pages[page_id]:
                return pages[page_id]["thumbnail"]["source"]
                
    except Exception as e:
        print(f"Wiki Image Error: {e}")
    
    return None

def extract_keyword(text):
    """從 AI 回答中嘗試抓取 **粗體** 的關鍵字 (通常是學名)"""
    match = re.search(r'\*\*(.*?)\*\*', text)
    if match:
        return match.group(1) # 回傳粗體內的字
    return None

# ==========================================
# 💾 資料庫函式
# ==========================================
def load_db():
    if not os.path.exists(DB_FILE): return {}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except: return {}

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_last_ai_context(messages):
    for msg in reversed(messages):
        if msg["role"] == "assistant" and len(msg["content"]) > 20:
            return msg["content"]
    return ""

# ==========================================
# 🌐 路由
# ==========================================
@app.route("/")
def index(): return render_template("index.html")

@app.route("/chat")
def chat_page(): return render_template("chat.html")

@app.route("/map")
def map_page(): return render_template("map.html")

# ==========================================
# 💬 API: 聊天與核心邏輯
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
    db[new_id] = {"title": "新對話", "timestamp": time.time(), "messages": []}
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
    if chat_id in db: return jsonify(db[chat_id]["messages"])
    return jsonify([]), 404

# --- 核心對話 API (包含圖片抓取邏輯) ---
@app.route("/chat_api", methods=["POST"])
def chat_api():
    data = request.json
    user_input = data.get("message")
    chat_id = data.get("chat_id")

    if not user_input or not chat_id: return jsonify({"error": "No input"}), 400

    db = load_db()
    if chat_id not in db:
        db[chat_id] = {"title": "新對話", "timestamp": time.time(), "messages": []}
    
    if len(db[chat_id]["messages"]) == 0:
        db[chat_id]["title"] = user_input[:15] + "..."
    db[chat_id]["timestamp"] = time.time()

    # 1. 判斷意圖
    intent = expert.determine_intent(user_input)
    print(f"User Intent: {intent}")

    ai_response_text = ""
    image_url = None # 這將存放 Wiki 圖片 或 演化圖

    # 2. 執行邏輯
    if intent == "IRRELEVANT":
        ai_response_text = "🦖 術業有專攻，FossilMind 無法回答與化石無關的問題喔！"

    elif intent == "IDENTIFY":
        # 鑑定化石
        ai_response_text = expert.identify_fossil(user_input)
        
        # 🔥 自動抓取 Wiki 圖片
        # 嘗試從回答中抓取粗體字 (例如: **Haliotis rubra**)
        keyword = extract_keyword(ai_response_text)
        if not keyword: 
            # 如果沒抓到粗體，就用使用者的輸入當關鍵字試試看
            keyword = user_input 
        
        print(f"Searching Wiki for: {keyword}")
        image_url = get_wiki_image(keyword)

    elif intent == "GRAPH":
        # 繪製演化圖
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
                    image_url = f"/static/{filename}.png" # ✅ 這裡產生的圖會傳回前端
                    ai_response_text = "這是根據目前的鑑定結果，所繪製的親緣演化關係圖："
                else:
                    ai_response_text = "抱歉，生成演化圖時發生錯誤，無法解析資料結構。"
            except Exception as e:
                print(f"Graph Error: {e}")
                ai_response_text = "系統繪圖模組發生異常 (Graphviz)。"
        else:
            ai_response_text = "請先讓我鑑定一個化石，我才知道要畫什麼演化圖喔！"

    elif intent == "EXPLAIN":
        context = get_last_ai_context(db[chat_id]["messages"])
        if context:
            ai_response_text = expert.explain_reasoning(context, user_input)
        else:
            ai_response_text = "請先提供化石資訊，我才能為您詳細解釋。"

    # 3. 儲存與回傳
    user_msg = {'role': 'user', 'content': user_input}
    
    # 如果有圖片 (Wiki圖 或 演化圖)，我們把它用 HTML 格式附加在訊息後面
    # 這樣即使 reload 網頁，歷史紀錄裡也會有圖
    final_content_for_db = ai_response_text
    if image_url:
        final_content_for_db += f'\n\n![Image]({image_url})' 

    ai_msg = {'role': 'assistant', 'content': final_content_for_db}

    db[chat_id]["messages"].append(user_msg)
    db[chat_id]["messages"].append(ai_msg)
    save_db(db)

    return jsonify({
        "response": ai_response_text,
        "image_url": image_url, # ✅ 確保這裡有傳回圖片網址
        "new_title": db[chat_id]["title"]
    })

# ==========================================
# 🌍 地圖 API (保持不變)
# ==========================================
@app.route("/api/bury", methods=["POST"])
def api_bury():
    data = request.json
    try:
        raw_data = expert.bury_fossil(data.get("lat"), data.get("lng"), data.get("era"))
        clean_json = raw_data.replace("```json", "").replace("```", "").strip()
        return jsonify({"success": True, "fossil": json.loads(clean_json)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/examine", methods=["POST"])
def api_examine():
    data = request.json
    try:
        explanation = expert.dig_fossil(str(data.get("fossil_info")))
        return jsonify({"success": True, "explanation": explanation.replace("```html", "").replace("```", "").strip()})
    except:
        return jsonify({"success": False, "explanation": "通訊錯誤"})

if __name__ == "__main__":
    if not os.path.exists('static'): os.makedirs('static')
    print("🦕 FossilMind 伺服器啟動中...")
    app.run(debug=True, port=5000)