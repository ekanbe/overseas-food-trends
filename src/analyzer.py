"""Gemini 2.5 Flash による食品トレンド構造化分析.

日報モード: 全セクション（トレンドTOP3、アジア市場、業界ニュース等）を生成
週報モード: 1週間分のデータを集約してウィークリーダイジェストを生成
"""

import json
import os
import logging

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────
# 共通のシステムインストラクション
# ──────────────────────────────────────────
SYSTEM_INSTRUCTION = """\
あなたはマルイ物産（外食チェーン向け業務用食品卸）専属の海外フード業界アナリストです。
10以上のSNS・メディアソースから収集したデータを分析し、構造化されたレポートを生成してください。

## マルイ物産について
- 外食チェーン向け業務用食品卸
- デザート・ドリンク原料が主力商品
- 台湾・東南アジアに調達ネットワークあり
- 顧客は日本の外食チェーン（カフェ、ファストフード、居酒屋等）

## 分析の視点
1. マルイ物産が「調達・供給」できる商材に直結するトレンドを優先
2. 日本の外食チェーンに提案可能な具体的商品・素材を常に意識
3. ライフサイクル分析（発生→成長→ピーク→日本波及）を正確に
4. 規制・政策変更がサプライチェーンに与える影響を具体的に

## 重要ルール
- 出力は必ず完全なJSONで返すこと
- 各フィールドは指定通りに必ず含めること
- 日本に既に定着している食品（タピオカ、バスクチーズケーキ等の原型）は除外
- 数値・指標は可能な限り具体的に（「急増」ではなく「前週比180%増」等）
- 参照元は必ず具体的なプラットフォーム名・メディア名を記載
"""

# ──────────────────────────────────────────
# 日報用プロンプト
# ──────────────────────────────────────────
DAILY_PROMPT = """\
以下は海外のSNS（YouTube, Reddit, TikTok, Instagram, X, 小红书, 抖音, 微博, Naver, PTT）
および食品メディアRSSから収集した食品関連データです。
日報レポート用に分析し、以下のJSON形式で出力してください。

## 過去に配信済み（選ばないこと）
{past_trends}

## 収集データ
{data}

## 出力JSON形式（厳守）

{{
  "executive_summary": "今日の最重要ポイントを5-6行で。マルイ物産への影響を必ず含める。",

  "top_trends": [
    {{
      "rank": 1,
      "name_en": "英語名",
      "name_ja": "日本語名（カタカナ）",
      "origin": "発祥国・都市",
      "detected_on": ["小红书", "抖音", "Weibo"],
      "metrics": "小红书12万投稿/週, 抖音8.3億再生",
      "lifecycle_stage": "成長期",
      "lifecycle_bar": "■■■□□",
      "japan_landing_estimate": "約4-6ヶ月後（2026年夏）",
      "why_trending": "流行理由を2-3文で",
      "japan_market_fit": "日本市場との親和性を2文で",
      "procurement_note": "マルイ物産の調達可能性を2文で",
      "references": ["小红书 #冰花奶茶 トレンドページ", "抖音 話題動画（再生数上位）"]
    }}
  ],

  "asia_trends": {{
    "china": [
      {{
        "headline": "見出し",
        "detail": "3-4行の詳細説明",
        "implication": "マルイ物産への示唆",
        "references": ["小红书 #轻食", "36Kr 消費トレンド"]
      }}
    ],
    "korea": [
      {{
        "headline": "見出し",
        "detail": "3-4行の詳細説明",
        "implication": "マルイ物産への示唆",
        "references": ["Naver Blog 약과", "r/KoreanFood"]
      }}
    ],
    "taiwan": [
      {{
        "headline": "見出し",
        "detail": "3-4行の詳細説明",
        "implication": "マルイ物産への示唆",
        "references": ["Instagram #果醬飲", "PTT美食板"]
      }}
    ],
    "southeast_asia": [
      {{
        "headline": "見出し",
        "detail": "3-4行の詳細説明",
        "implication": "マルイ物産への示唆",
        "references": ["Instagram #bangkokcoffee", "Food Navigator Asia"]
      }}
    ]
  }},

  "industry_news": {{
    "western": [
      {{
        "headline": "見出し",
        "detail": "2-3行の詳細",
        "implication": "マルイ物産への示唆",
        "references": ["Restaurant Business Online"]
      }}
    ],
    "asian": [
      {{
        "headline": "見出し",
        "detail": "2-3行の詳細",
        "implication": "マルイ物産への示唆",
        "references": ["KoreaBizWire"]
      }}
    ]
  }},

  "foodtech": [
    {{
      "headline": "見出し",
      "detail": "2-3行の詳細",
      "impact": "外食産業への影響",
      "references": ["The Spoon"]
    }}
  ],

  "regulation": {{
    "risks": [
      {{
        "headline": "見出し",
        "detail": "2-3行の詳細",
        "impact": "影響",
        "references": ["Food Navigator"]
      }}
    ],
    "opportunities": [
      {{
        "headline": "見出し",
        "detail": "2-3行の詳細",
        "opportunity": "チャンスの説明",
        "references": ["Food Navigator Asia"]
      }}
    ]
  }},

  "action_items": [
    {{
      "priority": "高",
      "action": "具体的なアクション",
      "reason": "理由を2文で"
    }}
  ]
}}

## 件数の目安
- top_trends: 3件（厳選）
- asia_trends: 中国2件, 韓国2件, 台湾2件, 東南アジア1件
- industry_news: 欧米3件, アジア3件
- foodtech: 3件
- regulation: リスク2件, チャンス2件
- action_items: 5件（高2, 中2, 低1）

## 重要: 各フィールドの文字数を抑えること
- 各テキストフィールドは100文字以内を目安に簡潔に
- why_trending, japan_market_fit, procurement_note は各2文以内
- detail は3文以内
- 完全なJSONを返すことを最優先し、冗長な説明は避ける
"""

# ──────────────────────────────────────────
# 週報用プロンプト
# ──────────────────────────────────────────
WEEKLY_PROMPT = """\
以下は今週1週間分の日報データ（各日の分析結果）です。
これを集約してウィークリーダイジェストを生成してください。

## 今週の日報データ
{weekly_data}

## 出力JSON形式（厳守）

{{
  "highlight": "今週最も注目すべきポイントを4-5行で深掘り",

  "trend_summary": {{
    "accelerating": [
      {{
        "name": "トレンド名",
        "last_week": "先週の指標",
        "this_week": "今週の指標",
        "stage_change": "成長初期 → 成長期に移行",
        "references": ["参照元"]
      }}
    ],
    "new_detected": [
      {{
        "name": "トレンド名",
        "description": "今週初検出。概要",
        "stage": "発生期",
        "references": ["参照元"]
      }}
    ],
    "decelerating": [
      {{
        "name": "トレンド名",
        "change": "先週比-15%。ピーク通過の兆候",
        "references": ["参照元"]
      }}
    ]
  }},

  "asia_weekly": {{
    "china": {{
      "rating": 5,
      "summary": "3-4行のサマリー",
      "references": ["参照元"]
    }},
    "taiwan": {{
      "rating": 4,
      "summary": "3-4行のサマリー",
      "references": ["参照元"]
    }},
    "korea": {{
      "rating": 4,
      "summary": "3-4行のサマリー",
      "references": ["参照元"]
    }},
    "southeast_asia": {{
      "rating": 3,
      "summary": "3-4行のサマリー",
      "references": ["参照元"]
    }}
  }},

  "industry_weekly": {{
    "important": [
      {{
        "headline": "見出し",
        "references": ["参照元"]
      }}
    ],
    "technology": [
      {{
        "headline": "見出し",
        "references": ["参照元"]
      }}
    ],
    "regulation": [
      {{
        "headline": "見出し",
        "emoji": "⚠ or 🔓",
        "references": ["参照元"]
      }}
    ]
  }},

  "next_week_outlook": [
    {{
      "point": "注目ポイント",
      "detail": "1-2行の補足"
    }}
  ]
}}
"""


def analyze_daily(collected_data: dict, past_trend_names: list[str] | None = None) -> dict | None:
    """収集データをGeminiで分析し、日報用の構造化データを返す."""
    data_str = _prepare_data(collected_data)
    past_str = "、".join(past_trend_names) if past_trend_names else "（なし）"
    prompt = DAILY_PROMPT.format(data=data_str, past_trends=past_str)
    return _call_gemini(prompt, "日報")


def analyze_weekly(weekly_data: list[dict]) -> dict | None:
    """週間データを集約してGeminiで週報を生成."""
    data_str = json.dumps(weekly_data, ensure_ascii=False, separators=(",", ":"))
    if len(data_str) > 50000:
        data_str = data_str[:50000] + "..."
    prompt = WEEKLY_PROMPT.format(weekly_data=data_str)
    return _call_gemini(prompt, "週報")


# 後方互換のためのエイリアス
def analyze(collected_data: dict, past_trend_names: list[str] | None = None) -> dict | None:
    """後方互換: analyze_daily へ委譲."""
    return analyze_daily(collected_data, past_trend_names)


def _prepare_data(collected_data: dict) -> str:
    """収集データをJSON文字列化."""
    data_str = json.dumps(collected_data, ensure_ascii=False, separators=(",", ":"))
    if len(data_str) > 60000:
        data_str = data_str[:60000] + "..."
    return data_str


def _call_gemini(prompt: str, mode_label: str) -> dict | None:
    """Gemini APIを呼び出して分析結果を返す."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY が未設定")
        return None

    client = genai.Client(api_key=api_key)

    for model_name in ["gemini-2.5-flash", "gemini-2.5-flash-lite"]:
        try:
            logger.info("Gemini %s分析開始: %s", mode_label, model_name)
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    temperature=0.5,
                    max_output_tokens=16384,
                ),
            )

            result = _parse_response(response.text)
            if result:
                logger.info("Gemini %s分析完了 (%s)", mode_label, model_name)
                return result

        except Exception as e:
            logger.warning("Gemini API失敗 (%s): %s", model_name, e)

    logger.error("全Geminiモデルで%s分析失敗", mode_label)
    return None


def _parse_response(text: str) -> dict | None:
    """Geminiの応答をパース。不完全なJSONも修復を試みる."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    try:
        fixed = text.rstrip()
        open_braces = fixed.count("{") - fixed.count("}")
        open_brackets = fixed.count("[") - fixed.count("]")

        last_complete = fixed.rfind("},")
        if last_complete > 0 and (open_braces > 0 or open_brackets > 0):
            fixed = fixed[: last_complete + 1]
            fixed += "]" * max(0, fixed.count("[") - fixed.count("]"))
            fixed += "}" * max(0, fixed.count("{") - fixed.count("}"))

        result = json.loads(fixed)
        logger.info("JSON修復成功")
        return result
    except (json.JSONDecodeError, ValueError):
        pass

    logger.error("JSON修復失敗。応答末尾: %s", text[-200:])
    return None
