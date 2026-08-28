# Phase 0a 上流裏取りレポート

- 実施: 2026-08-28
- 対象上流: `jgraph/drawio-mcp` (https://github.com/jgraph/drawio-mcp)
- 対象 PLAN: `docs/PLAN.md` v8 の §4 (上流追従) / §5 (ライセンス) / §10 Phase 0a gate
- 調査手段: GitHub REST API (repo metadata / commit / tree) と `codeload.github.com` の tarball 取得による実ファイル読み取り。推測による補完はしていない。

## 1. pin 対象の確定

| 項目 | 値 |
|---|---|
| default branch | `main` |
| 調査時点の `main` HEAD commit SHA | `14b318b19cc37b159f841227b9d11fbd18ce18ea` |
| 同 commit date | 2026-08-03T19:51:43Z |
| 同 commit message (先頭行) | `feat(app-server): add MCP Community Registry manifest and publish runbook` |
| repo 最終 push | 2026-08-03T20:10:27Z |
| repo license (GitHub 判定) | Apache-2.0 |
| tree entry 総数 (recursive, truncated=false) | 113 |
| mode 120000 (symlink) / 160000 (submodule) の entry | なし |

以降、本レポートで「上流」と書いたものはすべてこの SHA での実体を指す。

## 2. PLAN 前提の検証

### 2.1 「XML 作法の正本が `shared/xml-reference.md` にある」— 事実

上流 `CLAUDE.md` の実読で裏が取れた。該当は 2 か所。

- L10: `` **`shared/`** — Shared XML generation reference (`xml-reference.md`), the single source of truth for all LLM prompts. ``
- L125 以降に `## Shared References (Single Source of Truth)` という節があり、`shared/xml-reference.md` を「draw.io XML generation reference: styles, edge routing, containers, layers, tags, metadata, dark mode, well-formedness rules」と定義している。

したがって PLAN §3 の「上流 = XML 作法の原典」および §4.1 が閉包に `shared/xml-reference.md` を含める前提は、上流の現在の main で成立している。

ただし同節は正本を **2 ファイル**と書いている点が PLAN と食い違う。上流は `shared/xml-reference.md` と `shared/mermaid-reference.md` の 2 本を "canonical reference files" として並列に扱っており、PLAN §4.1 の閉包初期値は後者を落としている。§3 の allowlist で回収した。

### 2.2 `plugins/claude-code/skills/drawio/` の現在の構成 — PLAN の想定より狭い

この SHA での当該ディレクトリの中身は **`SKILL.md` 1 ファイルのみ**である。サブディレクトリも `references/` も存在しない。

```
100644 blob 54ead5150f79  20431  plugins/claude-code/skills/drawio/SKILL.md
```

PLAN §4.1 は閉包初期値を「`plugins/claude-code/skills/drawio/` 一式 + `shared/xml-reference.md`」と書いているが、「一式」の実体は 1 ファイルである。skill ディレクトリが自己完結していないのは意図的な設計で、SKILL.md は参照を **絶対 URL で外部 fetch する** 形になっている (次項)。

同一の `SKILL.md` blob (`54ead5150f79`) が `plugins/codex/drawio/skills/drawio/` と `plugins/copilot/skills/drawio/` にも配置されている。上流 `CLAUDE.md` L16-17 が「byte-identical」と明言しており、tree の blob SHA 一致でも確認した。etching が輸入するのは Claude Code 版のみでよい。

### 2.3 SKILL.md から shared への参照は相対 path ではなく `main` 追従の絶対 URL

SKILL.md 内の上流参照は次の 2 本だけで、いずれも commit ではなく **`main` を指す raw URL** である。

- L105 (Mermaid syntax reference 節): `https://raw.githubusercontent.com/jgraph/drawio-mcp/main/shared/mermaid-reference.md`
- L368 (XML reference 節): `https://raw.githubusercontent.com/jgraph/drawio-mcp/main/shared/xml-reference.md`

含意が 2 つある。

1. **上流の skill は実行時ネットワーク fetch に依存し、かつ内容が pin されていない。** `main` が動けば同じ SKILL.md でも読む内容が変わる。PLAN §4.2 が vendor snapshot + `vendor.lock` で pin する方針は、この性質に対する対処として妥当である。
2. **依存閉包はファイルシステム上の相対参照からは導けない。** URL 文字列を上流 path に写像する規則が必要になる。§3 でその規則を明示した。

なお SKILL.md には `shape-search.js` / `icon-search.js` への参照はない。これらは MCP サーバー側の shape 検索機能用で、skill の閉包には入らない。

### 2.4 閉包の 2 段目 — `xml-reference.md` からさらに 2 ファイルへ

`shared/xml-reference.md` L476-478 が、さらに上流の 2 ファイルを絶対 URL で参照している。

```
Complete style reference (...): https://github.com/jgraph/drawio-mcp/blob/main/shared/style-reference.md

XML Schema (XSD): https://github.com/jgraph/drawio-mcp/blob/main/shared/mxfile.xsd
```

また `shared/style-reference.md` L3 が `mxfile.xsd` を companion として参照する (既出につき閉包は増えない)。`shared/mermaid-reference.md` と `shared/mxfile.xsd` からの repo 内向き outbound 参照は 0 件で、ここで閉包が閉じる。

この 2 ファイルは PLAN §5 が「ローカル既存 vendoring が追加同梱した、出所要確認」として挙げていたものだが、**両方とも上流 `shared/` に実在し、閉包規則からも正当に導出される**。§4 のライセンス台帳と `docs/license-ledger.md` で確定した。

### 2.5 上流 LICENSE / NOTICE

- root `LICENSE` は Apache License 2.0 全文 + 末尾に `Copyright 2025 JGraph Ltd` の appendix。
- **`NOTICE` ファイルは存在しない**。PLAN §5 の「NOTICE (存在すれば) を保持」は、この SHA では該当なしとして扱う。
- 閉包内の各ファイルに個別の copyright / license ヘッダーは無い。root LICENSE が repo 全体に及ぶ形。
- `plugins/claude-code/.claude-plugin/plugin.json` は `"license": "Apache-2.0"`、`"version": "1.1.0"`、`"author": {"name": "draw.io"}` を宣言しており、root LICENSE と矛盾しない。

## 3. PLAN との差分まとめ

| # | PLAN の記述 | 実測 | 対応 |
|---|---|---|---|
| 1 | §4.1 閉包初期値 = skill 一式 + `xml-reference.md` | 実際は 5 ファイル必要 (`mermaid-reference.md` / `style-reference.md` / `mxfile.xsd` が不足) | `docs/closure-allowlist.md` で確定。PLAN §4.1 の初期値記述は要更新 |
| 2 | §4.1「閉包は snapshot 内ファイルが参照する上流 path を追加する規則で確定」 | 参照は相対 path ではなく絶対 URL。素直な path 解決では閉包が空になる | URL→path 写像規則を明文化 (closure-allowlist §2) |
| 3 | §3「`plugins/claude-code/skills/drawio/` 一式」 | 中身は `SKILL.md` 1 ファイル | 表現の実態合わせ。実害なし |
| 4 | §5「NOTICE (存在すれば)」 | この SHA には NOTICE なし | 該当なし。`propose-upstream-update.sh` は将来 NOTICE が生えた場合を検知できるようにする |
| 5 | §5「`mxfile.xsd` と `style-reference.md` の出所不明リスク」 | 両方とも上流 `shared/` の実在ファイルで、内容も一致 | 出所不明 0 件。release gate は license 面ではクリア |

上流裏取りの結論として、**PLAN の中核前提 (xml-reference.md が正本であること、上流が Apache-2.0 であること) はいずれも成立**しており、修正が要るのは閉包の粒度と参照解決規則の記述である。設計そのものの見直しは不要と判断する。

## 4. 未確認事項

- 上流 vault ローカル vendoring が **どの commit から取得されたか**は上流側にも vault 側にも記録がない。内容は `14b318b` と一致する (§ライセンス台帳) が、`14b318b` から取得したという事実は確認できていない。閉包各ファイルの最終変更 commit は 2026-02〜2026-07 に分散しており、`14b318b` 以前の複数 commit でも同一内容だった可能性がある。ライセンス判定には影響しない。
- 上流の将来的な破壊的変更 (skill ディレクトリの再編、`shared/` の分割) の予告は、`CLAUDE.md` / `README.md` / 直近 commit message の範囲では見当たらなかった。ただし issue / PR / discussion は本調査の対象外であり、「予告がない」ことの確認は skill と README の読解範囲に限る。
