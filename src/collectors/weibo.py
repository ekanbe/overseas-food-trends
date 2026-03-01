"""微博（Weibo）から食品関連のホットトピックを収集.

Weibo Open API またはWebページからトレンド情報を取得。
"""

import json
import logging
import re

import httpx

logger = logging.getLogger(__name__)

# 食品関連のホットサーチキーワード
FOOD_KEYWORDS = [
    "美食",
    "奶茶",
    "火锅",
    "甜品",
    "咖啡",
    "轻食",
    "新茶饮",
    "外卖",
    "网红餐厅",
    "食品安全",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# Weibo ホットサーチ API（公開エンドポイント）
HOT_SEARCH_URL = "https://weibo.com/ajax/side/hotSearch"


def collect() -> list[dict]:
    """微博から食品関連のホットトピックを収集."""
    results = []

    # 1. ホットサーチから食品関連を抽出
    try:
        hot_items = _fetch_hot_search()
        results.extend(hot_items)
    except Exception as e:
        logger.warning("Weibo ホットサーチ取得失敗: %s", e)

    # 2. キーワード検索
    for keyword in FOOD_KEYWORDS[:5]:
        try:
            items = _search_keyword(keyword)
            results.extend(items)
        except Exception as e:
            logger.warning("Weibo検索失敗 (%s): %s", keyword, e)

    if not results:
        logger.warning("Weibo: データ取得失敗。ヒント情報を生成します。")
        results = _generate_hints()
    else:
        logger.info("Weibo: %d 件取得", len(results))

    return results


def _fetch_hot_search() -> list[dict]:
    """Weiboのホットサーチから食品関連トピックを抽出."""
    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=15) as client:
        resp = client.get(HOT_SEARCH_URL)
        if resp.status_code != 200:
            return []
        data = resp.json()

    realtime = data.get("data", {}).get("realtime", [])
    food_related = []
    food_terms = {"美食", "吃", "餐", "食", "饮", "奶", "茶", "咖啡", "火锅",
                  "甜", "糖", "面", "饭", "菜", "外卖", "店", "厨"}

    for item in realtime:
        word = item.get("word", "")
        if any(term in word for term in food_terms):
            food_related.append({
                "platform": "Weibo",
                "type": "hot_search",
                "keyword": word,
                "hot_value": item.get("num", 0),
                "category": item.get("category", ""),
                "url": f"https://s.weibo.com/weibo?q=%23{word}%23",
            })

    return food_related[:10]


def _search_keyword(keyword: str) -> list[dict]:
    """Weiboのキーワード検索から情報を取得."""
    url = f"https://m.weibo.cn/api/container/getIndex?containerid=100103type%3D1%26q%3D{keyword}"

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=15) as client:
        resp = client.get(url)
        if resp.status_code != 200:
            return []

    try:
        data = resp.json()
    except (json.JSONDecodeError, ValueError):
        return []

    cards = data.get("data", {}).get("cards", [])
    results = []

    for card in cards[:5]:
        mblog = card.get("mblog", {})
        if not mblog:
            continue
        text = mblog.get("text", "")
        # HTMLタグを除去
        clean_text = re.sub(r"<[^>]+>", "", text)[:200]
        results.append({
            "platform": "Weibo",
            "type": "search",
            "keyword": keyword,
            "text": clean_text,
            "reposts": mblog.get("reposts_count", 0),
            "comments": mblog.get("comments_count", 0),
            "likes": mblog.get("attitudes_count", 0),
            "url": f"https://weibo.com/{mblog.get('user', {}).get('id', '')}/{mblog.get('bid', '')}",
        })

    return results


def _generate_hints() -> list[dict]:
    """Geminiに微博トレンド分析を促すヒント情報."""
    return [
        {
            "platform": "Weibo",
            "type": "keyword_hint",
            "keyword": kw,
            "description": f"微博で「{kw}」関連の議論がある可能性。中国の食品業界の話題を分析してください。",
        }
        for kw in FOOD_KEYWORDS[:5]
    ]
