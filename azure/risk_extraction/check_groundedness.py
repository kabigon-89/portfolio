import os
import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path="azure/ingestion/.env")

endpoint = os.getenv("CONTENT_SAFETY_ENDPOINT")
key = os.getenv("CONTENT_SAFETY_KEY")

# --- 根拠となる条文(グラウンディングソース) ---
grounding_source = "前条の申出は、甲が土地の使用を必要とする事情その他正当な事由があると認められる場合でなければすることができない。"

# --- AIが出した回答(さっきextract_risk.pyで得られた理由文の例) ---
ai_answer = "甲の主観的判断に依存して「必要とする事情」や「正当な事由」の基準が明確でないため、借主の申出が恣意的に却下される可能性がある。"

url = f"{endpoint}/contentsafety/text:detectGroundedness?api-version=2024-09-15-preview"

headers = {
    "Ocp-Apim-Subscription-Key": key,
    "Content-Type": "application/json"
}

body = {
    "domain": "Generic",
    "task": "QnA",
    "qna": {
        "query": "この条文にリスクはありますか？その理由は？"
    },
    "text": ai_answer,
    "groundingSources": [grounding_source]
}

print(f"リクエストURL: {url}")
response = requests.post(url, headers=headers, json=body)
print(f"ステータスコード: {response.status_code}")
print(response.json())