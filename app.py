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
# CONFIGURATIONS (वेबसाइट्स और YouTube API)
# ==========================================
WORDPRESS_FEED_URL = "https://servicemoney.in/feed/"
BLOGGER_FEED_URL = "https://www.allroundupdate.com/feeds/posts/default?alt=rss"
YOUTUBE_API_KEY = "AIzaSyDJb9FJxDfUDIH3Y9KW46pzUWuFa2Ilp24"
YOUTUBE_CHANNEL_NAME = "Educationanurag"

# ==========================================
# DYNAMIC KNOWLEDGE BASE LOADER (WordPress + Blogger + YouTube)
# ==========================================
def load_knowledge_base():
    kb_list = []
    
    # 1. WordPress (ServiceMoney.in)
    try:
        wp_feed = feedparser.parse(WORDPRESS_FEED_URL)
        for entry in wp_feed.entries:
            categories = [tag.term for tag in entry.get('tags', [])]
            kb_list.append({
                "keywords": [entry.title.lower()] + [c.lower() for c in categories],
                "title": entry.title,
                "platform": "ServiceMoney.in",
                "url": entry.link,
                "description": entry.get('summary', '')[:150]
            })
    except Exception as e:
        print(f"Error WordPress RSS: {e}")

    # 2. Blogger (AllRoundUpdate.com)
    try:
        blog_feed = feedparser.parse(BLOGGER_FEED_URL)
        for entry in blog_feed.entries:
            kb_list.append({
                "keywords": [entry.title.lower()],
                "title": entry.title,
                "platform": "AllRoundUpdate.com",
                "url": entry.link,
                "description": entry.get('summary', '')[:150]
            })
    except Exception as e:
        print(f"Error Blogger RSS: {e}")

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
                            "keywords": [title.lower(), "tally", "tax", "educationanurag", "youtube"],
                            "title": title,
                            "platform": "YouTube (@Educationanurag)",
                            "url": video_link,
                            "description": desc[:150]
                        })
    except Exception as e:
        print(f"Error YouTube API: {e}")

    return kb_list

@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({"status": "awake"}), 200

@app.route('/ask-ai', methods=['POST'])
def ask_ai():
    data = request.json
    user_query = data.get("query", "")
    
    if not user_query:
        return jsonify({"response": "Please ask your question!"}), 400

    # नॉलेज बेस से मैच करना
    site_knowledge_base = load_knowledge_base()
    matched_context = ""
    query_lower = user_query.lower()
    
    for item in site_knowledge_base:
        if any(kw in query_lower for kw in item["keywords"]):
            matched_context += f"- Found on {item['platform']}: [{item['title']}]({item['url']}) - {item['description']}\n"

    # एकदम स्मार्ट गूगल-जैसी जेमिनी प्रणाली
    full_prompt = f"""
    You are 'ServiceMoney Master AI', an advanced, highly intelligent professional assistant created by Anurag Panchal. 
    You represent the digital ecosystem of Anurag Panchal, including servicemoney.in, allroundupdate.com, and YouTube channel @Educationanurag.

    Here is relevant information found in our official website/YouTube databases for this query (if any):
    {matched_context if matched_context else "No specific internal database match found."}

    User Query: {user_query}

    Instructions:
    1. Language Match: Detect the user's language (English, Hindi, Hinglish, etc.) and reply in the exact same language professionally.
    2. Hybrid Capability: 
       - If relevant articles, tutorials, or YouTube videos from our platforms are provided above, use them, provide a clear explanation, and give the clickable markdown link so the user can visit or watch them.
       - If the answer is not in our internal database, use your world-class general intelligence (like Gemini/Google) to answer the user's question completely, accurately, and professionally.
    3. Be natural, helpful, polite, and smart like Google/Gemini. Never give a blank or repetitive error message. Always answer what the user asks.
    """

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(full_prompt)
        
        if response and response.text:
            return jsonify({"response": response.text}), 200
        else:
            return jsonify({"response": "I am here to help you with anything you need. Please ask your question!"}), 200

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"response": "Hello! I am Anurag's AI assistant. You can ask me anything about finance, GST rules, technology, or general topics!"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
