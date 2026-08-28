# 環境と profile

- **実装契約の正本は repo の `contracts/environment.md` / `contracts/exit-codes.md` / `contracts/profile.md`。** ここはそれを、エージェントが要る範囲だけ平易にしたもの。食い違ったら `contracts/` が正しい

## 1. 実行時に要るもの

ここに書いていないものは要求しない。`pip install` も `uv` も要らない。

| もの | 要求 | 無いとき |
|---|---|---|
| bash | 3.2 以上 | — |
| python3 | 3.9 以上、標準ライブラリのみ | exit 5 (`dependency/python3`) |
| draw.io Desktop | **書き出しのときだけ** | exit 5 (`dependency/drawio`) |
| `xmllint` | 任意。XSD 検証に使う | 該当 check を skip して続行 |
| `file` | 任意。PDF の magic 確認 | python3 の判定に落ちて続行 |

`etch validate` は draw.io Desktop を要求しない。Desktop が無い環境でも検証と起案はできる。「書き出せない」と「検証できない」を混同しない。

対応 OS は macOS と Ubuntu LTS。その他の Linux は best effort、Windows は WSL 上の Ubuntu として扱う。

## 2. draw.io Desktop の解決順

上から順に、最初に見つかった実行可能ファイルを使う。

1. 環境変数 `DRAWIO_CMD`。**設定されているのに実行できなければ、次に進まず exit 5。** 明示指定を黙って無視しない
2. `PATH` 上の `drawio`
3. macOS: `/Applications/draw.io.app/Contents/MacOS/draw.io` → `$HOME/Applications/draw.io.app/Contents/MacOS/draw.io`
4. Linux: `/usr/bin/drawio` → `/usr/local/bin/drawio` → `/opt/drawio/drawio` → `/snap/bin/drawio`

`DRAWIO_CMD` は**単一の実行ファイルのパス**であって、引数付きのコマンド行ではない。引数を足したいなら wrapper script を書いてそのパスを渡す。

Linux では draw.io Desktop が X を要求するので、`xvfb-run` 相当の下で走らせる。これは環境側の責務で、CLI は勝手に被せない。

## 3. exit code

| code | 意味 | JSON |
|---|---|---|
| 0 | 通った (`passed`)、または処理対象なし (`skipped`) | 出る |
| 1 | 検証で落ちた | 出る |
| 2 | 書き出し・出力検証で落ちた | 出る |
| 3 | hash 競合 | 出る |
| 4 | 引数・profile が不正 | **出ない** |
| 5 | 依存欠落 | 出る |
| 6 | CLI 内部エラー | ベストエフォート |
| 130 | signal で中断 | **出ない** |

`skipped` の exit code が 0 である点に注意する。処理対象が無いのは異常ではないので、code では `passed` と区別できない。JSON の `status` で見分ける。

exit 4 と 130 は JSON を出さない。stderr を読む。

## 4. profile の解決

環境固有の規約は 2 ファイルに分かれる。

| ファイル | 読む主体 | 中身 |
|---|---|---|
| `.etching/profile.json` | CLI | 分岐に使う値だけ。schema で検証される |
| `.etching/profile.md` | **エージェント (あなた)** | 置き場所の規約、埋め込みレシピなど |

解決順は上が優先で、最初に見つかったものだけを使う。

1. `--profile <path>`
2. 環境変数 `ETCHING_PROFILE`
3. カレントディレクトリ直下の `.etching/profile.json`
4. なし (host-neutral な既定)

**親ディレクトリを遡らない。相対参照で vault などを推測して探しにいかない。** 3 は「カレントディレクトリ直下」だけを見る。

ここが事故になりやすい。`.etching/profile.json` がある project の図を、別の cwd から絶対パスで指して `etch` を呼ぶと、**profile は見つからず既定 (`proposal_mode: false`) で走る**。exit code も警告も出ない。proposal mode のつもりだった環境では正本がそのまま置換される。

したがって etch を呼ぶときは、**`.etching/` があるディレクトリを cwd にする**か、**`--profile <path>` を明示する**。入力ファイルを絶対パスで渡せていることは、profile が見えていることの根拠にならない。

profile を読むと決めたパスが、無い・JSON として壊れている・schema に合わないときは exit 4 で止まる。既定値に落ちない。黙って既定に落ちると、proposal mode のつもりだった環境で正本が置換される。

### v1 のキー

```json
{
  "version": 1,
  "proposal_mode": true
}
```

この 2 つだけである。`proposal_mode` の既定は `false`。

出力先・書き出し形式・`DRAWIO_CMD`・検証の厳しさは profile では変えられない。毎回の引数か環境変数で決まる。

### profile.md の読み方

`.etching/profile.json` を見つけた場所と同じディレクトリに `profile.md` があれば、**起案に入る前に読む**。CLI はこれを解釈しないので、書かれた規約に従うのはエージェントの責任である。

典型的には、成果物の置き場所、図の埋め込みかた、その環境で禁じられている書き出しオプションが書いてある。無ければ host-neutral な既定で進めてよい。

## 5. 入力ポリシー (常時 ON)

profile で緩められない。

- 圧縮された diagram 本文は拒否する (exit 1、`input/compressed-payload`)。黙って展開しない。`<mxfile compressed="false">` で書く
- DTD と外部 entity は拒否する (`input/dtd-forbidden` / `input/external-entity`)
- byte 数・node 数・深さの上限を超えたら拒否する (`input/too-large` / `input/too-complex`)
- style / image 属性の中の http・file URL は `security/external-ref` の warning になる。exit code は変わらない。`--allow-external` を付けると check が waiver 付きで skip され、診断は出なくなる。付けたなら報告に書く
