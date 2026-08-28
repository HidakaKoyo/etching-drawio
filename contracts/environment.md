# environment contract (runtime 宣言と検証手順)

- 正本: `docs/PLAN.md` §7.1
- 依存欠落時の挙動: exit 5 (`contracts/exit-codes.md`)

エンドユーザーに要求する実行時依存を、ここで閉じる。ここに書いていないものは要求しない。

## 1. 対応 OS

| OS | 位置づけ |
|---|---|
| macOS (Apple Silicon / Intel) | 一次。CI マトリクスに入れる |
| Ubuntu (LTS) | 一次。CI マトリクスに入れる |
| その他の Linux | best effort。CI で検証しない |
| Windows | v1 では対象外 (WSL 上の Ubuntu として扱う) |

## 2. shell

- **bash 3.2 互換に固定する。** macOS 同梱 bash の下限がここにあるため
- POSIX sh への全面書き換えはしない
- したがって次は使わない: 連想配列 (`declare -A`)、`${var^^}` / `${var,,}`、`mapfile` / `readarray`、`&>>`、`|&`、negative array index、`declare -g`
- ShellCheck を CI で実行する

## 3. python3

- **標準ライブラリのみ。最低バージョンは 3.9。**
- 外部パッケージを import しない。`pip install` を要求しない
- **エンドユーザーに `uv` は要求しない。** `uv` はこの repo の開発ツーリング側でのみ使う
- python3 が無い、または 3.9 未満なら exit 5 (`dependency/python3`)

3.9 を下限に選んだのは、Ubuntu 20.04 と macOS の実用的な下限がそこに揃うためである。3.9 で使えない構文 (`match`、`X | Y` の型注記、`tomllib`) は使わない。

## 4. draw.io Desktop

export に必要。validation だけを行うサブコマンドでは不要で、その場合は依存として要求しない (要求してから無いと言うのではなく、必要になったときに初めて解決する)。

### 4.1 `DRAWIO_CMD` の解決順

`DRAWIO_CMD` は **単一の executable path** を保持する。shell 文字列 (引数付きコマンド行) として解釈しない。空白を含む path をそのまま扱えるようにするためで、追加引数が要る場合は wrapper script を作ってその path を渡す。

解決は上から順に、最初に見つかった実行可能ファイルを採用する。

1. 環境変数 `DRAWIO_CMD` が設定されていればそれを使う。**設定されているのに実行可能でなければ、次に進まず exit 5** (明示指定を黙って無視しない)
2. `PATH` 上の `drawio`
3. macOS の app bundle: `/Applications/draw.io.app/Contents/MacOS/draw.io`、次に `$HOME/Applications/draw.io.app/Contents/MacOS/draw.io`
4. Linux の既定パス: `/usr/bin/drawio`、`/usr/local/bin/drawio`、`/opt/drawio/drawio`、`/snap/bin/drawio`

いずれも見つからなければ exit 5 (`dependency/drawio`)。

### 4.2 headless 実行

Linux CI では draw.io Desktop が X を要求するため、`xvfb-run` 相当の仮想ディスプレイ下で実行する。これは CI 環境の責務であり、CLI が `xvfb-run` を自動で被せることはしない (被せると失敗の原因が二重になる)。

## 5. 任意コマンド

出力検証で使う。無い場合は該当 check を optional として `skipped` にし、その旨を diagnostics に warning で残す。exit code は変えない。

| コマンド | 用途 | 無い場合 |
|---|---|---|
| `xmllint` | SVG の well-formedness、mxfile.xsd 検証 | 該当 check を skipped。python3 の `xml.etree` による代替検証に落とす |
| `file` | PDF の magic 確認 | python3 による magic 読み取りに落とす |

PNG の chunk 走査と CRC 検証、IDAT の zlib 展開は python3 標準ライブラリ (`zlib` / `binascii` / `struct`) だけで行う。`sips` は使わない (macOS 専用で、検証としても弱いため v1 で廃止する)。

## 6. clean install での検証手順

「手元では動く」を排除するための受入手順。Phase 1c / 3a の CI がこれを実行する。

1. **素の環境を用意する。** Ubuntu LTS の container、および GitHub Actions の macOS runner。開発用の `uv` / Homebrew の追加パッケージを入れない
2. **配布物だけを置く。** 2 方式それぞれで行う
   - plugin marketplace 経由のインストール
   - `npx skills add` による skill 単体インストール
3. **閉包の自己完結を確認する。** インストールしたディレクトリの外を参照していないこと。sibling 依存が無いこと
4. **依存欠落の挙動を確認する。** `DRAWIO_CMD` を存在しない path に設定して実行し、exit 5 と `dependency/drawio` の診断が出ること。python3 を PATH から外して実行し、exit 5 と `dependency/python3` が出ること
5. **validation の実走。** 既知の不正な `.drawio` を検証し、期待した診断 code と exit 1 が出ること
6. **export の実走 (Phase 1d の gate)。** pin した draw.io Desktop で、OS 別の `DRAWIO_CMD` 解決 → 実 export → SVG / PNG / PDF の検証まで、**Ubuntu と macOS の両方で各 1 回以上**通ること
7. **納品の実走。** `generations/<id>/` の生成、`current` の切替、receipt の内容が `contracts/delivery.md` §6 を満たすこと

3〜7 のいずれかが落ちたら、その配布方式は受入不合格とする。
