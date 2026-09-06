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

## 2026-09-05

- 判定フロー修正：Groundedness検証→条件付きSelf-Consistency検証の2段階フローに変更（無条件で両方実行していたロジックを見直し）
- 信頼度スコアの統合ルールを確定：Groundedness通過時はそのスコアを採用、不通過時のみSelf-Consistencyの一致率を採用
- テストスクリプト（test_groundedness.py）を作成し、判定ロジックが実際に機能するか検証
- Groundedness検証のreasoning機能を試行
  - Content SafetyのマネージドID有効化、Azure OpenAIへのロール割り当て（Cognitive Services User）を設定
  - 対応必須とされるGPT-4o（0513・0806）が両バージョンとも既に廃止済み（新規デプロイ不可）と判明。別サブスクリプション（PAYG、East US 2）でも同様の結果を確認
  - 公式ドキュメントの記載と実際の提供状況に齟齬があることを、REST版ドキュメントの該当箇所で確認
  - reasoning=false（簡易検証）での運用を決定。
