"""LINE Messaging API によるトレンド配信."""

import os
import logging
from datetime import datetime, timezone, timedelta

from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    PushMessageRequest,
    TextMessage,
)

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))
MAX_MESSAGE_LENGTH = 4500  # 余裕を持って4500文字（LINE上限は5000）


def send(analysis_result: dict) -> bool:
    """分析結果をLINEで送信する. 成功時True."""
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = os.environ.get("LINE_USER_ID")

    if not token or not user_id:
        logger.error("LINE認証情報が未設定")
        return False

    message_text = _format_message(analysis_result)
    messages = _split_messages(message_text)

    configuration = Configuration(access_token=token)

    try:
        with ApiClient(configuration) as api_client:
            api = MessagingApi(api_client)
            api.push_message(
                PushMessageRequest(
                    to=user_id,
                    messages=[TextMessage(text=m) for m in messages],
                )
            )
        logger.info("LINE送信成功: %d メッセージ", len(messages))
        return True
    except Exception as e:
        logger.error("LINE送信失敗: %s", e)
        return False


def _format_message(result: dict) -> str:
    """Gemini分析結果をLINEメッセージに整形."""
    today = datetime.now(JST).strftime("%Y/%m/%d")
    trends = result.get("trends", [])
    summary = result.get("summary", "")

    lines = [
        f"🌏 海外フードトレンド速報",
        f"📅 {today}",
        "",
        f"📊 {summary}",
        "",
        "=" * 25,
    ]

    for t in trends:
        rank = t.get("rank", "?")
        name_en = t.get("product_name_en", "Unknown")
        name_ja = t.get("product_name_ja", "不明")
        country = t.get("origin_country", "不明")
        platforms = ", ".join(t.get("platforms", []))
        metrics = t.get("metrics", "N/A")
        target = t.get("target_audience", "不明")
        why = t.get("why_trending", "")
        forecast = t.get("japan_forecast", "")
        urls = t.get("reference_urls", [])

        lines.extend(
            [
                "",
                f"【{rank}位】{name_en}",
                f"　　（{name_ja}）",
                f"🌍 発祥: {country}",
                f"📱 検出: {platforms}",
                f"📈 数値: {metrics}",
                f"🎯 ターゲット: {target}",
                f"💡 流行理由: {why}",
                f"🇯🇵 日本予測: {forecast}",
            ]
        )
        if urls:
            lines.append(f"🔗 参照: {urls[0]}")
        lines.append("-" * 25)

    lines.extend(
        [
            "",
            "━━━━━━━━━━━━━",
            "🤖 マルイ物産 AI トレンド分析",
            "　 powered by Gemini + YouTube + Reddit",
        ]
    )

    return "\n".join(lines)


def _split_messages(text: str) -> list[str]:
    """LINE文字数制限に合わせてメッセージを分割."""
    if len(text) <= MAX_MESSAGE_LENGTH:
        return [text]

    messages = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > MAX_MESSAGE_LENGTH:
            messages.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line

    if current:
        messages.append(current)

    return messages
