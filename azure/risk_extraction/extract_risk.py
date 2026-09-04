import os
import json
from collections import Counter
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv(dotenv_path="azure/ingestion/.env")

endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
api_key = os.getenv("AZURE_OPENAI_KEY")

client = AzureOpenAI(
    azure_endpoint=endpoint,
    api_key=api_key,
    api_version="2024-02-01"
)

article_title = "第4条"
article_body = "前条の申出は、甲が土地の使用を必要とする事情その他正当な事由があると認められる場合でなければすることができない。"

prompt = f"""あなたは自治体の土地貸付契約を審査する、GRC専門家です。
以下の条文を読み、賃貸人（自治体側/借主側どちらの立場でも構いません）にとってリスクとなる可能性がある内容かどうかを判定してください。

【条文】
{article_title}
{article_body}

【出力形式】
以下のJSON形式のみで回答してください。説明文などは不要です。
{{
  "is_risk": true または false,
  "risk_level": "high", "medium", "low" のいずれか,
  "reason": "判定理由を1〜2文で"
}}
"""

# --- Self-Consistency: 同じ条文を3回判定させる ---
N_TRIALS = 3
results = []

for i in range(N_TRIALS):
    response = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    raw = response.choices[0].message.content

    # AIの返答からJSON部分だけを取り出す(念のため前後の余計な文字を除去)
    raw = raw.strip().strip("```json").strip("```").strip()
    parsed = json.loads(raw)
    results.append(parsed)
    print(f"--- 試行{i+1}回目 ---")
    print(parsed)

# --- 集計:「is_riskがtrue」と判定された回数の割合を確信度とする ---
risk_votes = [r["is_risk"] for r in results]
confidence = risk_votes.count(True) / N_TRIALS * 100

# --- risk_levelは多数決で決める ---
level_votes = Counter([r["risk_level"] for r in results])
final_level = level_votes.most_common(1)[0][0]

print("\n=== 最終結果(Self-Consistency) ===")
print(f"確信度: {confidence:.0f}%")
print(f"リスクレベル(多数決): {final_level}")
print(f"3回の判定結果: {risk_votes}")