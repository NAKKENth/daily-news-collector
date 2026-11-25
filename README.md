# 前日ニュース外部収集基盤 v0.2.1

既存の4本のChatGPTニュースタスク用の公開情報収集・候補整理プログラムです。**ニュースの確定・重要度判定は行いません。** v0.1/v0.2で生成した `data/news.sqlite` と `data/latest/` は削除せず、次回実行で引き継ぎます。SQLiteに補助テーブルを追加する方式です。

## v0.2.1への更新（既存GitHubリポジトリ）

1. `Actions` に実行中のジョブがない状態で、リポジトリの現行状態を保持してください（GitHubのコミット履歴に旧版は残ります）。
2. ZIPを展開し、`news-intake-kit` の**中身**を既存リポジトリに上書きしてください。`data/` は削除・置換しないでください。GitHubのWebアップロードでファイルを選択するとフォルダ構造が失われる場合があります。`.github/workflows/collect.yml`、`tests/test_collector.py`、`tests/test_v02.py`、`tests/test_v021.py` は各フォルダで個別に更新・追加してください。詳細は `UPDATE_v0.2.1.txt` を参照。
3. `Actions → News candidate collection → Run workflow → all` で手動実行。テストが失敗すれば収集前に停止します。
4. `data/latest/manifest.json` と `README.md`、4分野のJSONを確認してください。緑のチェックは全ソース成功を意味しません。`partial` は取得不足・部分失敗が残る状態です。
5. 初回実行では一覧監視やページ変更監視の基準を保存します。既存ページを新製品として掲載しません。2回目以降に観測した変化を「日時不明・要確認」の候補にします。

### Gitでの更新（Gitを導入済みの場合）

既存リポジトリを `git clone` したフォルダへ、ZIPの中身（`.github` と `tests` を含む）をコピーして上書きします。`git status` と `git diff` を確認してから `git add`、`git commit`、`git push`。**新しいリポジトリの作成・強制push・既存dataの削除は不要。**

## スケジュール（JST）

- 03:17、09:17、15:17、21:17：core（中核ソース＋前回失敗・部分失敗・延期ソース）
- 05:27：all（全159自動取得対象）
- 06:18：core＋前回失敗・部分失敗・延期ソースの再取得（以前の06:38を前倒し）
- 手動 `retry`：前回失敗・部分失敗・延期ソースを再取得。失敗なしなら追加取得なし。

ジョブの上限は35分です。GitHub Actionsの開始遅延・通信制限で7時に間に合う保証はありません。朝の全収集完了が遅れた場合は、ChatGPT側で生成日時・対象日を確認し、通常検索を補完に使います。

## v0.2.1で変わった点（v0.2からの変更を含む）

- 取得経路強化：FiiO・DUNU・Shanling・EarFun・MusicTeckの公開ニュース/製品一覧、Apple/Samsung等のRSS候補を追加。実ランナーでの成功は未確認。製品一覧はページ単位で基準を保存し直すため、更新直後は新製品扱いしません。Gemini利用上限とChatGPT料金の監視セレクタを改訂し、指定語を含む本文だけを監視します。
- `manifest.json` の `collector_version`、`search_attempted`、`search_deferred`、`pending_search_total`、`google_retry_after_utc`、`enrichment_errors` により延期・詳細取得失敗を確認できます。成功と延期を混同しないでください。

- 168登録・159自動・9手動という既存カタログを維持。TechPowerUp、Motorsport.com EN/JP、AKIBA PC Hotline、VideoCardzの5設定を明示RSSへ切り替え。追加のサイトには候補RSS・HTMLのalternate宣言探索を設定。候補RSSは実行時に成功するか確認します。
- 先に全対象の直接取得、その後4分野交互にGoogle Newsを検索。開始分野を実行ごとに回し、各分野内は延期/未取得・最終試行が古いものを優先。検索は1回48情報源まで、要求間隔は2秒以上。429はその時点で検索を中止し、Retry-After（最低30分）と未取得をSQLiteに保存。次の定期実行以降に再試行し、制限を回避しません。延期はdeferredと表示し、取得成功には数えません。
- RSSの旧25件上限を廃止（解析安全上限500件）。GitHubは100件/ページ・最大3ページ。古い対象期間外の行を取得後に除外します。配信元自体のフィード件数上限・APIのページ上限は残ります。`hit_cap` は上限到達の可能性を示す指標で、実際の全記事取得を保証しません。
- Google Newsは発見経路です。収集済みRSSの正規化タイトル完全一致＋発行元または登録ドメイン一致で元記事を探します。隣接日も照合し、検索索引日時の誤りを修正します。記事メタデータの `datePublished` を取得できればJST日付を更新します。Googleの中間ページから解決できないリンクは未解決のままです（非公開API・強制解除は使いません）。不透明なGoogle Newsリンクへの追加アクセスは停止し、直接URLの候補を1回最大80件（中間収集40）、1ホスト最大6件選んで詳細取得します。未解決候補は保存し、編集時に原典検索が必要です。全候補の元記事確認は保証しません。
- AIの公式ヘルプ、リリースノート、プラン・制限ページの変更ハッシュを保存。新旧の内容差分を自動確定する機能ではありません。ページの変更が観測されれば追加確認対象にします。
- 海外オーディオ・携帯機の公式/販売店設定に一覧ページの新リンク監視を追加。初回は基準保存。既存商品の再インデックスを新着発売とみなしません。動的サイト、一覧のDOM変更、価格や在庫のみの変化は検出できない場合があります。
- 記事単位の暫定再分類。明らかな対象外、通常セール、一覧ページなどを候補から隔離し、判定困難な記事は review として残します。正規表現による暫定処理のため誤判定は残り、`triage_audit.json` で見直し可能。
- 分野横断の同一URL統合。出典情報を保持し、同一正規化見出しを `possible_event_id` で関連候補化します。異なる見出しの同一事件を自動統合する機能はまだ限定的です。同一取材と独立取材の区別はChatGPT側で実施します。
- 全候補のJSONと50件単位のMarkdown分割ファイルを出力。小カテゴリーの表示件数で候補を削りません。`data/latest/<分野>.md` は索引です。
- Actionsのcheckout v5、setup-python v6（Node.js 24世代）に更新。実行前にユニットテスト。

## 出力と読み方

| ファイル | 内容 |
|---|---|
| `data/latest/manifest.json` | 対象JST日、生成UTC時刻、ソース別取得状態、部分失敗、詳細取得件数、分類件数、ページ監視結果 |
| `data/latest/README.md` | 分野別の日付付き候補件数（確定記事数ではない） |
| `data/latest/{motorsport,pc_ai,games_handhelds,audio}.json` | 暫定選別後の全候補と日時不明候補 |
| `data/latest/{group}.md` | 分野別の分割索引 |
| `data/latest/{group}_{topic}_{n}.md` | 50件ごとの全候補リンク（優先・保留を区別） |
| `data/latest/triage_audit.json` | 除外候補と除外理由 |
| `data/news.sqlite` | 過去候補、観測、実行記録。旧DBを継続利用 |

`priority` / `review` / `exclude` は収集時の仮選別であり、S/A/B/Cではありません。`date_jst` はタイムスタンプのJST日付で、記事に記載された出来事の発生日を保証しません。`google_news_index`、`source_feed_updated`、`listing_seen`、`page_change_observed` は正式な公開日時ではありません。`article_published` / `source_feed_published` / `github_release_published` / `github_pr_merged` も実際の出来事と同じか編集時に確認してください。

## ローカル実行

Python 3.11以降を推奨。`python -m pip install -r requirements.txt`、`python -m unittest discover -s tests -v`、`python collector.py --scope all`。手動再試行は `python collector.py --scope retry`。既存のBATも利用可能。`--date YYYY-MM-DD` は対象日の表示切替であり、過去日をさかのぼって全ソースを取得する機能ではありません。`--enrich-limit 0` で記事メタデータ取得を省略できます。

## 接続前の検証

まず all 実行後のmanifestと4分野のJSONを確認。さらに次回実行で一覧・ページ監視が動作するか確認。公開URLのChatGPTからの読取も試してください。**既存4本の自動タスクは外部基盤の品質と参照可能性が確認できるまで変更しません。** 詳細は `AUTOMATION_LINKS.md`。

## 制限・公開範囲

実サイト取得はGitHub Actionsでの運用検証が必要です。RSS候補URL、HTMLセレクタ、SNS・認証DB等は変化やアクセス制限があります。個々のURLの事前ライブ試験はしていません。全文記事・秘密鍵・個人情報を公開リポジトリに保存しないこと。公開取得可能な短い概要・URL・時刻・指紋を保存します。第三者サイトの規約・著作権・アクセス制限を尊重し、制限を回避しません。公開リポジトリのSQLiteは長期運用に伴って増えるため、容量と履歴を定期確認してください。

`sources.json` が運用設定です。`configure_sources.py` は初期カタログ再生成用で、実行すると独自変更が上書きされます。`catalog_upgrade.py` はv0.2用、`catalog_v021.py` はv0.2.1用の既存IDを保つ設定更新用。通常運用ではどちらも実行不要です。
