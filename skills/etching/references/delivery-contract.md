# 納品の作法

- 対象: 成果物を人や後続ツールに渡すエージェント
- **実装契約の正本は repo の `contracts/delivery.md`。** ここはそれを、エージェントが従う部分だけ平易にしたもの。食い違ったら `contracts/` が正しい

## 1. 何が出来上がるか

```
<出力ルート>/
  generations/
    <id>/            # 1 回の納品ぶん。rename 後は変更されない
      diagram.svg
      receipt.json
  current            # -> generations/<id>
```

- **世代 (generation)** は 1 回の納品で作った成果物の集合。確定後は中身が変わらない
- **receipt** はその世代の内容証明。成果物の SHA-256、etch のバージョン、draw.io Desktop のバージョンと実行オプション、入力 `.drawio` の hash、実行した checks を持つ。receipt 自身は hash 対象に入らない
- **`current`** は最新世代を指す pointer

出力ルートと正本は同じ filesystem 上に置く。またいだ配置は exit 4 で止まる。

## 2. コマンドの使い分け

| したいこと | コマンド |
|---|---|
| 検証だけ | `etch validate --json <file>` |
| 世代を作るが `current` は進めない | `etch export --format <fmt> --output-root <dir> [--content <作業コピー>] <正本>` |
| 世代を作って `current` を進める | `etch deliver` (引数は export と同じ) |
| 既存の世代が壊れていないか見る | `etch verify --output-root <dir>` |
| 古い世代の掃除 | `etch gc --output-root <dir> [--delete]` |

`--output-root` のディレクトリは**あらかじめ存在していなければならない**。CLI は作らない。無ければ exit 4 (usage error) で止まり、診断 JSON も出ない。

`--content` を渡すと、その内容で正本を置換してから書き出す。修復ループを回ったら必ず渡す。渡さなければ正本がそのまま入力になる。

1 回の実行が扱う形式は 1 つ。SVG と PNG の両方が要るなら 2 回実行する (世代は別になる)。

## 3. proposal mode

profile で `proposal_mode` が真のとき、次のように変わる。

- 正本を**置換しない**。かわりに `<名前>.agent-proposal.drawio` を同じディレクトリに書く
- `current` を**切り替えない**。世代ディレクトリと receipt だけができる
- receipt と `etch verify` の照合対象は、正本ではなく proposal ファイルになる

人が draw.io Desktop で同じファイルを開いている可能性がある環境ではこれを使う。proposal を正本に取り込むのは人の操作で、CLI もエージェントも勝手にやらない。

報告では「正本は変えていない。proposal を置いた」と明示する。黙っていると、相手は正本が更新されたと思い込む。

## 4. hash 競合 (exit 3)

CLI は正本が変わっていないことを 2 度確かめる。正本を置換する直前と、`current` を切り替える直前である。どちらかで外れたら、置換も切替も行わず exit 3 で止まる。

これは「誰かが同じファイルを触った」という事実である。**再実行で押し通さない。** 何が起きたかを報告し、どう進めるかを相手に決めてもらう。

この照合が競合を防げるのは、この作法に従う書き手どうしに限る。draw.io Desktop のような外部の書き手に対しては、防止ではなく検出を保証する。あとから `etch verify` を走らせれば、正本が receipt の記録から動いたことが分かる。

## 5. 成果物を読むとき

1. `current` を**一度だけ**解決して世代ディレクトリのパスを得る
2. そのパスから全成果物と receipt を読む
3. `current/<file>` の形でファイルごとに解決し直さない

途中で pointer が進むと、再解決のたびに別世代のファイルを掴んで混ざる。世代ディレクトリは確定後 immutable なので、一度解決してしまえば混在は起きない。

人に渡すパスも、`current` 経由ではなく解決後の世代ディレクトリのパスにする。

## 6. 掃除

- 旧世代は**自動で消えない**
- 自分のプロセスが作りかけた `.tmp` 世代だけは、成否によらず終了時に消える
- 完結した旧世代を消すのは `etch gc --delete` を明示したときだけ。既定では候補を並べるだけで何もしない
- `gc` は `current` が指す世代と `current` 自身を消さない
- CLI は「その世代を誰も読んでいない」ことを保証しない。消す判断は人がする

指示もなく `--delete` を付けない。

## 7. 報告に必ず入れるもの

- 成果物の絶対パス (解決後の世代ディレクトリ)
- `status` の 3 値 (`passed` / `skipped` / `failed`) をそのまま。言い換えない
- warning の診断と、skip された optional check (`xmllint` が無い等)
- `--embed-xml` / `--allow-external` を付けたなら、付けた事実と理由
- draw.io Desktop のバージョン (receipt にある)
- proposal mode なら、正本を触っていないこと
