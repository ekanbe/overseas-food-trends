"""Google Trends から食品関連の急上昇キーワードを収集."""

import logging
from pytrends.request import TrendReq

logger = logging.getLogger(__name__)

FOOD_SEEDS = [
    "food trend",
    "viral food",
    "new dessert",
    "trending drink",
    "street food",
    "korean food",
    "asian food",
    "boba",
    "matcha",
    "mochi",
]

REGIONS = ["", "US", "KR", "TW", "TH", "VN"]  # "" = worldwide


def collect() -> list[dict]:
    """Google Trends から食品関連の急上昇トピックを収集."""
    results = []

    try:
        pytrends = TrendReq(hl="en-US", tz=540, timeout=(10, 25))
    except Exception as e:
        logger.warning("Google Trends 初期化失敗: %s", e)
        return []

    # 1. 急上昇ワード (Daily Trending Searches)
    for region in ["united_states", "south_korea", "japan", "singapore", "india"]:
        try:
            trending = pytrends.trending_searches(pn=region)
            for _, row in trending.head(20).iterrows():
                keyword = row[0]
                results.append({
                    "platform": "Google Trends",
                    "source": f"trending:{region}",
                    "keyword": keyword,
                    "type": "trending_search",
                })
        except Exception as e:
            logger.warning("Google Trends trending取得失敗 (%s): %s", region, e)

    # 2. 関連キーワード (Related Queries)
    for seed in FOOD_SEEDS[:5]:  # API制限を考慮して5つに制限
        try:
            pytrends.build_payload([seed], cat=71, timeframe="now 7-d")  # cat=71 = Food & Drink
            related = pytrends.related_queries()
            if seed in related and related[seed]["rising"] is not None:
                rising_df = related[seed]["rising"]
                for _, row in rising_df.head(10).iterrows():
                    results.append({
                        "platform": "Google Trends",
                        "source": f"related:{seed}",
                        "keyword": row.get("query", ""),
                        "rising_value": int(row.get("value", 0)),
                        "type": "rising_query",
                    })
        except Exception as e:
            logger.warning("Google Trends related取得失敗 (%s): %s", seed, e)

    logger.info("Google Trends: %d 件取得", len(results))
    return results
