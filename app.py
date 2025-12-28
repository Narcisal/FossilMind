import os
import time
import uuid
import graphviz
from flask import Flask, render_template, request, jsonify

# ==========================================
# 👇 這裡就是關鍵！匯入我們剛拆好的模組
# ==========================================
from config import SECRET_KEY  # 從 config 拿設定
from backend import FossilExpert # 從 backend 拿 AI
from database import load_db, save_db, get_last_ai_context # 從 database 拿資料庫功能
from utils import get_wiki_image, extract_keyword # 從 utils 拿工具

app = Flask(__name__)
app.secret_key = SECRET_KEY

# 初始化 Expert (它會自己去 config 抓 Key)
expert = FossilExpert()

# ==========================================
# 🌐 頁面路由
# ==========================================
@app.route("/")
def index(): return render_template("index.html")

@app.route("/chat")
def chat_page(): return render_template("chat.html")

@app.route("/map")
def map_page(): return render_template("map.html")

# ==========================================
# 💬 對話 API (這裡使用了 database 和 utils 的功能)
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

# --- 核心對話 API ---
@app.route("/chat_api", methods=["POST"])
def chat_api():
    data = request.json
    user_input = data.get("message")
    chat_id = data.get("chat_id")

    if not user_input or not chat_id: return jsonify({"error": "No input"}), 400

    # 1. 讀取資料庫
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
    main_image_url = None # 這是要傳給前端顯示在泡泡最下方的「主圖片」

    # 3. 執行邏輯
    if intent == "IRRELEVANT":
        ai_response_text = "🦖 術業有專攻，FossilMind 無法回答與化石無關的問題喔！"

    elif intent == "IDENTIFY":
        # === 步驟 A: 鑑定化石 ===
        ai_response_text = expert.identify_fossil(user_input)
        
        # === 步驟 B: 找 Wiki 圖片 (設為主圖片) ===
        keyword = extract_keyword(ai_response_text)
        if not keyword: keyword = user_input 
        print(f"Searching Wiki for: {keyword}")
        main_image_url = get_wiki_image(keyword)

        # === 步驟 C: 自動畫演化圖 (這是新增的！) ===
        # 我們嘗試生成演化圖，並用 Markdown 語法把它加到文字最後面
        try:
            print("Auto-generating evolution graph...")
            dot_code = expert.generate_evolution_graph(ai_response_text)
            
            if dot_code and "digraph" in dot_code:
                # 產生唯一的檔名
                filename = f"evo_{uuid.uuid4().hex}"
                filepath = os.path.join('static', filename)
                
                # 繪製圖片
                src = graphviz.Source(dot_code)
                src.format = 'png'
                src.render(filepath, cleanup=True)
                
                # 生成 URL
                graph_url = f"/static/{filename}.png"
                
                # 🔥 關鍵：把演化圖用 Markdown 語法接在回答後面
                # 這樣前端就會顯示：[文字] + [演化圖] + [Wiki圖(在最下方)]
                ai_response_text += f"\n\n### 🧬 親緣演化關係\n![演化圖]({graph_url})"
                
        except Exception as e:
            print(f"Auto-Graph Error: {e}")
            # 畫圖失敗就算了，不要讓整個程式當掉，也不用特別顯示錯誤訊息給使用者

    elif intent == "GRAPH":
        # 主動要求畫圖的邏輯保持不變
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
                    
                    main_image_url = f"/static/{filename}.png"
                    ai_response_text = "這是根據目前的鑑定結果，所繪製的親緣演化關係圖："
                else:
                    ai_response_text = "抱歉，生成演化圖時發生錯誤。"
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

    # 4. 儲存與回傳
    user_msg = {'role': 'user', 'content': user_input}
    
    # 存進資料庫的內容要包含 Markdown 圖片語法，這樣歷史紀錄才看得到
    final_content_for_db = ai_response_text
    if main_image_url:
        final_content_for_db += f'\n\n![Image]({main_image_url})' 

    ai_msg = {'role': 'assistant', 'content': final_content_for_db}

    db[chat_id]["messages"].append(user_msg)
    db[chat_id]["messages"].append(ai_msg)
    save_db(db)

    return jsonify({
        "response": ai_response_text,     # 這裡面可能已經包含演化圖的 Markdown 了
        "image_url": main_image_url,      # 這是 Wiki 圖片 (會顯示在最後面)
        "new_title": db[chat_id]["title"]
    })

# ==========================================
# 🌍 地圖 API (這些已經正常工作了)
# ==========================================
@app.route("/api/bury", methods=["POST"])
def api_bury():
    data = request.json
    try:
        raw_data = expert.bury_fossil(data.get("lat"), data.get("lng"), data.get("era"))
        clean_json = raw_data.replace("```json", "").replace("```", "").strip()
        return jsonify({"success": True, "fossil": json.loads(clean_json)})
    except Exception as e:
        print(f"Bury Error: {e}") # 加個 print 方便除錯
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
    print("🦕 FossilMind 伺服器啟動中... (http://127.0.0.1:5000)")
    app.run(debug=True, port=5000)