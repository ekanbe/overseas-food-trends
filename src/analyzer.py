"""Gemini 2.5 Flash による食品トレンド分析・選別・スコアリング."""

import json
import os
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
"""

ANALYSIS_PROMPT = """\
以下は海外のYouTube、Reddit、TikTokから収集した食品関連データです。
このデータを分析し、日本の食品卸会社が注目すべきトレンドを3〜5件に厳選してください。

## 選別基準
1. **食品フィルタ**: 食品・ドリンク・スイーツに直接関連するもののみ
2. **急上昇判定**: 直近1週間で急激に注目度が上がっているもの
3. **日本未上陸判定**: まだ日本で広く知られていないもの（既に日本で流行済みのものは除外）
4. **再現可能性**: 日本の飲食店・食品メーカーで再現可能なもの
5. **ビジネスポテンシャル**: 食品卸会社として商機があるもの

## 収集データ
{data}

## 出力形式
以下のJSON形式で出力してください。必ず3〜5件に厳選すること。

{{
  "trends": [
    {{
      "rank": 1,
      "product_name_en": "English name",
      "product_name_ja": "日本語名（推定）",
      "origin_country": "発祥国",
      "platforms": ["検出されたプラットフォーム"],
      "metrics": "具体的な数値（再生数、スコア等）",
      "target_audience": "想定ターゲット層",
      "why_trending": "流行している理由（1-2文）",
      "japan_forecast": "日本上陸予測（時期・可能性・展開方法）",
      "reference_urls": ["参照URL"]
    }}
  ],
  "summary": "今週のトレンド総括（2-3文）"
}}
"""


def analyze(collected_data: dict) -> dict | None:
    """収集データをGeminiで分析し、厳選されたトレンドを返す."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY が未設定")
        return None

    client = genai.Client(api_key=api_key)

    # 収集データをJSON文字列化
    data_str = json.dumps(collected_data, ensure_ascii=False, indent=2)

    # データが大きすぎる場合は切り詰め（Geminiの入力制限対応）
    if len(data_str) > 30000:
        data_str = data_str[:30000] + "\n... (データが大きいため以降省略)"

    prompt = ANALYSIS_PROMPT.format(data=data_str)

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                temperature=0.7,
                max_output_tokens=8192,
            ),
        )

        result = json.loads(response.text)
        logger.info(
            "Gemini分析完了: %d 件のトレンドを検出", len(result.get("trends", []))
        )
        return result

    except json.JSONDecodeError as e:
        logger.error("Gemini応答のJSON解析失敗: %s", e)
        logger.info("Gemini raw response (last 300 chars): %s", response.text[-300:])
        return None
    except Exception as e:
        logger.error("Gemini API呼び出し失敗: %s", e)

        # フォールバック: gemini-2.5-flash-lite
        try:
            logger.info("フォールバック: gemini-2.5-flash-lite を試行")
            response = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    temperature=0.7,
                    max_output_tokens=4096,
                ),
            )
            result = json.loads(response.text)
            logger.info(
                "Gemini(lite)分析完了: %d 件のトレンドを検出",
                len(result.get("trends", [])),
            )
            return result
        except Exception as e2:
            logger.error("Gemini(lite)もAPI失敗: %s", e2)
            return None
