/**
 * LINE Works Bot → GitHub Actions トリガー用 GAS コード
 *
 * LINE Works Botのコールバック先として設定し、
 * 特定のメッセージを受信したらGitHub Actionsをトリガーする。
 *
 * スクリプトプロパティに以下を設定:
 *   GH_TOKEN : GitHub Personal Access Token
 *   GH_REPO  : リポジトリ (例: ekanbe/overseas-food-trends)
 */

var WELCOME_MSG = [
  "海外フード業界 デイリーレポートへようこそ！",
  "",
  "10以上のSNS・メディアから収集した",
  "海外フードトレンドを毎朝お届けします。",
  "",
  "■ 毎朝8:00に日報を自動配信",
  "■ 毎週日曜20:00に週報を自動配信",
  "■ 「日報」と送ればいつでも最新レポートを取得",
  "■ 「週報」と送ればウィークリーダイジェストを取得",
  "",
  "情報源: YouTube / Reddit / TikTok / Instagram / X",
  "       小红书 / 抖音 / Weibo / Naver / PTT",
  "       + 10以上の食品メディアRSS",
  "分析: Google Gemini AI",
].join("\n");

function doPost(e) {
  var data = JSON.parse(e.postData.contents);

  // LINE Works Bot のコールバック形式
  var content = data.content || {};
  var type = data.type || "";
  var text = (content.text || "").toLowerCase();

  if (type === "message" && content.type === "text") {
    if (text.indexOf("日報") >= 0 || text.indexOf("trend") >= 0 || text.indexOf("daily") >= 0) {
      triggerWorkflow("daily");
      return ContentService.createTextOutput("OK");
    }
    if (text.indexOf("週報") >= 0 || text.indexOf("weekly") >= 0) {
      triggerWorkflow("weekly");
      return ContentService.createTextOutput("OK");
    }
  }

  return ContentService.createTextOutput("OK");
}

function triggerWorkflow(mode) {
  var props = PropertiesService.getScriptProperties();
  var ghToken = props.getProperty("GH_TOKEN");
  var ghRepo = props.getProperty("GH_REPO") || "ekanbe/overseas-food-trends";

  var url = "https://api.github.com/repos/" + ghRepo + "/actions/workflows/daily_trend.yml/dispatches";

  UrlFetchApp.fetch(url, {
    method: "post",
    headers: {
      "Authorization": "Bearer " + ghToken,
      "Accept": "application/vnd.github+json"
    },
    contentType: "application/json",
    payload: JSON.stringify({
      ref: "master",
      inputs: { mode: mode }
    })
  });
}
