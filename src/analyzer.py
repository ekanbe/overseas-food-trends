"""Gemini 2.5 Flash による食品トレンド分析・選別・スコアリング."""

import json
import os
import re
import logging

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = """\
あなたは食品業界の海外トレンド分析の専門家です。
日本の食品卸会社の営業担当者に向けて、海外でバズっている食品・ドリンク・スイーツの中から
「次に日本で流行しそうなもの」を厳選して報告してください。

過去に海外から日本に上陸して大ヒットした例:
- タピオカミルクティー（台湾→日本）
- マリトッツォ（イタリア→日本）
- ドバイチョコ（UAE→日本）
- 台湾カステラ（台湾→日本）
- チーズタッカルビ（韓国→日本）

重要: 出力は必ず完全なJSONで返すこと。途中で切れないように、3件に厳選して簡潔に記述すること。
各フィールドの値は短く簡潔に（各50文字以内）。reference_urlsは1件のみ。
"""

ANALYSIS_PROMPT = """\
以下は海外のYouTube、Google Trends、海外フードメディア(RSS)等から収集した食品関連データです。
このデータを分析し、日本の食品卸会社が注目すべきトレンドを3件に厳選してください。

## 選別基準
1. 食品・ドリンク・スイーツに直接関連するもののみ
2. 直近1週間で急激に注目度が上がっているもの
3. まだ日本で広く知られていないもの
4. 日本の飲食店で再現可能なもの

## 収集データ
{data}

## 出力形式（厳守）
必ず3件。各値は短く簡潔に。

{{
  "trends": [
    {{
      "rank": 1,
      "product_name_en": "English name",
      "product_name_ja": "日本語名",
      "origin_country": "発祥国",
      "platforms": ["YouTube"],
      "metrics": "再生数100万等",
      "target_audience": "20-30代女性等",
      "why_trending": "理由を1文で",
      "japan_forecast": "予測を1文で",
      "reference_urls": ["https://example.com"]
    }}
  ],
  "summary": "総括を1文で"
}}
"""


def analyze(collected_data: dict) -> dict | None:
    """収集データをGeminiで分析し、厳選されたトレンドを返す."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY が未設定")
        return None

    client = genai.Client(api_key=api_key)

    # 収集データをJSON文字列化（コンパクトに）
    data_str = json.dumps(collected_data, ensure_ascii=False, separators=(",", ":"))

    # データが大きすぎる場合は切り詰め
    if len(data_str) > 25000:
        data_str = data_str[:25000] + "..."

    prompt = ANALYSIS_PROMPT.format(data=data_str)

    for model_name in ["gemini-2.5-flash", "gemini-2.5-flash-lite"]:
        try:
            logger.info("Gemini分析開始: %s", model_name)
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    temperature=0.5,
                    max_output_tokens=4096,
                ),
            )

            result = _parse_response(response.text)
            if result:
                logger.info(
                    "Gemini分析完了(%s): %d 件のトレンドを検出",
                    model_name,
                    len(result.get("trends", [])),
                )
                return result

        except Exception as e:
            logger.warning("Gemini API失敗 (%s): %s", model_name, e)

    logger.error("全Geminiモデルで分析失敗")
    return None


def _parse_response(text: str) -> dict | None:
    """Geminiの応答をパース。不完全なJSONも修復を試みる."""
    # まず普通にパース
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 不完全なJSONを修復: 閉じカッコを補完
    try:
        fixed = text.rstrip()
        # 開き括弧と閉じ括弧の数を数えて補完
        open_braces = fixed.count("{") - fixed.count("}")
        open_brackets = fixed.count("[") - fixed.count("]")

        # 末尾の不完全なオブジェクトを削除
        # 最後の完全なオブジェクトの後で切る
        last_complete = fixed.rfind("},")
        if last_complete > 0 and (open_braces > 0 or open_brackets > 0):
            fixed = fixed[: last_complete + 1]
            # 閉じカッコを補完
            fixed += "]" * max(0, fixed.count("[") - fixed.count("]"))
            fixed += "}" * max(0, fixed.count("{") - fixed.count("}"))

        result = json.loads(fixed)
        logger.info("JSON修復成功")
        return result
    except (json.JSONDecodeError, ValueError):
        pass

    logger.error("JSON修復失敗。応答末尾: %s", text[-200:])
    return None
