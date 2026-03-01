"""小红书（RED / Xiaohongshu）から食品トレンドを収集.

公式APIは存在しないため、Webページからの情報抽出を試みる。
失敗時はGeminiへのヒント情報として検索キーワードを返す。
"""

import json
import logging
import re

import httpx

logger = logging.getLogger(__name__)

# 食品関連の注目キーワード（中国語）
FOOD_KEYWORDS = [
    "网红美食",
    "新茶饮",
    "甜品趋势",
    "奶茶新品",
    "轻食",
    "一人食",
    "烘焙趋势",
    "冰饮",
    "咖啡新品",
    "街头小吃",
    "健康餐",
    "爆款饮品",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def collect() -> list[dict]:
    """小红书から食品トレンド情報を収集."""
    results = []

    for keyword in FOOD_KEYWORDS:
        try:
            data = _fetch_keyword(keyword)
            if data:
                results.append(data)
        except Exception as e:
            logger.warning("小红书取得失敗 (%s): %s", keyword, e)

    if not results:
        # Webスクレイピングが失敗しても、キーワード情報をGeminiに渡す
        logger.warning("小红书: Web取得失敗。キーワードヒントを生成します。")
        results = _generate_keyword_hints()
    else:
        logger.info("小红书: %d 件取得", len(results))

    return results


def _fetch_keyword(keyword: str) -> dict | None:
    """小红书のWebページからキーワード関連情報を抽出."""
    url = f"https://www.xiaohongshu.com/search_result?keyword={keyword}"

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=15) as client:
        resp = client.get(url)
        if resp.status_code in (302, 401, 403, 429):
            return None
        resp.raise_for_status()

    html = resp.text

    # ページタイトルやメタ情報を抽出
    title_match = re.search(r"<title>(.*?)</title>", html)
    meta_match = re.search(
        r'<meta\s+(?:name|property)="(?:description|og:description)"\s+content="([^"]*)"',
        html,
    )

    # JSON-LDデータを抽出
    json_ld_data = None
    json_ld_match = re.search(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
    )
    if json_ld_match:
        try:
            json_ld_data = json.loads(json_ld_match.group(1))
        except json.JSONDecodeError:
            pass

    # SSRされたコンテンツから投稿情報を抽出
    note_matches = re.findall(
        r'"noteId":"([^"]+)".*?"title":"([^"]*)".*?"likeCount":(\d+)',
        html,
    )

    if note_matches:
        notes = []
        for note_id, title, likes in note_matches[:5]:
            notes.append({
                "note_id": note_id,
                "title": title,
                "likes": int(likes),
            })
        return {
            "platform": "小红书",
            "keyword": keyword,
            "notes": notes,
            "url": url,
        }

    if title_match or meta_match:
        return {
            "platform": "小红书",
            "keyword": keyword,
            "title": title_match.group(1) if title_match else "",
            "description": (meta_match.group(1)[:200] if meta_match else ""),
            "url": url,
        }

    return None


def _generate_keyword_hints() -> list[dict]:
    """Web取得に失敗した場合、Geminiに中国トレンドの分析を促すヒントを返す."""
    return [
        {
            "platform": "小红书",
            "type": "keyword_hint",
            "keyword": kw,
            "description": f"小红书で「{kw}」が注目されている可能性。最新の中国食品トレンドを分析してください。",
            "url": f"https://www.xiaohongshu.com/search_result?keyword={kw}",
        }
        for kw in FOOD_KEYWORDS[:6]
    ]
