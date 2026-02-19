# 海外フードトレンド自動検出 & LINE配信システム

海外SNS（YouTube, Reddit, TikTok）でバズっている食品・ドリンク・スイーツを毎朝自動検出し、LINEに配信するシステム。

タピオカ、マリトッツォ、ドバイチョコのような「海外→日本」のトレンドを先取りすることが目的。

## アーキテクチャ

```
GitHub Actions (cron: 毎日 7:00 JST)
    │
    ├── 1. データ収集（並列実行）
    │   ├── YouTube    → 6カ国の食品トレンド動画
    │   ├── Reddit     → 食品系サブレディットの急上昇投稿
    │   └── TikTok     → 食品ハッシュタグのトレンド（失敗時スキップ）
    │
    ├── 2. AI分析（Gemini 2.5 Flash）
    │   └── 選別・スコアリング・3〜5件に厳選
    │
    └── 3. LINE配信
        └── 整形メッセージをプッシュ送信
```

## セットアップ

### 1. APIキーの取得

| サービス | 取得先 | 必要なもの |
|---|---|---|
| YouTube Data API v3 | [Google Cloud Console](https://console.cloud.google.com/) | APIキー |
| Reddit API | [Reddit Apps](https://www.reddit.com/prefs/apps) | Client ID, Secret |
| Gemini API | [Google AI Studio](https://aistudio.google.com/) | APIキー |
| LINE Messaging API | [LINE Developers](https://developers.line.biz/) | Channel Access Token, User ID |

### 2. YouTube API キー取得手順

1. [Google Cloud Console](https://console.cloud.google.com/) にアクセス
2. プロジェクトを作成（または既存のものを選択）
3. 「APIとサービス」→「ライブラリ」→「YouTube Data API v3」を有効化
4. 「認証情報」→「認証情報を作成」→「APIキー」
5. 作成されたAPIキーをコピー

### 3. Reddit アプリ登録手順

1. [Reddit Apps](https://www.reddit.com/prefs/apps) にアクセス
2. 「create another app...」をクリック
3. 名前: `FoodTrendBot`、タイプ: `script`、redirect uri: `http://localhost`
4. 作成後、表示される Client ID と Secret をコピー

### 4. Gemini API キー取得手順

1. [Google AI Studio](https://aistudio.google.com/) にアクセス
2. 「Get API key」→「Create API key」
3. 作成されたAPIキーをコピー

### 5. LINE公式アカウント作成手順

1. [LINE Official Account Manager](https://manager.line.biz/) でアカウント作成
2. [LINE Developers Console](https://developers.line.biz/) でプロバイダー作成
3. Messaging APIチャネルを作成
4. 「Messaging API設定」→「チャネルアクセストークン」を発行
5. 自分のUser IDは「チャネル基本設定」→「あなたのユーザーID」で確認

### 6. GitHub リポジトリへのデプロイ

```bash
# リポジトリ作成・初期化
git init
git add .
git commit -m "Initial commit"
gh repo create overseas-food-trends --public --source=. --push
```

### 7. GitHub Secrets の設定

リポジトリの Settings → Secrets and variables → Actions で以下を登録:

| Secret名 | 値 |
|---|---|
| `YOUTUBE_API_KEY` | YouTube APIキー |
| `REDDIT_CLIENT_ID` | Reddit Client ID |
| `REDDIT_CLIENT_SECRET` | Reddit Client Secret |
| `REDDIT_USER_AGENT` | `FoodTrendBot/1.0` |
| `GEMINI_API_KEY` | Gemini APIキー |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINEチャネルアクセストークン |
| `LINE_USER_ID` | LINE User ID |

## ローカルテスト

```bash
# 依存インストール
pip install -r requirements.txt

# .envファイル作成
cp .env.example .env
# .env にAPIキーを入力

# 実行
python src/main.py
```

## 手動トリガー

GitHub Actions の「Actions」タブ → 「Daily Food Trend Detection」 → 「Run workflow」で手動実行可能。

## コスト

全て無料枠内で運用:
- YouTube Data API: 10,000ユニット/日（使用: 約600）
- Reddit API: 60リクエスト/分
- Gemini 2.5 Flash: 250リクエスト/日
- LINE Messaging API: 200通/月
- GitHub Actions: 無料（public repo）

**月額: 0円**
