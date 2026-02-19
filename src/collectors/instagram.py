"""Instagram の食品関連トレンドをWebページから収集.

Instagram APIは制限が厳しいため、公開ページからの情報取得を試みる。
失敗時はスキップする（graceful degradation）。
"""

import json
import logging
import re

import httpx

logger = logging.getLogger(__name__)

FOOD_HASHTAGS = [
    "foodtrend",
    "viralfood",
    "koreanstreetfood",
    "dessertporn",
    "newfood",
    "trendingrecipe",
    "asiandesssert",
    "drinkstagram",
    "fooddiscovery",
    "streetfoodlover",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def collect() -> list[dict]:
    """Instagram から食品ハッシュタグの情報を収集。失敗時は空リストを返す."""
    results = []

    for tag in FOOD_HASHTAGS:
        try:
            data = _fetch_hashtag(tag)
            if data:
                results.append(data)
        except Exception as e:
            logger.warning("Instagramハッシュタグ取得失敗 (#%s): %s", tag, e)

    if not results:
        logger.warning("Instagram: データ取得失敗。スキップします。")
    else:
        logger.info("Instagram: %d 件取得", len(results))

    return results


def _fetch_hashtag(tag: str) -> dict | None:
    url = f"https://www.instagram.com/explore/tags/{tag}/"

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=15) as client:
        resp = client.get(url)
        if resp.status_code in (302, 401, 403, 429):
            return None
        resp.raise_for_status()

    html = resp.text

    # meta タグから投稿数を抽出
    # 例: <meta content="123,456 Posts - See Instagram photos and videos from '#foodtrend'"
    meta_match = re.search(
        r'<meta\s+content="([\d,.KMB]+)\s*(?:Posts|posts|publications)',
        html,
    )
    post_count = meta_match.group(1) if meta_match else None

    # og:description からも情報を取得
    og_match = re.search(
        r'<meta\s+property="og:description"\s+content="([^"]*)"',
        html,
    )
    description = og_match.group(1)[:150] if og_match else None

    # JSON-LDデータを抽出
    json_ld_match = re.search(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
    )
    if json_ld_match:
        try:
            ld_data = json.loads(json_ld_match.group(1))
            if isinstance(ld_data, dict):
                description = description or (ld_data.get("description") or "")[:150]
        except json.JSONDecodeError:
            pass

    if not post_count and not description:
        return None

    return {
        "platform": "Instagram",
        "hashtag": f"#{tag}",
        "post_count": post_count,
        "description": description,
        "url": url,
    }
