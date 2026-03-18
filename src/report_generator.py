"""構造化レポートのテキスト整形.

Gemini分析結果のJSONを、LINE配信用のプレーンテキストレポートに変換する。
日報（デイリー）と週報（ウィークリー）の2フォーマットに対応。
"""

import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))

# 曜日の日本語表記
WEEKDAYS_JA = ["月", "火", "水", "木", "金", "土", "日"]

LIFECYCLE_LEGEND = (
    "※ステージ凡例:\n"
    "■□□□□ 発生期 → ■■□□□ 成長初期\n"
    "→ ■■■□□ 成長期 → ■■■■□ ピーク期\n"
    "→ ■■■■■ 日本波及開始"
)


def format_daily_report(analysis: dict) -> str:
    """日報のテキストレポートを生成."""
    now = datetime.now(JST)
    date_str = f"{now.year}年{now.month}月{now.day}日"
    weekday = WEEKDAYS_JA[now.weekday()]

    sections = []

    # ━━ ヘッダー ━━
    sections.append(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "  海外フード業界 デイリーレポート\n"
        f"  {date_str}（{weekday}）\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    # ━━ エグゼクティブサマリー ━━
    summary = analysis.get("executive_summary", "")
    if summary:
        sections.append(f"■ エグゼクティブサマリー\n\n{summary}")

    # ━━ 注目トレンド商品 TOP3 ━━
    top_trends = analysis.get("top_trends", [])
    if top_trends:
        trend_lines = ["■ 注目トレンド商品 TOP3"]
        for t in top_trends:
            rank = t.get("rank", "?")
            name_en = t.get("name_en", "Unknown")
            name_ja = t.get("name_ja", "")
            if name_ja:
                name_display = f"{name_en}（{name_ja}）"
            else:
                name_display = name_en

            detected = ", ".join(t.get("detected_on", []))
            bar = t.get("lifecycle_bar", "□□□□□")
            stage = t.get("lifecycle_stage", "不明")

            trend_lines.append(f"\n【{rank}位】{name_display}")
            trend_lines.append(f"  発祥: {t.get('origin', '不明')}")
            trend_lines.append(f"  検出: {detected}")
            trend_lines.append(f"  指標: {t.get('metrics', 'N/A')}")
            trend_lines.append(f"  ステージ: {bar} {stage}")
            trend_lines.append(f"  日本上陸予測: {t.get('japan_landing_estimate', '不明')}")
            trend_lines.append("  ─ ─ ─")
            trend_lines.append(f"  流行理由: {t.get('why_trending', '')}")
            trend_lines.append(f"  日本市場: {t.get('japan_market_fit', '')}")
            trend_lines.append(f"  調達可能性: {t.get('procurement_note', '')}")

            refs = t.get("references", [])
            if refs:
                trend_lines.append("  参照:")
                for ref in refs:
                    trend_lines.append(f"    {_format_ref(ref)}")
            trend_lines.append("──────────────────")

        trend_lines.append(f"\n  {LIFECYCLE_LEGEND}")
        sections.append("\n".join(trend_lines))

    # ━━ アジア市場トレンド ━━
    asia = analysis.get("asia_trends", {})
    if asia:
        asia_lines = ["■ アジア市場トレンド"]
        region_map = {
            "china": "中国",
            "korea": "韓国",
            "taiwan": "台湾",
            "southeast_asia": "東南アジア",
        }
        for key, label in region_map.items():
            items = asia.get(key, [])
            if items:
                asia_lines.append(f"\n◆ {label}")
                for item in items:
                    asia_lines.append(f"  ▸ {item.get('headline', '')}")
                    detail = item.get("detail", "")
                    if detail:
                        for line in _wrap_text(detail, 38):
                            asia_lines.append(f"    {line}")
                    impl = item.get("implication", "")
                    if impl:
                        asia_lines.append(f"    → {impl}")
                    refs = item.get("references", [])
                    if refs:
                        asia_lines.append(f"    参照: {_format_refs_inline(refs)}")
                    asia_lines.append("")
        sections.append("\n".join(asia_lines))

    # ━━ 外食産業ニュース ━━
    news = analysis.get("industry_news", {})
    if news:
        news_lines = ["■ 外食産業ニュース"]
        for region_key, region_label in [("western", "米国・欧州"), ("asian", "アジア")]:
            items = news.get(region_key, [])
            if items:
                news_lines.append(f"\n◆ {region_label}")
                for item in items:
                    news_lines.append(f"\n  ▸ {item.get('headline', '')}")
                    detail = item.get("detail", "")
                    if detail:
                        for line in _wrap_text(detail, 38):
                            news_lines.append(f"    {line}")
                    impl = item.get("implication", "")
                    if impl:
                        news_lines.append(f"    → マルイ物産への示唆: {impl}")
                    refs = item.get("references", [])
                    if refs:
                        news_lines.append(f"    参照: {_format_refs_inline(refs)}")
        sections.append("\n".join(news_lines))

    # ━━ フードテック・イノベーション ━━
    foodtech = analysis.get("foodtech", [])
    if foodtech:
        ft_lines = ["■ フードテック・イノベーション"]
        for item in foodtech:
            ft_lines.append(f"\n  ▸ {item.get('headline', '')}")
            detail = item.get("detail", "")
            if detail:
                for line in _wrap_text(detail, 38):
                    ft_lines.append(f"    {line}")
            impact = item.get("impact", "")
            if impact:
                ft_lines.append(f"    影響: {impact}")
            refs = item.get("references", [])
            if refs:
                ft_lines.append(f"    参照: {_format_refs_inline(refs)}")
        sections.append("\n".join(ft_lines))

    # ━━ 規制・政策ウォッチ ━━
    reg = analysis.get("regulation", {})
    if reg:
        reg_lines = ["■ 規制・政策ウォッチ"]

        risks = reg.get("risks", [])
        if risks:
            for item in risks:
                reg_lines.append(f"\n  ⚠ リスク")
                reg_lines.append(f"  ▸ {item.get('headline', '')}")
                detail = item.get("detail", "")
                if detail:
                    for line in _wrap_text(detail, 38):
                        reg_lines.append(f"    {line}")
                impact = item.get("impact", "")
                if impact:
                    reg_lines.append(f"    影響: {impact}")
                refs = item.get("references", [])
                if refs:
                    reg_lines.append(f"    参照: {_format_refs_inline(refs)}")

        opps = reg.get("opportunities", [])
        if opps:
            for item in opps:
                reg_lines.append(f"\n  チャンス（規制緩和・撤廃）")
                reg_lines.append(f"  ▸ {item.get('headline', '')}")
                detail = item.get("detail", "")
                if detail:
                    for line in _wrap_text(detail, 38):
                        reg_lines.append(f"    {line}")
                opp = item.get("opportunity", "")
                if opp:
                    reg_lines.append(f"    → チャンス: {opp}")
                refs = item.get("references", [])
                if refs:
                    reg_lines.append(f"    参照: {_format_refs_inline(refs)}")
        sections.append("\n".join(reg_lines))

    # ━━ アクション示唆 ━━
    actions = analysis.get("action_items", [])
    if actions:
        action_lines = ["■ マルイ物産へのアクション示唆"]
        for item in actions:
            priority = item.get("priority", "中")
            action = item.get("action", "")
            reason = item.get("reason", "")
            action_lines.append(f"\n[{priority}] {action}")
            if reason:
                action_lines.append(f"  理由: {reason}")
        sections.append("\n".join(action_lines))

    # ━━ フッター ━━
    sections.append(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "  マルイ物産 AI デイリーブリーフィング\n"
        "  Powered by Gemini × 10+ SNS/メディア分析\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    return "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n".join(sections)


def format_weekly_report(analysis: dict, week_number: int, date_range: str) -> str:
    """週報のテキストレポートを生成."""
    sections = []

    # ━━ ヘッダー ━━
    sections.append(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "  海外フード業界 ウィークリーダイジェスト\n"
        f"  2026年 第{week_number}週（{date_range}）\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    # ━━ 今週のハイライト ━━
    highlight = analysis.get("highlight", "")
    if highlight:
        sections.append(f"■ 今週のハイライト\n\n{highlight}")

    # ━━ トレンド商品まとめ ━━
    trend_summary = analysis.get("trend_summary", {})
    if trend_summary:
        ts_lines = ["■ 今週のトレンド商品まとめ"]

        accel = trend_summary.get("accelerating", [])
        if accel:
            ts_lines.append("\n  トレンド加速 ↑↑")
            for item in accel:
                ts_lines.append(f"  ・{item.get('name', '')}")
                ts_lines.append(f"    先週: {item.get('last_week', '')} → 今週: {item.get('this_week', '')}")
                ts_lines.append(f"    ステージ: {item.get('stage_change', '')}")
                refs = item.get("references", [])
                if refs:
                    ts_lines.append(f"    参照: {_format_refs_inline(refs)}")
                ts_lines.append("")

        new_items = trend_summary.get("new_detected", [])
        if new_items:
            ts_lines.append("  新規検出")
            for item in new_items:
                ts_lines.append(f"  ・{item.get('name', '')}")
                ts_lines.append(f"    {item.get('description', '')}")
                ts_lines.append(f"    ステージ: {item.get('stage', '')}")
                refs = item.get("references", [])
                if refs:
                    ts_lines.append(f"    参照: {_format_refs_inline(refs)}")
                ts_lines.append("")

        decel = trend_summary.get("decelerating", [])
        if decel:
            ts_lines.append("  トレンド減速 ↓")
            for item in decel:
                ts_lines.append(f"  ・{item.get('name', '')}")
                ts_lines.append(f"    {item.get('change', '')}")
                refs = item.get("references", [])
                if refs:
                    ts_lines.append(f"    参照: {_format_refs_inline(refs)}")
                ts_lines.append("")

        sections.append("\n".join(ts_lines))

    # ━━ アジア市場サマリー ━━
    asia = analysis.get("asia_weekly", {})
    if asia:
        asia_lines = ["■ 今週のアジア市場サマリー"]
        region_map = {
            "china": "中国",
            "taiwan": "台湾",
            "korea": "韓国",
            "southeast_asia": "東南アジア",
        }
        for key, label in region_map.items():
            region = asia.get(key, {})
            if region:
                rating = region.get("rating", 0)
                stars = "★" * rating + "☆" * (5 - rating)
                asia_lines.append(f"\n◆ {label}（今週の注目度: {stars}）")
                summary_text = region.get("summary", "")
                if summary_text:
                    for line in _wrap_text(summary_text, 38):
                        asia_lines.append(f"  {line}")
                refs = region.get("references", [])
                if refs:
                    asia_lines.append(f"  参照: {_format_refs_inline(refs)}")
        sections.append("\n".join(asia_lines))

    # ━━ 業界動向まとめ ━━
    industry = analysis.get("industry_weekly", {})
    if industry:
        ind_lines = ["■ 今週の業界動向まとめ"]

        for category_key, category_label in [
            ("important", "重要度高"),
            ("technology", "テクノロジー"),
            ("regulation", "規制・政策"),
        ]:
            items = industry.get(category_key, [])
            if items:
                ind_lines.append(f"\n  {category_label}")
                for item in items:
                    emoji = item.get("emoji", "")
                    headline = item.get("headline", "")
                    display = f"  ・{headline} {emoji}" if emoji else f"  ・{headline}"
                    ind_lines.append(display)
                    refs = item.get("references", [])
                    if refs:
                        ind_lines.append(f"    参照: {_format_refs_inline(refs)}")
        sections.append("\n".join(ind_lines))

    # ━━ 来週の注目ポイント ━━
    outlook = analysis.get("next_week_outlook", [])
    if outlook:
        out_lines = ["■ 来週の注目ポイント"]
        for item in outlook:
            out_lines.append(f"\n  ▸ {item.get('point', '')}")
            detail = item.get("detail", "")
            if detail:
                for line in _wrap_text(detail, 38):
                    out_lines.append(f"    {line}")
        sections.append("\n".join(out_lines))

    # ━━ フッター ━━
    sections.append(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "  マルイ物産 AI ウィークリーダイジェスト\n"
        "  Powered by Gemini × 10+ SNS/メディア分析\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    return "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n".join(sections)


def _format_ref(ref) -> str:
    """参照を表示用テキストに変換する.

    dict形式: {"text": "...", "url": "..."} → "text (url)" or "text"
    str形式: そのまま返す
    """
    if isinstance(ref, dict):
        text = ref.get("text", "")
        url = ref.get("url", "")
        if url:
            return f"{text}\n      {url}"
        return text
    return str(ref)


def _format_refs_inline(refs: list) -> str:
    """参照リストをインライン表示用テキストに変換する."""
    return " / ".join(_format_ref(r) for r in refs)


def _wrap_text(text: str, width: int) -> list[str]:
    """テキストを指定幅で折り返す（日本語対応）."""
    if not text:
        return []
    lines = []
    current = ""
    for char in text:
        if char == "\n":
            if current:
                lines.append(current)
            current = ""
            continue
        current += char
        if len(current) >= width:
            lines.append(current)
            current = ""
    if current:
        lines.append(current)
    return lines
