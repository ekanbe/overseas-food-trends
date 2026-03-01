"""X（Twitter）から食品関連のトレンドを収集.

X API v2 (Free/Basic tier) を使用。
API未設定時はスキップする。
"""

import os
import logging
from datetime import datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)

BEARER_TOKEN_ENV = "X_BEARER_TOKEN"
BASE_URL = "https://api.twitter.com/2"

# 食品関連の検索クエリ
SEARCH_QUERIES = [
    "food trend 2026 lang:en -is:retweet",
    "viral food lang:en -is:retweet",
    "new restaurant opening lang:en -is:retweet",
    "foodtech innovation lang:en -is:retweet",
    "#foodtrend -is:retweet",
    "#newmenu -is:retweet",
    "외식 트렌드 lang:ko -is:retweet",
    "美食趋势 lang:zh -is:retweet",
]

HEADERS_BASE = {
    "User-Agent": "FoodTrendBot/2.0",
}


def collect() -> list[dict]:
    """X（Twitter）から食品関連ツイートを収集."""
    bearer = os.environ.get(BEARER_TOKEN_ENV)
    if not bearer:
        logger.warning("X_BEARER_TOKEN が未設定のためスキップ")
        return []

    headers = {
        **HEADERS_BASE,
        "Authorization": f"Bearer {bearer}",
    }

    results = []
    one_day_ago = (datetime.now(timezone.utc) - timedelta(days=1)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    for query in SEARCH_QUERIES:
        try:
            tweets = _search_recent(headers, query, one_day_ago)
            results.extend(tweets)
        except Exception as e:
            logger.warning("X検索失敗 (query=%s): %s", query[:30], e)

    logger.info("X(Twitter): %d 件取得", len(results))
    return results


def _search_recent(headers: dict, query: str, start_time: str) -> list[dict]:
    """Recent Search API v2 で直近ツイートを検索."""
    params = {
        "query": query,
        "start_time": start_time,
        "max_results": 10,
        "tweet.fields": "public_metrics,created_at,lang",
        "expansions": "author_id",
        "user.fields": "username,public_metrics",
    }

    with httpx.Client(headers=headers, timeout=15) as client:
        resp = client.get(f"{BASE_URL}/tweets/search/recent", params=params)
        if resp.status_code == 429:
            logger.warning("X API レート制限")
            return []
        resp.raise_for_status()

    data = resp.json()
    tweets = data.get("data", [])
    users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}

    results = []
    for tweet in tweets:
        author = users.get(tweet.get("author_id"), {})
        metrics = tweet.get("public_metrics", {})
        results.append({
            "platform": "X",
            "text": tweet.get("text", "")[:280],
            "author": author.get("username", ""),
            "author_followers": author.get("public_metrics", {}).get("followers_count", 0),
            "retweet_count": metrics.get("retweet_count", 0),
            "like_count": metrics.get("like_count", 0),
            "reply_count": metrics.get("reply_count", 0),
            "created_at": tweet.get("created_at", ""),
            "lang": tweet.get("lang", ""),
            "url": f"https://x.com/i/status/{tweet.get('id', '')}",
        })

    return results
