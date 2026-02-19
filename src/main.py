"""海外フードトレンド自動検出 & LINE配信 — メインオーケストレーター."""

import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# .env ファイルがあればロード（ローカルテスト用）
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from collectors import youtube, reddit, tiktok, google_trends, rss_feeds, instagram
from analyzer import analyze
from notifier import send

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def collect_all() -> dict:
    """全プラットフォームからデータを並列収集."""
    collected = {"youtube": [], "reddit": [], "tiktok": [], "google_trends": [], "rss_feeds": [], "instagram": []}

    collectors = {
        "youtube": youtube.collect,
        "reddit": reddit.collect,
        "tiktok": tiktok.collect,
        "google_trends": google_trends.collect,
        "rss_feeds": rss_feeds.collect,
        "instagram": instagram.collect,
    }

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(fn): name for name, fn in collectors.items()
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                collected[name] = future.result()
            except Exception as e:
                logger.error("%s コレクター例外: %s", name, e)

    total = sum(len(v) for v in collected.values())
    logger.info(
        "データ収集完了 — YouTube: %d, Reddit: %d, TikTok: %d, Google Trends: %d, RSS: %d, Instagram: %d (合計: %d)",
        len(collected["youtube"]),
        len(collected["reddit"]),
        len(collected["tiktok"]),
        len(collected["google_trends"]),
        len(collected["rss_feeds"]),
        len(collected["instagram"]),
        total,
    )
    return collected


def main():
    logger.info("=== 海外フードトレンド検出 開始 ===")

    # Step 1: データ収集
    collected = collect_all()

    total = sum(len(v) for v in collected.values())
    if total == 0:
        logger.error("データ収集結果が0件。全コレクターが失敗しました。")
        sys.exit(1)

    # Step 2: AI分析
    logger.info("Gemini分析を開始...")
    result = analyze(collected)
    if not result or not result.get("trends"):
        logger.error("Gemini分析が結果を返しませんでした。")
        sys.exit(1)

    logger.info("分析完了: %d 件のトレンドを検出", len(result["trends"]))

    # Step 3: LINE配信
    logger.info("LINE配信を開始...")
    success = send(result)
    if not success:
        logger.error("LINE配信に失敗しました。")
        sys.exit(1)

    logger.info("=== 海外フードトレンド検出 完了 ===")


if __name__ == "__main__":
    main()
