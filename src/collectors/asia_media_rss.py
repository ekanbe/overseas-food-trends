"""アジア食品業界メディアおよび外食産業メディアのRSSフィードを収集.

食品業界ニュース、外食産業動向、フードテック、規制情報などをカバー。
"""

import logging
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET

import httpx

logger = logging.getLogger(__name__)

# 外食産業・食品業界メディア
FEEDS = {
    # アジア食品メディア
    "Food Navigator Asia": "https://www.foodnavigator-asia.com/Info/RSS-Feeds",
    "Food Navigator": "https://www.foodnavigator.com/Info/RSS-Feeds",
    # 外食産業メディア（米国）
    "QSR Magazine": "https://www.qsrmagazine.com/rss.xml",
    "Nation's Restaurant News": "https://www.nrn.com/rss.xml",
    "Restaurant Business Online": "https://www.restaurantbusinessonline.com/rss.xml",
    # フードテック
    "The Spoon": "https://thespoon.tech/feed/",
    # 追加の食品メディア
    "Food Dive": "https://www.fooddive.com/feeds/news/",
    "Restaurant Dive": "https://www.restaurantdive.com/feeds/news/",
    # アジア経済メディア（食品関連）
    "36Kr": "https://36kr.com/feed",
    "KoreaBizWire": "https://koreabizwire.com/feed",
}

HEADERS = {
    "User-Agent": "FoodTrendBot/2.0 (RSS Reader)",
}


def collect() -> list[dict]:
    """アジア・外食産業メディアのRSSフィードから記事を収集."""
    results = []
    one_week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    for name, url in FEEDS.items():
        try:
            articles = _fetch_feed(name, url, one_week_ago)
            results.extend(articles)
        except Exception as e:
            logger.warning("Asia Media RSS取得失敗 (%s): %s", name, e)

    logger.info("Asia Media RSS: %d 件取得", len(results))
    return results


def _fetch_feed(name: str, url: str, since: datetime) -> list[dict]:
    """単一のRSSフィードをパースして記事リストを返す."""
    articles = []

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=15) as client:
        resp = client.get(url)
        resp.raise_for_status()

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError:
        logger.warning("RSS XMLパース失敗 (%s)", name)
        return []

    # RSS 2.0 形式
    for item in root.iter("item"):
        title = _get_text(item, "title")
        link = _get_text(item, "link")
        pub_date = _get_text(item, "pubDate")
        description = _get_text(item, "description")
        category = _get_text(item, "category")

        if title:
            articles.append({
                "platform": "Asia Media RSS",
                "source": name,
                "title": title,
                "url": link or "",
                "published_at": pub_date or "",
                "description": (description or "")[:300],
                "category": category or "",
            })

    # Atom 形式
    for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
        title_el = entry.find("{http://www.w3.org/2005/Atom}title")
        link_el = entry.find("{http://www.w3.org/2005/Atom}link")
        published_el = (
            entry.find("{http://www.w3.org/2005/Atom}published")
            or entry.find("{http://www.w3.org/2005/Atom}updated")
        )
        summary_el = entry.find("{http://www.w3.org/2005/Atom}summary")
        category_el = entry.find("{http://www.w3.org/2005/Atom}category")

        title = title_el.text if title_el is not None else None
        link = link_el.get("href") if link_el is not None else ""
        pub_date = published_el.text if published_el is not None else ""
        description = summary_el.text if summary_el is not None else ""
        category = category_el.get("term") if category_el is not None else ""

        if title:
            articles.append({
                "platform": "Asia Media RSS",
                "source": name,
                "title": title,
                "url": link,
                "published_at": pub_date,
                "description": (description or "")[:300],
                "category": category,
            })

    return articles[:15]


def _get_text(element, tag: str) -> str | None:
    el = element.find(tag)
    return el.text if el is not None else None
