# 依存閉包 allowlist (Phase 0a 確定)

- 実施: 2026-08-28
- 上流: `jgraph/drawio-mcp`
- pinned commit: `14b318b19cc37b159f841227b9d11fbd18ce18ea`
- 根拠の実測は `docs/phase0a-upstream-report.md`
- 本文書は PLAN §4.1 の「対象 path の明示 allowlist (依存閉包)」の確定値であり、`vendor.lock` を生成するときの入力になる。

## 1. 確定 allowlist (6 path)

| # | 上流 path | git mode | blob SHA (git) | size | SHA-256 | 閉包に入る根拠 |
|---|---|---|---|---|---|---|
| 1 | `plugins/claude-code/skills/drawio/SKILL.md` | 100644 | `54ead5150f790625fcccde2e93af0fe114c5aa14` | 20431 | `4db0d9428e855b602b5afd161929dc6e35cb28678d830cfafd939f0a71bba5f5` | 閉包の root。etching が輸入する skill 本体 |
| 2 | `shared/mermaid-reference.md` | 100644 | `25bb420f2f70a1f6f1cf59c90d958af1c53e3117` | 12806 | `977a11dd6c0e37922eb3615f50f41c0b8f2eeb732dc6905b1b8546ca829cbbf0` | (1) L105 が raw URL で参照 |
| 3 | `shared/xml-reference.md` | 100644 | `d2940943111c0b5b1973e430fe6a39cff3f37fa1` | 33402 | `3f7409f925ba35115ef7b644279c44b34f9fbf5b8ab539844368855db113d8aa` | (1) L368 が raw URL で参照 |
| 4 | `shared/style-reference.md` | 100644 | `d90ab70ff019c0909bda671f5fbd99850b4367c9` | 37100 | `094df96981f85adb3124f40fd5ef02dc02eade1615ed6ffe4631f0e123a6366d` | (3) L476 が blob URL で参照 |
| 5 | `shared/mxfile.xsd` | 100644 | `53277111bc48ad6cccd259ad95a244eb9701e261` | 29499 | `905db85d4e8ebec0e91518cdd62982e0afb3f09ebdcaf9e6b1952957a606639a` | (3) L478 と (4) L3 が blob URL で参照 |
| 6 | `LICENSE` | 100644 | `f44b900b6208bbff3463cea88049e47d4bdcfd7e` | 10762 | `006e61a1b8c97620d75ceacc283de7a363d78da7da9a5b92203324c40feb7232` | 参照解析では出ないが、Apache-2.0 §4(a) の再頒布義務により同梱必須 (PLAN §5) |

参考の tree OID (`vendor.lock` の「対象ディレクトリの tree OID」欄に使う):

- `plugins/claude-code/skills/drawio` = `f05186e51e58bc9a868c6b2c5114241f7fbc928a`
- `shared` = `57aaeb2c9402f7a134f5133b1014bcc1c528df0b`

`shared` の tree OID は閉包外ファイル (`icon-search.js` / `shape-search.js` / `package.json`) を含むため、`shared` 直下の任意の変更で動く。tree OID は「閉包の変化の早期検知シグナル」として使い、合否判定は path ごとの SHA-256 で行う。

## 2. 閉包の導出規則

PLAN §4.1 は「snapshot 内ファイルが参照する上流 path を追加する」と定めるが、上流の参照は相対 path ではなく **絶対 URL** である。素直に相対 path 解決だけを実装すると閉包が root 1 ファイルで閉じてしまい、規則が空回りする。そこで実装上の規則を次のように具体化する。

`scripts/propose-upstream-update.py` の閉包再確定ステップは、閉包内の各ファイル本文から次の 2 形の URL を抽出し、捕捉した `<path>` を閉包に追加する。追加がなくなるまで反復する (不動点)。

```
https://raw.githubusercontent.com/jgraph/drawio-mcp/<ref>/<path>
https://github.com/jgraph/drawio-mcp/blob/<ref>/<path>
```

規則の細目:

- `<ref>` は上流では `main` 固定だが、抽出時は ref を無視して `<path>` のみを取る。取得は常に pinned SHA から行う。
- 上流 repo 以外を指す URL (draw.io 本体、外部ドキュメント、CDN) は閉包に入れない。ホストと repo 名の完全一致で判定する。
- `LICENSE` は参照解析の産物ではなく、法的要件として無条件に閉包へ含める固定エントリとする。
- 抽出した path が pinned SHA の tree に存在しない場合は **警告ではなく失敗**とする (PLAN §4.2 の「path 消失は issue / 通知」に対応)。

### 不動点の到達過程 (この SHA での実測)

```
round 0: {SKILL.md}
round 1: + shared/mermaid-reference.md, shared/xml-reference.md      (SKILL.md より)
round 2: + shared/style-reference.md, shared/mxfile.xsd              (xml-reference.md より)
round 3: 追加なし (mermaid-reference.md / mxfile.xsd は上流内向き参照 0、
                   style-reference.md の mxfile.xsd 参照は既出)
固定エントリ: + LICENSE
```

## 3. 意図的に閉包へ入れないもの

| 上流 path | 除外理由 |
|---|---|
| `shared/shape-search.js` / `shared/icon-search.js` / `shared/package.json` | MCP サーバーの shape 検索機能用。閉包内のどのファイルからも参照されない (SKILL.md に shape-search の記述なし) |
| `plugins/codex/drawio/skills/drawio/SKILL.md` / `plugins/copilot/skills/drawio/SKILL.md` | Claude Code 版と byte-identical (同一 blob SHA `54ead5150f79`)。同梱しても情報量が増えない |
| `plugins/claude-code/.claude-plugin/plugin.json` | 上流 plugin のホスト manifest。etching は自前の `.claude-plugin/plugin.json` を持つ (PLAN §9) ため取り込むと version の正本が二重化する。上流版数の記録は `THIRD_PARTY_NOTICES.md` に文字列として残す (この SHA では `1.1.0`) |
| `plugins/claude-code/README.md` / `DEVELOPING.md` / root `README.md` / `CLAUDE.md` | 上流 repo の運用文書。skill の実行閉包に含まれない |
| `mcp-app-server/` / `mcp-tool-server/` / `shape-search/` / `project-instructions/` | MCP サーバー実装と別配布形態。PLAN §11 でスコープ外 |
| `NOTICE` | この SHA には存在しない。将来生えたら閉包の固定エントリに追加する (§2 の失敗規則とは別に、存在検知として `propose-upstream-update.py` でチェックする) |

## 4. Phase 0c への申し送り

- vendor snapshot の配置先は PLAN §3 の通り `skills/etching/references/upstream/`。上記 6 path を **無改変**で置く。
- URL の読み替え (raw URL → bundled path) は snapshot 側では行わず、SKILL.md 側の「参照解決規則」に置く (PLAN §4.2)。vault 既存 vendoring は snapshot を直接書き換える方式だったので、ここは意図的な設計変更である。読み替えが必要な URL は §2 で抽出したものと同じ 5 本 (SKILL.md 内 2 本、xml-reference.md 内 2 本、style-reference.md 内 1 本)。
- `vendor.lock` の取得日時は pinned SHA が変わったときだけ更新する (PLAN §4.1)。
