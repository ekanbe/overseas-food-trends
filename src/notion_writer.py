"""Notion データベースへのレポート蓄積モジュール.

日報/週報の分析結果を Notion データベースにページとして保存する。
セクションごとに Heading + Paragraph ブロック構造で蓄積し、
参照リンクは Notion のリッチテキストリンクとして表示する。
"""

import json
import logging
import os
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))

# Notion API のブロックあたり文字数上限
NOTION_TEXT_LIMIT = 2000


def _get_client():
    """Notion クライアントを取得する."""
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        logger.warning("NOTION_TOKEN が未設定のため Notion 保存をスキップ")
        return None

    try:
        from notion_client import Client
        return Client(auth=token)
    except ImportError:
        logger.warning("notion-client がインストールされていません")
        return None


def save_to_notion(analysis: dict, report_type: str) -> str | None:
    """分析結果を Notion データベースにページとして保存する.

    Args:
        analysis: Gemini分析結果のdict
        report_type: "daily" or "weekly"

    Returns:
        作成したページのURL。失敗時はNone。
    """
    client = _get_client()
    if not client:
        return None

    database_id = os.environ.get("NOTION_DATABASE_ID")
    if not database_id:
        logger.warning("NOTION_DATABASE_ID が未設定のため Notion 保存をスキップ")
        return None

    try:
        now = datetime.now(JST)
        title = _build_title(report_type, now)
        properties = _build_properties(title, report_type, analysis, now)
        children = _build_blocks(analysis, report_type)

        # Notion API は 1 リクエストあたり最大 100 ブロック
        # 最初の 100 ブロックはページ作成時に追加
        first_batch = children[:100]
        remaining = children[100:]

        page = client.pages.create(
            parent={"database_id": database_id},
            properties=properties,
            children=first_batch,
        )

        page_id = page["id"]

        # 残りのブロックを追加
        while remaining:
            batch = remaining[:100]
            remaining = remaining[100:]
            client.blocks.children.append(block_id=page_id, children=batch)

        page_url = page.get("url", "")
        logger.info("Notion ページ作成成功: %s", page_url)
        return page_url

    except Exception as e:
        logger.error("Notion 保存失敗: %s", e)
        return None


def _build_title(report_type: str, now: datetime) -> str:
    """ページタイトルを生成する."""
    if report_type == "weekly":
        week_num = now.isocalendar()[1]
        return f"週報 第{week_num}週"
    return f"日報 {now.year}-{now.month:02d}-{now.day:02d}"


def _build_properties(title: str, report_type: str, analysis: dict, now: datetime) -> dict:
    """Notion ページのプロパティを構築する."""
    trend_count = len(analysis.get("top_trends", []))
    if report_type == "weekly":
        ts = analysis.get("trend_summary", {})
        trend_count = (
            len(ts.get("accelerating", []))
            + len(ts.get("new_detected", []))
            + len(ts.get("decelerating", []))
        )

    return {
        "タイトル": {"title": [{"text": {"content": title}}]},
        "日付": {"date": {"start": now.strftime("%Y-%m-%d")}},
        "種別": {"select": {"name": "日報" if report_type == "daily" else "週報"}},
        "トレンド数": {"number": trend_count},
        "ステータス": {"select": {"name": "配信済み"}},
    }


def _build_blocks(analysis: dict, report_type: str) -> list[dict]:
    """分析結果を Notion ブロックに変換する."""
    if report_type == "weekly":
        return _build_weekly_blocks(analysis)
    return _build_daily_blocks(analysis)


# ────────────────────────────────────────────
# 日報ブロック
# ────────────────────────────────────────────

def _build_daily_blocks(analysis: dict) -> list[dict]:
    """日報の分析結果を Notion ブロックに変換する."""
    blocks = []

    # エグゼクティブサマリー
    summary = analysis.get("executive_summary", "")
    if summary:
        blocks.append(_heading2("エグゼクティブサマリー"))
        blocks.extend(_paragraphs(summary))

    # 注目トレンド商品 TOP3
    top_trends = analysis.get("top_trends", [])
    if top_trends:
        blocks.append(_heading2("注目トレンド商品 TOP3"))
        for t in top_trends:
            rank = t.get("rank", "?")
            name_en = t.get("name_en", "Unknown")
            name_ja = t.get("name_ja", "")
            name = f"【{rank}位】{name_en}（{name_ja}）" if name_ja else f"【{rank}位】{name_en}"
            blocks.append(_heading3(name))

            details = []
            details.append(f"発祥: {t.get('origin', '不明')}")
            details.append(f"検出: {', '.join(t.get('detected_on', []))}")
            details.append(f"指標: {t.get('metrics', 'N/A')}")
            bar = t.get("lifecycle_bar", "□□□□□")
            stage = t.get("lifecycle_stage", "不明")
            details.append(f"ステージ: {bar} {stage}")
            details.append(f"日本上陸予測: {t.get('japan_landing_estimate', '不明')}")
            blocks.extend(_paragraphs("\n".join(details)))

            why = t.get("why_trending", "")
            if why:
                blocks.extend(_paragraphs(f"流行理由: {why}"))
            fit = t.get("japan_market_fit", "")
            if fit:
                blocks.extend(_paragraphs(f"日本市場: {fit}"))
            proc = t.get("procurement_note", "")
            if proc:
                blocks.extend(_paragraphs(f"調達可能性: {proc}"))

            refs = t.get("references", [])
            if refs:
                blocks.extend(_ref_blocks(refs))
            blocks.append(_divider())

    # アジア市場トレンド
    asia = analysis.get("asia_trends", {})
    if asia:
        blocks.append(_heading2("アジア市場トレンド"))
        for key, label in [("china", "中国"), ("korea", "韓国"), ("taiwan", "台湾"), ("southeast_asia", "東南アジア")]:
            items = asia.get(key, [])
            if items:
                blocks.append(_heading3(label))
                for item in items:
                    blocks.extend(_paragraphs(f"▸ {item.get('headline', '')}"))
                    detail = item.get("detail", "")
                    if detail:
                        blocks.extend(_paragraphs(detail))
                    impl = item.get("implication", "")
                    if impl:
                        blocks.extend(_paragraphs(f"→ {impl}"))
                    refs = item.get("references", [])
                    if refs:
                        blocks.extend(_ref_blocks(refs))

    # 外食産業ニュース
    news = analysis.get("industry_news", {})
    if news:
        blocks.append(_heading2("外食産業ニュース"))
        for rkey, rlabel in [("western", "米国・欧州"), ("asian", "アジア")]:
            items = news.get(rkey, [])
            if items:
                blocks.append(_heading3(rlabel))
                for item in items:
                    blocks.extend(_paragraphs(f"▸ {item.get('headline', '')}"))
                    detail = item.get("detail", "")
                    if detail:
                        blocks.extend(_paragraphs(detail))
                    impl = item.get("implication", "")
                    if impl:
                        blocks.extend(_paragraphs(f"→ マルイ物産への示唆: {impl}"))
                    refs = item.get("references", [])
                    if refs:
                        blocks.extend(_ref_blocks(refs))

    # フードテック
    foodtech = analysis.get("foodtech", [])
    if foodtech:
        blocks.append(_heading2("フードテック・イノベーション"))
        for item in foodtech:
            blocks.extend(_paragraphs(f"▸ {item.get('headline', '')}"))
            detail = item.get("detail", "")
            if detail:
                blocks.extend(_paragraphs(detail))
            impact = item.get("impact", "")
            if impact:
                blocks.extend(_paragraphs(f"影響: {impact}"))
            refs = item.get("references", [])
            if refs:
                blocks.extend(_ref_blocks(refs))

    # 規制・政策
    reg = analysis.get("regulation", {})
    if reg:
        blocks.append(_heading2("規制・政策ウォッチ"))
        for item in reg.get("risks", []):
            blocks.extend(_paragraphs(f"⚠ リスク: {item.get('headline', '')}"))
            detail = item.get("detail", "")
            if detail:
                blocks.extend(_paragraphs(detail))
            refs = item.get("references", [])
            if refs:
                blocks.extend(_ref_blocks(refs))
        for item in reg.get("opportunities", []):
            blocks.extend(_paragraphs(f"チャンス: {item.get('headline', '')}"))
            detail = item.get("detail", "")
            if detail:
                blocks.extend(_paragraphs(detail))
            refs = item.get("references", [])
            if refs:
                blocks.extend(_ref_blocks(refs))

    # アクション示唆
    actions = analysis.get("action_items", [])
    if actions:
        blocks.append(_heading2("マルイ物産へのアクション示唆"))
        for item in actions:
            priority = item.get("priority", "中")
            action = item.get("action", "")
            reason = item.get("reason", "")
            text = f"[{priority}] {action}"
            if reason:
                text += f"\n理由: {reason}"
            blocks.extend(_paragraphs(text))

    return blocks


# ────────────────────────────────────────────
# 週報ブロック
# ────────────────────────────────────────────

def _build_weekly_blocks(analysis: dict) -> list[dict]:
    """週報の分析結果を Notion ブロックに変換する."""
    blocks = []

    # ハイライト
    highlight = analysis.get("highlight", "")
    if highlight:
        blocks.append(_heading2("今週のハイライト"))
        blocks.extend(_paragraphs(highlight))

    # トレンド商品まとめ
    ts = analysis.get("trend_summary", {})
    if ts:
        blocks.append(_heading2("今週のトレンド商品まとめ"))

        accel = ts.get("accelerating", [])
        if accel:
            blocks.append(_heading3("トレンド加速"))
            for item in accel:
                text = f"・{item.get('name', '')}\n"
                text += f"先週: {item.get('last_week', '')} → 今週: {item.get('this_week', '')}\n"
                text += f"ステージ: {item.get('stage_change', '')}"
                blocks.extend(_paragraphs(text))
                refs = item.get("references", [])
                if refs:
                    blocks.extend(_ref_blocks(refs))

        new_items = ts.get("new_detected", [])
        if new_items:
            blocks.append(_heading3("新規検出"))
            for item in new_items:
                text = f"・{item.get('name', '')}\n{item.get('description', '')}"
                blocks.extend(_paragraphs(text))
                refs = item.get("references", [])
                if refs:
                    blocks.extend(_ref_blocks(refs))

        decel = ts.get("decelerating", [])
        if decel:
            blocks.append(_heading3("トレンド減速"))
            for item in decel:
                text = f"・{item.get('name', '')}\n{item.get('change', '')}"
                blocks.extend(_paragraphs(text))
                refs = item.get("references", [])
                if refs:
                    blocks.extend(_ref_blocks(refs))

    # アジア市場サマリー
    asia = analysis.get("asia_weekly", {})
    if asia:
        blocks.append(_heading2("今週のアジア市場サマリー"))
        for key, label in [("china", "中国"), ("taiwan", "台湾"), ("korea", "韓国"), ("southeast_asia", "東南アジア")]:
            region = asia.get(key, {})
            if region:
                rating = region.get("rating", 0)
                stars = "★" * rating + "☆" * (5 - rating)
                blocks.append(_heading3(f"{label}（注目度: {stars}）"))
                summary_text = region.get("summary", "")
                if summary_text:
                    blocks.extend(_paragraphs(summary_text))
                refs = region.get("references", [])
                if refs:
                    blocks.extend(_ref_blocks(refs))

    # 業界動向
    industry = analysis.get("industry_weekly", {})
    if industry:
        blocks.append(_heading2("今週の業界動向まとめ"))
        for ckey, clabel in [("important", "重要度高"), ("technology", "テクノロジー"), ("regulation", "規制・政策")]:
            items = industry.get(ckey, [])
            if items:
                blocks.append(_heading3(clabel))
                for item in items:
                    headline = item.get("headline", "")
                    blocks.extend(_paragraphs(f"・{headline}"))
                    refs = item.get("references", [])
                    if refs:
                        blocks.extend(_ref_blocks(refs))

    # 来週の注目ポイント
    outlook = analysis.get("next_week_outlook", [])
    if outlook:
        blocks.append(_heading2("来週の注目ポイント"))
        for item in outlook:
            text = f"▸ {item.get('point', '')}"
            detail = item.get("detail", "")
            if detail:
                text += f"\n{detail}"
            blocks.extend(_paragraphs(text))

    return blocks


# ────────────────────────────────────────────
# ブロック生成ヘルパー
# ────────────────────────────────────────────

def _heading2(text: str) -> dict:
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{"type": "text", "text": {"content": text[:NOTION_TEXT_LIMIT]}}]
        },
    }


def _heading3(text: str) -> dict:
    return {
        "object": "block",
        "type": "heading_3",
        "heading_3": {
            "rich_text": [{"type": "text", "text": {"content": text[:NOTION_TEXT_LIMIT]}}]
        },
    }


def _paragraph(rich_text: list[dict]) -> dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": rich_text},
    }


def _paragraphs(text: str) -> list[dict]:
    """テキストを Notion の文字数制限に合わせて段落ブロックに分割する."""
    if not text:
        return []
    blocks = []
    while text:
        chunk = text[:NOTION_TEXT_LIMIT]
        text = text[NOTION_TEXT_LIMIT:]
        blocks.append(_paragraph([{"type": "text", "text": {"content": chunk}}]))
    return blocks


def _divider() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


def _ref_blocks(refs: list) -> list[dict]:
    """参照リストを Notion のリッチテキストブロックに変換する.

    URLがある参照はリンク付きリッチテキストにする。
    """
    rich_text_parts = [{"type": "text", "text": {"content": "参照: "}}]

    for i, ref in enumerate(refs):
        if i > 0:
            rich_text_parts.append({"type": "text", "text": {"content": " / "}})

        if isinstance(ref, dict):
            text = ref.get("text", "")
            url = ref.get("url", "")
            if url:
                rich_text_parts.append({
                    "type": "text",
                    "text": {"content": text, "link": {"url": url}},
                })
            else:
                rich_text_parts.append({"type": "text", "text": {"content": text}})
        else:
            rich_text_parts.append({"type": "text", "text": {"content": str(ref)}})

    # リッチテキスト全体の合計文字数をチェック
    total_len = sum(len(p["text"]["content"]) for p in rich_text_parts)
    if total_len > NOTION_TEXT_LIMIT:
        # 超える場合は簡素化
        simple_text = "参照: " + ", ".join(
            ref.get("text", str(ref)) if isinstance(ref, dict) else str(ref)
            for ref in refs
        )
        return _paragraphs(simple_text)

    return [_paragraph(rich_text_parts)]
