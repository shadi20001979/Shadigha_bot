from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests
import time
import os
from datetime import datetime

app = Flask(__name__, static_folder='.')
CORS(app)

# ========================================
# الإعدادات الأساسية
# ========================================

API_KEY = os.environ.get("OPENROUTER_API_KEY", "sk-or-v1-8714cd")
COUNCIL_MODELS = [
    "qwen/qwen3.6-plus:free",
    "arcee-ai/trinity-large-preview:free",
]
CHAIRMAN_MODEL = "arcee-ai/trinity-large-preview:free"
TIMEOUT = 45
MAX_ANSWER_LENGTH = 400

# ========================================
# دوال مجلس الخبراء
# ========================================

def get_model_short_name(model):
    return model.replace(":free", "").replace("arcee-ai/", "").replace("qwen/", "")

def ask_model(model, question):
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": question}]
            },
            timeout=TIMEOUT
        )
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        return None
    except:
        return None

def process_question(question):
    answers = {}
    for model in COUNCIL_MODELS:
        answer = ask_model(model, question)
        if answer:
            answers[model] = answer
    
    if not answers:
        return "❌ عذراً، لم يتمكن أي خبير من الإجابة حالياً."
    
    synthesis_prompt = f"""السؤال: {question}

إجابات الخبراء:
"""
    for model, answer in answers.items():
        short_name = get_model_short_name(model)
        short_answer = answer[:MAX_ANSWER_LENGTH] if len(answer) > MAX_ANSWER_LENGTH else answer
        synthesis_prompt += f"\nالخبير ({short_name}):\n{short_answer}\n"
    
    synthesis_prompt += "\nقدم إجابة نهائية واحدة شاملة ودقيقة ومنسقة بالعربية."
    
    final_answer = ask_model(CHAIRMAN_MODEL, synthesis_prompt)
    if not final_answer and answers:
        best_model = list(answers.keys())[0]
        final_answer = answers[best_model]
    
    return final_answer

# ========================================
# Routes
# ========================================

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/ask', methods=['POST'])
def ask():
    data = request.json
    question = data.get('question', '').strip()
    history = data.get('history', [])
    
    if not question:
        return jsonify({'error': 'No question provided'}), 400
    
    # إضافة السياق من المحادثة السابقة
    if history:
        context = "\n\nالسياق من المحادثة السابقة:\n"
        for item in history[-3:]:
            context += f"سؤال سابق: {item['question']}\n"
            context += f"إجابة سابقة: {item['answer'][:200]}...\n"
        question = question + context
    
    answer = process_question(question)
    
    return jsonify({
        'answer': answer,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'time': datetime.now().isoformat()})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)