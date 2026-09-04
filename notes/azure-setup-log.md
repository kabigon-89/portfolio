# Azure構築ログ

## 2026-09-03
- リソースグループ作成：rg-landlease-portfolio（Japan East）
- Foundryリソース作成：aoai-landlease-poc
- デフォルトプロジェクト：proj-default
- モデルデプロイ：gpt-5-mini（動作確認済み）
- サブスクリプション：Azure for Students（AOAI利用可能なことを確認）

## 2026-09-04

### Azure AI Search - チャンク分割の検証と方針転換
- Azure Portalの「データのインポート」ウィザードで自動チャンク分割を試行
- 「ドキュメント レイアウトの検出」を有効にするには、別途マルチサービスアカウント(Content Safety系)が必要と判明 → `cog-landlease-poc`(Japan East)を作成
- ウィザードでの分割は「ページ単位」の粗い分割になり、1チャンクに複数条文が混在する制約を発見
  → 根拠条文の特定精度・監査証跡の観点から不十分と判断し、方針転換
- **方針転換**: インデクサー(Pull型)から、自作Pythonスクリプトによる直接登録(Push型)へ切り替え

### 条文単位チャンク分割スクリプトの自作
- `azure/ingestion/split_contract.py` を新規作成
- `pypdf`で日本語PDFの文字化けが発生 → `pdfplumber`に切り替えて解消
- 正規表現(`第[0-9０-９]+条`)で条文単位に分割するロジックを実装
  - 見出しと本文のペアリングでインデックスずれのバグが発生 → 正規表現パターンを修正して解消(11条文、正しくペアリング確認済み)
- `text-embedding-3-large`でベクトル化し、Azure AI Searchへ直接アップロード(Push方式)
  - 学生サブスクリプションでは「グローバル標準」デプロイのクォータ不足 → 「標準」デプロイ方式に変更して解消
- 検索エクスプローラーで、条文単位(`header_1`に「第◯条」)でのヒットを確認済み

### リスク抽出パイプラインの実装
- `azure/risk_extraction/extract_risk.py` → `run_pipeline.py` として統合
- GPT-5-miniによるリスク判定を実装(条文単体、AIの内蔵知識ベース。RAG化=検索結果を根拠に含める実装は未着手、次回課題)
- **Self-Consistency**: 同一条文を3回判定させ、多数派判定との一致率を「確信度」として算出
  - 初期実装は「is_riskがtrueの割合」を確信度としており、全回falseで一致した場合に確信度0%と誤表示されるバグを発見・修正(多数派との一致率に変更)
- **採点基準の明示化**: リスクスコア(0〜100点)をAIの感覚任せにせず、5段階の採点基準をプロンプトに明記する方式に変更。`score_reason`で該当区分を言語化させ、説明可能性を担保
- **Groundedness検出(Azure AI Content Safety)**:
  - 学生サブスクリプションは `japaneast, malaysiawest, koreacentral, australiaeast, eastasia` のみ許可
  - Groundedness検出の対応リージョンは `East US 2 / West US / Sweden Central` のみ
  - 両者に重複がなく、学生サブスクリプションでは実装不可能と判明
  - → **Pay-As-You-Goサブスクリプション(`landlease-portfolio-payg`)を新規作成**し、`East US 2`にContent Safetyを作成して解決(既存リソースは学生サブスクリプション側にそのまま残存、影響なし)
  - 動作確認: `ungroundedDetected: False` を確認(AIの判定理由が条文内容から逸脱していないことを機械的に検証)
- JSON解析失敗時にプロセス全体が停止する不具合(AIが稀にJSON形式を崩して返す)→ try/exceptでスキップする処理を追加し解消

### 最終結果
- 11条文すべてに対し、リスクスコア・確信度・根拠検証・採点根拠が自動出力されるパイプラインが完成
- 第3条(自動更新条項)がリスクスコア70点(high)で最高値、条文内容と整合性のある妥当な判定結果を確認

### 今後の課題(次回)
- RAG化: Azure AI Searchの検索結果(自治体独自ルール・過去のナレッジ)を判定の根拠として組み込む
- Groundedness検出のロジックを`run_pipeline.py`内の本判定フローに統合(現状は個別ファイルでの検証のみ)
- 採点基準のさらなる精緻化(観点ごとの要素分解)は将来検討