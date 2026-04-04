import requests
import os
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

COUNCIL_MODELS = ["qwen/qwen3.6-plus:free", "arcee-ai/trinity-large-preview:free"]
CHAIRMAN_MODEL = "arcee-ai/trinity-large-preview:free"

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
   "إضافة ملف البوت"
