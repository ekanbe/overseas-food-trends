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


def _extract_url_from_ref(ref) -> str | None:
    """参照からURLを抽出する（dict/str両対応）."""
    if isinstance(ref, dict):
        url = ref.get("url", "")
        if url and url.startswith("http"):
            return url
        # text内にURLが含まれる場合
        text = ref.get("text", "")
        urls = URL_PATTERN.findall(text)
        return urls[0] if urls else None
    elif isinstance(ref, str):
        urls = URL_PATTERN.findall(ref)
        return urls[0] if urls else None
    return None


def validate_trends(trends: list[dict]) -> list[dict]:
    """各トレンドの参照URLを検証.

    対応形式:
    - dict形式: {"text": "...", "url": "https://..."} — url フィールドを検証
    - str形式: テキスト内のURLを抽出して検証（後方互換）
    - reference_urls（旧形式）: URLリストを検証
    """
    url_map: dict[str, bool] = {}
    all_urls = []

    for t in trends:
        # 旧形式: reference_urls
        for url in t.get("reference_urls", []):
            if url and url.startswith("http") and url not in url_map:
                all_urls.append(url)
                url_map[url] = True

        # references（dict/str 両対応）
        for ref in t.get("references", []):
            url = _extract_url_from_ref(ref)
            if url and url not in url_map:
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
        # references（dict/str 両対応）
        if "references" in t:
            valid_refs = []
            for ref in t["references"]:
                url = _extract_url_from_ref(ref)
                if url:
                    # URLがある場合: 到達可能なら残す、不可なら URL を空にして残す
                    if url_map.get(url, False):
                        valid_refs.append(ref)
                    else:
                        # URLが切れていてもテキスト参照は残す（URLだけ除去）
                        if isinstance(ref, dict):
                            valid_refs.append({"text": ref.get("text", ""), "url": ""})
                        # str形式は除去
                else:
                    # URLなしの参照はそのまま残す
                    valid_refs.append(ref)
            t["references"] = valid_refs

    return trends
