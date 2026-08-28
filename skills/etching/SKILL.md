---
name: etching
description: Always use when the user asks to create, generate, draw, edit, fix, or export a diagram — flowchart, architecture diagram, ER diagram, sequence diagram, class diagram, state diagram, network diagram, wireframe — or mentions draw.io, drawio, .drawio files, or exporting a diagram to SVG/PNG/PDF. 図・フローチャート・アーキテクチャ図・ER 図・シーケンス図・構成図の作成・編集・書き出し依頼で必ず使う。呼び出し名は etching。
---

# etching

`.drawio` の図を、起案 → 検証 → 修復 → 納品の順で作る。図の依頼はこの skill 一つで完結させる。素の `drawio` CLI で最終成果物を書き出さない。

工程は 4 つある。順番を飛ばさない。

## 0. 前提を確かめる

`etch` CLI の解決順は次のとおり。最初に見つかった実行可能ファイルを使う。

1. 環境変数 `ETCH_CMD`
2. `PATH` 上の `etch`
3. この SKILL.md から見た相対パス。plugin として入っているなら `../../bin/etch`、skill 単体の bundle なら `bin/etch`

見つからなければ、その旨を伝えて止まる。代わりに素の `drawio` を使ってはいけない。正本は `contracts/environment.md` §7 で、その平易版が `references/environment.md` §1.1 にある。

環境固有の規約 (置き場所、埋め込みの作法、proposal mode の既定) は profile にある。`references/environment.md` の解決規則で `.etching/profile.md` を探し、あれば**起案前に読む**。無ければ host-neutral な既定で進める。

profile は**カレントディレクトリ直下の `.etching/` しか見ない**。親を遡らない。したがって `etch` は次のどちらかで呼ぶ。

- `.etching/` があるディレクトリを cwd にして呼ぶ
- `--profile <path>` で明示する

別の cwd から呼ぶと profile が見つからず、既定 (`proposal_mode: false`) で走る。proposal mode を期待していた環境では、これは正本が置換される事故になる。**入力ファイルを絶対パスで渡せているからといって、profile も見えているとは限らない。**

## 1. 起案

XML の書き方・shape・スタイル・Mermaid との使い分けは、同梱した上流スナップショットが正本である。**ネットワークから取得しない。**

まず `references/upstream/plugins/claude-code/skills/drawio/SKILL.md` を読む。その中の URL は、次の表で同梱パスに読み替えて読む。

| 上流の URL | 読む先 (この skill ディレクトリ基準) |
|---|---|
| `raw.githubusercontent.com/jgraph/drawio-mcp/main/shared/xml-reference.md` | `references/upstream/shared/xml-reference.md` |
| `raw.githubusercontent.com/jgraph/drawio-mcp/main/shared/mermaid-reference.md` | `references/upstream/shared/mermaid-reference.md` |
| `github.com/jgraph/drawio-mcp/blob/main/shared/style-reference.md` | `references/upstream/shared/style-reference.md` |
| `github.com/jgraph/drawio-mcp/blob/main/shared/mxfile.xsd` | `references/upstream/shared/mxfile.xsd` |

一般規則: `jgraph/drawio-mcp` を指す raw / blob URL は `<path>` を取り出して `references/upstream/<path>` を読む。ref (`main` 等) は無視する。上流 repo 以外を指す URL は取得しない (参考リンクとして扱う)。

### 上流に対する override

同梱スナップショットは無改変なので、次の 5 点は上流の記述と食い違う。**etching 側が優先する。**

1. **書き出し後に `.drawio` を削除しない。** 正本は常に `.drawio`、SVG / PNG / PDF は派生物という二層で扱う。上流は「export 後に中間 `.drawio` を消す」と書いているが、これは採らない。Mermaid から起こしたときに `.mmd` を消すのは上流のとおりでよい (正本は `.drawio` に一本化する)
2. **最終成果物の書き出しは `etch export` / `etch deliver` に限る。** 素の `drawio -x` での最終 export は禁止。Mermaid → `.drawio` 変換と ELK `--layout` は etch が担わないので、**作業コピーの上でだけ**素の CLI を使ってよい。その結果を正本に反映してから etch に戻す
3. **必ず `<mxfile compressed="false">` で包む。** bare の `<mxGraphModel>` ファイルは作らない。圧縮された本文は etch が黙って展開せず拒否する
4. **公開・共有用の書き出しに `--embed-xml` を付けない。** 埋め込み XML は隠しレイヤや内部情報の流出経路になる。再編集可能な SVG が要るのは内部往復のときだけで、そのときだけ明示的に付ける
5. **`#create=` の browser URL 出力は成果物にしない。** 納品は世代ディレクトリと receipt で行う (`references/delivery-contract.md`)

既存図の修正では、全再生成でなく局所パッチを当て、既存の cell ID を維持する。ID が変わると、人が draw.io Desktop 側で持っている選択状態やリンクが壊れる。

## 2. validate

書いた図を検証する。出力は stdout の JSON がすべてで、人が読む行は stderr に出る。

```bash
etch validate --json <file.drawio>
```

exit 0 なら次へ進む。exit 1 なら修復ループに入る。exit 4 (引数・profile 不正) と exit 5 (依存欠落) は自分では直せないので、原因を述べて止まる。code の意味は `references/environment.md` にある。

読むのは JSON の 3 か所だけでよい。

- `status` — `passed` / `failed` / `skipped`
- `checks[]` — `required: true` が 1 つでも `passed` でなければ `failed`
- `diagnostics[]` — `code` と `subject` (`file` / `xpath` / `cellId`) が直す場所を指す

`severity: warning` の診断は納品を止めない。止めないが、報告では黙らせない。

## 3. 修復ループ

**正本には途中経過を一切書き戻さない。** 修復は作業コピーの上だけで行う。作業コピーは正本と同じディレクトリに置く (別 filesystem だと最後の置換が atomic でなくなる)。

1 周の手順は次のとおり。

1. 診断から **fix set** を組む。fix set は「互いに競合せず、決定的に適用できる修正の集合」。1 周に 1 fix set だけ当てる
2. 作業コピーに適用する
3. 作業コピーを再 validate する
4. 全 required check が passed なら納品へ進む

止まる条件は 2 つある。どちらかに当たったら**納品せず failed で報告する**。

- **循環**: 状態 fingerprint が既出のものに戻った。fingerprint = 作業コピー自体の hash + 正規化した `(code, subject)` の multiset。両方を毎周記録する
- **打ち切り**: fix set の適用が 5 回に達した

診断が減り続けている限り、同じ `code` がまた出ただけでは止めない。判断の詳細は `references/authoring-contract.md` にある。

失敗して止まったときは、正本は手つかずのまま残っている。作業コピーと最後の診断を添えて報告する。黙って捨てない。

## 4. deliver

検証を通った作業コピーを CLI に渡す。正本の置換・世代の構築・receipt・pointer の切替は CLI が一続きで行う。

```bash
etch deliver --format svg --output-root <出力ルート> --content <作業コピー> <正本.drawio>
```

- `--output-root` に渡すディレクトリは**先に作っておく**。無いと exit 4 で止まり、JSON は出ない
- `--content` を渡すと、その内容で正本を置換してから書き出す。修復ループを回ったら必ず渡す
- pointer を進めずに世代だけ作りたいときは `deliver` でなく `export` を使う
- 複数形式が要るなら `--format` を変えて実行し直す (1 回の実行が扱う形式は 1 つ)
- 納品が通ったら**作業コピーを消す**。正本と紛らわしいファイルを隣に残さない。失敗して止まったときだけ、証拠として残す

**proposal mode** (profile で有効) では、正本を置換せず `<名前>.agent-proposal.drawio` を並置し、`current` も切り替えない。人が draw.io Desktop で同じファイルを開いている可能性があるときはこちらを使う。取り込みは人の操作であって、CLI の責務ではない。

exit 3 は hash 競合で、誰かが正本を書き換えたことを意味する。**上書きを試みず**、競合として報告する。

書き出したら、レンダリング結果を実際に目で見る。SVG をテキストとして読んだだけで「確認済み」と書かない。画像を表示できない環境なら「未目視」と明記する。

**検証が通っても、図が意図どおりとは限らない。** 存在する ID を指す辺は、それが繋ぐべき相手でなくても検証を通る。線が意図しない箱を貫いていないか、ラベルが図形からはみ出していないかは、目で見るまで分からない。ここで見つけた問題は修復ループの対象ではなく、起案に戻ってやり直す。

## 報告

3 値を混ぜない。

- **passed** — 全 required check が passed。成果物のパスと `etch verify` が通ることを添える
- **skipped** — 処理対象が無かった。異常ではないので `passed` と言い換えない
- **failed** — required check の失敗、修復ループの停止、hash 競合。診断 code と、どこで止まったかを書く

`warning` の診断、optional check の skip (`xmllint` が無い等)、`--embed-xml` や `--allow-external` を付けた事実は、passed のときも報告に残す。「通った」だけで済ませない。draw.io Desktop のバージョンは receipt にあるので、export したときは併記する。

## 参照

- `references/authoring-contract.md` — 修復ループの規律 (fix set の組み方、fingerprint、停止条件)
- `references/delivery-contract.md` — 納品の作法 (世代、receipt、読者 protocol、proposal mode)
- `references/environment.md` — 依存、exit code、profile の解決
- `references/upstream/` — 上流スナップショット (無改変。編集しない)

実装契約の正本は repo の `contracts/` にある。ここの記述と食い違ったら `contracts/` が正しい。
