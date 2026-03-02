"""NotebookLM ポッドキャスト用テキスト生成モジュール.

レポートの分析結果を、NotebookLM の Audio Overview で
自然な音声に変換しやすいテキスト形式に整形する。
前日との重複コンテンツを自動検出し、新規・更新情報のみを含める。
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))
WEEKDAYS_JA = ["月", "火", "水", "木", "金", "土", "日"]

# ディレクトリ
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "podcast_sources"
DAILY_REPORTS_DIR = Path(__file__).resolve().parent.parent / "data" / "daily_reports"


def generate_podcast_text(analysis: dict, report_type: str) -> str:
    """分析結果を NotebookLM 向けのテキストに変換する（重複除去あり）."""
    if report_type == "weekly":
        return _generate_weekly_text(analysis)
    prev = _load_previous_analysis()
    return _generate_daily_text(analysis, prev)


def save_podcast_source(text: str, date_str: str) -> Path:
    """テキストを podcast_sources ディレクトリに保存する."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"{date_str}.txt"
    path.write_text(text, encoding="utf-8")
    logger.info("ポッドキャスト用テキスト保存: %s", path)
    return path


def _ref_text(ref) -> str:
    """参照を表示テキストに変換する."""
    if isinstance(ref, dict):
        return ref.get("text", "")
    return str(ref)


# ────────────────────────────────────────────
# 前日データ読み込み & 差分検出
# ────────────────────────────────────────────

def _load_previous_analysis() -> dict | None:
    """前日の日報分析JSONを読み込む。なければNone."""
    if not DAILY_REPORTS_DIR.exists():
        return None
    now = datetime.now(JST)
    # 直近3日分を遡って探す（土日スキップ対応）
    for i in range(1, 4):
        date = now - timedelta(days=i)
        path = DAILY_REPORTS_DIR / f"{date.strftime('%Y-%m-%d')}.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                logger.info("前日データ読み込み: %s", path.name)
                return data
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("前日データ読み込み失敗: %s", e)
    return None


def _extract_trend_names(analysis: dict) -> set[str]:
    """top_trends から name_en のセットを抽出."""
    return {t.get("name_en", "") for t in analysis.get("top_trends", [])}


def _extract_headlines(items: list) -> set[str]:
    """headline のセットを抽出."""
    return {item.get("headline", "") for item in items if item.get("headline")}


def _is_trend_updated(current: dict, previous: dict) -> bool:
    """同名トレンドの内容が更新されているか判定."""
    # メトリクス、ライフサイクル、順位が変わっていれば更新あり
    for key in ("metrics", "lifecycle_stage", "rank", "why_trending"):
        if current.get(key) != previous.get(key):
            return True
    return False


def _find_prev_trend(name_en: str, prev_trends: list) -> dict | None:
    """前日のトレンドリストから同名のものを探す."""
    for t in prev_trends:
        if t.get("name_en") == name_en:
            return t
    return None


# ────────────────────────────────────────────
# 日報テキスト（重複除去対応）
# ────────────────────────────────────────────

def _generate_daily_text(analysis: dict, prev: dict | None = None) -> str:
    """日報を NotebookLM 向けテキストに変換する（前日との差分のみ）."""
    now = datetime.now(JST)
    date_str = f"{now.year}年{now.month}月{now.day}日"
    weekday = WEEKDAYS_JA[now.weekday()]

    # 前日データから比較用セットを作成
    prev_trend_names: set[str] = set()
    prev_trends_list: list[dict] = []
    prev_asia_headlines: dict[str, set[str]] = {}
    prev_news_headlines: dict[str, set[str]] = {}
    prev_foodtech_headlines: set[str] = set()
    prev_reg_headlines: set[str] = set()
    prev_action_texts: set[str] = set()

    if prev:
        prev_trend_names = _extract_trend_names(prev)
        prev_trends_list = prev.get("top_trends", [])
        for key in ("china", "korea", "taiwan", "southeast_asia"):
            prev_asia_headlines[key] = _extract_headlines(
                prev.get("asia_trends", {}).get(key, [])
            )
        for rkey in ("western", "asian"):
            prev_news_headlines[rkey] = _extract_headlines(
                prev.get("industry_news", {}).get(rkey, [])
            )
        prev_foodtech_headlines = _extract_headlines(prev.get("foodtech", []))
        prev_reg = prev.get("regulation", {})
        prev_reg_headlines = _extract_headlines(
            prev_reg.get("risks", []) + prev_reg.get("opportunities", [])
        )
        prev_action_texts = {
            a.get("action", "") for a in prev.get("action_items", [])
        }

    lines = []
    has_new_content = False

    lines.append(f"海外フード業界デイリーレポート {date_str}（{weekday}）")
    lines.append("")

    # 導入
    lines.append("このレポートでは、10以上の海外SNSやメディアから収集した"
                 "食品業界のトレンド情報をお伝えします。")
    lines.append("")

    # エグゼクティブサマリー（常に含める — 日付ごとに異なる）
    summary = analysis.get("executive_summary", "")
    if summary:
        lines.append("まず、今日の要点です。")
        lines.append(summary)
        lines.append("")

    # トレンドTOP3（新規・更新のみ詳細、継続は簡潔に）
    top_trends = analysis.get("top_trends", [])
    if top_trends:
        new_trends = []
        updated_trends = []
        continuing_trends = []

        for t in top_trends:
            name_en = t.get("name_en", "")
            if name_en not in prev_trend_names:
                new_trends.append(t)
            else:
                prev_t = _find_prev_trend(name_en, prev_trends_list)
                if prev_t and _is_trend_updated(t, prev_t):
                    updated_trends.append(t)
                else:
                    continuing_trends.append(t)

        if new_trends or updated_trends:
            has_new_content = True
            lines.append("注目トレンド商品についてです。")
            lines.append("")

            for t in new_trends:
                rank = t.get("rank", "?")
                name_en = t.get("name_en", "")
                name_ja = t.get("name_ja", "")
                name = f"{name_en}、日本語では{name_ja}" if name_ja else name_en
                lines.append(f"新たにランクインした第{rank}位は、{name}です。")
                lines.append(f"発祥は{t.get('origin', '不明')}で、"
                             f"{', '.join(t.get('detected_on', []))}で検出されました。")
                _append_trend_details(lines, t)
                lines.append("")

            for t in updated_trends:
                rank = t.get("rank", "?")
                name_en = t.get("name_en", "")
                name_ja = t.get("name_ja", "")
                name = f"{name_en}、日本語では{name_ja}" if name_ja else name_en
                lines.append(f"第{rank}位の{name}にアップデートがあります。")
                _append_trend_details(lines, t)
                lines.append("")

        if continuing_trends:
            names = "、".join(
                t.get("name_ja") or t.get("name_en", "") for t in continuing_trends
            )
            lines.append(f"なお、{names}は引き続きトレンド上位に入っています。")
            lines.append("")

    # アジア市場（新規ヘッドラインのみ）
    asia = analysis.get("asia_trends", {})
    if asia:
        asia_lines = []
        for key, label in [("china", "中国"), ("korea", "韓国"),
                           ("taiwan", "台湾"), ("southeast_asia", "東南アジア")]:
            items = asia.get(key, [])
            prev_hl = prev_asia_headlines.get(key, set())
            new_items = [i for i in items if i.get("headline", "") not in prev_hl]
            if new_items:
                asia_lines.append(f"{label}からは、")
                for item in new_items:
                    headline = item.get("headline", "")
                    detail = item.get("detail", "")
                    impl = item.get("implication", "")
                    asia_lines.append(f"{headline}。{detail}")
                    if impl:
                        asia_lines.append(f"マルイ物産への示唆として、{impl}")
                asia_lines.append("")

        if asia_lines:
            has_new_content = True
            lines.append("次に、アジア市場の新しい動きです。")
            lines.append("")
            lines.extend(asia_lines)

    # 外食産業ニュース（新規のみ）
    news = analysis.get("industry_news", {})
    if news:
        news_lines = []
        for rkey, rlabel in [("western", "欧米"), ("asian", "アジア")]:
            items = news.get(rkey, [])
            prev_hl = prev_news_headlines.get(rkey, set())
            new_items = [i for i in items if i.get("headline", "") not in prev_hl]
            if new_items:
                news_lines.append(f"{rlabel}の新しい動きとして、")
                for item in new_items:
                    headline = item.get("headline", "")
                    detail = item.get("detail", "")
                    impl = item.get("implication", "")
                    news_lines.append(f"{headline}。{detail}")
                    if impl:
                        news_lines.append(f"マルイ物産への示唆は、{impl}")
                news_lines.append("")

        if news_lines:
            has_new_content = True
            lines.append("外食産業ニュースに移ります。")
            lines.append("")
            lines.extend(news_lines)

    # フードテック（新規のみ）
    foodtech = analysis.get("foodtech", [])
    new_ft = [i for i in foodtech if i.get("headline", "") not in prev_foodtech_headlines]
    if new_ft:
        has_new_content = True
        lines.append("フードテック・イノベーション関連です。")
        lines.append("")
        for item in new_ft:
            headline = item.get("headline", "")
            detail = item.get("detail", "")
            impact = item.get("impact", "")
            lines.append(f"{headline}。{detail}")
            if impact:
                lines.append(f"外食産業への影響として、{impact}")
        lines.append("")

    # 規制・政策（新規のみ）
    reg = analysis.get("regulation", {})
    if reg:
        risks = reg.get("risks", [])
        opps = reg.get("opportunities", [])
        new_risks = [i for i in risks if i.get("headline", "") not in prev_reg_headlines]
        new_opps = [i for i in opps if i.get("headline", "") not in prev_reg_headlines]
        if new_risks or new_opps:
            has_new_content = True
            lines.append("規制・政策の新しい動きについてです。")
            lines.append("")
            for item in new_risks:
                lines.append(f"リスクとして、{item.get('headline', '')}。"
                             f"{item.get('detail', '')}")
            for item in new_opps:
                lines.append(f"チャンスとして、{item.get('headline', '')}。"
                             f"{item.get('detail', '')}")
            lines.append("")

    # アクション示唆（新規のみ）
    actions = analysis.get("action_items", [])
    new_actions = [a for a in actions if a.get("action", "") not in prev_action_texts]
    if new_actions:
        has_new_content = True
        lines.append("最後に、マルイ物産への新たなアクション示唆です。")
        lines.append("")
        for item in new_actions:
            priority = item.get("priority", "中")
            action = item.get("action", "")
            reason = item.get("reason", "")
            lines.append(f"優先度{priority}：{action}")
            if reason:
                lines.append(f"その理由は、{reason}")
        lines.append("")

    # 全セクションが前日と同じだった場合
    if not has_new_content and prev:
        lines.append("本日は前日からの大きな変動はありませんでした。"
                     "引き続き、既存トレンドの動向をウォッチしていきます。")
        lines.append("")

    lines.append("以上、本日の海外フード業界デイリーレポートでした。")

    return "\n".join(lines)


def _append_trend_details(lines: list[str], t: dict) -> None:
    """トレンド詳細をlinesに追加するヘルパー."""
    metrics = t.get("metrics", "")
    if metrics:
        lines.append(f"指標としては{metrics}となっています。")
    stage = t.get("lifecycle_stage", "")
    landing = t.get("japan_landing_estimate", "")
    if stage and landing:
        lines.append(f"現在のステージは{stage}で、日本上陸は{landing}と予測されます。")
    why = t.get("why_trending", "")
    if why:
        lines.append(f"流行の理由は、{why}")
    fit = t.get("japan_market_fit", "")
    if fit:
        lines.append(f"日本市場との親和性について、{fit}")
    proc = t.get("procurement_note", "")
    if proc:
        lines.append(f"調達面では、{proc}")


# ────────────────────────────────────────────
# 週報テキスト
# ────────────────────────────────────────────

def _generate_weekly_text(analysis: dict) -> str:
    """週報を NotebookLM 向けテキストに変換する."""
    now = datetime.now(JST)
    week_num = now.isocalendar()[1]

    lines = []

    lines.append(f"海外フード業界ウィークリーダイジェスト 第{week_num}週")
    lines.append("")
    lines.append("今週1週間の海外フードトレンドをまとめてお届けします。")
    lines.append("")

    # ハイライト
    highlight = analysis.get("highlight", "")
    if highlight:
        lines.append("今週のハイライトです。")
        lines.append(highlight)
        lines.append("")

    # トレンドまとめ
    ts = analysis.get("trend_summary", {})
    if ts:
        lines.append("トレンド商品のまとめです。")
        lines.append("")

        accel = ts.get("accelerating", [])
        if accel:
            lines.append("まず、加速しているトレンドです。")
            for item in accel:
                name = item.get("name", "")
                last = item.get("last_week", "")
                this = item.get("this_week", "")
                change = item.get("stage_change", "")
                lines.append(f"{name}は、先週{last}から今週{this}に成長しました。"
                             f"ステージは{change}。")
            lines.append("")

        new_items = ts.get("new_detected", [])
        if new_items:
            lines.append("今週新たに検出されたトレンドです。")
            for item in new_items:
                lines.append(f"{item.get('name', '')}。{item.get('description', '')}")
            lines.append("")

        decel = ts.get("decelerating", [])
        if decel:
            lines.append("減速傾向にあるトレンドです。")
            for item in decel:
                lines.append(f"{item.get('name', '')}。{item.get('change', '')}")
            lines.append("")

    # アジア市場
    asia = analysis.get("asia_weekly", {})
    if asia:
        lines.append("アジア市場の今週のサマリーです。")
        lines.append("")
        for key, label in [("china", "中国"), ("taiwan", "台湾"),
                           ("korea", "韓国"), ("southeast_asia", "東南アジア")]:
            region = asia.get(key, {})
            if region:
                rating = region.get("rating", 0)
                lines.append(f"{label}の今週の注目度は5段階中{rating}です。")
                summary_text = region.get("summary", "")
                if summary_text:
                    lines.append(summary_text)
                lines.append("")

    # 業界動向
    industry = analysis.get("industry_weekly", {})
    if industry:
        lines.append("業界動向のまとめです。")
        lines.append("")
        for ckey, clabel in [("important", "重要ニュース"),
                             ("technology", "テクノロジー"),
                             ("regulation", "規制・政策")]:
            items = industry.get(ckey, [])
            if items:
                lines.append(f"{clabel}として、")
                for item in items:
                    lines.append(f"{item.get('headline', '')}。")
                lines.append("")

    # 来週の展望
    outlook = analysis.get("next_week_outlook", [])
    if outlook:
        lines.append("来週の注目ポイントです。")
        for item in outlook:
            point = item.get("point", "")
            detail = item.get("detail", "")
            lines.append(f"{point}。{detail}")
        lines.append("")

    lines.append("以上、今週のウィークリーダイジェストでした。")

    return "\n".join(lines)
