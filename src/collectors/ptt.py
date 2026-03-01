"""PTT（台湾最大の掲示板）から食品関連の話題を収集.

PTT Web版から美食板（Food）、Drink板などの人気記事を取得。
"""

import logging
import re

import httpx

logger = logging.getLogger(__name__)

# PTT の食品関連板
BOARDS = {
    "Food": "美食板（グルメ全般）",
    "Drink": "飲料板",
    "Lifeismoney": "お買い得情報（食品含む）",
    "Gossiping": "八卦板（話題全般、食品トレンド含む）",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Cookie": "over18=1",  # 年齢確認バイパス
}

PTT_BASE = "https://www.ptt.cc"


def collect() -> list[dict]:
    """PTT から台湾の食品関連スレッドを収集."""
    results = []

    for board, description in BOARDS.items():
        try:
            posts = _fetch_board(board)
            results.extend(posts)
        except Exception as e:
            logger.warning("PTT取得失敗 (%s): %s", board, e)

    if not results:
        logger.warning("PTT: データ取得失敗。ヒント情報を生成します。")
        results = _generate_hints()
    else:
        logger.info("PTT: %d 件取得", len(results))

    return results


def _fetch_board(board: str) -> list[dict]:
    """PTTの板から最新の人気記事を取得."""
    url = f"{PTT_BASE}/bbs/{board}/index.html"

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=15) as client:
        resp = client.get(url)
        if resp.status_code != 200:
            return []

    html = resp.text
    results = []

    # 記事のパース: タイトル、推薦数、リンク
    entries = re.findall(
        r'<div class="r-ent">.*?<div class="nrec"><span[^>]*>([^<]*)</span>.*?'
        r'<a href="([^"]*)">(.*?)</a>',
        html,
        re.DOTALL,
    )

    for push_count_str, link, title in entries:
        title = title.strip()
        # 食品関連のフィルタリング
        food_terms = {"吃", "食", "飲", "喝", "餐", "店", "茶", "咖啡",
                      "甜", "麵", "飯", "菜", "奶", "果", "料理", "美食"}

        is_food = board in ("Food", "Drink") or any(t in title for t in food_terms)
        if not is_food:
            continue

        # 推薦数をパース
        push_count = 0
        if push_count_str == "爆":
            push_count = 100
        elif push_count_str.startswith("X"):
            push_count = -10
        elif push_count_str.isdigit():
            push_count = int(push_count_str)

        results.append({
            "platform": "PTT",
            "board": board,
            "title": title,
            "push_count": push_count,
            "url": f"{PTT_BASE}{link}",
        })

    # 推薦数でソートして上位を返す
    results.sort(key=lambda x: x["push_count"], reverse=True)
    return results[:15]


def _generate_hints() -> list[dict]:
    """Geminiに台湾トレンド分析を促すヒント情報."""
    return [
        {
            "platform": "PTT",
            "type": "keyword_hint",
            "keyword": "台湾 美食 トレンド",
            "description": "PTT美食板で台湾の食品トレンドが議論されている可能性。台湾の新しいドリンク・スイーツ・外食トレンドを分析してください。",
        },
        {
            "platform": "PTT",
            "type": "keyword_hint",
            "keyword": "台灣 手搖飲 新品",
            "description": "台湾の手搖飲（タピオカドリンク店）の新商品トレンドを分析してください。",
        },
    ]
