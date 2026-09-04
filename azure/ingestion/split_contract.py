import re
import pdfplumber

# PDFファイルを読み込んで、全ページの文章を1つにつなげる
full_text = ""
with pdfplumber.open("docs/documents/test-contract-01.pdf") as pdf:
    for page in pdf.pages:
        full_text += page.extract_text() + "\n"

# 「第◯条」を区切りとして、条文ごとに分割する
# 正規表現：「第」+ 数字 + 「条」というパターンを探す
pattern = r"(第[0-9０-９]+条)"
parts = re.split(pattern, full_text)

# 分割結果を確認のため表示する
print(f"分割された数: {len(parts)}")
print("------")
for part in parts:
    print(repr(part[:50]))  # 各部分の先頭50文字だけ表示
    print("------")

# 見出し(第◯条)と本文をペアにして、条文ごとの辞書のリストにする
articles = []
current_title = None

for part in parts:
    part = part.strip()  # 前後の余計な空白・改行を削除
    if not part:
        continue  # 空っぽの要素はスキップ

    if re.match(r"^第[0-9０-９]+条", part):
        # これは「見出し」部分
        current_title = part
    else:
        # これは「本文」部分
        if current_title:
            articles.append({
                "title": current_title,
                "body": part
            })
            current_title = None

# 結果を確認
print(f"\n条文の数: {len(articles)}")
for a in articles:
    print(f"[{a['title']}] {a['body'][:40]}...")

import os
from dotenv import load_dotenv
from openai import AzureOpenAI

# .envファイルから設定を読み込む
load_dotenv()

endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
api_key = os.getenv("AZURE_OPENAI_KEY")
deployment_name = os.getenv("EMBEDDING_DEPLOYMENT_NAME")

# Azure OpenAIに接続するクライアントを準備する
client = AzureOpenAI(
    azure_endpoint=endpoint,
    api_key=api_key,
    api_version="2024-02-01"
)

# 試しに、1件目の条文だけをベクトル化してみる
sample_text = articles[0]["body"]
response = client.embeddings.create(
    model=deployment_name,
    input=sample_text
)

vector = response.data[0].embedding
print(f"\nベクトルの次元数: {len(vector)}")
print(f"最初の5個の値: {vector[:5]}")

from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
import hashlib

search_endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
search_key = os.getenv("AZURE_SEARCH_KEY")
index_name = os.getenv("AZURE_SEARCH_INDEX_NAME")

search_client = SearchClient(
    endpoint=search_endpoint,
    index_name=index_name,
    credential=AzureKeyCredential(search_key)
)

# --- 前回のテスト（ページ単位の粗い分割）で登録されたデータを、一旦すべて消す ---
existing_docs = search_client.search(search_text="*", select=["chunk_id"])
ids_to_delete = [{"chunk_id": doc["chunk_id"]} for doc in existing_docs]
if ids_to_delete:
    search_client.delete_documents(documents=ids_to_delete)
    print(f"削除した件数: {len(ids_to_delete)}")

# --- 11件の条文を、それぞれベクトル化してアップロードする ---
upload_docs = []
for i, article in enumerate(articles):
    response = client.embeddings.create(
        model=deployment_name,
        input=article["body"]
    )
    vector = response.data[0].embedding

    # ユニークなIDを作る（ファイル名+連番からハッシュを作成）
    doc_id = hashlib.md5(f"test-contract-01_{i}".encode()).hexdigest()

    upload_docs.append({
        "chunk_id": doc_id,
        "parent_id": "test-contract-01",
        "chunk": article["body"],
        "title": "test-contract-01.pdf",
        "header_1": article["title"],
        "text_vector": vector
    })

result = search_client.upload_documents(documents=upload_docs)
print(f"\nアップロード完了: {len(upload_docs)}件")

