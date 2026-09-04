import re
import pdfplumber

# PDFファイルを読み込んで、全ページの文章を1つにつなげる
full_text = ""
with pdfplumber.open("docs/documents/test-contract-01.pdf") as pdf:
    for page in pdf.pages:
        full_text += page.extract_text() + "\n"

# 「第◯条」を区切りとして、条文ごとに分割する
# 正規表現：「第」+ 数字 + 「条」というパターンを探す
pattern = r"(第[0-9０-９]+条[^\n]*)"
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