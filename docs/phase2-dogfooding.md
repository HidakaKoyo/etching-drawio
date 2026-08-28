# Phase 2 dogfooding 記録

- 実施: 2026-08-28
- gate (PLAN §10 Phase 2): 「クリーン環境で skill を読んだエージェントが修復ループを一巡できる」
- 結果: **通過**。修復は 2 fix set で収束し、納品まで到達した。SKILL.md の欠陥を 3 件見つけて直した

## 1. やりかた

`skills/etching/SKILL.md` の記述だけを頼りに、壊れた `.drawio` を validate → 修復 → 再 validate → deliver まで一巡した。作業は repo の外のクリーンな一時ディレクトリで行い、CLI の実装 (`lib/`) を読まずに SKILL.md と `references/` だけで進められるかを見た。

fixture は 4 種類の指摘が出る `.drawio` を用意した。

| 診断 code | 仕込み |
|---|---|
| `xml/duplicate-cell-id` | 2 つの vertex が同じ `node-a` を持つ |
| `xml/invalid-geometry` | vertex の `width="0"` |
| `xml/missing-reference` | edge の `target` が存在しない `node-deliver` を指す |
| `input/compressed-attribute` (warning) | `mxfile` に `compressed="false"` が無い |

## 2. 修復ループの経過

fingerprint は SKILL.md の定義 (作業コピーの SHA-256 + 正規化した `(code, subject)` の multiset) で毎周記録した。

| 周 | fingerprint (先頭 16) | 診断数 | 当てた fix set |
|---|---|---|---|
| 0 (初回検証) | `3c9ffcabe48ef796` | 4 | — (exit 1) |
| 1 | `7144466e1a94c7de` | 2 | 重複 ID の一意化 + `width` を正の値に |
| 2 | `f5bb0a6e306f04b9` | 0 | 欠けていた `node-deliver` の追加 + `compressed="false"` の付与 (exit 0) |

fingerprint は毎周異なり、診断数は 4 → 2 → 0 と単調に減った。循環検知にも 5 回打ち切りにも当たっていない。

2 周目の「欠けた ID を足す」は診断だけからは決まらない判断だった (edge が指す名前から Deliver 段の図形が欠けていると読んだ)。この扱いが SKILL.md で曖昧だったので、欠陥 4 として直した。

## 3. 納品

```
etch deliver --format svg --output-root <dir> --content <作業コピー> <正本>
```

- exit 0 / `status: passed` / required check の失敗なし
- `generations/20260828T113004Z-.../` と `current` symlink が期待どおり生成
- receipt に draw.io Desktop 31.3.2、正本の hash、vendor.lock、checks が入っていた
- `etch verify --output-root <dir>` が exit 0
- **proposal mode** も別途確認した。cwd に `.etching/profile.json` (`proposal_mode: true`) を置いて実行すると、正本の hash は変わらず、`current` も動かず、`pipeline.agent-proposal.drawio` だけが並置された

## 4. 見つけた欠陥と直したところ

### 欠陥 1 — 出力ルートを先に作れと書いていなかった

`--output-root` に存在しないディレクトリを渡し、exit 4 で止まった。exit 4 は診断 JSON を出さないので、JSON を読む手順に乗ったままだと何が起きたか分からない。SKILL.md にも `references/delivery-contract.md` にも「CLI はディレクトリを作らない」と書いていなかった。

→ SKILL.md §4 と delivery-contract §2 に、事前に作ること・無ければ exit 4 で JSON が出ないことを明記。

### 欠陥 2 — 作業コピーの後始末が未定義

納品が通ったあと、正本と同じディレクトリに作業コピー (`*.work.drawio`) が残った。中身は正本と同一で、次に開く人にはどちらが正本か分からない。「正本は常に `.drawio` 一つ」という二層の原則と衝突する。

→ SKILL.md §4 と authoring-contract §1 に「納品が通ったら消す。失敗して止まったときだけ証拠として残す」を追加。

### 欠陥 3 — profile が cwd 依存であることを警告していなかった (最も重い)

`.etching/profile.json` で `proposal_mode: true` を置いた project の図を、**別の cwd から絶対パスで**指して `etch deliver` を呼ぶと、profile は解決されず既定 (`proposal_mode: false`) で走り、**正本がそのまま置換された**。実測で確認している (exit 0、正本の hash が `c18441ca` → `5cd20d26` に変化)。

contract どおりの挙動 (`contracts/profile.md` §1 は「親を遡らない」と定めている) ではあるが、エージェントは入力を絶対パスで渡しがちなので、SKILL.md 側で塞ぐべき穴だった。警告も exit code も出ないため、事故は静かに起きる。

→ SKILL.md §0 と environment.md §4 に、`.etching/` のあるディレクトリを cwd にするか `--profile` を明示すること、絶対パスで入力を渡せていることは profile が見えている根拠にならないことを明記。

### 欠陥 4 — 判断を伴う直しの数えかたが曖昧

authoring-contract は「診断だけからは決まらない直しは修復ではなく起案のやり直し」と書いていたが、それが 5 回の打ち切りに数えられるのかを書いていなかった。数えないと読むと、判断を伴う直しを無限に繰り返せる抜け道になる。

→ authoring-contract §2 に「判断を伴う直しも 1 周として数える。根拠を述べる」を明記。

## 5. 検証が通っても図が正しいとは限らない (実例)

修復ループが exit 0 で終わったあと、PNG を書き出して目視したところ、Author → Deliver の辺が Validate の箱を貫いていた。edge の `target` は実在する ID を指しているので検証は通る。意図 (Author → Validate → Deliver) と食い違っていることは、レンダリング結果を見るまで分からなかった。

起案に戻って辺を張り直し、再度書き出して目視で確認した。SKILL.md §4 の目視要求はこの型の欠陥のためにあるので、その旨を本文に追記した。

## 6. gate の判定

| 条件 | 結果 |
|---|---|
| SKILL.md の記述だけで validate → 修復 → 再 validate → deliver を一巡できる | 通過 (欠陥 3 件を直したあとの記述で成立) |
| 修復ループが停止条件に触れず収束する | 通過 (2 fix set、fingerprint は毎周更新) |
| 納品物と receipt が `contracts/delivery.md` を満たす | 通過 (`etch verify` exit 0) |
| proposal mode が正本を触らない | 通過 (実測) |

**未確認**: Linux 上での一巡は試していない (macOS + draw.io Desktop 31.3.2 のみ)。skill 単体配布の閉包で `references/upstream/` と `bin/etch` が解決できるかも Phase 3a の受入テストの範囲で、ここでは repo layout での実行しか確かめていない。

→ **いずれも Phase 3a で回収済み** (2026-08-28)。`tests/acceptance/test_distribution.py` が plugin / standalone の 2 layout を Ubuntu・macOS 両方で一巡する。単体配布での `references/upstream/` 解決は実際に壊れており (repo layout 直書き)、`lib/etch_paths.py` で直した。詳細は `docs/phase3a-release-candidate.md`。
