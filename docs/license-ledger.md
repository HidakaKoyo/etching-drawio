# ライセンス台帳 (Phase 0a)

- 実施: 2026-08-28
- 対象: `docs/closure-allowlist.md` で確定した閉包 6 ファイル、および Koyo-HQ vault の既存 vendoring `.agents/skills/drawio/` の全 6 ファイル
- 判定基準: PLAN §5。**出所不明が 1 件でもあれば public 化 (Phase 3b) を禁止する release gate**。推測による「jgraph 由来なら Apache」判定はしない
- 実査方法: 上流 tarball を pinned SHA `14b318b19cc37b159f841227b9d11fbd18ce18ea` で取得し、実ファイルの SHA-256 と本文を vault 側の実ファイルと突き合わせた。vault は read-only で参照した

## 0. 結論

| 項目 | 件数 |
|---|---|
| 台帳エントリ総数 (上流閉包) | 6 |
| 出所確定 | 6 |
| **出所不明** | **0** |
| vault 既存 vendoring のファイル数 | 6 |
| うち上流に対応が確定したもの | 6 |
| うち出所不明 | 0 |

**license gate は通過可能な状態にある** (Phase 3b の public 化を license 面で阻む要因はない)。PLAN §5 が名指しでリスク視していた `mxfile.xsd` と `style-reference.md` は、いずれも上流 `shared/` の実在ファイルであり、内容も一致した。

ただし gate の最終判定は Phase 3a で `THIRD_PARTY_NOTICES.md` を作成し、その時点の pinned SHA に対して本台帳を再実行してから行う。本台帳は Phase 0a 時点のスナップショットである。

## 1. 上流ライセンスの実体

- **License**: Apache License 2.0
- **Copyright**: `Copyright 2025 JGraph Ltd` (root `LICENSE` 末尾 appendix)
- **NOTICE ファイル**: **存在しない** (pinned SHA の tree を全走査して確認)。Apache-2.0 §4(d) の NOTICE 再頒布義務は発生しない
- **per-file ヘッダー**: 閉包 6 ファイルのいずれにも個別の copyright / license ヘッダーは無い。root `LICENSE` が repo 全体を覆う形
- **plugin manifest の宣言**: `plugins/claude-code/.claude-plugin/plugin.json` が `"license": "Apache-2.0"`, `"author": {"name": "draw.io"}`, `"version": "1.1.0"` を宣言。root LICENSE と矛盾しない

## 2. 上流閉包ファイルの台帳

すべて source = `https://github.com/jgraph/drawio-mcp` @ `14b318b19cc37b159f841227b9d11fbd18ce18ea`、license = Apache-2.0、copyright = JGraph Ltd (2025)。改変は **全件なし** (snapshot は無改変で置く方針。PLAN §4.2)。

| # | path | SHA-256 | 当該 path の最終変更 commit | 出所判定 |
|---|---|---|---|---|
| 1 | `plugins/claude-code/skills/drawio/SKILL.md` | `4db0d942…bba5f5` | `908e8bdf2d72` (2026-07-08) | 確定 |
| 2 | `shared/mermaid-reference.md` | `977a11dd…9cbbf0` | `aa00015ec81f` (2026-06-18) | 確定 |
| 3 | `shared/xml-reference.md` | `3f7409f9…13d8aa` | `be57d3d4cb73` (2026-07-19) | 確定 |
| 4 | `shared/style-reference.md` | `094df969…a6366d` | `079768d7a0c8` (2026-04-03) | 確定 |
| 5 | `shared/mxfile.xsd` | `905db85d…06639a` | `079768d7a0c8` (2026-04-03) | 確定 |
| 6 | `LICENSE` | `006e61a1…eb7232` | `7c26aa9f6957` (2026-02-24) | 確定 |

SHA-256 の完全値は `docs/closure-allowlist.md` の表を正本とする (上表は可読性のため短縮しており、照合には使わない)。

### 2.1 `style-reference.md` の二次的な出自について

`shared/style-reference.md` L4-5 は本文中で次を明言している。

> All data was extracted from the draw.io source code.

つまりこのファイルは draw.io 本体 (`jgraph/drawio`) からの抽出物である。ただし `jgraph/drawio` も Apache-2.0 かつ著作権者は同じ JGraph Ltd であり、`drawio-mcp` の root LICENSE の下で頒布されている以上、etching 側の再頒布条件は Apache-2.0 のままで足りる。**追加のライセンス義務は発生しないと判断する** が、`THIRD_PARTY_NOTICES.md` にはこの derivation を注記する。

なお `jgraph/drawio` 本体のライセンスが Apache-2.0 であることは本調査では直接確認していない (調査対象を `drawio-mcp` に限ったため)。この判断は `drawio-mcp` の root LICENSE が当該ファイルを覆っているという事実だけで成立するので、上流本体の確認は必須ではない。Phase 3a で notices を書く際に念のため一次確認することを推奨する。

## 3. vault 既存 vendoring の突き合わせ

対象: `/Users/kh/Library/Mobile Documents/iCloud~md~obsidian/Documents/Koyo-HQ/.agents/skills/drawio/` (read-only 参照)。symlink・追加ファイルは無く、実ファイル 6 件。

| vault 内 path | SHA-256 | 対応する上流 path | 上流 @14b318b との一致 |
|---|---|---|---|
| `LICENSE` | `006e61a1b8c97620d75ceacc283de7a363d78da7da9a5b92203324c40feb7232` | `LICENSE` | **byte-identical** |
| `references/mxfile.xsd` | `905db85d4e8ebec0e91518cdd62982e0afb3f09ebdcaf9e6b1952957a606639a` | `shared/mxfile.xsd` | **byte-identical** |
| `references/mermaid-reference.md` | `977a11dd6c0e37922eb3615f50f41c0b8f2eeb732dc6905b1b8546ca829cbbf0` | `shared/mermaid-reference.md` | **byte-identical** |
| `SKILL.md` | `8a622c2258e50529b366a4cacafba2e2ed9dc9177390ec61d1c797e9beb4a004` | `plugins/claude-code/skills/drawio/SKILL.md` | 差分あり (下記 3.1) |
| `references/xml-reference.md` | `d89e29ca0cf0c4326da34a3dae801805645b4fb2d2c4661499fc2ceedf41dc76` | `shared/xml-reference.md` | 差分あり (下記 3.1) |
| `references/style-reference.md` | `af1d02e937d2dcf45fc4846be6111f0063a19b75565a2b1ff618cda1cc69b77c` | `shared/style-reference.md` | 差分あり (下記 3.1) |

### 3.1 差分の内訳 (全件を実 diff で確認)

差分は 3 ファイル・合計 13 行で、すべて **URL の bundled path への読み替え**と**provenance 注記の追記**である。技術内容の改変・追記・削除はない。

- `SKILL.md` (13 行中 9 行がここ)
  - L105: raw URL → `references/mermaid-reference.md (bundled locally in this skill)`
  - L368: raw URL → `references/xml-reference.md (bundled locally in this skill)`
  - 末尾: `## Provenance (local vendoring note)` 節 (7 行) を追記。上流 repo・対象 path・plugin v1.1.0・Apache-2.0・改変内容・更新手順を自己申告している
- `references/xml-reference.md` (2 か所)
  - L476: blob URL → `style-reference.md (bundled in this directory)`
  - L478: blob URL → `mxfile.xsd (bundled in this directory)`
- `references/style-reference.md` (1 か所)
  - L3: blob URL → `` `mxfile.xsd` (bundled in this directory) ``

### 3.2 判定

vault 既存 vendoring の 6 ファイルはいずれも上流 `drawio-mcp` 由来で、**出所不明は 0 件**。`mxfile.xsd` と `style-reference.md` は「vendoring が独自に追加した由来不明ファイル」ではなく、`xml-reference.md` からの正当な閉包メンバーだった (`docs/closure-allowlist.md` §2 の不動点で round 2 に導出される)。

ライセンス的には vault vendoring も Apache-2.0 の下にあり、`LICENSE` が同ディレクトリに同梱されているため §4(a) の要件も満たしている。改変を加えたファイル (SKILL.md / xml-reference.md / style-reference.md) について Apache-2.0 §4(b) は「改変ファイルに変更した旨の顕著な告知を付す」ことを求めるが、SKILL.md の Provenance 節が改変内容を明示しているため実質的に満たされている。**etching では PLAN §4.2 の方針どおり snapshot を無改変で置くため、§4(b) の論点自体が消える。**

### 3.3 未確認事項

vault vendoring が **どの上流 commit から取得されたか**は、vault 側にも上流側にも記録がない。確認できたのは「内容が `14b318b` の実体と一致する (改変分を除いて)」という事実までで、`14b318b` から取得したという事実ではない。閉包各ファイルの最終変更は 2026-02〜2026-07 に分散しているため、より古い複数の commit でも同一内容だった可能性がある。ライセンス判定と Phase 4 の migration (§8 の「既知の旧 hash 一覧との照合」) には、取得元 commit ではなく実 hash を使うので実害はない。

## 4. etching 側の自作部分

| 対象 | license |
|---|---|
| root `LICENSE` (etching 自作部分) | MIT。vendor が対象外であることを本文に明記する (PLAN §5) |
| `references/upstream/` 配下 | Apache-2.0 (本台帳 §2) |
| `THIRD_PARTY_NOTICES.md` | Phase 3a で作成。component / source URL / commit SHA / 対象 path / 改変一覧 (「改変なし」) を記載 |

## 5. 再実行の手順

pinned SHA を更新したとき、および Phase 3a の release gate 判定時に本台帳を再作成する。手順は `scripts/propose-upstream-update.sh` の閉包再確定 (closure-allowlist §2) の後に、閉包各ファイルの (a) SHA-256、(b) per-file license ヘッダーの有無、(c) NOTICE の有無、(d) root LICENSE の SPDX 判定、を再取得して本文書の §1 と §2 を差し替える。1 件でも出所不明が出たら Phase 3b を止める。
