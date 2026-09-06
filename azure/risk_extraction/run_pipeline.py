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


# --- ② AI判定 ---

RISK_JUDGE_PROMPT = """あなたは自治体の土地貸付契約を審査する、GRC専門家です。
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


def _call_ai_once(title, body):
    """AIに1回だけ問い合わせ、パースした結果を返す。JSON解析に失敗した場合はNoneを返す。"""
    prompt = RISK_JUDGE_PROMPT.format(title=title, body=body)
    response = aoai_client.chat.completions.create(
        model="gpt-5-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    raw = response.choices[0].message.content
    raw = raw.strip().strip("```json").strip("```").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"  [警告] JSON解析に失敗しました: {raw[:50]}")
        return None


def _level_label(score):
    if score >= 70:
        return "high"
    elif score >= 40:
        return "medium"
    else:
        return "low"


def judge_risk_with_self_consistency(title, body, n_trials=3):
    """
    Self-Consistency検証: 同一条文に対しAIをn_trials回呼び出し、
    多数決の一致率を確信度(confidence)として算出する。
    Groundedness検証で根拠が薄いと判定された項目についてのみ呼び出される。
    """
    results = []
    for _ in range(n_trials):
        r = _call_ai_once(title, body)
        if r is not None:
            results.append(r)

    if not results:
        # 複数回試みても全てJSON解析に失敗した場合の保険
        return {
            "confidence": 0,
            "risk_score": 0,
            "risk_level": "unknown",
            "reason": "AIの応答解析に失敗しました",
            "score_reason": "N/A"
        }

    risk_votes = [r["is_risk"] for r in results]
    majority_vote = Counter(risk_votes).most_common(1)[0][0]
    confidence = risk_votes.count(majority_vote) / len(results) * 100

    scores = [r["risk_score"] for r in results]
    avg_score = sum(scores) / len(scores)

    return {
        "confidence": confidence,
        "risk_score": avg_score,
        "risk_level": _level_label(avg_score),
        "reason": results[0]["reason"],
        "score_reason": results[0]["score_reason"]
    }


# --- ③ Groundedness検証 ---
def check_groundedness(grounding_source, ai_answer):
    """
    AIの回答(ai_answer)が、引用元の条文原文(grounding_source)と整合しているかを検証する。
    戻り値: (is_grounded: bool, groundedness_score: float 0〜100)
    ungroundedPercentage(根拠から外れている割合)を100から引く形でスコア化する。

    注意: reasoning=falseのままだと、Azure Content Safetyのgroundedness検出は
    明らかに無関係な内容でもungroundedDetected=falseを返すことがある(Microsoft側でも
    報告されている既知の挙動)。そのためreasoning=trueにし、判定の裏付けとして
    Azure OpenAIのモデルを使わせる。これにはContent Safetyリソース側に
    Azure OpenAIリソースへのアクセス権(マネージドID経由)が付与されている必要がある。
    """
    url = f"{cs_endpoint}/contentsafety/text:detectGroundedness?api-version=2024-09-15-preview"
    headers = {"Ocp-Apim-Subscription-Key": cs_key, "Content-Type": "application/json"}
    body = {
        "domain": "Generic",
        "task": "QnA",
        "qna": {"query": "この条文にリスクはありますか？その理由は？"},
        "text": ai_answer,
        "groundingSources": [grounding_source],
        "reasoning": True,
        "llmResource": {
            "resourceType": "AzureOpenAI",
            "azureOpenAIEndpoint": os.getenv("AZURE_OPENAI_ENDPOINT"),
            "azureOpenAIDeploymentName": "gpt-5-mini"
        }
    }
    response = requests.post(url, headers=headers, json=body)

    if response.status_code != 200:
        # マネージドID経由のアクセス権が未設定の場合などにここで気づけるようにする
        print(f"  [警告] Groundedness APIがエラーを返しました(status={response.status_code}): {response.text[:200]}")
        return False, 0

    result = response.json()

    ungrounded_detected = result.get("ungroundedDetected", True)
    ungrounded_percentage = result.get("ungroundedPercentage", 1.0)
    groundedness_score = (1 - ungrounded_percentage) * 100

    is_grounded = not ungrounded_detected
    return is_grounded, groundedness_score


# --- ④ 信頼度スコアの算出フロー(仕様書5章⑵①準拠) ---
def judge_risk(title, body):
    """
    1. まず1回だけAIに判定させる
    2. その回答をGroundedness検証にかけ、条文原文との整合性を確認する
    3a. 整合性がある(is_grounded=True)場合
        → 追加のAI呼び出しは行わず、Groundednessスコアをそのまま最終的な信頼度スコアとする
    3b. 整合性が低い(is_grounded=False)場合のみ
        → Self-Consistency検証(複数回再推論)を追加実行し、その一致率を最終的な信頼度スコアとする
    """
    first_result = _call_ai_once(title, body)

    if first_result is None:
        # 1回目の応答が壊れていた場合は、根拠検証をスキップしてSelf-Consistencyで立て直す
        result = judge_risk_with_self_consistency(title, body)
        result["is_grounded"] = False
        result["confidence_source"] = "self_consistency"
        return result

    is_grounded, groundedness_score = check_groundedness(body, first_result["reason"])

    if is_grounded:
        return {
            "confidence": groundedness_score,
            "confidence_source": "groundedness",
            "is_grounded": True,
            "risk_score": first_result["risk_score"],
            "risk_level": _level_label(first_result["risk_score"]),
            "reason": first_result["reason"],
            "score_reason": first_result["score_reason"]
        }

    result = judge_risk_with_self_consistency(title, body)
    result["is_grounded"] = False
    result["confidence_source"] = "self_consistency"
    return result


# --- メイン処理 ---
if __name__ == "__main__":
    articles = load_and_split_pdf("docs/documents/test-contract-01.pdf")
    print(f"条文数: {len(articles)}\n")

    for article in articles:
        print(f"=== {article['title']} ===")
        judgement = judge_risk(article["title"], article["body"])

        source_label = "Groundedness" if judgement["confidence_source"] == "groundedness" else "Self-Consistency"
        print(f"リスクスコア: {judgement['risk_score']:.0f}点（{judgement['risk_level']}）")
        print(f"信頼度: {judgement['confidence']:.0f}%（算出元: {source_label}）")
        print(f"根拠検証: {'OK(根拠あり)' if judgement['is_grounded'] else 'NG(要確認のため再推論を実施)'}")
        print(f"理由: {judgement['reason']}")
        print(f"採点根拠: {judgement['score_reason']}")
        print()