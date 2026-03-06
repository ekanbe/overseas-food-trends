"""ポッドキャスト用画像付きまとめページ生成モジュール.

Notion DBから日報ページを取得 → トレンドキーワード抽出 →
Pexels APIで画像検索 → 日付別HTMLページを生成。
GitHub Pagesで配信し、ポッドキャスト聴取中に画像確認する用途。
"""

import json
import logging
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))
DOCS_DIR = Path(__file__).resolve().parent.parent / "docs" / "podcast"

# ────────────────────────────────────────────
# 1. Notion からページ取得
# ────────────────────────────────────────────

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _notion_request(method: str, path: str, body: dict | None = None) -> dict:
    """Notion API に直接HTTPリクエストを送信."""
    token = os.environ.get("NOTION_TOKEN", "")
    url = f"{NOTION_API_BASE}/{path}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }

    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, method=method, headers=headers, data=data)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _format_database_id(db_id: str) -> str:
    """ハイフンなし32文字ならUUID形式に変換."""
    if len(db_id) == 32 and "-" not in db_id:
        return f"{db_id[:8]}-{db_id[8:12]}-{db_id[12:16]}-{db_id[16:20]}-{db_id[20:]}"
    return db_id


def fetch_latest_daily_page(target_date: str | None = None) -> dict | None:
    """Notion DBから指定日（デフォルト: 今日）の日報ページを取得.

    Returns:
        {"title": str, "date": str, "page_id": str, "blocks": list} or None
    """
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        logger.warning("NOTION_TOKEN が未設定")
        return None

    database_id = os.environ.get("NOTION_DATABASE_ID", "")
    if not database_id:
        logger.warning("NOTION_DATABASE_ID が未設定")
        return None

    database_id = _format_database_id(database_id)

    if not target_date:
        target_date = datetime.now(JST).strftime("%Y-%m-%d")

    try:
        # 日付フィルタで日報ページを検索
        response = _notion_request("POST", f"databases/{database_id}/query", {
            "filter": {
                "and": [
                    {"property": "日付", "date": {"equals": target_date}},
                    {"property": "種別", "select": {"equals": "日報"}},
                ]
            },
            "page_size": 1,
        })

        results = response.get("results", [])
        if not results:
            logger.warning("日報ページが見つかりません: %s", target_date)
            return None

        page = results[0]
        page_id = page["id"]

        # タイトル取得
        title_prop = page.get("properties", {}).get("タイトル", {})
        title_arr = title_prop.get("title", [])
        title = title_arr[0]["plain_text"] if title_arr else f"日報 {target_date}"

        # ページのブロック（本文）を全取得
        blocks = _fetch_all_blocks(page_id)

        return {
            "title": title,
            "date": target_date,
            "page_id": page_id,
            "blocks": blocks,
        }

    except Exception as e:
        logger.error("Notion ページ取得失敗: %s", e)
        return None


def _fetch_all_blocks(block_id: str) -> list[dict]:
    """ページの全ブロックをページネーション対応で取得."""
    blocks = []
    cursor = None
    while True:
        params = f"page_size=100"
        if cursor:
            params += f"&start_cursor={cursor}"
        resp = _notion_request("GET", f"blocks/{block_id}/children?{params}")
        blocks.extend(resp.get("results", []))
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return blocks


# ────────────────────────────────────────────
# 2. キーワード抽出
# ────────────────────────────────────────────

def extract_keywords(blocks: list[dict]) -> list[dict]:
    """Notionブロックからトレンドキーワードを抽出.

    heading_3 ブロックから「【N位】EnglishName（日本語名）」パターンを検出し、
    その直後の段落からコンテキスト情報も収集する。

    Returns:
        [{"rank": int, "name_en": str, "name_ja": str, "context": str}, ...]
    """
    keywords = []
    # 【N位】パターン
    rank_pattern = re.compile(r"【(\d+)位】(.+?)(?:（(.+?)）)?$")

    for i, block in enumerate(blocks):
        block_type = block.get("type", "")
        if block_type != "heading_3":
            continue

        text = _extract_plain_text(block.get("heading_3", {}))
        match = rank_pattern.match(text)
        if not match:
            continue

        rank = int(match.group(1))
        name_en = match.group(2).strip()
        name_ja = match.group(3).strip() if match.group(3) else ""

        # 直後の段落からコンテキストを集める
        context_lines = []
        for j in range(i + 1, min(i + 6, len(blocks))):
            next_block = blocks[j]
            next_type = next_block.get("type", "")
            if next_type in ("heading_2", "heading_3", "divider"):
                break
            if next_type == "paragraph":
                para_text = _extract_plain_text(next_block.get("paragraph", {}))
                if para_text:
                    context_lines.append(para_text)

        keywords.append({
            "rank": rank,
            "name_en": name_en,
            "name_ja": name_ja,
            "context": "\n".join(context_lines),
        })

    # アジア市場のヘッドラインも抽出（heading_3 配下の ▸ で始まる段落）
    asia_section = False
    for block in blocks:
        block_type = block.get("type", "")
        if block_type == "heading_2":
            text = _extract_plain_text(block.get("heading_2", {}))
            asia_section = "アジア" in text
            continue
        if asia_section and block_type == "paragraph":
            text = _extract_plain_text(block.get("paragraph", {}))
            if text.startswith("▸ "):
                headline = text[2:].strip()
                if headline:
                    keywords.append({
                        "rank": 0,
                        "name_en": headline,
                        "name_ja": "",
                        "context": "",
                    })

    return keywords


def _extract_plain_text(block_content: dict) -> str:
    """リッチテキストブロックからプレーンテキストを抽出."""
    parts = block_content.get("rich_text", [])
    return "".join(p.get("plain_text", "") for p in parts)


# ────────────────────────────────────────────
# 3. Pexels API で画像検索
# ────────────────────────────────────────────

def _is_searchable_keyword(kw: dict) -> bool:
    """画像検索に適したキーワードか判定.

    英語の食品名・料理名が含まれるものは画像検索向き。
    日本語のみの抽象的なヘッドラインは不向き。
    """
    name = kw.get("name_en", "")
    # ASCII英字が含まれていれば具体的な食品名の可能性が高い
    has_english = bool(re.search(r"[a-zA-Z]{3,}", name))
    return has_english


def search_images(keywords: list[dict], max_per_keyword: int = 3) -> list[dict]:
    """キーワードごとにPexelsで画像を検索.

    具体的な食品名（英語名あり）のみ画像検索し、
    抽象的なキーワードはGoogle画像検索リンクにフォールバック。

    Returns:
        [{"name_en": str, "name_ja": str, "rank": int, "images": [{"url": str, "title": str, "source": str}]}]
    """
    api_key = os.environ.get("PEXELS_API_KEY", "")
    if not api_key:
        logger.warning("PEXELS_API_KEY が未設定。フォールバック画像を使用します")
        return _fallback_image_results(keywords)

    results = []
    for kw in keywords:
        if _is_searchable_keyword(kw):
            query = f"{kw['name_en']} food"
            images = _pexels_search(api_key, query, max_per_keyword)
            results.append({
                "name_en": kw["name_en"],
                "name_ja": kw.get("name_ja", ""),
                "rank": kw.get("rank", 0),
                "context": kw.get("context", ""),
                "images": images,
            })
        else:
            # 抽象的なキーワードはGoogle画像検索リンクのみ
            query = kw["name_en"]
            search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&tbm=isch"
            results.append({
                "name_en": kw["name_en"],
                "name_ja": kw.get("name_ja", ""),
                "rank": kw.get("rank", 0),
                "context": kw.get("context", ""),
                "images": [],
                "search_url": search_url,
            })

    return results


def _pexels_search(api_key: str, query: str, num: int = 3) -> list[dict]:
    """Pexels API で画像検索を実行."""
    try:
        params = urllib.parse.urlencode({
            "query": query,
            "per_page": min(num, 15),
            "size": "medium",
        })
        url = f"https://api.pexels.com/v1/search?{params}"

        req = urllib.request.Request(url, headers={
            "Authorization": api_key,
            "User-Agent": "FoodTrendBot/1.0",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        photos = data.get("photos", [])
        return [
            {
                "url": photo.get("src", {}).get("large", ""),
                "title": photo.get("alt", "") or photo.get("photographer", ""),
                "source": f"Pexels / {photo.get('photographer', '')}",
                "page_url": photo.get("url", ""),
            }
            for photo in photos
        ]

    except Exception as e:
        logger.warning("画像検索失敗 (%s): %s", query, e)
        return []


def _fallback_image_results(keywords: list[dict]) -> list[dict]:
    """API未設定時のフォールバック: Google画像検索リンクを生成."""
    results = []
    for kw in keywords:
        query = kw["name_en"]
        search_url = f"https://www.google.com/search?q={urllib.parse.quote(query + ' food')}&tbm=isch"
        results.append({
            "name_en": kw["name_en"],
            "name_ja": kw.get("name_ja", ""),
            "rank": kw.get("rank", 0),
            "context": kw.get("context", ""),
            "images": [],
            "search_url": search_url,
        })
    return results


# ────────────────────────────────────────────
# 4. HTML ページ生成
# ────────────────────────────────────────────

def generate_html(date_str: str, title: str, image_results: list[dict]) -> str:
    """日付別の画像付きまとめHTMLを生成."""
    # トレンドTOP（rank > 0）とその他に分類
    top_trends = sorted([r for r in image_results if r["rank"] > 0], key=lambda x: x["rank"])
    other_items = [r for r in image_results if r["rank"] == 0]

    trend_sections = []
    for item in top_trends:
        trend_sections.append(_render_trend_section(item))

    other_sections = []
    for item in other_items:
        other_sections.append(_render_other_section(item))

    other_html = ""
    if other_sections:
        other_html = f"""
    <h2>アジア市場トレンド</h2>
    {"".join(other_sections)}
"""

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Hiragino Kaku Gothic ProN', sans-serif;
      background: #0a0a0a;
      color: #e0e0e0;
      line-height: 1.6;
      padding: 20px;
      max-width: 900px;
      margin: 0 auto;
    }}
    header {{
      text-align: center;
      padding: 30px 0;
      border-bottom: 1px solid #333;
      margin-bottom: 30px;
    }}
    header h1 {{
      font-size: 1.5rem;
      color: #fff;
      margin-bottom: 8px;
    }}
    header .date {{
      color: #888;
      font-size: 0.95rem;
    }}
    h2 {{
      font-size: 1.3rem;
      color: #4fc3f7;
      margin: 30px 0 15px;
      padding-bottom: 8px;
      border-bottom: 1px solid #333;
    }}
    .trend-card {{
      background: #1a1a2e;
      border-radius: 12px;
      padding: 20px;
      margin-bottom: 25px;
      border: 1px solid #2a2a4a;
    }}
    .trend-card h3 {{
      font-size: 1.15rem;
      color: #fff;
      margin-bottom: 10px;
    }}
    .trend-card .rank {{
      display: inline-block;
      background: #ff6b35;
      color: #fff;
      padding: 2px 10px;
      border-radius: 20px;
      font-size: 0.85rem;
      font-weight: bold;
      margin-right: 8px;
    }}
    .trend-card .context {{
      color: #aaa;
      font-size: 0.9rem;
      margin: 10px 0;
      white-space: pre-line;
    }}
    .image-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
      gap: 12px;
      margin-top: 15px;
    }}
    .image-grid figure {{
      background: #111;
      border-radius: 8px;
      overflow: hidden;
    }}
    .image-grid img {{
      width: 100%;
      height: 200px;
      object-fit: cover;
      display: block;
      cursor: pointer;
      transition: opacity 0.2s;
    }}
    .image-grid img:hover {{ opacity: 0.8; }}
    .image-grid img.error {{ display: none; }}
    .image-grid figcaption {{
      padding: 8px 10px;
      font-size: 0.8rem;
      color: #888;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .fallback-link {{
      display: inline-block;
      margin-top: 10px;
      color: #4fc3f7;
      text-decoration: none;
      font-size: 0.9rem;
    }}
    .fallback-link:hover {{ text-decoration: underline; }}
    .other-item {{
      background: #1a1a2e;
      border-radius: 8px;
      padding: 15px;
      margin-bottom: 15px;
      border: 1px solid #2a2a4a;
    }}
    .other-item h3 {{
      font-size: 1rem;
      color: #e0e0e0;
      margin-bottom: 8px;
    }}
    .nav {{
      text-align: center;
      padding: 30px 0;
      border-top: 1px solid #333;
      margin-top: 30px;
    }}
    .nav a {{
      color: #4fc3f7;
      text-decoration: none;
      margin: 0 15px;
      font-size: 0.95rem;
    }}
    .nav a:hover {{ text-decoration: underline; }}
    @media (max-width: 600px) {{
      body {{ padding: 12px; }}
      .image-grid {{ grid-template-columns: 1fr; }}
      .image-grid img {{ height: 180px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>{title}</h1>
    <div class="date">{date_str}</div>
  </header>

  <h2>注目トレンド TOP3</h2>
  {"".join(trend_sections)}
  {other_html}

  <nav class="nav">
    <a href="index.html">一覧に戻る</a>
  </nav>

  <script>
    // 画像読み込みエラー時に非表示
    document.querySelectorAll('.image-grid img').forEach(img => {{
      img.addEventListener('error', () => {{
        img.closest('figure').style.display = 'none';
      }});
    }});
  </script>
</body>
</html>"""
    return html


def _render_trend_section(item: dict) -> str:
    """トレンドTOP3のHTML."""
    rank = item["rank"]
    name_en = _escape_html(item["name_en"])
    name_ja = _escape_html(item.get("name_ja", ""))
    name_display = f"{name_en}（{name_ja}）" if name_ja else name_en
    context = _escape_html(item.get("context", ""))

    images_html = ""
    if item.get("images"):
        figures = []
        for img in item["images"]:
            img_url = _escape_html(img["url"])
            img_title = _escape_html(img.get("title", ""))
            source = _escape_html(img.get("source", ""))
            figures.append(f"""      <figure>
        <a href="{img_url}" target="_blank" rel="noopener">
          <img src="{img_url}" alt="{img_title}" loading="lazy">
        </a>
        <figcaption>{source}</figcaption>
      </figure>""")
        images_html = f"""    <div class="image-grid">
{chr(10).join(figures)}
    </div>"""
    elif item.get("search_url"):
        search_url = _escape_html(item["search_url"])
        images_html = f'    <a class="fallback-link" href="{search_url}" target="_blank" rel="noopener">Google画像検索で見る &rarr;</a>'

    context_html = ""
    if context:
        context_html = f'    <div class="context">{context}</div>'

    return f"""  <div class="trend-card">
    <h3><span class="rank">{rank}位</span> {name_display}</h3>
{context_html}
{images_html}
  </div>
"""


def _render_other_section(item: dict) -> str:
    """アジア市場等のHTML."""
    name = _escape_html(item["name_en"])
    images_html = ""
    if item.get("images"):
        figures = []
        for img in item["images"][:2]:
            img_url = _escape_html(img["url"])
            source = _escape_html(img.get("source", ""))
            figures.append(f"""      <figure>
        <a href="{img_url}" target="_blank" rel="noopener">
          <img src="{img_url}" alt="{name}" loading="lazy">
        </a>
        <figcaption>{source}</figcaption>
      </figure>""")
        images_html = f"""    <div class="image-grid">
{chr(10).join(figures)}
    </div>"""
    elif item.get("search_url"):
        search_url = _escape_html(item["search_url"])
        images_html = f'    <a class="fallback-link" href="{search_url}" target="_blank" rel="noopener">Google画像検索で見る &rarr;</a>'

    return f"""  <div class="other-item">
    <h3>{name}</h3>
{images_html}
  </div>
"""


def _escape_html(text: str) -> str:
    """HTML特殊文字をエスケープ."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


# ────────────────────────────────────────────
# 5. インデックスページ生成
# ────────────────────────────────────────────

def generate_index_html(pages: list[dict]) -> str:
    """日付別ページ一覧のインデックスHTML.

    Args:
        pages: [{"date": str, "title": str, "filename": str}, ...]
    """
    # 日付降順でソート
    pages_sorted = sorted(pages, key=lambda x: x["date"], reverse=True)

    rows = []
    for p in pages_sorted:
        date = _escape_html(p["date"])
        title = _escape_html(p["title"])
        fname = _escape_html(p["filename"])
        rows.append(f'      <li><a href="{fname}">{date} - {title}</a></li>')

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>海外フードトレンド - ポッドキャスト画像まとめ</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Hiragino Kaku Gothic ProN', sans-serif;
      background: #0a0a0a;
      color: #e0e0e0;
      line-height: 1.8;
      padding: 20px;
      max-width: 700px;
      margin: 0 auto;
    }}
    header {{
      text-align: center;
      padding: 40px 0 30px;
      border-bottom: 1px solid #333;
      margin-bottom: 30px;
    }}
    header h1 {{
      font-size: 1.4rem;
      color: #fff;
      margin-bottom: 8px;
    }}
    header p {{
      color: #888;
      font-size: 0.9rem;
    }}
    ul {{
      list-style: none;
    }}
    li {{
      padding: 12px 0;
      border-bottom: 1px solid #1a1a1a;
    }}
    a {{
      color: #4fc3f7;
      text-decoration: none;
      font-size: 1rem;
    }}
    a:hover {{ text-decoration: underline; }}
    .empty {{
      text-align: center;
      color: #666;
      padding: 40px 0;
    }}
  </style>
</head>
<body>
  <header>
    <h1>海外フードトレンド</h1>
    <p>ポッドキャスト画像まとめ</p>
  </header>

  {"<p class='empty'>まだページがありません</p>" if not rows else f"<ul>{chr(10).join(rows)}{chr(10)}    </ul>"}
</body>
</html>"""


# ────────────────────────────────────────────
# 6. メイン実行
# ────────────────────────────────────────────

def save_page(html: str, filename: str) -> Path:
    """HTMLファイルを保存."""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    path = DOCS_DIR / filename
    path.write_text(html, encoding="utf-8")
    logger.info("ページ保存: %s", path)
    return path


def update_index():
    """既存のHTMLページを走査してインデックスを更新."""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    pages = []
    for html_file in sorted(DOCS_DIR.glob("????-??-??.html")):
        date_str = html_file.stem
        # タイトルをHTMLから抽出
        content = html_file.read_text(encoding="utf-8")
        title_match = re.search(r"<title>(.+?)</title>", content)
        title = title_match.group(1) if title_match else date_str
        pages.append({
            "date": date_str,
            "title": title,
            "filename": html_file.name,
        })

    index_html = generate_index_html(pages)
    save_page(index_html, "index.html")
    logger.info("インデックス更新: %d ページ", len(pages))


def run(target_date: str | None = None):
    """ポッドキャスト画像ページの生成を実行.

    Args:
        target_date: 対象日付（YYYY-MM-DD）。Noneなら今日。
    """
    logger.info("=== ポッドキャスト画像ページ生成 開始 ===")

    if not target_date:
        target_date = datetime.now(JST).strftime("%Y-%m-%d")

    # Step 1: Notion からページ取得
    page_data = fetch_latest_daily_page(target_date)
    if not page_data:
        logger.error("Notionからデータを取得できませんでした")
        return None

    # Step 2: キーワード抽出
    keywords = extract_keywords(page_data["blocks"])
    if not keywords:
        logger.warning("キーワードが抽出できませんでした")
        return None
    logger.info("抽出キーワード: %d 件", len(keywords))

    # Step 3: 画像検索
    image_results = search_images(keywords)

    # Step 4: HTML生成
    html = generate_html(target_date, page_data["title"], image_results)

    # Step 5: 保存
    filename = f"{target_date}.html"
    save_page(html, filename)

    # Step 6: インデックス更新
    update_index()

    logger.info("=== ポッドキャスト画像ページ生成 完了 ===")
    return DOCS_DIR / filename


if __name__ == "__main__":
    import argparse
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="ポッドキャスト画像ページ生成")
    parser.add_argument("--date", help="対象日付 (YYYY-MM-DD)", default=None)
    args = parser.parse_args()

    run(args.date)
