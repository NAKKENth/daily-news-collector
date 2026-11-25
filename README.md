# 前日ニュース外部収集基盤 v0.1 — 既存4タスクの情報源を再利用

**目的：** ChatGPTの4本の自動タスクが毎回ゼロから検索しなくてもよいよう、指定済みの公開ニュースサイト・公式発表・GitHubの更新候補を定期収集し、**日本時間の前日分**を分野別に整形する。

> **重要：本キットは記事の候補収集エンジンであり、自動で正しい記事を確定する仕組みではありません。** 「記事のRSS公開日時」「Google Newsが配信した日時」「出来事の発生日」は一致しないことがあります。ChatGPT側で原典と日付を検証してから配信します。

## 1. 今ある4タスクとの対応

| 時刻 (JST) | 既存タスク | 収集データ（GitHub公開リポジトリ配置後） |
|---|---|---|
| 07:00 | 前日ニュース｜モータースポーツ | `data/latest/motorsport.md` |
| 07:15 | 前日ニュース｜PC・AI・スマホ | `data/latest/pc_ai.md` |
| 07:30 | 前日ニュース｜ゲーム・ハンドヘルド | `data/latest/games_handhelds.md` |
| 07:45 | 前日ニュース｜オーディオ | `data/latest/audio.md` |

初期設定で**168情報源**（うち**159は機械的な取得を試行**、**9は手動調査の入口として登録**）を用意しています。現在の4タスクに明記されたサイト・メーカー・GitHubを優先して登録しました。収集方法の列は下記の4種類です。全159情報源が確実に毎回取得できるという意味ではありません。

- **`rss`**：公式／メディアのRSSを直接読む。公開されているフィードの更新日時と個別記事URLを保存。
- **`github_releases`, `github_merged_pr`**：GitHub APIのリリース日時／PRマージ日時を取得。PRはマージ済みの変更であり、正式製品リリースとは区別。
- **RSS取得失敗時**：サイト別Google News RSSへフォールバック。`manifest.json`に `fallback` / `fallback_empty` と元RSSの失敗を記録（原典確認を要する）。
- **`news`**：Google News RSSの `site:domain` 検索で候補を発見。これは**元サイトを直接巡回したものではなく、発見用の索引**。リンクや日付をそのまま正式発表の裏付けに使わない。
- **`manual`**：Discord、QQ、Weibo、認証資料の特定検索など。一般公開されたAPIを使用しないため自動取得しない。

`source.json` ではなく **`sources.json`** が実際の構成ファイルです。`configure_sources.py` は初期カタログ生成用です。**日常的な追加・修正は `sources.json` を直接編集**してください。生成スクリプトを再実行すると手動編集が上書きされます。

## 2. 運用方式：GitHub Actions（推奨）

ニュース候補は公開情報のみを保存する設計です。**公開GitHubリポジトリ**で動かすとChatGPTからリンク経由で候補リストを読めます。保存した情報が公開されるため、個人的なメモ・アカウント情報・トークンなどを `sources.json` や `data/` に記載しないでください。

1. GitHubで**空の公開リポジトリ**を作成（例：`daily-news-collector`）。秘密のアカウント情報はコミットしない。
2. このZIPを展開し、`collector.py`、`sources.json`、`.github/workflows/collect.yml` など**中身をルート直下**に配置してコミット・pushする。GitHub Webからアップロードする場合、隠しフォルダ `.github` が保持されているか確認する。Gitコマンド例は下記。
3. GitHubリポジトリ **Actions → News candidate collection → Run workflow → all** を実行。実行ログを確認する。
4. **Settings → Actions → General** でActionsが有効か、`GITHUB_TOKEN`に `contents: write` 権限を許可しているか確認する。組織のポリシーや保護ルールでpushが拒否される場合は個別設定が必要。
5. 最初の実行が成功すると `data/latest/` に4分野のMarkdown/JSON、`manifest.json`、SQLiteの `data/news.sqlite` が生成され、自動コミットされる。**成功判定はジョブが緑色だけではなく `manifest.json` の取得失敗数を確認**。
6. 下の「既存タスクへの追記」にあるテンプレートで、4本のChatGPT自動タスクに公開リポジトリのURLを設定する。**URL未決定の段階で既存タスクを変更しない**。

`git` と GitHub認証が使える場合の例：

```powershell
# 展開した news-intake-kit フォルダで実行（あらかじめGitHubで空リポジトリを作成）
git init
git branch -M main
git add .
git commit -m "Add public news candidate collector"
git remote add origin https://github.com/ユーザー名/daily-news-collector.git
git push -u origin main
```

GitHub Actionsのスケジュール（UTC）：
- `00:17 / 06:17 / 12:17 / 18:17` UTC：中核ソースを中間収集
- **`20:27` UTC = 翌朝 `05:27 JST`：全自動ソースを収集（早めの前日分候補ベースライン）**
- **`21:38` UTC = 翌朝 `06:38 JST`：全自動ソースを再探索して最新状態へ更新**

GitHub Actionsの定期実行は**遅延・スキップがあり得ます**。07:00のタスク開始までに06:38のジョブが終わる保証はありません。05:27の初回収集があればその候補も使えますが、配信では最新の生成時刻を確認してください。ChatGPT配信側で**`manifest.json` の `target_date_jst` と `generated_at_utc` を照合**し、古いときは補助資料として使い、通常検索に切り替えてください。公開リポジトリのscheduled workflowは60日間活動がないと無効化される場合があります。定期的に `Actions` と `manifest` を確認してください。

## 3. 出力の見方

`data/latest/`：

- `manifest.json`：収集日時、対象日、各ソースの `ok` / `empty` / `failed` / `manual` / `skipped`、記事候補数。**検索失敗と真の0件を区別**。
- `motorsport.md` / `pc_ai.md` / `games_handhelds.md` / `audio.md`：ChatGPTが最初に読むべき分野別候補一覧。記事は時間順、分野内の長い一覧は表示上限あり。**候補リストであり事実確認済みのニュース本文ではない**。
- 同名 `.json`：各分野の取得した全候補と日時の根拠（RSS、Google News、GitHub）。
- `news.sqlite`：複数日の候補を一意URLで保存し、再実行時に重複登録しないSQLiteデータベース。
- `README.md`：4分野の候補件数サマリー。

日時欄の信頼度：

| `timestamp_basis` | 意味 | ニュース本採用前の確認 |
|---|---|---|
| `github_release_published` | GitHub公式リリース公開時刻 | リリース内容と影響を確認 |
| `github_pr_merged` | GitHub PRのマージ時刻 | 本番版に含まれたかどうかを区別 |
| `source_feed_published` | 元媒体のRSS記事日時 | **報道内容の出来事がいつ起きたか確認** |
| `google_news_index` | Google News側の配信日時 | **元記事のURLと公開日時を別に確認** |

`news` は**Google Newsに見つからなかった＝元サイトにニュースがなかった**を意味しません。公式SNS・販売店の発売開始・Help Centerのサイレント変更などは現在の取得経路で見逃す可能性があります。

## 4. 既存のChatGPTタスクへの接続

4本のタスクは**現在有効なまま**です。公開先が用意できるまでは変更不要。

次の文章を各タスクの指示書**冒頭**に追加します。`{GROUP}` はそれぞれ `motorsport`、`pc_ai`、`games_handhelds`、`audio` に置き換えます。

```text
【外部ニュース候補索引の優先確認】
配信当日、まず以下の公開GitHubリポジトリに保存された前日ニュース候補を確認する。
https://github.com/ユーザー名/daily-news-collector/blob/main/data/latest/manifest.json
https://github.com/ユーザー名/daily-news-collector/blob/main/data/latest/{GROUP}.md
原則として manifest.json の target_date_jst が前日のJST日付と一致していること、生成時刻が新しいことを確認する。
一致しない、参照不可、失敗ソースが多い場合は当該索引を不完全な補助情報として扱い、従来の公式・専門媒体のWeb検索を継続する。
この索引は発見候補であり、RSS時刻やGoogle Newsの日時だけで出来事の日付を確定してはいけない。
特にGoogle News索引は必ず元記事の個別URL・発表日時・内容を調べ直す。
既存の担当領域、S/A/B/C、JST期間、リーク確度判定、海外正式発表・予約/発売の採用規則を維持する。
今回の候補が多い場合は独立した重要S/Aを優先し、実用的なBも幅広く拾う。
取得失敗をニュース0件と誤認しない。索引に載らない独自取材やSNS一次発表も必要に応じて補う。
```

**GitHubへの公開後に、実際のリポジトリURLを教えてください。** 4本の既存タスクへ、この正しいURLに置換した接続指示を追加できます。URLを決める前に架空URLへ切り替えると、配信品質がさらに悪化します。

## 5. ローカルでの検証と実行

Python 3.12以上を推奨（標準 `zoneinfo` を使用）。

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python collector.py --scope core
python collector.py --scope all
python collector.py --scope all --date 2026-11-24
```

すべてネットワークに出るのは `collector.py` のみ。テストはローカルで完結します。Windowsのタスクスケジューラでも実行できますが、**ChatGPT自動タスクがPC上のファイルを自動的に参照できるわけではありません**。4本へ接続するには公開URLまたは認証済みのファイルコネクタなどの取り込み経路が別途必要です。

## 6. 注意・実装の限界

- RSSやGoogle Newsの検索結果は**記事候補**であり、メーカー発表の網羅性・ニュースの正確さ・重大度を保証しません。
- JavaScript限定のサイト、ログインが必要なSNS、X・QQ・Discord・Weiboの非公開情報、動的な商品ページの更新は現時点では完全自動化していません。
- 公式Help Centerの**サイレントな内容変更**は現時点では検知しません。追加のページ差分監視が必要です。
- 同じ事件を複数媒体が記事化した場合、URL単位の重複は除外しますが、**異なるURLが同じ原典を引用しているかの判定はChatGPT側**で行います。
- 一部の設定ソースURLはドメイン調査が必要です。`manifest.json`で個別サイトの失敗を確認して都度修正します。Google News経由でしか取得しないサイトは、`ok`でも元サイトを直接チェックしたことになりません。
- GitHub Actionsに無料枠・実行時間・レート制限、外部媒体にアクセス制限があります。高負荷時には `--scope core` を使うか監視対象を段階的に調整します。
- 「記事が増えるか」は**導入後に実測で検証**します。最初の数日間は旧方式の配信も残し、外部候補から実際に新規採用できた件数を比較するのがおすすめです。

## 7. 次期改良（現時点では未実装）

1. 公開Webページのサイレント差分監視（OpenAI/Claude/Geminiの利用制限・価格、公式製品ストア）
2. サイト別RSS自動発見＋原典URL解決、英語・日本語・中国語の発表をより広くカバー
3. 毎日の機械的な発見率監査、失敗時の再試行アラート、出典重複候補の半自動グループ化
4. Web検索だけでなく公式API・RSSを優先したデータ品質改善
