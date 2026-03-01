"""週報用データ集約.

過去1週間分の日報データ（history.jsonに保存されたanalysis結果）を
集約して、週報分析に渡すためのデータを構築する。
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))
DAILY_REPORTS_DIR = Path(__file__).resolve().parent.parent / "data" / "daily_reports"


def save_daily_analysis(analysis: dict) -> None:
    """日報の分析結果を日付付きで保存."""
    DAILY_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(JST).strftime("%Y-%m-%d")
    filepath = DAILY_REPORTS_DIR / f"{today}.json"
    filepath.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("日報データ保存: %s", filepath.name)


def load_weekly_data() -> list[dict]:
    """過去7日分の日報分析データを読み込む."""
    if not DAILY_REPORTS_DIR.exists():
        logger.warning("日報データディレクトリが存在しません")
        return []

    now = datetime.now(JST)
    weekly_data = []

    for i in range(7):
        date = now - timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        filepath = DAILY_REPORTS_DIR / f"{date_str}.json"
        if filepath.exists():
            try:
                data = json.loads(filepath.read_text(encoding="utf-8"))
                data["_report_date"] = date_str
                weekly_data.append(data)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("日報データ読み込み失敗 (%s): %s", date_str, e)

    logger.info("週報用データ: %d 日分を読み込み", len(weekly_data))
    return weekly_data


def get_week_info() -> tuple[int, str]:
    """現在の週番号と日付範囲を返す."""
    now = datetime.now(JST)
    week_number = now.isocalendar()[1]

    # 週の開始日（月曜）と終了日（日曜）
    monday = now - timedelta(days=now.weekday())
    sunday = monday + timedelta(days=6)

    date_range = f"{monday.strftime('%-m/%-d')}〜{sunday.strftime('%-m/%-d')}"
    return week_number, date_range


def cleanup_old_reports(keep_days: int = 30) -> None:
    """古い日報データファイルを削除."""
    if not DAILY_REPORTS_DIR.exists():
        return

    cutoff = datetime.now(JST) - timedelta(days=keep_days)

    for filepath in DAILY_REPORTS_DIR.glob("*.json"):
        try:
            date_str = filepath.stem
            file_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=JST)
            if file_date < cutoff:
                filepath.unlink()
                logger.info("古い日報データを削除: %s", filepath.name)
        except (ValueError, OSError):
            pass
