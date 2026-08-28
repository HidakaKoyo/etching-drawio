# Phase 1a: 既存 wrapper の挙動棚卸し

- 対象: `Koyo-HQ/bin/drawio-verify-export` (bash 658 行)。**read-only。この Phase で vault 側は一切変更しない**
- 目的: 移植で「維持する invariant」と「意図的に変える点」を分け、前者を characterization test で固定する
- gate (`docs/PLAN.md` §10 Phase 1a): 現行 wrapper に対し invariant テストが green。意図的変更は旧値→新値の migration test として定義済み
- テスト: `tests/characterization/test_invariants.py` (invariant) / `tests/characterization/test_migration.py` (意図的変更)

## 1. 現行 wrapper の処理順

exit code の確定順を読むうえで、この順序が前提になる。

1. 引数解析 (不明オプション・値欠落は exit 4)
2. 値の妥当性 (ページ番号・倍率・出力形式・`--embed-xml` の組み合わせ)
3. 依存コマンドの存在確認 (`drawio` `xmllint` `python3` `shasum`、export 時は加えて `file`、PNG なら `sips`)
4. 入出力パスの解決と同一ファイル判定
5. 出力 lock の取得 (`<出力>.lock` ディレクトリ、`--check-only` では取らない)
6. 一時コピーの作成と `BEFORE_HASH` の記録
7. XML well-formedness → root 要素 → `compressed` 属性 → XSD → semantic lint → ページ数
8. `--check-only` ならここで exit 0
9. draw.io export (専用 process group、120 秒でタイムアウト)
10. `AFTER_HASH` 照合 → export 終了状態 → 出力形式の検証
11. `FINAL_HASH` 照合 → `mv` で公開 → 公開先の絶対パスを stdout に出力

## 2. 維持する invariant

移植後も同じ判定・同じ exit code でなければならないもの。括弧内はテスト ID。

| # | 挙動 | 現行の exit | テスト |
|---|---|---|---|
| I-1 | XML が well-formed でない入力を拒否する | 1 | INV-01 |
| I-2 | 生の `&` を検出したとき、行番号付きのヒントを出す | 1 | INV-02 |
| I-3 | `parent` の参照先 id が存在しない mxCell を検出する | 1 | INV-03 |
| I-4 | `source` / `target` の参照先 id が存在しないエッジを検出する | 1 | INV-04 |
| I-5 | 同一ページ内の mxCell id 重複を検出する | 1 | INV-05 |
| I-6 | root 要素が `<mxfile>` でない入力を拒否する | 1 | INV-06 |
| I-7 | 実在ページ数を超えるページ番号を拒否する | 1 | INV-07 |
| I-8 | `compressed="false"` でないとき警告する。ただし処理は続行する | 0 + 警告 | INV-08 |
| I-9 | `compressed="false"` のときは警告を出さない | 0 | INV-09 |
| I-10 | style / image 属性中の http・file URL を外部参照として警告し、`--allow-external` で抑止できる | 0 + 警告 | INV-10 |
| I-11 | 入力ファイル自身を出力先に指定することを拒否する (実体パスと `samefile` の両方で判定) | 4 | INV-11 |
| I-12 | 引数不備・未知オプション・不正な倍率やページ番号・存在しない入力・存在しない出力先ディレクトリ・入力 2 件指定を拒否する | 4 | INV-12 |
| I-13 | 出力ごとの lock が排他である。取得できなければ export せず、他プロセスの lock を消さない | 2 | INV-13 |
| I-14 | 正常終了時に自分の lock を解放し、検証済み出力を公開する | 0 | INV-14 |
| I-15 | export 中に入力が書き換わったら競合として扱い、出力を公開しない | 3 | INV-15 |
| I-16 | 競合で終了しても出力先に一時ディレクトリを残さない | 3 | INV-16 |
| I-17 | 出力の形式検証に落ちた成果物を公開しない | 2 | INV-17 |
| I-18 | draw.io が異常終了したら公開せず、ログ冒頭を stderr に出す | 2 | INV-18 |
| I-19 | 実 CLI で SVG / PNG / embedded-XML SVG を書き出し、検証を通す | 0 | SMOKE-01〜03 |

I-15 から I-18 に共通する上位の invariant は「**検証を通っていない成果物を公開しない**」である。
新 CLI では公開の単位が世代ディレクトリと `current` pointer に変わるが (MIG-08)、この性質そのものは変わらない。

### 2.1 CLI 依存の分離

`tests/characterization/test_invariants.py` は 2 群に分かれる。

- **INV-01〜18**: draw.io Desktop 本体を必要としない。PATH の先頭に bash 製の stub `drawio` を置き、wrapper の `command -v drawio` を満たす。検証だけで終わる case は stub を起動すらせず、export を伴う case は stub を使って「出力が壊れている」「入力が書き換わる」「異常終了する」を決定的に再現する
- **SMOKE-01〜03**: 実 CLI が要る。PATH 上に本物が無ければ skip する

stub は draw.io の代用ではなく、wrapper 側の分岐を決定的に踏むための test double である。
描画結果の正しさは SMOKE 側でしか主張しない。

テストは毎回 `tempfile.mkdtemp()` で作った作業ディレクトリ内で完結し、fixture の `.drawio` もそこに生成する。
vault の実ファイルは読み書きしない。

## 3. 意図的に変える点

`test_migration.py` に新期待値として定義済み。**現行 wrapper には実行しない** (現行が満たさないことが定義であるため)。
Phase 1b で `ETCH_CLI` を新 CLI に向け、`argv_for()` を埋めて有効化する。

| # | 領域 | 旧 (現行 wrapper) | 新 (contract) | 根拠 |
|---|---|---|---|---|
| MIG-01 | 依存 | 必須コマンド欠落は **exit 4** | **exit 5** + `dependency/*` の required check failed | exit-codes.md §2 / environment.md §3, §4.1 |
| MIG-02 | 依存 | `DRAWIO_CMD` を見ない。PATH の `drawio` のみ | `DRAWIO_CMD` が最優先。設定済みで実行不可なら PATH に落ちず **exit 5** | environment.md §4.1 |
| MIG-03 | 入力安全 | 圧縮 diagram を復号して検査し、**警告のみ**で続行 | 暗黙変換せず **exit 1** + `input/*` で拒否 | PLAN §6.4 |
| MIG-04 | 入力安全 | DTD・外部 entity の方針なし。サイズ・ノード数・深さの上限なし | DTD / 外部 entity を **exit 1** + `input/*` で拒否 | PLAN §6.4 |
| MIG-05 | 検証の重み | XSD 不適合は **警告**で続行 | **exit 1** + `xml/*` | exit-codes.md §2 |
| MIG-06 | 報告 | stdout に公開先パス、指摘は日本語散文で stderr | stdout は診断 JSON のみ、ログは stderr | PLAN §6.1 / exit-codes.md §3 |
| MIG-07 | 報告 | usage error は stderr に散文、stdout は空 | 形は同じだが契約化: **exit 4 は JSON を出さない** | exit-codes.md §1 |
| MIG-08 | 納品 | `-o <path>` へ `mv` で直接公開 | `generations/<id>.tmp` → rename → `current` の atomic 差し替え | delivery.md §1, §2 |
| MIG-09 | 納品 | receipt なし | 世代ごとに `receipt.json` (成果物 hash / 版 / `Hfinal` / vendor.lock sha / checks) | delivery.md §6 |
| MIG-10 | 納品 | proposal mode なし | `proposal_mode` では正本を触らず `*.agent-proposal.drawio` を並置し `current` を動かさない | delivery.md §3 |
| MIG-11 | 出力検証 | PNG は `file` の magic + `sips` の画素数 | `sips` 廃止。chunk 全走査 + CRC + IDAT を zlib 展開して IHDR と整合確認 | PLAN §7.2 / environment.md §5 |
| MIG-12 | 任意コマンド | `xmllint` `file` は必須 (欠落は exit 4) | 任意。欠落は該当 check を skipped + warning にし、exit code を変えない | environment.md §5 |

exit 1 と exit 3 の意味は旧新で変わらない。
ただし exit 3 の発火機構は「export 前後の入力 hash 比較」から「`H0` / `Hfinal` の 2 点照合 (delivery.md §2 の S2 と S6)」に置き換わる。
コードとしては invariant、機構としては migration である。

## 4. contract が未確定で、Phase 1b までに決めるべき点

`test_migration.py` の `OPEN_QUESTIONS` と同一内容。推測で新期待値を書かず、未決として残した。

| # | 論点 | 現行の挙動 | 欠けているもの |
|---|---|---|---|
| OPEN-01 | 出力 lock の競合 | 同一出力への二重実行は **exit 2** | `contracts/exit-codes.md` に lock 競合の項が無い。世代ディレクトリ方式では出力単位の lock 自体が不要になる可能性もある |
| OPEN-02 | signal 終了 | HUP/INT/TERM で export の process group を止め **exit 130** | 130 が exit code 表に無い。契約外コードとして明記するか、signal 時の報告を定義する必要がある |
| OPEN-03 | lint 自体の異常終了 | 想定外の linter 終了状態を **exit 4** (usage error) にしている | 内部異常は usage error ではない。「ツール自身が壊れた」に対応する code が無い |
| OPEN-04 | 外部リソース参照 | style / image の URL を警告。`--allow-external` で抑止 | 診断 code の namespace が未予約。warning 診断・optional check・ポリシー下の error のどれにするか未決 |
| OPEN-05 | 非圧縮強制ポリシーの指定場所 | 該当なし (常に警告) | MIG-03 はポリシー ON を前提にしている。`profile.schema.json` は `version` と `proposal_mode` しか許可しておらず、ポリシーを書く場所が無い |

## 5. 移植時に持ち込まない実装詳細

invariant ではあるが、実装手段としては継承しないもの。

- **process group による export の隔離**: 現行は python3 の `fork` + `setsid` + pgid handshake で draw.io を独立 process group に置き、タイムアウトと signal でグループごと終了させる。目的 (子孫プロセスの取り残しを防ぐ) は維持するが、実装は `subprocess` の `start_new_session` で置き換えられる
- **`SECONDS` によるタイムアウト計測**: bash 3.2 で動くが、移植先では python3 側に寄せる
- **同種エラーの 10 件打ち切りと「他 N 件」要約**: 散文出力の都合。診断 JSON では `diagnostics[]` に構造として載るため、打ち切り方針は別途決める (打ち切るなら診断 JSON 側の表現が要る)

## 6. 実行方法

```
python3 tests/characterization/test_invariants.py -v   # 現行 wrapper に対する invariant
python3 tests/characterization/test_migration.py       # 新期待値の一覧 (Phase 1a では全 skip)
```

`LEGACY_WRAPPER=<path>` で検証対象を差し替えられる。
既定値は vault の `bin/drawio-verify-export`。
