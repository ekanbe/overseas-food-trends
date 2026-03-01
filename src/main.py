"""海外フードトレンド自動検出 & LINE Works配信 — メインオーケストレーター.

モード:
  daily  — 日報（毎朝8時配信）: 全ソースからデータ収集→Gemini分析→レポート生成→配信
  weekly — 週報（毎週日曜20時配信）: 1週間分のデータ集約→Gemini分析→ダイジェスト生成→配信
"""

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from collectors import (
    youtube, reddit, tiktok, google_trends, rss_feeds, instagram,
    x_twitter, xiaohongshu, douyin, weibo, naver, ptt, asia_media_rss,
)
from analyzer import analyze_daily, analyze_weekly
from report_generator import format_daily_report, format_weekly_report
from notifier import send
from history import load as load_history, get_past_names, save as save_history
from weekly_aggregator import (
    save_daily_analysis, load_weekly_data, get_week_info, cleanup_old_reports,
)
from url_validator import validate_trends
from link_generator import enrich_references
from notion_writer import save_to_notion

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# 全コレクターの定義
COLLECTORS = {
    # 欧米SNS
    "youtube": youtube.collect,
    "reddit": reddit.collect,
    "tiktok": tiktok.collect,
    "instagram": instagram.collect,
    "x_twitter": x_twitter.collect,
    # 中国SNS
    "xiaohongshu": xiaohongshu.collect,
    "douyin": douyin.collect,
    "weibo": weibo.collect,
    # 韓国
    "naver": naver.collect,
    # 台湾
    "ptt": ptt.collect,
    # データ
    "google_trends": google_trends.collect,
    # メディアRSS
    "rss_feeds": rss_feeds.collect,
    "asia_media_rss": asia_media_rss.collect,
}


def collect_all() -> dict:
    """全プラットフォームからデータを並列収集."""
    collected = {name: [] for name in COLLECTORS}

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(fn): name for name, fn in COLLECTORS.items()
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                collected[name] = future.result()
            except Exception as e:
                logger.error("%s コレクター例外: %s", name, e)

    total = sum(len(v) for v in collected.values())
    source_counts = ", ".join(
        f"{name}: {len(v)}" for name, v in collected.items() if v
    )
    logger.info("データ収集完了 — %s (合計: %d)", source_counts, total)
    return collected


def run_daily():
    """日報モード: データ収集→分析→レポート生成→配信."""
    logger.info("=== 日報モード 開始 ===")

    # Step 1: データ収集
    collected = collect_all()
    total = sum(len(v) for v in collected.values())
    if total == 0:
        logger.error("データ収集結果が0件。全コレクターが失敗しました。")
        sys.exit(1)

    # Step 2: 過去の配信履歴を読み込み
    history = load_history()
    past_names = get_past_names(history)
    if past_names:
        logger.info("過去の配信済みトレンド: %d 件を除外対象に設定", len(past_names))

    # Step 3: Gemini分析（構造化レポート）
    logger.info("Gemini日報分析を開始...")
    analysis = analyze_daily(collected, past_trend_names=past_names)
    if not analysis:
        logger.error("Gemini分析が結果を返しませんでした。")
        sys.exit(1)
    logger.info("日報分析完了")

    # Step 4: 参照リンクの補完（URLが空の参照に検索URLを自動生成）
    logger.info("参照リンクを補完中...")
    analysis = enrich_references(analysis)

    # Step 5: 参照URLの検証（トレンドTOP3のみ）
    top_trends = analysis.get("top_trends", [])
    if top_trends:
        logger.info("参照URLを検証中...")
        analysis["top_trends"] = validate_trends(top_trends)

    # Step 6: 日報データを保存（週報用）
    save_daily_analysis(analysis)

    # Step 7: レポートテキストを生成
    report_text = format_daily_report(analysis)
    logger.info("日報レポート生成完了（%d 文字）", len(report_text))

    # Step 8: LINE Works配信
    logger.info("LINE Works配信を開始...")
    success = send(report_text)
    if not success:
        logger.error("配信に失敗しました。")
        sys.exit(1)

    # Step 9: Notion データベースに保存
    logger.info("Notion に保存中...")
    notion_url = save_to_notion(analysis, "daily")
    if notion_url:
        logger.info("Notion 保存完了: %s", notion_url)

    # Step 10: 配信履歴を更新
    if top_trends:
        save_history(history, top_trends)

    # Step 11: 古いデータのクリーンアップ
    cleanup_old_reports()

    logger.info("=== 日報モード 完了 ===")


def run_weekly():
    """週報モード: 週間データ集約→分析→ダイジェスト生成→配信."""
    logger.info("=== 週報モード 開始 ===")

    # Step 1: 1週間分のデータを読み込み
    weekly_data = load_weekly_data()
    if not weekly_data:
        logger.error("週報用のデータがありません。日報が正常に動作しているか確認してください。")
        sys.exit(1)

    logger.info("週報分析開始: %d 日分のデータ", len(weekly_data))

    # Step 2: Gemini週報分析
    analysis = analyze_weekly(weekly_data)
    if not analysis:
        logger.error("Gemini週報分析が結果を返しませんでした。")
        sys.exit(1)
    logger.info("週報分析完了")

    # Step 3: 参照リンクの補完
    logger.info("参照リンクを補完中...")
    analysis = enrich_references(analysis)

    # Step 4: 週番号と日付範囲を取得
    week_number, date_range = get_week_info()

    # Step 5: レポートテキストを生成
    report_text = format_weekly_report(analysis, week_number, date_range)
    logger.info("週報レポート生成完了（%d 文字）", len(report_text))

    # Step 6: LINE Works配信
    logger.info("LINE Works配信を開始...")
    success = send(report_text)
    if not success:
        logger.error("週報配信に失敗しました。")
        sys.exit(1)

    # Step 7: Notion データベースに保存
    logger.info("Notion に保存中...")
    notion_url = save_to_notion(analysis, "weekly")
    if notion_url:
        logger.info("Notion 保存完了: %s", notion_url)

    logger.info("=== 週報モード 完了 ===")


def main():
    parser = argparse.ArgumentParser(description="海外フードトレンド レポート生成")
    parser.add_argument(
        "--mode",
        choices=["daily", "weekly"],
        default="daily",
        help="実行モード: daily（日報）or weekly（週報）",
    )
    args = parser.parse_args()

    if args.mode == "weekly":
        run_weekly()
    else:
        run_daily()


if __name__ == "__main__":
    main()
