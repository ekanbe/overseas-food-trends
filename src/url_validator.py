"""参照URLの到達確認。切れたリンクを除外する.

新旧両形式に対応:
- 旧: reference_urls フィールド（URLリスト）
- 新: references フィールド（テキスト参照。URLを含むものだけ検証）
"""

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

logger = logging.getLogger(__name__)

TIMEOUT = 8
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FoodTrendBot/2.0)",
}

URL_PATTERN = re.compile(r'https?://[^\s<>"]+')


def is_reachable(url: str) -> bool:
    """URLにアクセスできるか確認する."""
    try:
        with httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True) as client:
            resp = client.head(url)
            if resp.status_code < 400:
                return True
            if resp.status_code == 405:
                resp = client.get(url)
                return resp.status_code < 400
        return False
    except (httpx.HTTPError, Exception):
        return False


def validate_trends(trends: list[dict]) -> list[dict]:
    """各トレンドの参照URLを検証.

    reference_urls（旧形式）と references（新形式）の両方に対応。
    新形式の場合、references内のURLを抽出して検証。
    URLが含まれないテキスト参照はそのまま残す。
    """
    url_map: dict[str, bool] = {}
    all_urls = []

    for t in trends:
        # 旧形式: reference_urls
        for url in t.get("reference_urls", []):
            if url and url.startswith("http") and url not in url_map:
                all_urls.append(url)
                url_map[url] = True  # プレースホルダー

        # 新形式: references（テキストからURL抽出）
        for ref in t.get("references", []):
            urls_in_ref = URL_PATTERN.findall(ref)
            for url in urls_in_ref:
                if url not in url_map:
                    all_urls.append(url)
                    url_map[url] = True

    if not all_urls:
        return trends

    # 並列でURL検証
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(is_reachable, url): url for url in all_urls}
        for future in as_completed(futures):
            url = futures[future]
            try:
                url_map[url] = future.result()
            except Exception:
                url_map[url] = False

    broken = [u for u, ok in url_map.items() if not ok]
    if broken:
        logger.warning("切れたリンクを除外: %s", broken)
    else:
        logger.info("全URLが到達可能（%d件）", len(url_map))

    # 切れたURLを含む参照を除外
    for t in trends:
        # 旧形式
        if "reference_urls" in t:
            t["reference_urls"] = [
                url for url in t["reference_urls"]
                if not url.startswith("http") or url_map.get(url, False)
            ]
        # 新形式: URLが切れている参照テキストを除去
        if "references" in t:
            valid_refs = []
            for ref in t["references"]:
                urls_in_ref = URL_PATTERN.findall(ref)
                if urls_in_ref:
                    if all(url_map.get(u, False) for u in urls_in_ref):
                        valid_refs.append(ref)
                else:
                    # URLを含まないテキスト参照はそのまま残す
                    valid_refs.append(ref)
            t["references"] = valid_refs

    return trends
