"""LINE Messaging API によるレポート配信.

ブロードキャスト → 個別プッシュ の順で送信を試行。
長文は自動分割して複数メッセージとして配信。

必要な環境変数:
  LINE_CHANNEL_ACCESS_TOKEN : チャネルアクセストークン
  LINE_USER_ID              : 配信先ユーザーID（個別プッシュ用）
"""

import os
import logging

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 2000


def send(report_text: str) -> bool:
    """レポートテキストをLINEに配信する."""
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    if not token:
        logger.error("LINE_CHANNEL_ACCESS_TOKEN が未設定")
        return False

    try:
        from linebot.v3.messaging import (
            Configuration,
            ApiClient,
            MessagingApi,
            BroadcastRequest,
            PushMessageRequest,
            TextMessage,
        )
    except ImportError:
        logger.error("line-bot-sdk がインストールされていません")
        return False

    messages_text = _split_messages(report_text)
    configuration = Configuration(access_token=token)

    # ブロードキャスト試行
    try:
        with ApiClient(configuration) as api_client:
            api = MessagingApi(api_client)
            api.broadcast(
                BroadcastRequest(
                    messages=[TextMessage(text=m) for m in messages_text[:5]],
                )
            )
        logger.info("LINEブロードキャスト送信成功: %d メッセージ", len(messages_text))
        return True
    except Exception as e:
        logger.warning("ブロードキャスト失敗: %s — 個別プッシュを試行", e)

    # 個別プッシュ
    user_id = os.environ.get("LINE_USER_ID")
    if not user_id:
        logger.error("LINE_USER_ID も未設定のため送信不可")
        return False
    try:
        with ApiClient(configuration) as api_client:
            api = MessagingApi(api_client)
            api.push_message(
                PushMessageRequest(
                    to=user_id,
                    messages=[TextMessage(text=m) for m in messages_text[:5]],
                )
            )
        logger.info("LINE個別プッシュ送信成功: %d メッセージ", len(messages_text))
        return True
    except Exception as e2:
        logger.error("LINE送信完全失敗: %s", e2)
        return False


def _split_messages(text: str) -> list[str]:
    """文字数制限に合わせてメッセージを分割.

    セクション区切り（━━━ の行）を優先的に分割ポイントにする。
    """
    if len(text) <= MAX_MESSAGE_LENGTH:
        return [text]

    # セクション区切りで分割を試みる
    separator = "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    parts = text.split(separator)

    messages = []
    current = ""

    for part in parts:
        candidate = f"{current}{separator}{part}" if current else part
        if len(candidate) <= MAX_MESSAGE_LENGTH:
            current = candidate
        else:
            if current:
                messages.append(current)
            # 1パートが上限を超える場合は行単位で分割
            if len(part) > MAX_MESSAGE_LENGTH:
                sub_messages = _split_by_lines(part)
                messages.extend(sub_messages)
                current = ""
            else:
                current = part

    if current:
        messages.append(current)

    return messages


def _split_by_lines(text: str) -> list[str]:
    """行単位でメッセージを分割."""
    messages = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > MAX_MESSAGE_LENGTH:
            if current:
                messages.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        messages.append(current)
    return messages
