# Phase 3a release candidate 記録

- 実施: 2026-08-28
- gate (PLAN §10 Phase 3a): 「受入テスト green + license gate 通過 + CHANGELOG/tag/version 整合」
- 結果: **通過**。CI 7 job green ([run 33168792964](https://github.com/HidakaKoyo/etching-drawio/actions/runs/33168792964))
- public 化・git tag・GitHub release は **未実施** (Phase 3b、Koyo の明示承認待ち)

## 1. 配布 manifest と version

- `.claude-plugin/plugin.json` (0.1.0 / MIT / author / repository) と `.claude-plugin/marketplace.json` (単一 plugin、`source: "./"`) を reflection-cc と同型で作成
- root `LICENSE` (MIT) を作成。vendor が対象外であることを本文末尾に明記
- `scripts/build-release.py` が plugin.json の version を正本とし、`marketplace.json` と `skills/etching/VERSION` を生成する。`--check` を CI の `test` job に入れ、手編集による drift を落とす
- root にあった `VERSION` は廃し、**`skills/etching/VERSION` を唯一の生成物**にした。standalone 配布の閉包内に version が要るため (PLAN §9)。`bin/etch` は 2 layout 両方を見て読む
- receipt / `--json` の `toolVersion` がこの VERSION を読むことを実測で確認した (standalone bundle 実行時に `toolVersion: 0.1.0`)

CHANGELOG は 0.1.0 の 1 節を手書きし、build-release の `--check` が「先頭の節が現行 version であること」まで見る。

## 2. Phase 2 からの持ち越し 3 件

### 2.1 XSD 解決の repo layout 依存

`check_xsd` と receipt の vendor.lock 記録が `<root>/skills/etching/…` を直書きしていた。repo と plugin install では正しく、**skill 単体配布では黙って外れる** (XSD check が optional の skip に落ち、vendorLock が receipt から消える)。失敗より静かなので気付けない。

`lib/etch_paths.py` を追加し、install root 直下の 2 候補 (`<root>/skills/etching` → `<root>`) のうち `references/upstream/` を持つ方を採る形にした。**install root の外は探さない**。`ETCH_ROOT` は従来どおり root の上書き手段。

受入テストの `the bundled XSD resolves` が両 layout でこれを確認する (waiver の理由が「not found」でないこと)。

### 2.2 `ETCH_CMD` 解決順の contract 昇格

SKILL.md にしか書かれておらず、契約として引用できなかった。`contracts/environment.md` §7 に昇格し、§7.1 に同梱ファイル解決 (2.1) の規則を併記した。`DRAWIO_CMD` (§4.1) とは「CLI が draw.io を探す」/「呼び出す側が CLI を探す」の別物である旨を §1 冒頭に明記。skill 側 `references/environment.md` §1.1 が平易版のミラー。

### 2.3 smoke receipt の pin 一致 assert

従来は「`unknown` でなければ通る」だったので、**pin と違う draw.io で走っても green になった**。`EXPECT_DRAWIO_VERSION` (CI が install した version を渡す) を導入し、①起動時に解決した実行ファイルの `--version`、②receipt の `drawio.version` の両方で完全一致を要求する。

併せて receipt を監査者の読み方に寄せた: source hash・全 artifact の hash・vendor.lock の hash を disk から再計算して照合し、`toolVersion` を同梱 VERSION と突き合わせる。

実測: ubuntu `/usr/bin/drawio (31.3.2)` / macOS `/Applications/draw.io.app/…​ (31.3.2)`、いずれも `pinned: 31.3.2` で 6 case 通過。

## 3. 受入テスト (`tests/acceptance/test_distribution.py`)

`contracts/environment.md` §6 の clean install 手順を機械化した。2 layout × 5 case = 10 case。

| layout | 模したもの | CLI |
|---|---|---|
| plugin | marketplace install 後の plugin cache (配布ファイルを丸ごと copy、CLI は skill の隣) | `<install>/bin/etch` |
| standalone | `build-release.py --bundle` が書く skill 単体 bundle (CLI が skill の中) | `<install>/bin/etch` |

case は ①閉包 12 ファイルの存在と CLI の実行権 ②壊れた図の validate が exit 1 と期待 code を出す ③同梱 XSD が解決する ④SKILL.md の一巡 (validate → 作業コピー修復 → 再 validate → deliver → verify) と receipt がその install 自身の VERSION / vendor.lock を指すこと ⑤`DRAWIO_CMD` が実行不能なら exit 5 と `dependency/drawio`。

作業ディレクトリは install の外に置き、CLI へは `ETCH_CMD` 経由でのみ到達する。repo の存在に依存する layout はここで落ちる。draw.io は stub (layout の話であって exporter の話ではない。実 export は smoke)。

CI に `acceptance` job を **ubuntu と macos の両方**で追加した。これで Phase 2 で「未確認」としていた **Linux 上の一巡が回収された** (Phase 2 は macOS のみ)。

## 4. license gate (release gate)

pinned SHA `14b318b1…` の上流 tarball を再取得して実査した。結果は `docs/license-ledger.md` §0.1 を正本とする。

- 閉包 6 ファイルの SHA-256: **6/6 一致** (byte-identical)、ローカル snapshot も lock と一致
- 上流 `NOTICE`: **無し** (Apache-2.0 §4(d) は発生しない)、per-file license ヘッダー: **6 件とも無し**
- `drawio-mcp` の SPDX: Apache-2.0。加えて Phase 0a ledger §2.1 が「推奨」に留めていた `jgraph/drawio` 本体を一次確認し、**Apache-2.0** と確定した (`style-reference.md` の二次的出自に追加義務なし、が推定から確認済みに変わった)
- **出所不明: 0 件。license gate 通過**

`THIRD_PARTY_NOTICES.md` は再確認日と結果を反映して更新した (root LICENSE が Phase 3a で入った旨も現状に合わせた)。

## 5. 文書と CI

- `README.md` 全面 (英語): what / why / requirements / install (2 経路) / usage / safety boundary / scope statement / upstream / versioning / development。reflection-cc の型
- `docs/security.md` (英語): 脅威モデルを 3 つ (敵対的入力・vendor supply chain・成果物からの流出) に分け、**防止と検知の線** (非協調 writer は検知どまり) と scope 外を明記
- `CHANGELOG.md`: 0.1.0 (unreleased)
- CI: `actions/checkout` v4 → **v7**、`actions/setup-python` v5 → **v7** (指示は checkout v5 だったが、現行 major が v7 で「最新 major に」という指示の意図を優先した。green で互換性を確認済み)
- `.github/workflows/upstream.yml`: 週次 (月 04:17 UTC) + 手動。`propose-upstream-update.py --ref main --check-docs` を read-only で走らせ、exit 1 (上流が動いた) と exit 2 (検査自体が失敗) の**どちらでも issue を作る**。candidate SHA ごとに 1 件だけ立てる (週次で重複を作ると無視されるようになるため)。手動 dispatch で実走を確認済み ([run 33168885379](https://github.com/HidakaKoyo/etching-drawio/actions/runs/33168885379)、上流は pin と同一で issue 無し)

## 6. gate の判定

| 条件 | 結果 |
|---|---|
| 受入テスト green (両配布方式 × ubuntu/macos) | 通過 (10 case × 2 OS) |
| license gate 通過 (出所不明 0) | 通過 |
| CHANGELOG / version 整合 | 通過 (`build-release.py --check` が CI で強制) |
| CI 全 job green | 通過 (7 job) |
| tag との 1:1 対応 | **未実施**。tag は Phase 3b で打つ (規則は README「Versioning」に記載済み) |

## 7. 残件 (Phase 3b 以降)

- public 化 / `v0.1.0` tag / GitHub release — Koyo の明示承認待ち
- `schemaVersion` を据え置いたまま schema を変えた場合に release CI で拒否する検査 (PLAN §9) は未実装。schema が動くのは v1 では稀で、動かす回が来たときに入れる方が仕様が定まる
- Phase 4 の vault one-shot migration は未着手
