"""
check_groundedness()が「根拠が薄い」ケースを正しく検出できるかを確認する簡易テスト。

やっていること:
  第1条の本文(条文原文)に対して、わざと条文の内容とは全く関係のない
  でたらめな「理由」を渡し、is_grounded=False になることを確認する。

  もしこれで is_grounded=True になってしまう場合、
  check_groundedness()側(API呼び出し・レスポンス解析)に問題がある可能性が高い。

実行方法(リポジトリのルートで):
  python azure/risk_extraction/test_groundedness.py
"""

from run_pipeline import load_and_split_pdf, check_groundedness

articles = load_and_split_pdf("docs/documents/test-contract-01.pdf")
first_article = articles[0]

print(f"=== テスト対象: {first_article['title']} ===")
print(f"条文本文: {first_article['body'][:60]}...\n")

# わざと条文の内容と無関係な、でたらめな理由文を用意する
fake_reason = "この条文は、宇宙飛行士の労働時間の上限を定めており、賃貸人に重大な不利益を及ぼす。"

is_grounded, score = check_groundedness(first_article["body"], fake_reason)

print(f"テストに使った(でたらめな)理由: {fake_reason}")
print(f"is_grounded: {is_grounded}")
print(f"groundedness_score: {score:.1f}")

print()
if is_grounded:
    print("[要確認] でたらめな理由なのにis_grounded=Trueになっています。"
          "check_groundedness()の実装かAPI呼び出しを見直してください。")
else:
    print("[OK] でたらめな理由はis_grounded=Falseと正しく判定されました。"
          "Self-Consistency側の分岐も機能するはずです。")