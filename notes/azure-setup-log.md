# Azure構築ログ

## 2026-09-03
- リソースグループ作成：rg-landlease-portfolio（Japan East）
- Foundryリソース作成：aoai-landlease-poc
- デフォルトプロジェクト：proj-default
- モデルデプロイ：gpt-5-mini（動作確認済み）
- サブスクリプション：Azure for Students（AOAI利用可能なことを確認）

## 2026-09-04
- リソース作成：リソースグループ、Foundry(Azure OpenAI)、Blob Storage、AI Search
- モデルデプロイ：gpt-5-mini、text-embedding-3-large
- AI Searchの自動チャンク分割はページ単位となり、条文単位の分割は不可と判明
  → Pythonスクリプトを自作し、正規表現で条文単位に分割、Push方式でインデックスへ直接登録する方式に変更
- リスク抽出パイプライン(run_pipeline.py)を実装
  - GPT-5-miniによるリスク判定(Self-Consistency：3回判定→多数派一致率を確信度化)
  - リスクスコア0-100点(5段階の採点基準をプロンプトに明記)
  - Groundedness検出(Azure AI Content Safety)による根拠検証
    - 検証用サブスクリプションの許可リージョンとGroundedness検出の対応リージョンが一致しなかったため、東部リージョン用に別サブスクリプションを用意して対応
  - 11条文全件で動作確認済み
- リポジトリ構成整理：docs/notes/servicenow/azureフォルダに分割、GitHub Pages公開設定を修正

