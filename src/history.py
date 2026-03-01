"""過去に配信済みのトレンドを管理し、重複配信を防ぐ.

新しいアナライザーのtop_trends形式（name_en/name_ja）にも対応。
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))
HISTORY_FILE = Path(__file__).resolve().parent.parent / "data" / "history.json"
RETENTION_DAYS = 90


def load() -> list[dict]:
    """履歴ファイルを読み込む。存在しなければ空リストを返す."""
    if not HISTORY_FILE.exists():
        return []
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("履歴ファイル読み込み失敗: %s", e)
        return []


def get_past_names(history: list[dict]) -> list[str]:
    """保持期間内の過去トレンド名（英語・日本語両方）のリストを返す."""
    cutoff = datetime.now(JST) - timedelta(days=RETENTION_DAYS)
    names = []
    for entry in history:
        sent_at = entry.get("sent_at", "")
        if sent_at:
            try:
                entry_date = datetime.fromisoformat(sent_at)
                if entry_date < cutoff:
                    continue
            except ValueError:
                pass
        if entry.get("name_en"):
            names.append(entry["name_en"])
        if entry.get("name_ja"):
            names.append(entry["name_ja"])
    return names


def save(history: list[dict], new_trends: list[dict]) -> None:
    """新しいトレンドを履歴に追加して保存する.

    新旧両方の形式に対応:
    - 旧: product_name_en / product_name_ja
    - 新: name_en / name_ja
    """
    now = datetime.now(JST).isoformat()
    for t in new_trends:
        name_en = t.get("name_en") or t.get("product_name_en", "")
        name_ja = t.get("name_ja") or t.get("product_name_ja", "")
        history.append({
            "name_en": name_en,
            "name_ja": name_ja,
            "sent_at": now,
        })

    # 保持期間を過ぎたエントリーを削除
    cutoff = datetime.now(JST) - timedelta(days=RETENTION_DAYS)
    history = [
        e for e in history
        if not e.get("sent_at") or _parse_date(e["sent_at"]) >= cutoff
    ]

    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("履歴を更新: %d 件（新規 %d 件追加）", len(history), len(new_trends))


def _parse_date(s: str) -> datetime:
    """ISO形式の日時文字列をパース。失敗時は遠い過去を返す."""
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return datetime.min.replace(tzinfo=JST)
