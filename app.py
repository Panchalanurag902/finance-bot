import os
import re
import feedparser
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai

app = Flask(__name__)
CORS(app)

# आपकी ऑफिशियल जेमिनी एपीआई की
GEMINI_API_KEY = "AQ.Ab8RN6IPDnNb7qH7TkjP7PwxZqPFLjXGsNdhI-4_dWDT_Y8GyA"
genai.configure(api_key=GEMINI_API_KEY)

# ==========================================
# CONFIGURATIONS (आपकी वेबसाइट्स और YouTube API Key)
# ==========================================
WORDPRESS_FEED_URL = "https://servicemoney.in/feed/"
BLOGGER_FEED_URL = "https://www.allroundupdate.com/feeds/posts/default?alt=rss"
YOUTUBE_API_KEY = "AIzaSyDJb9FJxDfUDIH3Y9KW46pzUWuFa2Ilp24"
YOUTUBE_CHANNEL_NAME = "Educationanurag" 

# YouTube URL से Video ID निकालने का फंक्शन
def extract_youtube_id(url):
    if not url:
        return None
    patterns = [
        r'(?:v=|\/embed\/|\/v\/|youtu\.be\/|\/watch\?v=)([a-zA-Z0-9_-]{11})',
        r'(?:shorts\/)([a-zA-Z0-9_-]{11})'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

# ==========================================
# DYNAMIC KNOWLEDGE BASE LOADER
# ==========================================
def load_knowledge_base():
    kb_list = []
    
    # 1. WordPress (servicemoney.in)
    try:
        wp_feed = feedparser.parse(WORDPRESS_FEED_URL)
        for entry in wp_feed.entries:
            categories = [tag.term for tag in entry.get('tags', [])]
            kb_list.append({
                "keywords": [entry.title.lower()] + [c.lower() for c in categories],
                "title": entry.title,
                "platform": "ServiceMoney.in",
                "category": "ERP Audit & Tax Guide",
                "url": entry.link,
                "image_url": "https://servicemoney.in/wp-content/uploads/default-hub.png",
                "description": entry.get('summary', 'Read full article on ServiceMoney.in')[:150] + "..."
            })
    except Exception as e:
        print(f"Error fetching WordPress RSS: {e}")

    # 2. Blogger (allroundupdate.com)
    try:
        blog_feed = feedparser.parse(BLOGGER_FEED_URL)
        for entry in blog_feed.entries:
            categories = [tag.term for tag in entry.get('term', [])]
            kb_list.append({
                "keywords": [entry.title.lower()] + [c.lower() for c in categories],
                "title": entry.title,
                "platform": "AllRoundUpdate.com",
                "category": "Regulatory & Tech News",
                "url": entry.link,
                "image_url": "",
                "description": entry.get('summary', 'Read latest update on AllRoundUpdate.com')[:150] + "..."
            })
    except Exception as e:
        print(f"Error fetching Blogger RSS: {e}")

    # 3. YouTube API (@Educationanurag)
    try:
        if YOUTUBE_API_KEY:
            search_url = f"https://www.googleapis.com/youtube/v3/search?key={YOUTUBE_API_KEY}&q={YOUTUBE_CHANNEL_NAME}&part=snippet,id&type=video&order=date&maxResults=10"
            yt_res = requests.get(search_url).json()
            if "items" in yt_res:
                for item in yt_res["items"]:
                    vid_id = item["id"].get("videoId")
                    if vid_id:
                        title = item["snippet"]["title"]
                        desc = item["snippet"]["description"]
                        video_link = f"https://www.youtube.com/watch?v={vid_id}"
                        kb_list.append({
                            "keywords": [title.lower(), "tally", "tax", "educationanurag", "youtube", "asmt", "gst"],
                            "title": title,
                            "platform": "YouTube (@Educationanurag)",
                            "category": "Video Walkthrough",
                            "url": video_link,
                            "image_url": f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg",
                            "description": desc[:150] + "..."
                        })
    except Exception as e:
        print(f"Error fetching YouTube API: {e}")

    return kb_list

@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({"status": "awake"}), 200

@app.route('/ask-ai', methods=['POST'])
def ask_ai():
    data = request.json
    user_query = data.get("query", "")
    
    if not user_query:
        return jsonify({"response": "Please ask your question or type a query! / कृपया अपना सवाल पूछें।"}), 400

    site_knowledge_base = load_knowledge_base()
    matched_context = ""
    query_lower = user_query.lower()
    
    for item in site_knowledge_base:
        if any(kw in query_lower for kw in item["keywords"]):
            img_tag = f"\n  ![Thumbnail/Image]({item.get('image_url', '')})" if item.get('image_url') else ""
            matched_context += f"\n- **Found on {item['platform']} ({item['category']}):** [{item['title']}]({item['url']})\n  Description: {item['description']}{img_tag}\n"

    # सुधारा हुआ मास्टर सिस्टम प्रॉम्प्ट (स्ट्रिक्ट भाषा और डायरेक्ट आंसर के लिए)
    system_instruction = f"""
    You are 'ServiceMoney Master AI', the official network and brand assistant created by Anurag Panchal for his digital ecosystem:
    1. servicemoney.in (Primary financial hub, ERP audit calculators, business tools, and compliance portal)
    2. allroundupdate.com (Sister portal for deep regulatory guides, GST Rules, tech updates, and financial news)
    3. YouTube Channel: @Educationanurag (https://www.youtube.com/@Educationanurag for Tally Prime, corporate tax compliance, and video walkthroughs)

    REAL-TIME MATCHED DATA FROM KNOWLEDGE BASE FOR THIS QUERY:
    {matched_context if matched_context else "No direct internal link match found in local database. Use general expert knowledge about GST, tax, finance, and technology, and subtly recommend checking servicemoney.in or allroundupdate.com if relevant."}

    STRICT BEHAVIORAL & OPERATIONAL RULES:
    1. STRICT LANGUAGE MATCHING:
       - Detect the language of the user's query (`user_query`). If the user asks in English, you MUST reply entirely in professional English. If the user asks in Hindi/Hinglish, reply accordingly. Never mix or force Hindi when the query is in English.
    
    2. DIRECT & ACCURATE ANSWERS:
       - Give a direct, precise, and professional answer to what the user is asking (e.g., if they ask about ASMT like Form ASMT-10 under GST, explain it clearly and professionally). Do not just paste a generic introduction every time.
    
    3. RICH MEDIA & SITE INTEGRATION:
       - If matched data or relevant links are available above, seamlessly integrate them into your response.
    
    4. SMART AFFILIATE PUSH (Wise):
       - If the user discusses international money transfers or PayPal vs Wise, conclude smoothly with a helpful recommendation.
    """

    try:
        model = genai.GenerativeModel('gemini-1.5-flash', system_instruction=system_instruction)
        response = model.generate_content(user_query)
        
        if response and response.text:
            return jsonify({"response": response.text}), 200
        else:
            return jsonify({"response": "I am here to help you with GST, tax compliance, and tech guides. Please let me know your specific question!"}), 200

    except Exception as e:
        # अब यहाँ कोई भारी-भरकम हिंदी फॉलबैक नहीं रहेगा, बल्कि सटीक अंग्रेजी जवाब मिलेगा
        error_msg = f"Hello! I am Anurag's network assistant. For details regarding your query, please explore servicemoney.in, allroundupdate.com, or check out our YouTube channel @Educationanurag."
        return jsonify({"response": error_msg}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
