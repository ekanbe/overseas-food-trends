"""抖音（Douyin / 中国版TikTok）から食品トレンドを収集.

公式APIは海外から利用不可のため、Webページとキーワードヒントで対応。
"""

import logging
import re

import httpx

logger = logging.getLogger(__name__)

# 食品関連ハッシュタグ・キーワード
FOOD_HASHTAGS = [
    "美食推荐",
    "网红饮品",
    "新茶饮",
    "甜品",
    "烘焙",
    "咖啡",
    "奶茶",
    "轻食沙拉",
    "火锅",
    "街头美食",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def collect() -> list[dict]:
    """抖音から食品トレンド情報を収集."""
    results = []

    for tag in FOOD_HASHTAGS:
        try:
            data = _fetch_hashtag(tag)
            if data:
                results.append(data)
        except Exception as e:
            logger.warning("抖音取得失敗 (#%s): %s", tag, e)

    if not results:
        logger.warning("抖音: Web取得失敗。キーワードヒントを生成します。")
        results = _generate_hints()
    else:
        logger.info("抖音: %d 件取得", len(results))

    return results


def _fetch_hashtag(tag: str) -> dict | None:
    """抖音のハッシュタグページから情報を抽出."""
    url = f"https://www.douyin.com/search/{tag}?type=general"

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=15) as client:
        resp = client.get(url)
        if resp.status_code in (302, 403, 429):
            return None
        resp.raise_for_status()

    html = resp.text

    # ページ内の動画情報を抽出
    title_match = re.search(r"<title>(.*?)</title>", html)
    # 再生数・いいね数の抽出を試みる
    view_matches = re.findall(r'"playCount":(\d+)', html)
    like_matches = re.findall(r'"diggCount":(\d+)', html)

    if view_matches or title_match:
        total_views = sum(int(v) for v in view_matches[:10]) if view_matches else 0
        return {
            "platform": "抖音",
            "hashtag": tag,
            "title": title_match.group(1) if title_match else "",
            "sample_views": total_views,
            "video_samples": len(view_matches),
            "url": url,
        }

    return None


def _generate_hints() -> list[dict]:
    """Geminiに抖音トレンド分析を促すヒント情報."""
    return [
        {
            "platform": "抖音",
            "type": "keyword_hint",
            "keyword": tag,
            "description": f"抖音（中国版TikTok）で「{tag}」が人気の可能性。中国の食品バズ動画トレンドを分析してください。",
            "url": f"https://www.douyin.com/search/{tag}",
        }
        for tag in FOOD_HASHTAGS[:6]
    ]
