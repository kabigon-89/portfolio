import os
import re
import json
import hashlib
import requests
from collections import Counter
import pdfplumber
from dotenv import load_dotenv
from openai import AzureOpenAI
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential

load_dotenv(dotenv_path="azure/ingestion/.env")

# --- 各種クライアントの準備 ---
aoai_client = AzureOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_KEY"),
    api_version="2024-02-01"
)
embedding_deployment = os.getenv("EMBEDDING_DEPLOYMENT_NAME")

search_client = SearchClient(
    endpoint=os.getenv("AZURE_SEARCH_ENDPOINT"),
    index_name=os.getenv("AZURE_SEARCH_INDEX_NAME"),
    credential=AzureKeyCredential(os.getenv("AZURE_SEARCH_KEY"))
)

cs_endpoint = os.getenv("CONTENT_SAFETY_ENDPOINT")
cs_key = os.getenv("CONTENT_SAFETY_KEY")


# --- ① PDFを読み込んで条文ごとに分割する ---
def load_and_split_pdf(path):
    full_text = ""
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            full_text += page.extract_text() + "\n"

    pattern = r"(第[0-9０-９]+条)"
    parts = re.split(pattern, full_text)

    articles = []
    current_title = None
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if re.match(r"^第[0-9０-９]+条", part):
            current_title = part
        else:
            if current_title:
                articles.append({"title": current_title, "body": part})
                current_title = None
    return articles


# --- ② AIにリスク判定させる(Self-Consistency:3回判定) ---
def judge_risk(title, body, n_trials=3):
    prompt = f"""あなたは自治体の土地貸付契約を審査する、GRC専門家です。
以下の条文を読み、賃貸人にとってリスクとなる可能性がある内容かどうかを判定してください。

【条文】
{title}
{body}

【リスクスコアの採点基準】
以下の基準に従って、0〜100点で採点してください。基準から外れた独自の判断はせず、必ずこの基準に沿って点数を決めてください。

- 0〜20点: 一般的・定型的な条文で、実務上のリスクはほぼない
- 21〜40点: 解釈の余地はあるが、通常の運用で問題になりにくい
- 41〜60点: 曖昧な文言があり、当事者間で解釈の相違が生じうる
- 61〜80点: 賃貸人に明確な不利益・義務・制約が生じる可能性がある
- 81〜100点: 契約の根幹に関わる重大な不利益・法的リスクがある(例: 一方的な解除・違約金の欠如・権利の不当な制限等)

【出力形式】
以下のJSON形式のみで回答してください。説明文などは不要です。
{{
  "is_risk": true または false,
  "risk_score": 0から100の整数,
  "score_reason": "採点基準のどの区分に該当すると判断したか、1文で",
  "reason": "判定理由を1〜2文で"
}}
"""
    results = []
    for _ in range(n_trials):
        response = aoai_client.chat.completions.create(
            model="gpt-5-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.choices[0].message.content
        raw = raw.strip().strip("```json").strip("```").strip()
        try:
            results.append(json.loads(raw))
        except json.JSONDecodeError:
            print(f"  [警告] JSON解析に失敗したため、この回はスキップします: {raw[:50]}")
            continue

    if not results:
        # 3回とも失敗した場合の保険
        return {
            "confidence": 0,
            "risk_score": 0,
            "risk_level": "unknown",
            "reason": "AIの応答解析に失敗しました",
            "score_reason": "N/A"
        }

    risk_votes = [r["is_risk"] for r in results]
    majority_vote = Counter(risk_votes).most_common(1)[0][0]  # 多数派の判定
    confidence = risk_votes.count(majority_vote) / n_trials * 100

    scores = [r["risk_score"] for r in results]
    avg_score = sum(scores) / len(scores)

    if avg_score >= 70:
        level_label = "high"
    elif avg_score >= 40:
        level_label = "medium"
    else:
        level_label = "low"

    reason = results[0]["reason"]

    return {
        "confidence": confidence,
        "risk_score": avg_score,
        "risk_level": level_label,
        "reason": reason,
        "score_reason": results[0]["score_reason"]
    }

# --- ③ Groundedness検出 ---
def check_groundedness(grounding_source, ai_answer):
    url = f"{cs_endpoint}/contentsafety/text:detectGroundedness?api-version=2024-09-15-preview"
    headers = {"Ocp-Apim-Subscription-Key": cs_key, "Content-Type": "application/json"}
    body = {
        "domain": "Generic",
        "task": "QnA",
        "qna": {"query": "この条文にリスクはありますか？その理由は？"},
        "text": ai_answer,
        "groundingSources": [grounding_source]
    }
    response = requests.post(url, headers=headers, json=body)
    result = response.json()
    return not result.get("ungroundedDetected", True)  # True=根拠あり


# --- メイン処理 ---
if __name__ == "__main__":
    articles = load_and_split_pdf("docs/documents/test-contract-01.pdf")
    print(f"条文数: {len(articles)}\n")

    for article in articles:
        print(f"=== {article['title']} ===")
        judgement = judge_risk(article["title"], article["body"])
        is_grounded = check_groundedness(article["body"], judgement["reason"])

        print(f"リスクスコア: {judgement['risk_score']:.0f}点（{judgement['risk_level']}）")
        print(f"確信度: {judgement['confidence']:.0f}%")
        print(f"根拠検証: {'OK(根拠あり)' if is_grounded else 'NG(要確認)'}")
        print(f"理由: {judgement['reason']}")
        print(f"採点根拠: {judgement['score_reason']}")
        print()