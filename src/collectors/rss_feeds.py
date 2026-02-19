"""海外フードメディアのRSSフィードから最新記事を収集."""

import logging
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET

import httpx

logger = logging.getLogger(__name__)

# 海外フードメディアのRSSフィード
FEEDS = {
    "Eater": "https://www.eater.com/rss/index.xml",
    "Food52": "https://food52.com/blog.rss",
    "Bon Appetit": "https://www.bonappetit.com/feed/rss",
    "Serious Eats": "https://www.seriouseats.com/rss",
    "Delish": "https://www.delish.com/rss/",
    "Tastingtable": "https://www.tastingtable.com/rss",
    "FoodBeast": "https://www.foodbeast.com/feed/",
    "The Kitchn": "https://www.thekitchn.com/rss2",
}

HEADERS = {
    "User-Agent": "FoodTrendBot/1.0 (RSS Reader)",
}


def collect() -> list[dict]:
    """RSSフィードから食品ニュース記事を収集."""
    results = []
    one_week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    for name, url in FEEDS.items():
        try:
            articles = _fetch_feed(name, url, one_week_ago)
            results.extend(articles)
        except Exception as e:
            logger.warning("RSS取得失敗 (%s): %s", name, e)

    logger.info("RSS Feeds: %d 件取得", len(results))
    return results


def _fetch_feed(name: str, url: str, since: datetime) -> list[dict]:
    """単一のRSSフィードをパースして記事リストを返す."""
    articles = []

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=15) as client:
        resp = client.get(url)
        resp.raise_for_status()

    root = ET.fromstring(resp.text)

    # RSS 2.0 形式
    for item in root.iter("item"):
        title = _get_text(item, "title")
        link = _get_text(item, "link")
        pub_date = _get_text(item, "pubDate")
        description = _get_text(item, "description")

        if title:
            articles.append({
                "platform": "RSS",
                "source": name,
                "title": title,
                "url": link or "",
                "published_at": pub_date or "",
                "description": (description or "")[:200],
            })

    # Atom 形式
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
        title_el = entry.find("atom:title", ns)
        link_el = entry.find("atom:link", ns)
        published_el = entry.find("atom:published", ns) or entry.find("atom:updated", ns)
        summary_el = entry.find("atom:summary", ns)

        title = title_el.text if title_el is not None else None
        link = link_el.get("href") if link_el is not None else ""
        pub_date = published_el.text if published_el is not None else ""
        description = summary_el.text if summary_el is not None else ""

        if title:
            articles.append({
                "platform": "RSS",
                "source": name,
                "title": title,
                "url": link,
                "published_at": pub_date,
                "description": (description or "")[:200],
            })

    return articles[:15]  # 1フィードあたり最大15記事


def _get_text(element, tag: str) -> str | None:
    el = element.find(tag)
    return el.text if el is not None else None
