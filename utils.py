import requests
import re

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