import html as html_lib
import json
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from time import sleep
from urllib.parse import urljoin, urlparse
import feedparser
import requests
from flask import Flask, jsonify, request
from flask_cors import CORS
app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("smart-knowledge-bot")
# ============================================================
# CONFIGURATION
# ============================================================
SERVICE_MONEY_FEED = os.environ.get(
    "WORDPRESS_FEED_URL",
    "https://servicemoney.in/feed/",
)
ALLROUNDUPDATE_FEED = os.environ.get(
    "BLOGGER_FEED_URL",
    "https://www.allroundupdate.com/feeds/posts/default?alt=rss&max-results=50",
)
SERVICE_MONEY_SITEMAP = os.environ.get(
    "SERVICEMONEY_SITEMAP_URL",
    "https://servicemoney.in/sitemap_index.xml",
)
ALLROUNDUPDATE_SITEMAP = os.environ.get(
    "ALLROUNDUPDATE_SITEMAP_URL",
    "https://www.allroundupdate.com/sitemap.xml",
)
YOUTUBE_CHANNEL_URL = os.environ.get(
    "YOUTUBE_CHANNEL_URL",
    "https://www.youtube.com/@Educationanurag/videos",
)
SERVICE_MONEY_ABOUT_URL = os.environ.get(
    "SERVICEMONEY_ABOUT_URL",
    "https://servicemoney.in/about-us/",
)
ALLROUNDUPDATE_FINANCE_URL = os.environ.get(
    "ALLROUNDUPDATE_FINANCE_URL",
    "https://www.allroundupdate.com/search/label/Finance",
)
GEMINI_MODEL = os.environ.get(
    "GEMINI_MODEL",
    "gemini-3.6-flash",
)
CACHE_SECONDS = 5 * 60
HTTP_HEADERS = {
    "User-Agent": (
        "SmartKnowledgeBot/1.0 "
        "(+https://servicemoney.in)"
    )
}
TOOL_PATTERN = re.compile(
    r"calculator|calculate|audit|tool|utility|checker|generator|"
    r"formula|solve|erp",
    re.IGNORECASE,
)
SITEMAP_DISCOVERY_PATTERN = re.compile(
    r"tool|calculator|audit|gst|tax|finance|erp|revenue|"
    r"compliance|accounting",
    re.IGNORECASE,
)
TRANSIENT_HTTP_STATUSES = {429, 502, 503, 504}
# ============================================================
# CORS
# ============================================================
configured_origins = os.environ.get("ALLOWED_ORIGINS", "").strip()
if configured_origins:
    allowed_origins = [
        origin.strip()
        for origin in configured_origins.split(",")
        if origin.strip()
    ]
else:
    allowed_origins = [
        "https://servicemoney.in",
        "https://www.servicemoney.in",
        "https://allroundupdate.com",
        "https://www.allroundupdate.com",
        "http://localhost:3000",
        "http://localhost:5000",
    ]
CORS(
    app,
    resources={
        r"/*": {
            "origins": allowed_origins,
            "methods": ["GET", "POST", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
        }
    },
)
# ============================================================
# ERROR TYPES
# ============================================================
class TemporaryAssistantError(Exception):
    """Temporary Gemini/network failure safe for frontend responses."""
TEMPORARY_ASSISTANT_MESSAGE = (
    "The assistant is taking a brief pause. "
    "Please try asking your question again in a moment."
)
# ============================================================
# BASIC HELPERS
# ============================================================
def decode_html(value):
    if not value:
        return ""
    value = re.sub(
        r"<!\[CDATA\[(.*?)\]\]>",
        r"\1",
        str(value),
        flags=re.DOTALL | re.IGNORECASE,
    )
    value = re.sub(r"<[^>]+>", " ", value)
    value = html_lib.unescape(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()
def absolute_url(value, base_url):
    if not value:
        return ""
    try:
        return urljoin(base_url, value)
    except Exception:
        return value
def slug_title(url):
    try:
        path_parts = [
            part for part in urlparse(url).path.split("/")
            if part
        ]
        if not path_parts:
            return url
        slug = path_parts[-1]
        slug = re.sub(r"[-_]+", " ", slug)
        return slug.title()
    except Exception:
        return url
def fetch_text(url, timeout=8):
    """
    Returns an empty string when a source is unavailable.
    A single failed feed will not crash the complete knowledge loader.
    """
    try:
        response = requests.get(
            url,
            headers=HTTP_HEADERS,
            timeout=timeout,
        )
        if not response.ok:
            logger.warning(
                "Knowledge source returned HTTP %s: %s",
                response.status_code,
                url,
            )
            return ""
        return response.text or ""
    except requests.RequestException as error:
        logger.warning("Knowledge source fetch failed for %s: %s", url, error)
        return ""
def classify_resource(title, url, description):
    searchable = f"{title} {url} {description}".lower()
    if TOOL_PATTERN.search(searchable):
        return "tool"
    return "article"
# ============================================================
# RSS / ATOM FEED DISCOVERY
# ============================================================
def parse_feed(xml_text, site_name, base_url):
    if not xml_text:
        return []
    try:
        parsed = feedparser.parse(xml_text)
    except Exception as error:
        logger.warning("Could not parse feed for %s: %s", site_name, error)
        return []
    resources = []
    for entry in getattr(parsed, "entries", []):
        title = decode_html(entry.get("title", ""))
        url = entry.get("link", "") or ""
        if not url:
            links = entry.get("links", []) or []
            for link_item in links:
                if link_item.get("rel") in (None, "alternate"):
                    url = link_item.get("href", "")
                    if url:
                        break
        url = absolute_url(url, base_url)
        description = decode_html(
            entry.get("summary", "")
            or entry.get("description", "")
            or entry.get("content", "")
        )
        category = None
        tags = entry.get("tags", []) or []
        if tags:
            category = decode_html(tags[0].get("term", "")) or None
        image = None
        media_content = entry.get("media_content", []) or []
        if media_content:
            image = media_content[0].get("url")
        if not image:
            enclosures = entry.get("enclosures", []) or []
            if enclosures:
                image = enclosures[0].get("href")
        if not image:
            image_match = re.search(
                r"<img[^>]+src=[\"']([^\"']+)",
                str(entry.get("summary", "")),
                flags=re.IGNORECASE,
            )
            if image_match:
                image = image_match.group(1)
        image = absolute_url(image, base_url) if image else None
        if not title:
            title = slug_title(url)
        if not title or not url.startswith(("http://", "https://")):
            continue
        resources.append(
            {
                "title": title,
                "url": url,
                "site": site_name,
                "kind": classify_resource(title, url, description),
                "description": description[:360],
                "image": image,
                "category": category,
            }
        )
    return resources
def load_feed_resources(feed_url, site_name, base_url):
    feed_text = fetch_text(feed_url)
    if not feed_text:
        return {
            "online": False,
            "resources": [],
        }
    return {
        "online": True,
        "resources": parse_feed(feed_text, site_name, base_url),
    }
# ============================================================
# SITEMAP DISCOVERY
# ============================================================
def parse_sitemap_resources(sitemap_url, site_name):
    index_text = fetch_text(sitemap_url)
    if not index_text:
        return []
    sitemap_locations = [
        html_lib.unescape(value.strip())
        for value in re.findall(
            r"<loc[^>]*>(.*?)</loc>",
            index_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
    ]
    child_sitemaps = [
        value
        for value in sitemap_locations
        if "sitemap" in value.lower()
    ][:5]
    documents = []
    if child_sitemaps:
        for child_sitemap in child_sitemaps:
            child_text = fetch_text(child_sitemap)
            if child_text:
                documents.append(child_text)
    else:
        documents.append(index_text)
    discovered_urls = []
    for document in documents:
        locations = re.findall(
            r"<loc[^>]*>(.*?)</loc>",
            document,
            flags=re.IGNORECASE | re.DOTALL,
        )
        for location in locations:
            url = html_lib.unescape(location.strip())
            if not url.startswith(("http://", "https://")):
                continue
            if re.search(
                r"/(category|tag|author|feed|page)/",
                url,
                flags=re.IGNORECASE,
            ):
                continue
            if not SITEMAP_DISCOVERY_PATTERN.search(url):
                continue
            discovered_urls.append(url)
    unique_urls = list(dict.fromkeys(discovered_urls))[:120]
    resources = []
    for url in unique_urls:
        title = slug_title(url)
        resources.append(
            {
                "title": title,
                "url": url,
                "site": site_name,
                "kind": (
                    "tool"
                    if TOOL_PATTERN.search(url)
                    else "article"
                ),
                "description": (
                    "A live resource discovered from the website sitemap."
                ),
                "image": None,
                "category": None,
            }
        )
    return resources
# ============================================================
# YOUTUBE DISCOVERY
# ============================================================
def parse_youtube_resources():
    page_text = fetch_text(YOUTUBE_CHANNEL_URL)
    fallback_channel = {
        "title": "Educationanurag on YouTube",
        "url": "https://www.youtube.com/@Educationanurag",
        "site": "YouTube",
        "kind": "page",
        "description": (
            "Official channel for Anurag Panchal's explainers and tutorials."
        ),
        "image": None,
        "category": "Video",
    }
    if not page_text:
        return [fallback_channel]
    video_ids = re.findall(
        r"\"videoId\":\"([^\"]+)\"",
        page_text,
    )
    video_titles = re.findall(
        r"\"title\":\{\"runs\":\[\{\"text\":\"((?:\\.|[^\"])*)\"",
        page_text,
    )
    resources = []
    used_ids = set()
    for index, video_id in enumerate(video_ids[:12]):
        if video_id in used_ids:
            continue
        used_ids.add(video_id)
        raw_title = (
            video_titles[index]
            if index < len(video_titles)
            else "Educationanurag video"
        )
        title = (
            raw_title
            .replace('\\"', '"')
            .replace("\\u0026", "&")
        )
        resources.append(
            {
                "title": html_lib.unescape(title),
                "url": (
                    f"https://www.youtube.com/watch?v={video_id}"
                ),
                "site": "YouTube",
                "kind": "video",
                "description": (
                    "A video from the official Educationanurag channel."
                ),
                "image": (
                    f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
                ),
                "category": "Video",
            }
        )
    resources.append(fallback_channel)
    return resources
# ============================================================
# KNOWLEDGE SNAPSHOT AND CACHE
# ============================================================
knowledge_cache = None
knowledge_cache_expires_at = 0
knowledge_cache_lock = threading.Lock()
def build_knowledge_snapshot():
    service_feed_job = lambda: load_feed_resources(
        SERVICE_MONEY_FEED,
        "ServiceMoney.in",
        "https://servicemoney.in/",
    )
    allround_feed_job = lambda: load_feed_resources(
        ALLROUNDUPDATE_FEED,
        "AllRoundUpdate.com",
        "https://www.allroundupdate.com/",
    )
    service_sitemap_job = lambda: parse_sitemap_resources(
        SERVICE_MONEY_SITEMAP,
        "ServiceMoney.in",
    )
    allround_sitemap_job = lambda: parse_sitemap_resources(
        ALLROUNDUPDATE_SITEMAP,
        "AllRoundUpdate.com",
    )
    youtube_job = parse_youtube_resources
    jobs = {
        "service_feed": service_feed_job,
        "allround_feed": allround_feed_job,
        "service_sitemap": service_sitemap_job,
        "allround_sitemap": allround_sitemap_job,
        "youtube": youtube_job,
    }
    results = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_map = {
            name: executor.submit(job)
            for name, job in jobs.items()
        }
        for name, future in future_map.items():
            try:
                results[name] = future.result()
            except Exception as error:
                logger.exception(
                    "Knowledge loader failed for %s: %s",
                    name,
                    error,
                )
                if name.endswith("_feed"):
                    results[name] = {
                        "online": False,
                        "resources": [],
                    }
                elif name == "youtube":
                    results[name] = [parse_youtube_resources()[0]]
                else:
                    results[name] = []
    service_feed_result = results.get(
        "service_feed",
        {"online": False, "resources": []},
    )
    allround_feed_result = results.get(
        "allround_feed",
        {"online": False, "resources": []},
    )
    service_feed_resources = service_feed_result["resources"]
    allround_feed_resources = allround_feed_result["resources"]
    service_sitemap_resources = results.get(
        "service_sitemap",
        [],
    )
    allround_sitemap_resources = results.get(
        "allround_sitemap",
        [],
    )
    youtube_resources = results.get("youtube", [])
    fixed_resources = [
        {
            "title": "About Anurag Panchal",
            "url": SERVICE_MONEY_ABOUT_URL,
            "site": "ServiceMoney.in",
            "kind": "page",
            "description": (
                "Learn about the author and the ServiceMoney.in "
                "knowledge hub."
            ),
            "image": None,
            "category": "About",
        },
        {
            "title": "Finance on AllRoundUpdate.com",
            "url": ALLROUNDUPDATE_FINANCE_URL,
            "site": "AllRoundUpdate.com",
            "kind": "page",
            "description": (
                "Browse the Finance category on AllRoundUpdate.com."
            ),
            "image": None,
            "category": "Finance",
        },
    ]
    resources_by_url = {}
    all_resources = (
        service_feed_resources
        + allround_feed_resources
        + service_sitemap_resources
        + allround_sitemap_resources
        + youtube_resources
        + fixed_resources
    )
    for resource in all_resources:
        url = resource.get("url")
        if url:
            resources_by_url[url] = resource
    refreshed_at = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ",
        time.gmtime(),
    )
    youtube_video_count = len(
        [
            resource
            for resource in youtube_resources
            if resource.get("kind") == "video"
        ]
    )
    snapshot = {
        "resources": list(resources_by_url.values()),
        "refreshedAt": refreshed_at,
        "sources": [
            {
                "site": "servicemoney.in",
                "label": "ServiceMoney.in",
                "status": (
                    "online"
                    if service_feed_result["online"]
                    else (
                        "partial"
                        if service_feed_resources
                        or service_sitemap_resources
                        else "offline"
                    )
                ),
                "itemCount": (
                    len(service_feed_resources)
                    + len(service_sitemap_resources)
                ),
                "refreshedAt": refreshed_at,
            },
            {
                "site": "allroundupdate.com",
                "label": "AllRoundUpdate.com",
                "status": (
                    "online"
                    if allround_feed_result["online"]
                    else (
                        "partial"
                        if allround_feed_resources
                        or allround_sitemap_resources
                        else "offline"
                    )
                ),
                "itemCount": (
                    len(allround_feed_resources)
                    + len(allround_sitemap_resources)
                ),
                "refreshedAt": refreshed_at,
            },
            {
                "site": "youtube.com/@Educationanurag",
                "label": "Educationanurag",
                "status": (
                    "online"
                    if youtube_video_count > 0
                    else "partial"
                ),
                "itemCount": youtube_video_count,
                "refreshedAt": refreshed_at,
            },
        ],
    }
    return snapshot
def get_knowledge_snapshot():
    global knowledge_cache
    global knowledge_cache_expires_at
    now = time.time()
    with knowledge_cache_lock:
        if knowledge_cache and knowledge_cache_expires_at > now:
            return knowledge_cache
    snapshot = build_knowledge_snapshot()
    with knowledge_cache_lock:
        knowledge_cache = snapshot
        knowledge_cache_expires_at = time.time() + CACHE_SECONDS
    return snapshot
# ============================================================
# RESOURCE MATCHING
# ============================================================
STOP_WORDS = {
    "the",
    "and",
    "for",
    "what",
    "how",
    "can",
    "about",
    "please",
    "tell",
    "with",
    "from",
    "this",
    "that",
    "mujhe",
    "batao",
    "kya",
    "hai",
    "ke",
    "par",
    "mein",
    "mera",
    "meri",
    "ko",
    "ka",
    "ki",
    "se",
}
def query_terms(query):
    normalized = re.sub(
        r"[^\w]+",
        " ",
        query.lower(),
        flags=re.UNICODE,
    )
    terms = [
        term
        for term in normalized.split()
        if len(term) > 2 and term not in STOP_WORDS
    ]
    return list(dict.fromkeys(terms))
def find_relevant_resources(snapshot, query):
    normalized_query = query.lower().strip()
    terms = query_terms(query)
    matches = []
    for resource in snapshot.get("resources", []):
        searchable = " ".join(
            [
                resource.get("title", ""),
                resource.get("description", ""),
                resource.get("url", ""),
                resource.get("category") or "",
            ]
        ).lower()
        score = 0
        for term in terms:
            if term in resource.get("title", "").lower():
                score += 5
            elif term in searchable:
                score += 2
        if normalized_query and normalized_query in searchable:
            score += 8
        calculation_query = re.search(
            r"tool|calculate|calculator|audit|formula|solve|"
            r"check|gst|erp|revenue",
            query,
            flags=re.IGNORECASE,
        )
        if (
            resource.get("kind") == "tool"
            and calculation_query
        ):
            score += 3
        if score > 0:
            copied_resource = dict(resource)
            copied_resource["_score"] = score
            matches.append(copied_resource)
    matches.sort(
        key=lambda item: item.get("_score", 0),
        reverse=True,
    )
    clean_matches = []
    for resource in matches[:6]:
        resource.pop("_score", None)
        clean_matches.append(resource)
    return clean_matches
def get_affiliate_suggestion(query):
    transfer_query = re.search(
        r"wise|paypal|remittance|transfer|cross[- ]?border|"
        r"send money|विदेश|पैसे भेज",
        query,
        flags=re.IGNORECASE,
    )
    if not transfer_query:
        return None
    affiliate_url = os.environ.get("WISE_AFFILIATE_URL")
    if not affiliate_url:
        return None
    return {
        "label": "Wise account offer",
        "disclosure": (
            "If you want to open a Wise account, signing up through "
            "this link may waive the fee on your first transfer. "
            "This is an affiliate link."
        ),
        "url": affiliate_url,
    }
def resource_context(resources):
    if not resources:
        return "No matching first-party resources were found."
    lines = []
    for resource in resources:
        lines.append(
            "- "
            f"{resource.get('title')} | "
            f"{resource.get('site')} | "
            f"{resource.get('kind')} | "
            f"{resource.get('url')} | "
            f"{resource.get('description')}"
        )
    return "\n".join(lines)
# ============================================================
# LANGUAGE DETECTION
# ============================================================
def detect_language(text):
    if re.search(r"[\u0900-\u097F]", text):
        return "Hindi"
    if re.search(
        r"\b(mujhe|batao|baare|mein|kya|hai|ke|par|ka|ki|ko|"
        r"aap|apko|chahiye|samjhao|karo|karna)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return "Hinglish"
    if re.search(r"[\u0400-\u04FF]", text):
        return "Russian"
    if re.search(r"[\u0600-\u06FF]", text):
        return "Arabic"
    if (
        re.search(r"[À-ÿ]", text)
        and re.search(
            r"\b(le|la|les|des|une|pour|avec)\b",
            text,
            flags=re.IGNORECASE,
        )
    ):
        return "French"
    if re.search(
        r"\b(der|die|das|und|für|mit|eine)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return "German"
    if re.search(
        r"\b(el|la|los|las|para|con|una)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return "Spanish"
    return "English"
# ============================================================
# GEMINI API
# ============================================================
def generate_gemini_answer(query, history, resources, language):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured in environment variables."
        )
    prompt = f"""
You are ServiceMoney Master AI, a careful multilingual assistant
created by Anurag Panchal.
You represent:
- ServiceMoney.in
- AllRoundUpdate.com
- Educationanurag YouTube channel
Reply in the same language as the user. The requested language is:
{language}
Rules:
1. Answer the user's actual question first.
2. Never repeat a generic greeting or old fallback answer.
3. Use general knowledge for ordinary questions.
4. Only mention a first-party article, tool, video, category, image,
   or page when it appears in the verified resource list below.
5. Do not invent URLs, categories, pagination numbers, tools, images,
   or website content.
6. If a matching tool exists, explain what the user can do with it.
7. If the best resource is on AllRoundUpdate.com, say so clearly.
8. If the best resource is on ServiceMoney.in, say so clearly.
9. If no first-party resource matches, answer normally without
   pretending that a site resource exists.
10. Do not copy full articles or long copyrighted passages.
11. Give original explanations and link users to the source pages.
12. For legal, tax, financial, or compliance questions, avoid
    absolute certainty and suggest professional verification when
    appropriate.
13. Keep the response concise but useful.
Verified first-party resource candidates:
{resource_context(resources)}
Conversation history:
{json.dumps(history[-12:], ensure_ascii=False)}
Current user question:
{query}
""".strip()
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
    )
    request_body = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "maxOutputTokens": 8192,
        },
    }
    for attempt in range(2):
        try:
            response = requests.post(
                endpoint,
                params={"key": api_key},
                headers={"Content-Type": "application/json"},
                json=request_body,
                timeout=45,
            )
        except requests.Timeout as error:
            logger.warning("Gemini request timed out: %s", error)
            raise TemporaryAssistantError(
                TEMPORARY_ASSISTANT_MESSAGE
            ) from error
        except requests.RequestException as error:
            if attempt == 0:
                sleep(0.75)
                continue
            logger.warning("Gemini network request failed: %s", error)
            raise TemporaryAssistantError(
                TEMPORARY_ASSISTANT_MESSAGE
            ) from error
        if response.status_code in TRANSIENT_HTTP_STATUSES:
            if attempt == 0:
                sleep(0.75)
                continue
            logger.warning(
                "Gemini temporary HTTP error %s: %s",
                response.status_code,
                response.text[:300],
            )
            raise TemporaryAssistantError(
                TEMPORARY_ASSISTANT_MESSAGE
            )
        if not response.ok:
            detail = response.text[:300].replace("\n", " ")
            raise RuntimeError(
                f"Gemini request failed with HTTP "
                f"{response.status_code}: {detail}"
            )
        try:
            payload = response.json()
        except ValueError as error:
            raise RuntimeError(
                "Gemini returned an invalid JSON response."
            ) from error
        candidates = payload.get("candidates", [])
        if not candidates:
            raise RuntimeError("Gemini returned no candidates.")
        parts = (
            candidates[0]
            .get("content", {})
            .get("parts", [])
        )
        answer = "".join(
            part.get("text", "")
            for part in parts
            if isinstance(part, dict)
        ).strip()
        if not answer:
            raise RuntimeError("Gemini returned an empty response.")
        return answer
    raise TemporaryAssistantError(TEMPORARY_ASSISTANT_MESSAGE)
# ============================================================
# API ROUTES
# ============================================================
@app.get("/ping")
@app.get("/api/healthz")
def health_check():
    return jsonify({"status": "ok"}), 200
@app.get("/api/assistant/knowledge-status")
def knowledge_status():
    try:
        snapshot = get_knowledge_snapshot()
        return jsonify(
            {
                "refreshedAt": snapshot["refreshedAt"],
                "sources": snapshot["sources"],
            }
        ), 200
    except Exception:
        logger.exception("Knowledge status request failed")
        return jsonify(
            {
                "error": (
                    "Live knowledge sources are temporarily unavailable."
                )
            }
        ), 503
def chat_handler():
    data = request.get_json(silent=True) or {}
    query = str(data.get("query", "")).strip()
    if not query:
        return jsonify(
            {
                "error": (
                    "Please enter a question up to 4,000 characters."
                )
            }
        ), 400
    if len(query) > 4000:
        return jsonify(
            {
                "error": (
                    "Please enter a question up to 4,000 characters."
                )
            }
        ), 400
    raw_history = data.get("history", [])
    history = []
    if isinstance(raw_history, list):
        for turn in raw_history[-12:]:
            if not isinstance(turn, dict):
                continue
            role = turn.get("role")
            content = turn.get("content")
            if role in ("user", "assistant") and isinstance(content, str):
                history.append(
                    {
                        "role": role,
                        "content": content[:4000],
                    }
                )
    try:
        snapshot = get_knowledge_snapshot()
        resources = find_relevant_resources(snapshot, query)
        language = detect_language(query)
        answer = generate_gemini_answer(
            query=query,
            history=history,
            resources=resources,
            language=language,
        )
        return jsonify(
            {
                "response": answer,
                "language": language,
                "resources": resources,
                "affiliate": get_affiliate_suggestion(query),
                "knowledgeUpdatedAt": snapshot["refreshedAt"],
            }
        ), 200
    except TemporaryAssistantError:
        logger.warning(
            "Temporary assistant provider failure for query."
        )
       return jsonify(
            {
                "error": TEMPORARY_ASSISTANT_MESSAGE,
            }
        )

