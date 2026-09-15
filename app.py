import os
import time
import re
import requests
import feedparser
from flask import Flask, request, jsonify
from flask_cors import CORS
from google import genai
from google.genai import types

app = Flask(__name__)
# Enable CORS for WordPress, Blogger, and web embedding
CORS(app, resources={r"/*": {"origins": "*"}})

# ==========================================
# 1. OFFICIAL CREDENTIALS & ENDPOINTS
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AQ.Ab8RN6IPDnNb7qH7Tkjp7PwxZqPFLjXGsNdhI-4_dWDT_Y8GyA")
WORDPRESS_FEED_URL = "https://servicemoney.in/feed/"
BLOGGER_FEED_URL = "https://www.allroundupdate.com/feeds/posts/default?alt=rss"
YOUTUBE_API_KEY = "AIzaSyDJb9FJxDfUDIH3Y9KW46pzUWuFa2Ilp24"
YOUTUBE_CHANNEL_NAME = "Educationanurag"

# Initialize Google GenAI Client with modern SDK
client = genai.Client(api_key=GEMINI_API_KEY)

# ==========================================
# 2. IN-MEMORY DYNAMIC KNOWLEDGE BASE
# Auto-syncs new tools, categories & articles
# ==========================================
CACHE_TTL_SECONDS = 900  # 15 minutes cache to keep response lightning fast
cached_knowledge_items = []
last_cache_update = 0

def fetch_dynamic_ecosystem(force_refresh=False):
    """
    Dynamically loads all current and FUTURE tools, pages, and blogs
    from servicemoney.in, allroundupdate.com, and YouTube.
    Any new tool or article added to the sites will automatically be picked up here.
    """
    global cached_knowledge_items, last_cache_update
    now = time.time()
    
    if not force_refresh and cached_knowledge_items and (now - last_cache_update < CACHE_TTL_SECONDS):
        return cached_knowledge_items

    items = [
        # Built-in Core Pages & Tools
        {
            "id": "audit-calculator-tool",
            "title": "Audit Calculator Tool (ERP & Compliance)",
            "platform": "ServiceMoney.in",
            "category": "ERP Category",
            "url": "https://servicemoney.in/category/erp/",
            "description": "Financial audit calculator to compute GST liability, annual revenue/turnover, tax reconciliations, and accounting arithmetic.",
            "keywords": ["audit", "calculator", "audit tool", "erp", "gst calculator", "annual revenue", "turnover", "calculation", "multiplication", "math", "hisab", "clautiom", "clautate"]
        },
        {
            "id": "gst-rule-37a-86b",
            "title": "GST Rule 37A & 86B: Stop Losing 15% of Your Company Valuation to Regulatory Debt",
            "platform": "AllRoundUpdate.com",
            "category": "Finance Category (2nd Pagination / Page 2)",
            "url": "https://www.allroundupdate.com/search/label/Finance",
            "description": "Critical guide on GST Rule 37A (ITC reversal) and Rule 86B (1% cash tax payment limit) preventing company valuation decay.",
            "keywords": ["gst rule 37a", "rule 86b", "company valuation", "regulatory debt", "itc reversal", "finance category", "pagination", "15% valuation"]
        },
        {
            "id": "dpdp-act",
            "title": "DPDP Act (Digital Personal Data Protection Act) Compliance Guide",
            "platform": "AllRoundUpdate.com",
            "category": "Technology & Legal Compliance",
            "url": "https://www.allroundupdate.com/search?q=DPDP",
            "description": "Complete breakdown of India's DPDP Act, data fiduciary obligations, consent managers, and corporate compliance checklists.",
            "keywords": ["dpdp", "dpdp act", "digital personal data protection", "data privacy", "fiduciary", "consent manager"]
        },
        {
            "id": "about-founder",
            "title": "About Anurag Panchal & Official Network",
            "platform": "ServiceMoney.in",
            "category": "About Us",
            "url": "https://servicemoney.in/about-us/",
            "description": "Anurag Panchal is a financial consultant, GST expert, and tech educator founder of ServiceMoney.in, AllRoundUpdate.com, and YouTube channel @Educationanurag.",
            "keywords": ["anurag", "anurag panchal", "founder", "creator", "owner", "author", "about us", "who are you", "social profiles"]
        }
    ]

    # 1. Dynamically Auto-Fetch ALL Posts and Tools from ServiceMoney.in
    try:
        wp_feed = feedparser.parse(WORDPRESS_FEED_URL)
        if hasattr(wp_feed, 'entries') and wp_feed.entries:
            for entry in wp_feed.entries[:30]:
                tags = [t.term.lower() for t in entry.get('tags', [])]
                title = entry.get('title', '')
                summary = (entry.get('summary') or entry.get('description') or '')
                # Clean html tags from summary
                clean_summary = re.sub(r'<[^>]+>', '', summary)[:200]
                
                # Check if this item is a tool or calculator
                is_tool = any(w in title.lower() or w in clean_summary.lower() for w in ['tool', 'calculator', 'generator', 'checker', 'audit', 'converter'])
                
                items.append({
                    "id": f"sm-{entry.get('link')}",
                    "title": title,
                    "platform": "ServiceMoney.in",
                    "category": entry.get('category', 'ERP & Tools' if is_tool else 'Finance'),
                    "url": entry.get('link', 'https://servicemoney.in'),
                    "description": clean_summary,
                    "is_tool": is_tool,
                    "keywords": [title.lower()] + tags + (["tool", "calculator"] if is_tool else []) + ["servicemoney"]
                })
    except Exception as e:
        print(f"ServiceMoney feed fetch warning: {e}")

    # 2. Dynamically Auto-Fetch ALL Posts and Updates from AllRoundUpdate.com
    try:
        blog_feed = feedparser.parse(BLOGGER_FEED_URL)
        if hasattr(blog_feed, 'entries') and blog_feed.entries:
            for entry in blog_feed.entries[:30]:
                tags = [t.term.lower() for t in entry.get('tags', [])]
                title = entry.get('title', '')
                summary = (entry.get('summary') or entry.get('description') or '')
                clean_summary = re.sub(r'<[^>]+>', '', summary)[:200]
                
                is_tool = any(w in title.lower() or w in clean_summary.lower() for w in ['tool', 'calculator', 'app', 'update'])

                items.append({
                    "id": f"aru-{entry.get('link')}",
                    "title": title,
                    "platform": "AllRoundUpdate.com",
                    "category": entry.get('category', 'Technology & Finance'),
                    "url": entry.get('link', 'https://www.allroundupdate.com'),
                    "description": clean_summary,
                    "is_tool": is_tool,
                    "keywords": [title.lower()] + tags + ["allroundupdate"]
                })
    except Exception as e:
        print(f"AllRoundUpdate feed fetch warning: {e}")

    # 3. Dynamically Fetch Videos from YouTube (@Educationanurag)
    try:
        if YOUTUBE_API_KEY:
            yt_url = f"https://www.googleapis.com/youtube/v3/search?key={YOUTUBE_API_KEY}&q=Education+Anurag+Tally+GST&part=snippet,id&type=video&order=relevance&maxResults=8"
            yt_res = requests.get(yt_url, timeout=4).json()
            if "items" in yt_res:
                for v in yt_res["items"]:
                    vid_id = v.get("id", {}).get("videoId")
                    if vid_id:
                        title = v.get("snippet", {}).get("title", "")
                        items.append({
                            "id": f"yt-{vid_id}",
                            "title": title,
                            "platform": "YouTube (@Educationanurag)",
                            "category": "Video Tutorial",
                            "url": f"https://www.youtube.com/watch?v={vid_id}",
                            "description": v.get("snippet", {}).get("description", "")[:150],
                            "keywords": [title.lower(), "educationanurag", "youtube", "tally", "gst", "video"]
                        })
    except Exception as e:
        print(f"YouTube API notice: {e}")

    cached_knowledge_items = items
    last_cache_update = now
    return cached_knowledge_items

def detect_language(text):
    """Detects query language for seamless global user communication."""
    # Check for Devanagari script (Hindi, Marathi, etc.)
    if re.search(r'[\u0900-\u097F]', text):
        return "Hindi"
    
    # Check for common Hinglish/Hindi romanized words
    hinglish_tokens = ["kya", "kaise", "karna", "batao", "hai", "nahi", "chahiye", "mera", "meri", "karo", "mujhe", "bataiye"]
    text_lower = text.lower()
    if any(re.search(rf'\b{w}\b', text_lower) for w in hinglish_tokens):
        return "Hinglish"
        
    # Check German
    if any(re.search(rf'\b{w}\b', text_lower) for w in ["wie", "was", "ist", "bitte", "danke", "nicht", "kann", "steuer"]):
        return "German"
        
    # Check French
    if any(re.search(rf'\b{w}\b', text_lower) for w in ["comment", "pourquoi", "merci", "bonjour", "est", "une"]):
        return "French"
        
    # Default to English
    return "English"

# ==========================================
# 3. PING ENDPOINT (KEEPS BOT AWAKE 24x7)
# ==========================================
@app.route('/ping', methods=['GET'])
@app.route('/api/ping', methods=['GET'])
def ping():
    return jsonify({
        "status": "awake",
        "service": "ServiceMoney Master AI",
        "timestamp": time.time()
    }), 200

# ==========================================
# 4. CHATBOT QUERY ENDPOINT (/ask-ai)
# ==========================================
@app.route('/ask-ai', methods=['POST'])
@app.route('/api/ask-ai', methods=['POST'])
def ask_ai():
    data = request.json or {}
    user_query = data.get("query", data.get("prompt", "")).strip()

    if not user_query:
        return jsonify({"response": "Please provide your question."}), 400

    kb = fetch_dynamic_ecosystem()
    detected_lang = detect_language(user_query)
    query_lower = user_query.lower()

    # Intent Detection
    has_audit_calc_intent = any(w in query_lower for w in [
        "audit", "calculator", "calculate", "calute", "revenue", "turnover", 
        "multiplication", "math", "hisab", "clautiom", "clautate", "erp", "tax math"
    ])
    has_wise_intent = any(w in query_lower for w in [
        "wise", "transferwise", "foreign", "payout", "international", 
        "remittance", "us to india", "paypal", "fincen", "cross border", "wire"
    ])
    has_gst_37a = any(w in query_lower for w in ["37a", "86b", "regulatory debt", "valuation"])
    has_dpdp = any(w in query_lower for w in ["dpdp", "data privacy", "fiduciary"])
    has_about_author = any(w in query_lower for w in ["anurag", "founder", "owner", "author", "about us", "who are you"])

    # Match User Query with ALL Existing and Future Tools/Articles
    matched_tools = []
    matched_articles = []

    for item in kb:
        # Check title and keyword overlap
        score = 0
        for kw in item.get("keywords", []):
            if kw in query_lower or query_lower in kw:
                score += 2
        
        # Word token matching
        tokens = [t for t in re.split(r'\W+', query_lower) if len(t) > 3]
        for token in tokens:
            if token in item.get("title", "").lower():
                score += 3
            if token in item.get("description", "").lower():
                score += 1

        if score > 0:
            if item.get("is_tool") or "tool" in item.get("title", "").lower():
                matched_tools.append(item)
            else:
                matched_articles.append(item)

    # Build context string
    context_str = ""
    for item in (matched_tools + matched_articles)[:6]:
        context_str += f"- [{item['platform']}] Title: {item['title']} | Category: {item.get('category', 'General')} | URL: {item['url']} | Summary: {item['description']}\n"

    # Multilingual System Prompt
    system_instruction = f"""You are 'ServiceMoney Master AI', an elite, helpful assistant representing Anurag Panchal's official network:
1. servicemoney.in (Flagship: Financial audit tools, GST compliance, FinCEN, banking, ERP tools)
2. allroundupdate.com (Sister Portal: Technology news, DPDP Act, GST Rule 37A & 86B valuation guide, business updates)
3. YouTube (@Educationanurag): Practical video tutorials for Tally Prime, GST, and automation.
4. Founder: Anurag Panchal

CRITICAL RULES:
1. LANGUAGE CONSISTENCY: The detected user language is '{detected_lang}'. Formulate your entire answer in '{detected_lang}'. If user wrote in German, reply in German. If in Hindi, reply in Hindi. If English, reply in English.
2. DYNAMIC TOOL & BLOG SUGGESTION (CURRENT & FUTURE):
   - Whenever a user asks for a calculation, audit, math, or problem solving, ALWAYS check the matching tools from ServiceMoney.in.
   - For calculations/turnover/GST audits, specifically guide them to the 'Audit Calculator Tool' in the 'ERP Category' on ServiceMoney.in (https://servicemoney.in/category/erp/).
   - If ANY new tool or article is present in the context below that solves their problem, proactively recommend it with its category and direct URL.
3. CROSS-WEBSITE GUIDANCE:
   - For 'DPDP Act' or 'GST Rule 37A & 86B: Stop Losing 15% Valuation', inform the user that this article is on sister site AllRoundUpdate.com (Finance Category, Page 2) with URL https://www.allroundupdate.com/search/label/Finance.
4. AFFILIATE RECOMMENDATION (WISE):
   - If the query is about international money transfer, foreign remittance, B2B payouts, PayPal alternatives, or Wise:
   - Include a courteous invitation in the USER'S LANGUAGE offering fee-free first transfer via https://wise.com:
     * In Hindi: "💡 **कमाई व बचत का मौका**: अगर आप अंतरराष्ट्रीय ट्रांसफर या B2B payouts के लिए Wise पर अकाउंट बनाना चाहते हैं, तो इस पार्टनर लिंक से साइन-अप करने पर आपको पहले ट्रांसफर पर कोई फीस नहीं देनी होगी: https://wise.com"
     * In English: "💡 **Special Offer**: If you need to open an account for international payouts, using our partner link grants you a zero-fee first transfer: https://wise.com"
     * For other languages, translate this concept smoothly into that language.
5. YOUTUBE TUTORIALS:
   - When appropriate for Tally Prime, practical GST filing, or accounting automation, recommend @Educationanurag (https://www.youtube.com/@Educationanurag).
6. 100% COPYRIGHT-FREE & COMPREHENSIVE:
   - Even if the exact topic is not covered on our websites, provide a thorough, accurate, and original explanation.
   - Never copy external copyrighted text verbatim."""

    prompt = f"""User Query: "{user_query}"
Detected Language: {detected_lang}

Live Dynamic Knowledge Context:
{context_str if context_str else "No direct internal post match. Answer using high-level expert intelligence while guiding the user to relevant ecosystem categories."}

Tool Suggestion Needed: {"YES (Highlight Audit Calculator Tool in ERP on ServiceMoney.in)" if has_audit_calc_intent else "NO"}
Wise Affiliate Offer Needed: {"YES (Append fee-free Wise invitation in user's language)" if has_wise_intent else "NO"}
GST 37A / Valuation Intent: {"YES (Guide to AllRoundUpdate Finance Category Page 2)" if has_gst_37a else "NO"}

Respond in {detected_lang}."""

    try:
        # Use gemini-2.5-flash: high speed, reliable, zero deprecation issues
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction
            )
        )
        if response and response.text:
            return jsonify({
                "response": response.text,
                "answer": response.text,
                "language": detected_lang,
                "status": "success"
            }), 200
        else:
            return jsonify({"response": "I am ready to help you with ServiceMoney tools, GST, and tech updates."}), 200

    except Exception as e:
        print(f"Gemini API Exception: {e}")
        # Multilingual intelligent fallback
        if detected_lang in ["Hindi", "Hinglish"]:
            if has_audit_calc_intent:
                fallback = "नमस्ते! आपके कैलकुलेशन या ऑडिट संबंधी सवाल के लिए **ServiceMoney.in** पर **Audit Calculator Tool** उपलब्ध है। आप **ERP & Compliance** केटेगरी में जाकर डायरेक्ट GST व रेवेन्यू कैलकुलेट कर सकते हैं: https://servicemoney.in/category/erp/"
            elif has_wise_intent:
                fallback = "नमस्ते! अंतरराष्ट्रीय ट्रांसफर या B2B payouts के लिए आप **Wise** का उपयोग कर सकते हैं। पार्टनर लिंक से पहले ट्रांसफर पर ज़ीरो फीस का लाभ उठाएं: https://wise.com"
            else:
                fallback = "नमस्ते! आपके सवाल के समाधान के लिए आप **ServiceMoney.in** के ERP टूल्स और **AllRoundUpdate.com** के फाइनेंस आर्टिकल्स देख सकते हैं। वीडियो ट्यूटोरियल्स के लिए हमारे यूट्यूब चैनल **@Educationanurag** (https://www.youtube.com/@Educationanurag) पर विजिट करें।"
        else:
            if has_audit_calc_intent:
                fallback = "Hello! For your calculation or audit requirements, **ServiceMoney.in** provides an **Audit Calculator Tool** in the **ERP & Compliance** category: https://servicemoney.in/category/erp/"
            elif has_wise_intent:
                fallback = "Hello! For international transfers or business payouts, you can use **Wise**. Get zero fees on your first transfer using our official partner link: https://wise.com"
            else:
                fallback = "Hello! You can explore dedicated compliance tools on **ServiceMoney.in** and in-depth tech updates on **AllRoundUpdate.com**. For video tutorials, visit our YouTube channel **@Educationanurag** (https://www.youtube.com/@Educationanurag)."

        return jsonify({
            "response": fallback,
            "answer": fallback,
            "error_debug": str(e)
        }), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
