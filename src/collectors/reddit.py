"""Reddit API (PRAW) を使った食品系サブレディットの急上昇投稿収集."""

import os
import logging
from datetime import datetime, timezone

import praw

logger = logging.getLogger(__name__)

# 巡回対象サブレディット
SUBREDDITS = {
    "global": ["food", "foodporn", "cooking", "Baking", "eatsandwiches"],
    "asian": [
        "KoreanFood",
        "ChineseFood",
        "ThaiFood",
        "VietnamFood",
        "filipinofood",
    ],
    "trend": ["FoodTrends", "foodhacks"],
}


def collect() -> list[dict]:
    """Reddit から食品系の急上昇投稿を収集して返す."""
    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    user_agent = os.environ.get("REDDIT_USER_AGENT", "FoodTrendBot/1.0")

    if not client_id or not client_secret:
        logger.warning("Reddit認証情報が未設定のためスキップ")
        return []

    reddit = praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
    )

    results = []
    all_subs = []
    for subs in SUBREDDITS.values():
        all_subs.extend(subs)

    for sub_name in all_subs:
        try:
            subreddit = reddit.subreddit(sub_name)

            # hot投稿
            for post in subreddit.hot(limit=30):
                parsed = _parse_post(post, sub_name, "hot")
                if parsed:
                    results.append(parsed)

            # rising投稿（急上昇）
            for post in subreddit.rising(limit=15):
                parsed = _parse_post(post, sub_name, "rising")
                if parsed:
                    results.append(parsed)

        except Exception as e:
            logger.warning("Reddit取得失敗 (r/%s): %s", sub_name, e)

    logger.info("Reddit: %d 件取得", len(results))
    return results


def _parse_post(post, sub_name: str, source: str) -> dict | None:
    # ピン留め投稿はスキップ
    if post.stickied:
        return None

    created_dt = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)

    return {
        "platform": "Reddit",
        "subreddit": f"r/{sub_name}",
        "source": source,
        "title": post.title,
        "score": post.score,
        "num_comments": post.num_comments,
        "upvote_ratio": post.upvote_ratio,
        "created_at": created_dt.isoformat(),
        "url": f"https://reddit.com{post.permalink}",
    }
