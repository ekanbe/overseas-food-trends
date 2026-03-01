"""参照リンクの自動補完モジュール.

Gemini が URL を返せなかった参照に対し、
プラットフォーム名からキーワード検索URLを自動生成して補完する。
"""

import logging
import re
from urllib.parse import quote

logger = logging.getLogger(__name__)

# プラットフォーム名 → 検索URLテンプレート（{keyword} を置換）
PLATFORM_SEARCH_URLS = {
    "小红书": "https://www.xiaohongshu.com/search_result?keyword={keyword}",
    "xiaohongshu": "https://www.xiaohongshu.com/search_result?keyword={keyword}",
    "抖音": "https://www.douyin.com/search/{keyword}",
    "douyin": "https://www.douyin.com/search/{keyword}",
    "weibo": "https://s.weibo.com/weibo?q={keyword}",
    "微博": "https://s.weibo.com/weibo?q={keyword}",
    "tiktok": "https://www.tiktok.com/search?q={keyword}",
    "instagram": "https://www.instagram.com/explore/tags/{keyword}",
    "naver": "https://search.naver.com/search.naver?where=blog&query={keyword}",
    "naver blog": "https://search.naver.com/search.naver?where=blog&query={keyword}",
    "reddit": "https://www.reddit.com/search/?q={keyword}",
    "youtube": "https://www.youtube.com/results?search_query={keyword}",
    "google trends": "https://trends.google.com/trends/explore?q={keyword}",
    "x": "https://x.com/search?q={keyword}",
    "twitter": "https://x.com/search?q={keyword}",
    "ptt": "https://www.ptt.cc/bbs/Food/search?q={keyword}",
}

# ハッシュタグや引用符で囲まれたキーワードを抽出するパターン
HASHTAG_PATTERN = re.compile(r"#(\S+)")
KEYWORD_PATTERN = re.compile(r"[「『](.+?)[」』]")


def _extract_keyword(text: str) -> str:
    """参照テキストからキーワードを抽出する."""
    # ハッシュタグがあればそれを使う
    match = HASHTAG_PATTERN.search(text)
    if match:
        return match.group(1)

    # 括弧内のキーワード
    match = KEYWORD_PATTERN.search(text)
    if match:
        return match.group(1)

    # プラットフォーム名を除去した残りをキーワードにする
    keyword = text
    for platform in PLATFORM_SEARCH_URLS:
        keyword = keyword.replace(platform, "").strip()

    # 先頭の記号や空白を除去
    keyword = keyword.strip(" 　・:：-—")

    return keyword if keyword else text


def _detect_platform(text: str) -> str | None:
    """参照テキストからプラットフォーム名を検出する."""
    text_lower = text.lower()
    for platform in PLATFORM_SEARCH_URLS:
        if platform.lower() in text_lower:
            return platform
    return None


def _generate_search_url(text: str) -> str:
    """参照テキストからプラットフォーム検索URLを生成する."""
    platform = _detect_platform(text)
    if not platform:
        return ""

    keyword = _extract_keyword(text)
    if not keyword:
        return ""

    template = PLATFORM_SEARCH_URLS[platform.lower() if platform.lower() in PLATFORM_SEARCH_URLS else platform]
    return template.format(keyword=quote(keyword, safe=""))


def _enrich_ref(ref) -> dict:
    """単一の参照を正規化・URL補完する.

    入力形式:
    - str: 旧形式テキスト → {"text": str, "url": 検索URL}
    - dict: 新形式 {"text": ..., "url": ...} → url が空なら補完
    """
    if isinstance(ref, str):
        url = _generate_search_url(ref)
        return {"text": ref, "url": url}

    if isinstance(ref, dict):
        text = ref.get("text", "")
        url = ref.get("url", "")
        if not url and text:
            url = _generate_search_url(text)
        return {"text": text, "url": url}

    return {"text": str(ref), "url": ""}


def _enrich_refs_in_list(refs: list) -> list[dict]:
    """参照リスト内の各参照を正規化・URL補完する."""
    return [_enrich_ref(ref) for ref in refs]


def enrich_references(analysis: dict) -> dict:
    """分析結果全体の references を URL 補完する.

    日報・週報どちらの形式にも対応。
    references フィールドを再帰的に探索して補完する。
    """
    if not analysis:
        return analysis

    _walk_and_enrich(analysis)

    enriched = sum(
        1 for ref in _collect_all_refs(analysis)
        if ref.get("url")
    )
    total = len(_collect_all_refs(analysis))
    logger.info("参照リンク補完完了: %d/%d 件にURLあり", enriched, total)

    return analysis


def _walk_and_enrich(obj):
    """辞書・リストを再帰的に走査し、references フィールドを補完する."""
    if isinstance(obj, dict):
        if "references" in obj and isinstance(obj["references"], list):
            obj["references"] = _enrich_refs_in_list(obj["references"])
        for value in obj.values():
            _walk_and_enrich(value)
    elif isinstance(obj, list):
        for item in obj:
            _walk_and_enrich(item)


def _collect_all_refs(obj, collected=None) -> list[dict]:
    """全 references を収集する（統計用）."""
    if collected is None:
        collected = []
    if isinstance(obj, dict):
        if "references" in obj and isinstance(obj["references"], list):
            collected.extend(obj["references"])
        for value in obj.values():
            _collect_all_refs(value, collected)
    elif isinstance(obj, list):
        for item in obj:
            _collect_all_refs(item, collected)
    return collected
