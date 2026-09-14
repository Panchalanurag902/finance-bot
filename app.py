import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai

app = Flask(__name__)
# CORS चालू करना ज़रूरी है ताकि आपकी वर्डप्रेस साइट इस बैकएंड से बात कर सके
CORS(app)

# आपकी भेजी हुई बिल्कुल नई और असली चाबी यहाँ सुरक्षित है
GEMINI_API_KEY = "AQ.Ab8RN6IPDnNb7qH7TkjP7PwxZqPFLjXGsNdhI-4_dWDT_Y8GyA"
genai.configure(api_key=GEMINI_API_KEY)

@app.route('/ping', methods=['GET'])
def ping():
    # यह वेबसाइट खुलते ही बोट की सुस्ती (Cold Start) को खत्म करने के लिए है
    return jsonify({"status": "awake"}), 200

@app.route('/ask-ai', methods=['POST'])
def ask_ai():
    data = request.json
    user_query = data.get("query", "")
    
    if not user_query:
        return jsonify({"response": "कृपया अपना सवाल पूछें।"}), 400

    # बॉट का महा-निर्देश (System Prompt) जो आपकी दोनों साइट्स और यूट्यूब को जोड़ता है
    system_instruction = """
    You are 'ServiceMoney Master AI', the official network assistant created by Anurag Panchal. 
    You manage two primary financial platforms: servicemoney.in and allroundupdate.com, along with the YouTube channel @Educationanurag.
    
    CRITICAL BEHAVIOR:
    1. If the user asks about calculations, financial tracking, or revenue matrices, immediately direct them to the 'Audit Risk Calculator' tool in the ERP/Audit section on servicemoney.in.
    2. If the query is about 'GST Rule 37A & 86B', 'Regulatory Debt', or topics hosted on your second site, explicitly tell them: 'This topic is comprehensively covered on our sister website allroundupdate.com under the Finance section on the 2nd Pagination page.' Provide a clear reference to search for that title there.
    3. If the question matches tutorials or explainers found on YouTube (@Educationanurag), summarize the core concept cleanly and recommend checking the channel's specific video walkthroughs.
    4. For personal information, guide them to the About Us or Contact Us sections of servicemoney.in.
    5. Always smoothly insert the Wise Affiliate link when users express a need to send or convert international currency.
    6. COPYRIGHT PROTECTION: For any information sourced from your universal internet knowledge, synthesize and rewrite the entire text completely in your own professional phrasing. Do not copy sentences verbatim from external publishers to avoid any plagiarism or copyright complaints.
    """

    try:
        model = genai.GenerativeModel('gemini-1.5-flash', system_instruction=system_instruction)
        response = model.generate_content(user_query)
        return jsonify({"response": response.text}), 200
    except Exception as e:
        # अगर कभी भी API लिमिट खत्म हो जाए तो यूजर को यह सुंदर बैकअप मैसेज दिखेगा
        return jsonify({"response": "क्षमा करें, मेरा मस्तिष्क अभी बहुत व्यस्त है! आप तब तक हमारी वेबसाइट पर उपलब्ध 'Audit Risk Calculator' टूल का उपयोग करके देख सकते हैं।"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
