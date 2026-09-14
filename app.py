import os
import re
import feedparser
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai

app = Flask(__name__)
CORS(app)

# आपकी ऑफिशियल जेमिनी एपीआई की (जो आपने चैट हिस्ट्री में दी थी)
GEMINI_API_KEY = "AQ.Ab8RN6IPDnNb7qH7TkjP7PwxZqPFLjXGsNdhI-4_dWDT_Y8GyA"
genai.configure(api_key=GEMINI_API_KEY)

# ==========================================
# CONFIGURATIONS (आपकी वेबसाइट्स और YouTube API Key)
# ==========================================
WORDPRESS_FEED_URL = "https://servicemoney.in/feed/"
BLOGGER_FEED_URL = "https://www.allroundupdate.com/feeds/posts/default?alt=rss"
YOUTUBE_API_KEY = "AIzaSyDJb9FJxDfUDIH3Y9KW46pzUWuFa2Ilp24"

# नोट: यदि आपको अपने YouTube चैनल की 'Channel ID' (जो UC से शुरू होती है) मालूम है, 
# तो यहाँ डाल सकते हैं। अगर नहीं मालूम, तो नीचे दिए गए 'search' वाले तरीके से चैनल का नाम 
# डायरेक्ट इस्तेमाल किया जा सकता है।
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
# DYNAMIC KNOWLEDGE BASE LOADER (RSS + YouTube से ऑटो-सिंक)
# ==========================================
def load_knowledge_base():
    kb_list = []
    
    # 1. WordPress (servicemoney.in) से लाइव ब्लॉग फेच करना
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

    # 2. Blogger (allroundupdate.com) से लाइव ब्लॉग फेच करना
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

    # 3. YouTube API से लेटेस्ट वीडियो फेच करना (@Educationanurag)
    try:
        if YOUTUBE_API_KEY:
            # YouTube Search API का उपयोग करके चैनल के वीडियो ढूंढ़ना
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
                            "category": "Video Walkthrough",
                            "url": video_link,
                            "image_url": f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg",
                            "description": desc[:150] + "..."
                        })
    except Exception as e:
        print(f"Error fetching YouTube API: {e}")

    # यदि किसी कारणवश इंटरनेट या फीड काम न करे, तो यह डिफॉल्ट फॉलबैक रहेगा
    if not kb_list:
        kb_list = [
            {
                "keywords": ["tally", "corporate tax", "compliance", "educationanurag"],
                "title": "Tally Prime & Corporate Tax Compliance Tutorials",
                "platform": "YouTube (@Educationanurag)",
                "category": "Video Walkthrough",
                "url": "https://www.youtube.com/@Educationanurag",
                "image_url": "https://img.youtube.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
                "description": "Practical tutorials aur explainers ke liye Anurag ke official channel ko dekhein."
            }
        ]

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

    # लाइव डेटाबेस लोड करना (WordPress, Blogger और YouTube से ऑटोमैटिक)
    site_knowledge_base = load_knowledge_base()
    matched_context = ""
    query_lower = user_query.lower()
    
    for item in site_knowledge_base:
        if any(kw in query_lower for kw in item["keywords"]):
            img_tag = f"\n  ![Thumbnail/Image]({item.get('image_url', '')})" if item.get('image_url') else ""
            matched_context += f"\n- **Found on {item['platform']} ({item['category']}):** [{item['title']}]({item['url']})\n  Description: {item['description']}{img_tag}\n"

    # मास्टर सिस्टम प्रॉम्प्ट
    system_instruction = f"""
    You are 'ServiceMoney Master AI', the official network and brand assistant created by Anurag Panchal for his digital ecosystem:
    1. servicemoney.in (Primary financial hub, ERP audit calculators, business tools, and compliance portal)
    2. allroundupdate.com (Sister portal for deep regulatory guides, GST Rules, tech updates, and financial news)
    3. YouTube Channel: @Educationanurag (https://www.youtube.com/@Educationanurag for Tally Prime, corporate tax compliance, and video walkthroughs)

    REAL-TIME MATCHED DATA FROM KNOWLEDGE BASE FOR THIS QUERY:
    {matched_context if matched_context else "No direct internal link match found in local database. Use general expert knowledge and recommend checking servicemoney.in or allroundupdate.com."}

    STRICT BEHAVIORAL & OPERATIONAL RULES:
    1. GLOBAL LANGUAGE & TONE ADAPTATION:
       - Automatically detect the user's language (Hindi, English, Hinglish, etc.) and reply in the exact same language and professional tone.
    
    2. DIRECT SITE & TOOL ROUTING WITH IMAGES/LINKS:
       - If matched data is provided above, seamlessly integrate the titles, links, descriptions, and markdown image formats into your response so the user gets a rich visual card experience.
    
    3. SMART AFFILIATE PUSH (Wise):
       - Whenever a user discusses international currency transfers, cross-border payments, or comparing PayPal vs Wise, conclude smoothly with:
         "अगर आप Wise पर अकाउंट बनाना चाहते हैं, तो इस लिंक से साइन-अप करने पर आपको पहले ट्रांसफर पर कोई फीस नहीं देनी होगी: [Your Wise Affiliate Link]" (Adapt language accordingly).

    4. GENERAL FALLBACK KNOWLEDGE:
       - If the query does not match the local database items, use your world-class general intelligence to provide a phenomenal, accurate, and professional answer, and subtly guide them back to servicemoney.in or allroundupdate.com.

    5. COPYRIGHT & PLAGIARISM PROTECTION:
       - Completely rewrite external information in original, high-value professional phrasing with zero plagiarism.
    """

    try:
        model = genai.GenerativeModel('gemini-1.5-flash', system_instruction=system_instruction)
        response = model.generate_content(user_query)
        
        if response and response.text:
            return jsonify({"response": response.text}), 200
        else:
            raise Exception("Empty response from AI model")

    except Exception as e:
        fallback_msg = (
            "नमस्ते! मैं अनुराग पंचाल का नेटवर्क असिस्टेंट हूँ। आपकी इस क्वेरी के लिए आप हमारी वेबसाइट "
            "servicemoney.in के सेक्शन या allroundupdate.com और हमारे YouTube चैनल @Educationanurag को देख सकते हैं!"
        )
        return jsonify({"response": fallback_msg}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
