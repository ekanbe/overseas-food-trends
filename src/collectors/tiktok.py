"""TikTok の食品関連トレンドを収集.

TikTokはボット検知が厳しいため、複数の方法を試みて失敗時はスキップする。
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
    "trendingfood",
    "foodasmr",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
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
        logger.warning("TikTok: データ取得失敗。スキップします。")
    else:
        logger.info("TikTok: %d 件取得", len(results))

    return results


def _fetch_hashtag(tag: str) -> dict | None:
    url = f"https://www.tiktok.com/tag/{tag}"

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=15) as client:
        resp = client.get(url)
        resp.raise_for_status()

    html = resp.text

    # 複数のJSON抽出パターンを試行
    extractors = [
        _extract_sigi_state,
        _extract_universal_data,
        _extract_next_data,
        _extract_json_ld,
    ]

    for extractor in extractors:
        try:
            result = extractor(html, tag)
            if result:
                return result
        except Exception:
            continue

    # JSONが取れなくても、ページタイトルから情報を抽出
    title_match = re.search(r"<title>(.*?)</title>", html)
    if title_match:
        title = title_match.group(1)
        # タイトルに動画数が含まれている場合がある (例: "123.4K videos")
        count_match = re.search(r"([\d.]+[KMB]?)\s*(?:videos|posts)", title, re.I)
        if count_match:
            return {
                "platform": "TikTok",
                "hashtag": f"#{tag}",
                "video_count_text": count_match.group(1),
                "url": url,
            }

    return None


def _extract_sigi_state(html: str, tag: str) -> dict | None:
    match = re.search(
        r'<script id="SIGI_STATE"[^>]*>(.*?)</script>', html, re.DOTALL
    )
    if not match:
        return None
    state = json.loads(match.group(1))
    stats = (
        state.get("ChallengePage", {})
        .get("challengeInfo", {})
        .get("stats", {})
    )
    if not stats:
        return None
    return {
        "platform": "TikTok",
        "hashtag": f"#{tag}",
        "video_count": stats.get("videoCount"),
        "view_count": stats.get("viewCount"),
        "url": f"https://www.tiktok.com/tag/{tag}",
    }


def _extract_universal_data(html: str, tag: str) -> dict | None:
    match = re.search(
        r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not match:
        return None
    state = json.loads(match.group(1))
    # ネスト構造を探索
    for key in state:
        scope = state[key] if isinstance(state[key], dict) else {}
        for subkey in scope:
            if "challenge" in subkey.lower():
                challenge_data = scope[subkey]
                if isinstance(challenge_data, dict):
                    stats = challenge_data.get("challengeInfo", {}).get("stats", {})
                    if stats:
                        return {
                            "platform": "TikTok",
                            "hashtag": f"#{tag}",
                            "video_count": stats.get("videoCount"),
                            "view_count": stats.get("viewCount"),
                            "url": f"https://www.tiktok.com/tag/{tag}",
                        }
    return None


def _extract_next_data(html: str, tag: str) -> dict | None:
    match = re.search(
        r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL
    )
    if not match:
        return None
    state = json.loads(match.group(1))
    # props.pageProps内を探索
    page_props = state.get("props", {}).get("pageProps", {})
    if page_props:
        return {
            "platform": "TikTok",
            "hashtag": f"#{tag}",
            "data_available": True,
            "url": f"https://www.tiktok.com/tag/{tag}",
        }
    return None


def _extract_json_ld(html: str, tag: str) -> dict | None:
    matches = re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
    )
    for m in matches:
        try:
            data = json.loads(m)
            if isinstance(data, dict) and data.get("name"):
                return {
                    "platform": "TikTok",
                    "hashtag": f"#{tag}",
                    "name": data.get("name"),
                    "description": (data.get("description") or "")[:100],
                    "url": f"https://www.tiktok.com/tag/{tag}",
                }
        except json.JSONDecodeError:
            continue
    return None
