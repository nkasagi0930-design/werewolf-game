# 競馬アプリ用データの回収手順（PC用）

スマホから作業したデータを、一時的に `werewolf-game` リポジトリの
`claude/kind-maxwell-hyg5wf` ブランチの `jra_agents/` フォルダに置いています。
PCが使えるようになったら、下のどちらかの方法で競馬アプリのフォルダに取り込んでください。

## 方法A: Claude Code に頼む（いちばん簡単）

競馬アプリのフォルダで Claude Code を起動して、次の文をそのまま貼り付けてください。

```
GitHub の nkasagi0930-design/werewolf-game リポジトリの
claude/kind-maxwell-hyg5wf ブランチにある jra_agents フォルダを、
このプロジェクトに取り込んでください。
手順は git fetch https://github.com/nkasagi0930-design/werewolf-game.git claude/kind-maxwell-hyg5wf
のあと git checkout FETCH_HEAD -- jra_agents です。
取り込んだら、置き場所をこのプロジェクトの構成に合わせて整理し、
jra_agents/RECOVERY.md は削除してからコミットしてください。
そのあと jra_agents/HANDOVER.md を読んで、内容を要約してください。
```

## 方法B: 自分でコマンドを打つ

競馬アプリのフォルダでターミナルを開き、次を順番に実行します（Mac / Windows 共通）。

```
git fetch https://github.com/nkasagi0930-design/werewolf-game.git claude/kind-maxwell-hyg5wf
git checkout FETCH_HEAD -- jra_agents
git add jra_agents
git commit -m "Add JRA jockey agent data"
```

`jra_agents/` フォルダが競馬アプリの中にできれば完了です。

## 入っているもの

| ファイル | 中身 |
|---|---|
| `HANDOVER.md` | 「人」に注目したモデル改善の方針メモ（PCのClaude Codeに読ませる） |
| `README.md` | エージェント別の担当騎手一覧（表） |
| `agents.csv` / `agents.json` | エージェントごとの担当騎手データ |
| `jockeys.csv` | 騎手ごとの所属・若手かどうか・担当エージェント |
| `build.py` | JRAのPDFからデータを作り直すスクリプト |
| `agent_results_2026-11-07_08.md` / `.csv` | 2026年11月7・8日（東京・京都・福島 全72レース）のエージェント別成績 |
| `agent_results.py` | レース結果ページからエージェント別成績を集計するスクリプト |
| `same_agent_races_2026-11-07_08.md` | 同じエージェントの騎手が同じレースに出たときと単独のときの成績比較 |
| `same_agent_races.py` | 上の比較を作るスクリプト |
| `agent_pairs_2026-11-07_08.md` | エージェント×馬主、エージェント×調教師の成績（主な組み合わせ） |
| `agent_x_owner_2026-11-07_08.csv` / `agent_x_trainer_2026-11-07_08.csv` | 上の全組み合わせ |
| `agent_pairs.py` | 上の集計を作るスクリプト（馬主は出馬表ページから取る） |

## データを最新にしたいとき

JRAのPDFは更新されるので、新しい時点のデータが欲しいときは次を実行します。
最後の日付は、[JRAのページ](https://www.jra.go.jp/datafile/meikan/agent.html)に書かれている「〇年〇月〇日現在」に合わせてください。

```
pip install pdfplumber
mkdir pdf
curl -o pdf/agent_miho.pdf https://www.jra.go.jp/datafile/meikan/pdf/agent_miho.pdf
curl -o pdf/agent_rittou.pdf https://www.jra.go.jp/datafile/meikan/pdf/agent_rittou.pdf
curl -o pdf/agent_other.pdf https://www.jra.go.jp/datafile/meikan/pdf/agent_other.pdf
python jra_agents/build.py pdf jra_agents 2026-11-05
```

Windows の PowerShell では `curl` を `curl.exe` に置き換えてください。

## 回収が終わったら（任意）

`werewolf-game` 側のこのブランチは不要になります。
GitHub の werewolf-game リポジトリの「Branches」から `claude/kind-maxwell-hyg5wf` を削除してかまいません
（`main` には入っていないので、人狼ゲーム本体には影響しません）。
