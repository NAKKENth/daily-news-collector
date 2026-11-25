# ChatGPT既存4タスクの接続先（運用検証後）

共通: https://github.com/NAKKENth/daily-news-collector/blob/main/data/latest/manifest.json

| 配信 | Markdown索引 | 全候補JSON |
|---|---|---|
| 07:00 | https://github.com/NAKKENth/daily-news-collector/blob/main/data/latest/motorsport.md | https://github.com/NAKKENth/daily-news-collector/blob/main/data/latest/motorsport.json |
| 07:15 | https://github.com/NAKKENth/daily-news-collector/blob/main/data/latest/pc_ai.md | https://github.com/NAKKENth/daily-news-collector/blob/main/data/latest/pc_ai.json |
| 07:30 | https://github.com/NAKKENth/daily-news-collector/blob/main/data/latest/games_handhelds.md | https://github.com/NAKKENth/daily-news-collector/blob/main/data/latest/games_handhelds.json |
| 07:45 | https://github.com/NAKKENth/daily-news-collector/blob/main/data/latest/audio.md | https://github.com/NAKKENth/daily-news-collector/blob/main/data/latest/audio.json |

まずmanifestの対象日・生成日時を確認し、担当JSONまたは分割Markdownを全件走査。priorityは優先調査、reviewは要確認、excludeは通常除外だが監査可能。検索索引時刻や観測時刻を公式発表日にしない。外部収集だけで完結せず、部分失敗や手動ソースを通常検索で補完。個別記事原典を確認してS/A/B判定。接続可否は実測前のため既存タスクは変更しない。

追加共通: https://github.com/NAKKENth/daily-news-collector/blob/main/data/latest/coverage.json

回収候補: `data/latest/<group>_recovery.json`（担当groupは上表と同じ）。日付別候補は `data/archive/YYYY-MM-DD/<group>.json`。これらのURLはv0.3の初回成功後に生成される。回収候補は当日分と分離し、既報の繰り返しを避ける。
