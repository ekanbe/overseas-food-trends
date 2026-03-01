"""Naver Blog / Naver Search から韓国の食品トレンドを収集.

Naver Open API (検索API) を使用。未設定時はWebスクレイピングにフォールバック。
"""

import os
import json
import logging
import re

import httpx

logger = logging.getLogger(__name__)

NAVER_CLIENT_ID_ENV = "NAVER_CLIENT_ID"
NAVER_CLIENT_SECRET_ENV = "NAVER_CLIENT_SECRET"

# 韓国の食品トレンドキーワード
FOOD_KEYWORDS = [
    "맛집 트렌드",
    "신메뉴",
    "디저트 트렌드",
    "카페 트렌드",
    "약과",
    "탕후루",
    "무인카페",
    "밀키트",
    "비건",
    "푸드테크",
    "외식 트렌드 2026",
    "음료 트렌드",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}

NAVER_SEARCH_URL = "https://openapi.naver.com/v1/search/blog.json"


def collect() -> list[dict]:
    """Naver から韓国の食品トレンドを収集."""
    client_id = os.environ.get(NAVER_CLIENT_ID_ENV)
    client_secret = os.environ.get(NAVER_CLIENT_SECRET_ENV)

    results = []

    if client_id and client_secret:
        # Naver Open API を使用
        for keyword in FOOD_KEYWORDS:
            try:
                items = _search_api(client_id, client_secret, keyword)
                results.extend(items)
            except Exception as e:
                logger.warning("Naver API検索失敗 (%s): %s", keyword, e)
    else:
        logger.warning("Naver API認証情報が未設定。Webフォールバックを試行")
        for keyword in FOOD_KEYWORDS[:6]:
            try:
                items = _search_web(keyword)
                results.extend(items)
            except Exception as e:
                logger.warning("Naver Web検索失敗 (%s): %s", keyword, e)

    if not results:
        logger.warning("Naver: データ取得失敗。ヒント情報を生成します。")
        results = _generate_hints()
    else:
        logger.info("Naver: %d 件取得", len(results))

    return results


def _search_api(client_id: str, client_secret: str, keyword: str) -> list[dict]:
    """Naver Open Search API でブログ記事を検索."""
    headers = {
        **HEADERS,
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }
    params = {
        "query": keyword,
        "display": 10,
        "sort": "date",
    }

    with httpx.Client(headers=headers, timeout=15) as client:
        resp = client.get(NAVER_SEARCH_URL, params=params)
        resp.raise_for_status()

    data = resp.json()
    items = data.get("items", [])

    results = []
    for item in items:
        title = re.sub(r"<[^>]+>", "", item.get("title", ""))
        description = re.sub(r"<[^>]+>", "", item.get("description", ""))[:200]
        results.append({
            "platform": "Naver Blog",
            "keyword": keyword,
            "title": title,
            "description": description,
            "blogger": item.get("bloggername", ""),
            "url": item.get("link", ""),
            "published_at": item.get("postdate", ""),
        })

    return results


def _search_web(keyword: str) -> list[dict]:
    """Naver WebスクレイピングでGeminiへの情報を取得."""
    url = f"https://search.naver.com/search.naver?where=blog&query={keyword}"

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=15) as client:
        resp = client.get(url)
        if resp.status_code != 200:
            return []

    html = resp.text

    # ブログ記事タイトルを抽出
    title_matches = re.findall(
        r'class="title_link[^"]*"[^>]*>(.*?)</a>',
        html,
        re.DOTALL,
    )

    results = []
    for title_html in title_matches[:10]:
        title = re.sub(r"<[^>]+>", "", title_html).strip()
        if title:
            results.append({
                "platform": "Naver Blog",
                "keyword": keyword,
                "title": title,
                "url": url,
            })

    return results


def _generate_hints() -> list[dict]:
    """Geminiに韓国トレンド分析を促すヒント情報."""
    return [
        {
            "platform": "Naver Blog",
            "type": "keyword_hint",
            "keyword": kw,
            "description": f"Naver Blogで「{kw}」が話題の可能性。韓国の食品トレンドを分析してください。",
        }
        for kw in FOOD_KEYWORDS[:6]
    ]
