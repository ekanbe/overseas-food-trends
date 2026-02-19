"""YouTube Data API v3 を使った食品トレンド動画の収集."""

import os
import logging
from datetime import datetime, timedelta, timezone
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

TARGET_REGIONS = ["US", "KR", "TW", "TH", "VN", "PH"]
SEARCH_QUERIES = [
    "food trend 2026",
    "viral recipe",
    "mukbang",
    "street food",
    "dessert trend",
    "new drink trend",
    "food hack",
]
# カテゴリ 26 = Howto & Style（食品レシピ系が多い）
CATEGORY_ID = "26"


def collect() -> list[dict]:
    """YouTube から食品トレンド動画を収集して返す."""
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        logger.warning("YOUTUBE_API_KEY が未設定のためスキップ")
        return []

    youtube = build("youtube", "v3", developerKey=api_key)
    results = []

    # 1週間前の日時（RFC 3339形式）
    one_week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    # --- 各国の人気動画を取得 ---
    for region in TARGET_REGIONS:
        try:
            resp = (
                youtube.videos()
                .list(
                    part="snippet,statistics",
                    chart="mostPopular",
                    regionCode=region,
                    videoCategoryId=CATEGORY_ID,
                    maxResults=10,
                )
                .execute()
            )
            for item in resp.get("items", []):
                results.append(_parse_video(item, region, "popular"))
        except Exception as e:
            logger.warning("YouTube popular取得失敗 (region=%s): %s", region, e)

    # --- キーワード検索で直近バズり動画を取得 ---
    for query in SEARCH_QUERIES:
        for region in TARGET_REGIONS[:3]:  # API消費を抑えるため主要3カ国
            try:
                search_resp = (
                    youtube.search()
                    .list(
                        part="snippet",
                        q=query,
                        regionCode=region,
                        order="viewCount",
                        publishedAfter=one_week_ago,
                        type="video",
                        maxResults=5,
                    )
                    .execute()
                )
                video_ids = [
                    item["id"]["videoId"]
                    for item in search_resp.get("items", [])
                    if item["id"].get("videoId")
                ]
                if not video_ids:
                    continue

                # 統計情報を別途取得
                stats_resp = (
                    youtube.videos()
                    .list(part="snippet,statistics", id=",".join(video_ids))
                    .execute()
                )
                for item in stats_resp.get("items", []):
                    results.append(_parse_video(item, region, f"search:{query}"))
            except Exception as e:
                logger.warning(
                    "YouTube検索失敗 (query=%s, region=%s): %s", query, region, e
                )

    logger.info("YouTube: %d 件取得", len(results))
    return results


def _parse_video(item: dict, region: str, source: str) -> dict:
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})
    video_id = item.get("id", "")
    if isinstance(video_id, dict):
        video_id = video_id.get("videoId", "")

    return {
        "platform": "YouTube",
        "region": region,
        "source": source,
        "title": snippet.get("title", ""),
        "channel": snippet.get("channelTitle", ""),
        "view_count": int(stats.get("viewCount", 0)),
        "like_count": int(stats.get("likeCount", 0)),
        "published_at": snippet.get("publishedAt", ""),
        "url": f"https://www.youtube.com/watch?v={video_id}",
    }
