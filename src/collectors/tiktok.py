"""TikTok ハッシュタグページの軽量スクレイピング.

TikTokはボット検知が厳しいため、失敗時はスキップする（graceful degradation）。
"""

import json
import logging
import re

import httpx

logger = logging.getLogger(__name__)

FOOD_HASHTAGS = [
    "foodtiktok",
    "recipe",
    "koreanfood",
    "streetfood",
    "dessert",
    "baking",
    "foodtrend",
    "viralrecipe",
    "newdrink",
    "asianfood",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def collect() -> list[dict]:
    """TikTok からハッシュタグ情報を収集。失敗時は空リストを返す."""
    results = []

    for tag in FOOD_HASHTAGS:
        try:
            data = _fetch_hashtag(tag)
            if data:
                results.append(data)
        except Exception as e:
            logger.warning("TikTokハッシュタグ取得失敗 (#%s): %s", tag, e)

    if not results:
        logger.warning("TikTok: 全ハッシュタグ取得失敗。スキップします。")
    else:
        logger.info("TikTok: %d 件取得", len(results))

    return results


def _fetch_hashtag(tag: str) -> dict | None:
    url = f"https://www.tiktok.com/tag/{tag}"

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=15) as client:
        resp = client.get(url)
        resp.raise_for_status()

    html = resp.text

    # SIGI_STATE または __UNIVERSAL_DATA_FOR_REHYDRATION__ からJSON抽出を試みる
    video_count = None
    view_count = None

    # パターン1: SIGI_STATE
    match = re.search(
        r'<script id="SIGI_STATE"[^>]*>(.*?)</script>', html, re.DOTALL
    )
    if match:
        try:
            state = json.loads(match.group(1))
            challenge_info = (
                state.get("ChallengePage", {})
                .get("challengeInfo", {})
                .get("stats", {})
            )
            video_count = challenge_info.get("videoCount")
            view_count = challenge_info.get("viewCount")
        except (json.JSONDecodeError, AttributeError):
            pass

    # パターン2: __UNIVERSAL_DATA_FOR_REHYDRATION__
    if video_count is None:
        match = re.search(
            r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
            html,
            re.DOTALL,
        )
        if match:
            try:
                state = json.loads(match.group(1))
                # ネストされたデータ構造を探索
                default_scope = state.get("__DEFAULT_SCOPE__", {})
                webapp_data = default_scope.get("webapp.challenge-detail", {})
                challenge_info = webapp_data.get("challengeInfo", {})
                stats = challenge_info.get("stats", {})
                video_count = stats.get("videoCount")
                view_count = stats.get("viewCount")
            except (json.JSONDecodeError, AttributeError):
                pass

    if video_count is None and view_count is None:
        logger.debug("TikTok #%s: データ抽出失敗", tag)
        return None

    return {
        "platform": "TikTok",
        "hashtag": f"#{tag}",
        "video_count": video_count,
        "view_count": view_count,
        "url": url,
    }
