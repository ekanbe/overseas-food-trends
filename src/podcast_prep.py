"""NotebookLM ポッドキャスト用テキスト生成モジュール.

レポートの分析結果を、NotebookLM の Audio Overview で
自然な音声に変換しやすいテキスト形式に整形する。
"""

import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))
WEEKDAYS_JA = ["月", "火", "水", "木", "金", "土", "日"]

# 出力先ディレクトリ
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "podcast_sources"


def generate_podcast_text(analysis: dict, report_type: str) -> str:
    """分析結果を NotebookLM 向けのテキストに変換する."""
    if report_type == "weekly":
        return _generate_weekly_text(analysis)
    return _generate_daily_text(analysis)


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
# 日報テキスト
# ────────────────────────────────────────────

def _generate_daily_text(analysis: dict) -> str:
    """日報を NotebookLM 向けテキストに変換する."""
    now = datetime.now(JST)
    date_str = f"{now.year}年{now.month}月{now.day}日"
    weekday = WEEKDAYS_JA[now.weekday()]

    lines = []

    lines.append(f"海外フード業界デイリーレポート {date_str}（{weekday}）")
    lines.append("")

    # 導入
    lines.append("このレポートでは、10以上の海外SNSやメディアから収集した"
                 "食品業界のトレンド情報をお伝えします。")
    lines.append("")

    # エグゼクティブサマリー
    summary = analysis.get("executive_summary", "")
    if summary:
        lines.append("まず、今日の要点です。")
        lines.append(summary)
        lines.append("")

    # トレンドTOP3
    top_trends = analysis.get("top_trends", [])
    if top_trends:
        lines.append("続いて、注目トレンド商品トップ3をご紹介します。")
        lines.append("")
        for t in top_trends:
            rank = t.get("rank", "?")
            name_en = t.get("name_en", "")
            name_ja = t.get("name_ja", "")
            name = f"{name_en}、日本語では{name_ja}" if name_ja else name_en

            lines.append(f"第{rank}位は、{name}です。")
            lines.append(f"発祥は{t.get('origin', '不明')}で、"
                         f"{', '.join(t.get('detected_on', []))}で検出されました。")

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

            lines.append("")

    # アジア市場
    asia = analysis.get("asia_trends", {})
    if asia:
        lines.append("次に、アジア市場のトレンドです。")
        lines.append("")
        for key, label in [("china", "中国"), ("korea", "韓国"),
                           ("taiwan", "台湾"), ("southeast_asia", "東南アジア")]:
            items = asia.get(key, [])
            if items:
                lines.append(f"{label}からは、")
                for item in items:
                    headline = item.get("headline", "")
                    detail = item.get("detail", "")
                    impl = item.get("implication", "")
                    lines.append(f"{headline}。{detail}")
                    if impl:
                        lines.append(f"マルイ物産への示唆として、{impl}")
                lines.append("")

    # 外食産業ニュース
    news = analysis.get("industry_news", {})
    if news:
        lines.append("外食産業ニュースに移ります。")
        lines.append("")
        for rkey, rlabel in [("western", "欧米"), ("asian", "アジア")]:
            items = news.get(rkey, [])
            if items:
                lines.append(f"{rlabel}の動きとして、")
                for item in items:
                    headline = item.get("headline", "")
                    detail = item.get("detail", "")
                    impl = item.get("implication", "")
                    lines.append(f"{headline}。{detail}")
                    if impl:
                        lines.append(f"マルイ物産への示唆は、{impl}")
                lines.append("")

    # フードテック
    foodtech = analysis.get("foodtech", [])
    if foodtech:
        lines.append("フードテック・イノベーション関連です。")
        lines.append("")
        for item in foodtech:
            headline = item.get("headline", "")
            detail = item.get("detail", "")
            impact = item.get("impact", "")
            lines.append(f"{headline}。{detail}")
            if impact:
                lines.append(f"外食産業への影響として、{impact}")
        lines.append("")

    # 規制・政策
    reg = analysis.get("regulation", {})
    if reg:
        risks = reg.get("risks", [])
        opps = reg.get("opportunities", [])
        if risks or opps:
            lines.append("規制・政策の動きについてです。")
            lines.append("")
            for item in risks:
                lines.append(f"リスクとして、{item.get('headline', '')}。"
                             f"{item.get('detail', '')}")
            for item in opps:
                lines.append(f"チャンスとして、{item.get('headline', '')}。"
                             f"{item.get('detail', '')}")
            lines.append("")

    # アクション示唆
    actions = analysis.get("action_items", [])
    if actions:
        lines.append("最後に、マルイ物産へのアクション示唆です。")
        lines.append("")
        for item in actions:
            priority = item.get("priority", "中")
            action = item.get("action", "")
            reason = item.get("reason", "")
            lines.append(f"優先度{priority}：{action}")
            if reason:
                lines.append(f"その理由は、{reason}")
        lines.append("")

    lines.append("以上、本日の海外フード業界デイリーレポートでした。")

    return "\n".join(lines)


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
