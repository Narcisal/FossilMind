import requests
import re

def get_wiki_image(query):
    """搜尋維基百科並回傳第一張圖片的 URL"""
    print(f"[Wiki] Searching for: [{query}]...") # Debug 訊息
    try:
        # 偽裝成瀏覽器，避免被擋
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        # 1. 搜尋頁面
        search_url = "https://en.wikipedia.org/w/api.php"
        search_params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "format": "json",
            "origin": "*"
        }
        res = requests.get(search_url, params=search_params, headers=headers, timeout=5)
        data = res.json()
        
        if not data.get("query", {}).get("search"):
            print(f"[Wiki] Search returned no results for '{query}'")
            return None 
        
        title = data["query"]["search"][0]["title"]
        print(f"[Wiki] Found page: {title}")

        # 2. 抓圖片
        img_url = "https://en.wikipedia.org/w/api.php"
        img_params = {
            "action": "query",
            "titles": title,
            "prop": "pageimages",
            "format": "json",
            "pithumbsize": 600,
            "origin": "*"
        }
        img_res = requests.get(img_url, params=img_params, headers=headers, timeout=5).json()
        
        pages = img_res.get("query", {}).get("pages", {})
        for page_id in pages:
            if "thumbnail" in pages[page_id]:
                img_src = pages[page_id]["thumbnail"]["source"]
                print(f"[Wiki] Image found: {img_src}")
                return img_src
                
    except Exception as e:
        print(f"[Wiki] Error: {e}")
    
    return None

def extract_keyword(text):
    """
    超級寬容的關鍵字抓取
    容許：[[Wiki:Keyword]]、[[ Wiki : Keyword ]]、[[Wiki: Keyword]]
    """
    match = re.search(r'\[\[\s*Wiki\s*:\s*(.*?)\s*\]\]', text, re.IGNORECASE | re.DOTALL)
    if match:
        keyword = match.group(1).strip()
        keyword = keyword.replace('*', '').replace('_', '')
        return keyword
    
    bold_match = re.search(r'\*\*(.*?)\*\*', text)
    if bold_match:
        return bold_match.group(1).strip()
        
    return None

def clean_ai_response(text):
    """
    把醜醜的標籤剪掉
    """
    # 同樣使用寬容模式
    return re.sub(r'\[\[\s*Wiki\s*:\s*.*?\s*\]\]', '', text, flags=re.IGNORECASE | re.DOTALL).strip()