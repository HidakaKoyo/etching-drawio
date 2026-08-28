# exit code contract

- 正本: `docs/PLAN.md` §6.1。本文書はそれを発火点の粒度まで展開したもの
- 対象: `etch` CLI の全サブコマンド
- 対応する診断 JSON の schema: `contracts/diagnostics.schema.json`

## 1. 一覧

| code | 意味 | 診断 JSON を stdout に出すか | JSON の `status` |
|---|---|---|---|
| 0 | 正常終了 (全 required check が passed、または処理対象なし) | 出す | `passed` または `skipped` |
| 1 | validation failure (export 前の検証で落ちた) | 出す | `failed` |
| 2 | export・出力検証失敗 | 出す | `failed` |
| 3 | hash 競合 (正本が想定外に書き換わっていた) | 出す | `failed` |
| 4 | usage error (引数・profile が不正で、何を処理すべきか決められない) | **出さない** | — |
| 5 | 依存欠落 (必須の外部コマンド・ランタイムが無い) | 出す | `failed` |
| 6 | internal error (検証系自体の異常終了) | ベストエフォートで出す | `failed` |
| 130 | signal 終了 (HUP / INT / TERM) | **出さない** | — |

`status: skipped` の exit code が 0 である点に注意する。処理対象外は異常ではないので code では区別せず、JSON の `status` で `passed` と区別する。

exit 4 と exit 130 は診断 JSON を出さない。引数や profile が壊れている段階では出力先も対象成果物も確定できず、`checks[]` を組み立てられないためである。エラー本文は stderr に出す。この非対称は意図的なもので、schema の集約規則 (`status: failed` は unmet な required check の存在を要求する) と矛盾させないための設計である。

exit 130 も JSON を出さない。signal を受けた時点で実行は途中であり、`checks[]` は「まだ走っていない」だけの状態を含む。それを `failed` として出すと、検証で落ちたのか中断されたのかを読者が区別できない。130 は POSIX 慣行 (128 + SIGINT) に合わせた**予約 code** であり、診断 contract の外にある。stderr に中断した旨だけを出す。

exit 6 は「検証系自体が壊れた」場合に限る。入力が悪いのではなく、CLI か CLI が呼ぶ内部処理が想定外の状態で落ちたときである。診断 JSON は**ベストエフォート**で出す (組み立てられるところまで組み立て、`internal/*` の required check を failed にする)。組み立てられなければ stderr だけで終わってよい。

## 2. 発火点

### exit 0

- 全 required check が `passed` (optional check の failed / skipped は 0 を妨げない)
- 対象 deliverable が 1 件も無い指定だった (`status: skipped`)
- `etch gc` が削除対象なしで正常終了した場合を含む
- 外部リソース参照 (style / image 属性中の http・file URL) を検出した。これは **optional check `security/no-external-ref` の failed** として表現し、診断は `security/external-ref` の severity=warning にする。top-level status も exit code も変えない。`--allow-external` を渡した場合は check を waiver 付きの skipped にし、診断を出さない

### exit 1 — validation failure

export に入る前の、入力とその修復結果に対する検証で落ちたもの。

- XML の well-formedness 違反 (`xml/*`)
- mxfile スキーマ (`shared/mxfile.xsd`) との不整合 (`xml/*`)
- スタイル規約違反 (`style/*`)
- 入力安全ポリシー違反 (`input/*`): DTD・外部 entity の検出、byte 数 / node 数 / 深さ / 圧縮展開後サイズの上限超過、非圧縮強制ポリシー下での圧縮入力
- 修復ループが停止条件に達した (循環検知、fix set 5 回打ち切り)。正本は `H0` のまま無傷

### exit 2 — export・出力検証失敗

draw.io Desktop を起動して以降の失敗。

- draw.io Desktop の異常終了 / タイムアウト
- 期待した出力ファイルが生成されなかった
- PNG の chunk 構造または CRC 不正、IDAT を zlib 展開した寸法が IHDR と不整合
- SVG が well-formed でない
- PDF の magic 不一致

### exit 3 — hash 競合

`contracts/delivery.md` の hash handoff で照合が外れたとき。

- 正本置換の直前に実測した正本 hash が `H0` と一致しない
- `current` pointer 切替の直前に実測した正本 hash が `Hfinal` と一致しない
- proposal mode で、proposal ファイルが自分の書いた内容から変化していた

いずれの場合も正本の置換も pointer の切替も行わない。

### exit 4 — usage error

- 未知のサブコマンド / 未知のオプション / 必須引数の欠落
- 入力 path が存在しない、ディレクトリを指している等の指定不整合
- profile の解決に失敗した (JSON parse 失敗、schema 不合格、`--profile` に指定した path が無い)。profile は fail-closed で、不正なら既定値へフォールバックしない

### exit 5 — 依存欠落

- `DRAWIO_CMD` が未設定かつ解決順のどこでも draw.io Desktop が見つからない
- `python3` が無い、または 3.9 未満
- 出力検証に必要な任意コマンドのうち、その実行で必須になったものが無い

依存欠落は診断 JSON 上では required check の `failed` として表現する (`dependency/*`)。したがって `status` は `failed` になり、exit 1 / 2 との区別は code だけが担う。

### exit 6 — internal error

CLI 自身の異常。入力の不備ではない。

- 想定していない例外が検証・export・納品のいずれかの段で送出された
- 内部で呼んだ補助処理が契約外の終了状態を返した (旧 wrapper が semantic lint の想定外終了を exit 4 にしていたのを、ここに移す)
- 出力すべき診断 JSON を組み立てられなかった

診断 code は `internal/*`。JSON はベストエフォートで、出せる場合は `internal/*` の required check を failed にする。

### exit 130 — signal 終了

HUP / INT / TERM を受け取ったとき。実行中の子プロセス (draw.io) を含めて後始末し、`current` の切替も正本の置換も行わない。自プロセスが作った `.tmp` 世代は消す。診断 JSON は出さない。

## 3. 実装上の不変条件

- 1 回の実行が返す code は 1 つ。複数の失敗が同時に起きた場合は **小さい番号ではなく、最初に確定した停止事由** を返す。処理順は argv 解析 → 依存解決 → validation → export → delivery で固定されており、実際には **4 → 5 → 1 → 2 → 3** の順に確定する (何を処理するかが決まらないと、どの依存が要るかも決まらないため 4 が先)。6 と 130 はこの順序の外側で、どの段からでも発生しうる
- code と JSON の `status` は必ず上表の対応に従う。テストで機械照合する
- stdout に JSON 以外を書かない。診断 JSON を出す code では、JSON が単一のトップレベル値として完結している
