import os
import time
import uuid
import graphviz
from flask import Flask, render_template, request, jsonify


from config import SECRET_KEY 
from backend import FossilExpert 
from database import load_db, save_db, get_last_ai_context 
from utils import get_wiki_image, extract_keyword 

app = Flask(__name__)
app.secret_key = SECRET_KEY

expert = FossilExpert()

# 頁面路由
@app.route("/")
def index(): return render_template("index.html")

@app.route("/chat")
def chat_page(): return render_template("chat.html")

@app.route("/map")
def map_page(): return render_template("map.html")


# 對話 API

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

# 核心對話 API
@app.route("/chat_api", methods=["POST"])
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
        ai_response_text = expert.identify_fossil(user_input)
        
        # B. 找 Wiki 圖片 (新增功能)
        # a. 找學名
        keyword = extract_keyword(ai_response_text)
        if not keyword: 
            keyword = user_input # 沒找到就用使用者輸入去搜
        
        print(f"Searching Wiki for: {keyword}")
        
        # b. 用工具抓圖
        found_img = get_wiki_image(keyword)
        
        # c. 只有當真的有抓到圖時，才設定變數，避免顯示空框
        if found_img:
            wiki_image_url = found_img

        # C. 畫演化分支圖
        try:
            print("Auto-generating evolution graph...")
            dot_code = expert.generate_evolution_graph(ai_response_text)
            if dot_code and "digraph" in dot_code:
                filename = f"evo_{uuid.uuid4().hex}"
                filepath = os.path.join('static', filename)
                src = graphviz.Source(dot_code)
                src.format = 'png'
                src.render(filepath, cleanup=True)
                
                # 把演化圖「嵌入」在文字最後面
                graph_url = f"/static/{filename}.png"
                ai_response_text += f"\n\n### 🧬 親緣演化關係\n![演化圖]({graph_url})"
        except Exception as e:
            print(f"Auto-Graph Error: {e}")

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



# 地圖 API 
@app.route("/api/bury", methods=["POST"])
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
    app.run(debug=True, port=5000)