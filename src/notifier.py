"""LINE Works Bot API v2.0 によるレポート配信.

Bot から個人ユーザーへ直接メッセージを送信する。
長文は自動分割して複数メッセージとして配信。

必要な環境変数:
  LINEWORKS_BOT_ID          : Bot ID
  LINEWORKS_CLIENT_ID       : OAuth Client ID
  LINEWORKS_CLIENT_SECRET   : OAuth Client Secret
  LINEWORKS_SERVICE_ACCOUNT : Service Account
  LINEWORKS_PRIVATE_KEY     : RSA Private Key (PEM) or ファイルパス
  LINEWORKS_USER_ID         : 配信先ユーザーID（メールアドレス形式）

フォールバック: LINE Messaging API（既存の個人LINE配信）
"""

import os
import time
import logging
from datetime import datetime, timezone, timedelta

import httpx
import jwt

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))
MAX_MESSAGE_LENGTH = 2000  # LINE Works テキスト上限（余裕を持って設定）

# LINE Works API v2.0 endpoints
AUTH_URL = "https://auth.worksmobile.com/oauth2/v2.0/token"
API_BASE = "https://www.worksapis.com/v1.0"


def send(report_text: str) -> bool:
    """レポートテキストをLINE Worksに配信する.

    LINE Works環境変数が未設定の場合は従来のLINE配信にフォールバック。
    """
    # LINE Works を試行
    if _has_lineworks_config():
        success = _send_lineworks(report_text)
        if success:
            return True
        logger.warning("LINE Works送信失敗。LINE個人配信にフォールバック")

    # フォールバック: 従来のLINE Messaging API
    return _send_line_fallback(report_text)


def _has_lineworks_config() -> bool:
    """LINE Works の設定が揃っているか確認."""
    required = [
        "LINEWORKS_BOT_ID",
        "LINEWORKS_CLIENT_ID",
        "LINEWORKS_CLIENT_SECRET",
        "LINEWORKS_SERVICE_ACCOUNT",
        "LINEWORKS_PRIVATE_KEY",
        "LINEWORKS_USER_ID",
    ]
    return all(os.environ.get(key) for key in required)


def _send_lineworks(text: str) -> bool:
    """LINE Works Bot API v2.0 でメッセージ送信."""
    try:
        access_token = _get_access_token()
    except Exception as e:
        logger.error("LINE Works アクセストークン取得失敗: %s", e)
        return False

    user_id = os.environ["LINEWORKS_USER_ID"]
    bot_id = os.environ["LINEWORKS_BOT_ID"]
    messages = _split_messages(text)

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    url = f"{API_BASE}/bots/{bot_id}/users/{user_id}/messages"

    try:
        with httpx.Client(headers=headers, timeout=30) as client:
            for i, msg in enumerate(messages):
                body = {
                    "content": {
                        "type": "text",
                        "text": msg,
                    }
                }
                resp = client.post(url, json=body)

                if resp.status_code >= 400:
                    logger.error(
                        "LINE Works API エラー [%s]: %s",
                        resp.status_code,
                        resp.text,
                    )
                    resp.raise_for_status()

                # レート制限対策: 複数メッセージ間に短い待機
                if i < len(messages) - 1:
                    time.sleep(0.5)

        logger.info("LINE Works送信成功: %d メッセージ", len(messages))
        return True

    except Exception as e:
        logger.error("LINE Works API送信失敗: %s", e)
        return False


def _get_access_token() -> str:
    """Service Account認証でアクセストークンを取得."""
    client_id = os.environ["LINEWORKS_CLIENT_ID"]
    client_secret = os.environ["LINEWORKS_CLIENT_SECRET"]
    service_account = os.environ["LINEWORKS_SERVICE_ACCOUNT"]
    private_key_input = os.environ["LINEWORKS_PRIVATE_KEY"]

    # PEMキーを読み込み（ファイルパスまたは直接値）
    if private_key_input.startswith("-----"):
        private_key = private_key_input
    else:
        with open(private_key_input, "r") as f:
            private_key = f.read()

    # JWT生成
    now = int(time.time())
    payload = {
        "iss": client_id,
        "sub": service_account,
        "iat": now,
        "exp": now + 3600,
    }
    assertion = jwt.encode(payload, private_key, algorithm="RS256")

    # トークン取得
    data = {
        "assertion": assertion,
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "bot",
    }

    with httpx.Client(timeout=15) as client:
        resp = client.post(AUTH_URL, data=data)
        resp.raise_for_status()

    return resp.json()["access_token"]


def _send_line_fallback(text: str) -> bool:
    """従来のLINE Messaging API によるフォールバック配信."""
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

    messages_text = _split_messages(text)
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
