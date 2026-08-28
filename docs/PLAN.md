# etching-drawio 設計・実装プラン (draft v9)

- 作成: 2026-08-28 / 司令塔セッション
- 状態: Phase 0a (上流裏取り・ライセンス実査) の実測結果を反映した改訂版 (v9)。v8 は Codex 敵対的レビュー 7 巡目までを反映したもの
- v9 の変更点: §4.1 の依存閉包初期値を実測 6 path に修正、閉包導出規則に URL→path 写像を明記、§5 の `mxfile.xsd` / `style-reference.md` への疑義を解消。いずれも `docs/phase0a-upstream-report.md` / `docs/closure-allowlist.md` / `docs/license-ledger.md` が根拠
- 確定後の置き場所: `93_operation-docs/plan/2026-08-28_etching-drawio.md` (japanese-tech-writing 適用のうえ移設)

## 1. 目的

図生成 skill 群を `etching-drawio` として再編する。archify (tt-a1i/archify) の思想 — 機械可読診断による Generate→Validate→Repair ループ、納品規律、contract 文書の分離 — を drawio 基盤に輸入し、GitHub 公開 OSS として他環境でも動く形に整備する。

## 2. 命名と呼び出し (v2 major-7 反映)

- OSS repo / plugin 名: `etching-drawio`。
- plugin 内の skill ディレクトリは `skills/etching/SKILL.md` とし、Claude Code 公式仕様 (directory 名 = skill command、plugin skill は `plugin-name:skill-name`) に従って公開呼び出し名は **`/etching-drawio:etching`** となる。
- Koyo-HQ vault では project skill として `.agents/skills/etching/` に配置するため bare `/etching` で呼べる (vault は marketplace 経由ではなく OSS→vault 一方向同期で導入する。§8)。
- 自動発火は frontmatter description で担保する (「図・フローチャート・アーキテクチャ図等の作成・編集・書き出し依頼で必ず使う」)。

## 3. レイヤ構成

| 層 | 役割 | 扱い |
|---|---|---|
| 上流 (jgraph/drawio-mcp) | XML 作法の原典 | pristine snapshot。**無改変** |
| `etching` skill | **唯一の公開 entry point**。起案→validate→修復→deliver の orchestrator | 新設 |
| `etch` CLI (名称仮) | 決定論的な検証・書き出し・納品。既存 bash wrapper (約600行) を移植・汎用化 | 移植 |
| host profile | 環境固有規約 (Koyo-HQ の置き場所・Obsidian 埋め込み等) | 非同梱。§7.3 の解決規則で読む |

- 既存 `drawio-authoring` overlay は etching に吸収して廃止する。
- 既存 `.agents/skills/drawio/` (改変込み vendoring) は **Phase 4 で削除**する。snapshot は `etching` skill 内の `references/upstream/` にのみ置く。**移行後の skill scan で図生成系の公開 skill が etching 一つだけであることを Phase 4 の受入条件とする** (v2 blocker-1 反映)。
- 上流 skill が持つ「export 後に中間 .drawio を削除する」挙動は etching の contract (正本/派生二層) で明示的に override する。

## 4. 上流追従 (v2 major-1, minor-1 反映)

### 4.1 vendor.lock

機械可読な lockfile を **skill ディレクトリ内 (`skills/etching/vendor.lock`) に置く** (v4 minor-2 反映: standalone 配布の閉包内に含め、実行時 receipt が常に参照できるようにする)。フィールド:

- upstream repo URL / **pinned commit SHA** / 対象 path の明示 allowlist (依存閉包)
- 各ファイルの SHA-256 / Git mode / symlink target / path / 対象ディレクトリの tree OID
- 取得日時 (**pinned SHA が変わったときのみ更新**。定期 verify では触らない)

依存閉包の初期値 (v9: Phase 0a の実測で確定。正本は `docs/closure-allowlist.md`):

1. `plugins/claude-code/skills/drawio/SKILL.md` — 閉包の root。上流の当該ディレクトリの中身はこの 1 ファイルのみである
2. `shared/xml-reference.md` — 上流 `CLAUDE.md` が正本と定義する 2 ファイルの片方
3. `shared/mermaid-reference.md` — 同じく正本と定義される片方 (v8 まで落ちていた)
4. 参照解析で導出される `shared/` 配下のファイル。この pinned SHA では `shared/style-reference.md` と `shared/mxfile.xsd` の 2 件が `xml-reference.md` 経由で導出される
5. `LICENSE` — 参照解析の産物ではなく、Apache-2.0 §4(a) の再頒布義務による固定エントリ

**閉包導出規則 (v9 追記)**: 上流の参照は相対 path ではなく `main` を指す**絶対 URL** (`raw.githubusercontent.com/...` および `github.com/.../blob/...`) である。素直な相対 path 解決だけを実装すると閉包が root 1 ファイルで閉じるため、URL 文字列を上流 path へ写像してから閉包に追加する。`<ref>` は無視し、取得は常に pinned SHA から行う。上流 repo 以外を指す URL は閉包に入れない。**詳細規則 (抽出パターン・不動点の反復・path 消失時の失敗規則・意図的な除外リスト) は `docs/closure-allowlist.md` §2 を正とする。**

### 4.2 verify と update の分離

- `scripts/verify-vendor.py`: 現行 snapshot を vendor.lock と照合するだけ。差分 = 改ざん or 手編集であり、**即失敗**。CI の全ジョブで実行。
- `scripts/propose-upstream-update.py`: ①tracking ref (main) から candidate SHA を解決 → ②allowlist + 参照解析で閉包を再確定 → ③candidate snapshot + 新 vendor.lock を生成 → ④contract test 実行 → ⑤合格したら PR 作成。path 消失・認証失敗・テスト失敗はすべて issue / 通知にする (警告放置にしない)。週次で CI 実行。
- vendor ファイルは無改変。旧 vendoring の URL 書き換えは SKILL.md 側の「参照解決規則」(bundled パス読み替え表) に移す。

## 5. ライセンス (v2 major-9 反映)

- root `LICENSE` = MIT (自作部分)。vendor が対象外であることを明記。
- `references/upstream/` に上流の Apache-2.0 LICENSE と NOTICE (存在すれば) を保持。pinned SHA `14b318b` に NOTICE は存在しないため、この時点では該当なし (将来生えた場合の検知は `propose-upstream-update.sh` が行う)。
- `THIRD_PARTY_NOTICES.md`: component / source URL / commit SHA / 対象 path / 改変一覧 (原則「改変なし」)。
- 出所不明が 1 件でもあれば public 化を止める **release gate** は維持する (推測での「jgraph 由来なら Apache」判定はしない)。
- **v9 更新**: Phase 0a の実査で、閉包 6 ファイルすべての source・license・copyright を実ファイル単位で確定した。v8 が名指しで疑義を挙げていた `mxfile.xsd` と `style-reference.md` は、**いずれも上流 `shared/` の実在ファイルで、閉包規則からも正当に導出される上流由来と確定済み** (Apache-2.0 / Copyright 2025 JGraph Ltd)。出所不明は 0 件。台帳と根拠は `docs/license-ledger.md` を正とする。ただし gate の最終判定は Phase 3a 時点の pinned SHA に対して台帳を再実行して行う。

## 6. 契約 (contracts)

> Phase 0b で本節と §7 を実装可能な精度へ展開した。確定文書は `contracts/` 配下 (`diagnostics.schema.json` / `exit-codes.md` / `delivery.md` / `profile.schema.json` / `profile.md` / `environment.md`)。両者が食い違った場合は `contracts/` を正とし、PLAN を追随させる。

### 6.1 診断 JSON contract (v2 major-2 反映) — Phase 0 で確定

- JSON Schema を repo に置き正本とする。stdout は JSON のみ、ログは stderr。
- 構造 (骨子):
  - top-level: `schemaVersion` / `toolVersion` / `status` / `checks[]` / `diagnostics[]` / `artifacts[]`
  - `checks[]`: `{id, required(bool), status: passed|failed|skipped, waiver?: {reason, authorizedBy}}`。**v1 では required check は waiver 不可** (waiver フィールドを持てるのは optional check のみ。将来 required の waiver を許す場合は許可 check ID の列挙と認可経路の定義を schema 変更として行う)
  - `diagnostics[]`: `{code, severity: error|warning, message, subject: {file, xpath?|cellId?, line?}, evidence: {expected?, actual?, params?}, supportedFixes[]: {fixId, target, precondition, description}}`
  - `artifacts[]`: `{path, sha256, kind}`
- **集約規則 (truth table)**: top-level `status` は 3 値で、次の判定を上から順に適用する。
  1. deliverable を一切処理しなかった (対象外指定) → `skipped`
  2. required check に failed または skipped が 1 つでもある → `failed` (**必須依存の欠落も required check の failed として扱う** + exit 5)
  3. required がすべて passed → `passed`。optional check の failed / skipped (waiver の有無を問わず) は top-level を変えず、diagnostics (severity=warning) と receipt に残る (v4 minor-1 反映: optional の skip に waiver は必須でない。waiver は理由の記録手段)
- top-level `skipped` の exit code は **0** (処理対象外は異常ではない。JSON の `status` で `passed` と区別する)。
- exit code (確定): 0=passed / 1=validation failure / 2=export・出力検証失敗 / 3=hash 競合 / 4=usage error / **5=依存欠落** (v2 で未決だった分離を採用)。
- 互換性規則: `schemaVersion` は additive 変更で minor、フィールド削除・意味変更で major。

### 6.2 修復ループ (v2 major-3 反映)

- 単位は fix set (非競合で決定的な修正の集合)。**全修復ラウンドは 1 つの作業コピー上で完結させ、正本 (.drawio) には途中経過を一切書き戻さない** (v5 major-1 反映)。fix set は作業コピーの temp 上で適用し、適用成功後に作業コピーを置換 → 全体を再検証、を繰り返す。
- **hash handoff (並行編集の保護)**: 修復開始時に正本の SHA-256 を `H0` として保持。全 required check 合格後、**正本置換の直前に実測が `H0` であることを再照合し、一度だけ `Hfinal` (合格した作業コピーの内容) へ置換する** (不一致なら置換せず exit 3)。**納品 commit (= `current` pointer の切替。世代 rename ではない) の直前**にも正本が `Hfinal` のままであることを確認 (不一致なら pointer を切り替えず exit 3)。修復が失敗終了 (循環・打ち切り) した場合、正本は `H0` のまま無傷で、作業コピーは診断とともに failed 報告へ添付する。
- **保護範囲の限定 (v6 major-1 反映)**: hash handoff と lock が競合を**防止**できるのは、この contract に従う協調 writer (etch CLI・etching skill 経由のエージェント) 同士に限る。draw.io Desktop 等の非協調 writer は lock を守らないため、照合と pointer 切替の間の競合窓を完全には閉じられない。この窓については**防止でなく検出**を保証する: receipt に入力正本の hash (`Hfinal`) を記録し、`etch verify` が現行正本の実測 hash と receipt を比較して不一致を診断 code 付きで報告する。人間との同時編集が予期される場面では、正本を直接置換せず `*.agent-proposal.drawio` として並置する既存 handoff 手順 (現 drawio-authoring 由来) を profile で選択できるようにする。**proposal mode では正本置換も `current` 切替も行わず、proposal ファイルとその receipt だけを生成し、receipt および `etch verify` の照合対象は proposal ファイルの hash とする** (v7 minor-1 反映)。
- 停止条件: 状態 fingerprint = **修復対象の作業コピー自体の canonical hash** + canonical 化した `(code, subject)` multiset (export 前の validation failure でも作業コピー hash は常に存在する)。**既出の fingerprint に戻ったら停止** (循環検知)。加えて fix set 5 回で打ち切り。文書が変化し診断が減っている限り、同一 code の再発だけでは止めない。
- 停止時は納品禁止。diagnostics を添えて failed 報告。

### 6.3 納品規律 (v2 blocker-2 反映)

- atomic の単位は成果物集合。手順:
  1. 同一 filesystem 上の `generations/<id>.tmp/` に全成果物を書く
  2. 全検証合格後、receipt を書く。**receipt は自分自身を hash 対象に含めない** (対象は成果物のみ)
  3. ディレクトリを `generations/<id>/` に rename
  4. `current` pointer (symlink または manifest ファイル) を atomic replace で新世代に向ける
- **読者 protocol**: 読者は `current` を**一度だけ解決**し、得られた世代ディレクトリ (immutable) の path から全成果物と receipt を読む。`current/<file>` 形式で成果物ごとに再解決してはならない (世代混在の防止)。
- 回収規則 (v4 major-2, v5 minor-1 反映): **v1 では旧世代の自動削除をしない**。自動回収の対象は **自プロセスが作った `.tmp` 世代のみ** (他プロセスの `.tmp` は経過時間だけでは削除しない。扱うなら作成者 PID の lock ownership とプロセス消滅の確認を必要条件とする)。完結した旧世代の削除は明示コマンド (`etch gc`) によるユーザー操作とし、reader lease を持たない以上「読み取り中でない」ことを CLI は保証しない、と contract に明記する。
- receipt の内容 (v2 minor-2 反映): 各成果物の SHA-256 / etch CLI バージョン / **draw.io Desktop バージョンと実行オプション** / 入力 .drawio の hash / vendor.lock の SHA / 実行 checks と status / waiver。

### 6.4 入力安全

- XML パースで DTD / 外部 entity 拒否 (XXE 対策)。入力上限: byte 数 / node 数 / 深さ / 圧縮展開後サイズ。
- 非圧縮強制ポリシー下では圧縮入力を暗黙変換せず、明示の診断 code で拒否。

## 7. CLI 実装方針 (v2 major-6 反映)

### 7.1 runtime の確定

- shell target は **bash 3.2 互換に固定** (macOS 同梱 bash の下限。POSIX sh への全面書き換えはしない)。ShellCheck を CI に入れる。
- Python は **python3 標準ライブラリのみ・最低 3.9** を実行時依存として明示する。エンドユーザーに uv は要求しない (uv は本 repo の開発ツーリング側でのみ使用)。python3 欠落は exit 5。
- `DRAWIO_CMD` は単一 executable path (shell 文字列にしない)。未設定時の解決順: PATH → macOS app bundle → Linux 既定パス。
- environment contract (references/environment.md) に、対応 OS / 必須・任意コマンド / clean install での検証手順を明記。

### 7.2 出力検証

- PNG: 全 chunk 走査 (構造 + CRC 検証) + IDAT を zlib 展開して寸法整合を確認 (IHDR/IEND の存在確認だけにしない)。`sips` は廃止。
- SVG / PDF: 既存 wrapper の検証 (xmllint、magic) を継承。

### 7.3 host profile の解決 (v2 major-8 反映)

- 解決順序 (上が優先): ①`--profile <path>` ②環境変数 `ETCHING_PROFILE` ③カレント project の固定 path `.etching/profile.json` ④なし (host-neutral 既定動作)。
- **相対参照で vault 等を推測しない**。
- profile は 2 ファイルに分離する (v4 major-3 反映: YAML parser は標準ライブラリに無いため使わない):
  - `.etching/profile.json` — **CLI が読む機械可読部** (version 付き JSON。許可キーを列挙した schema で検証。json モジュールのみで処理)。schema 不合格なら fail-closed。
  - `.etching/profile.md` — エージェント向けの環境規約 (置き場所・埋め込みレシピ等)。CLI は解釈しない。
- Koyo-HQ では vault 直下に両ファイルを置く。

## 8. vault との関係 (v2 major-10 反映)

- OSS repo (`HidakaKoyo/etching-drawio`) を唯一の編集元とし、同期は OSS→vault の一方向のみ。vault 側 receipt (release tag / commit / managed-file hash) を照合し、managed file に差分があれば上書きせず失敗する (fail-closed)。
- **初回移行は通常同期と別の one-shot migration** とする: ①既存 `.agents/skills/drawio/`・`drawio-authoring` の現物 hash を既知の旧 hash 一覧と照合 ②旧内容を `99_log/` 外の退避先に backup ③期待した旧版のみ削除・置換 ④新 receipt 作成 ⑤事後検証 (skill scan の公開対象が etching のみ / export 実走 / Obsidian 埋め込みの表示確認)。予期しない差分があれば停止して Koyo に報告。

## 9. 配布 (v2 minor-3 反映)

- 一次: Claude Code plugin marketplace (reflection-cc と同型)。二次: `npx skills add`。
- skill ディレクトリ単体で実行閉包を閉じる (sibling 依存なし)。両方式で「クリーン環境にインストール → 実行」の受入テストを CI に置く。
- **バージョンの編集上の正本は `.claude-plugin/plugin.json` の version**。ただし standalone 配布 (skill 単体) の閉包内でも version を参照できるよう、**release build で plugin.json から skill ディレクトリ内に `VERSION` ファイルを生成**し、CI で両者の一致を検証する (v3 major-5 反映。「編集する正本」と「配布物へ生成する複製」を区別)。実行時の toolVersion / receipt はこの VERSION を読む。git tag は `v<plugin version>` で 1:1 対応。診断 schemaVersion は §6.1 の規則で独立に上がる (release CI で「schema 変更があるのに schemaVersion 据え置き」を拒否)。vendor-only 更新は plugin version の patch を上げる。この対応表を README に記載。
- CHANGELOG は手書き (reflection-cc 方式)。

## 10. 実装フェーズ分割 (v2 major-4, major-5 反映)

「セッション数」ではなく **gate (受入条件) 単位**で管理する。順序は contract 確定 → 同期機構 → CLI の依存方向に直した。

| Phase | 内容 | gate (これを満たすまで次に進まない) |
|---|---|---|
| 0a | 上流裏取り (shared/xml-reference.md の正本性、依存閉包の確定)、全 vendor ファイルのライセンス実査 | 閉包 allowlist 確定 + license 台帳完成。**license gate は release gate であって development gate ではない**: 不明が残っても private 開発 (Phase 0b〜3a) は継続できるが、**Phase 3b (public 化) は不明ゼロになるまで禁止** (v3 minor-2 反映) |
| 0b | contract 確定: 診断 JSON Schema / exit code / 納品手順 / profile 解決 / 配布 layout / runtime 宣言 | schema と contract 文書が repo にあり、fake データで schema validation が通る |
| 0c | repo scaffold (private) + verify-vendor / propose-upstream-update 実装 + **その機構を使った初回 vendoring** | verify-vendor が CI で green。vendor.lock と snapshot が一致 |
| 1a | 既存 wrapper の characterization test 作成。**「維持する invariant」(検証内容・競合検知・lock 排他) と「意図的変更」(exit code 再編・出力形式) に分けて書く** (v3 major-6 反映) | 現行 wrapper に対し invariant テストが green。意図的変更は旧値→新値の migration test として定義済み |
| 1b | etch CLI 移植 (--json contract 実装、staging+pointer 納品) | invariant テスト + migration test (新期待値) + contract test が新 CLI で green |
| 1c | portability / security (sips 除去、PNG chunk 検証、DRAWIO_CMD、XXE・上限、bash 3.2 + ShellCheck) | Ubuntu + macOS の CI マトリクス green |
| 1d | real export smoke test (pin した draw.io Desktop) | **Ubuntu と macOS の両方**で、OS 別の DRAWIO_CMD 解決 → 実 export → SVG/PNG/PDF 検証まで各 1 回以上実走して合格 (v5 minor-2 反映) |
| 2 | skill 本体 (SKILL.md + authoring/delivery/environment contracts + 参照解決規則) | クリーン環境で skill を読んだエージェントが修復ループを一巡できる (dogfooding) |
| 3a | release candidate: marketplace manifest / 受入テスト (両配布方式) / THIRD_PARTY_NOTICES / README / security.md | 受入テスト green + license gate 通過 + CHANGELOG/tag/version 整合 |
| 3b | public 化 + v0.1.0 release | Koyo の明示承認 (repo public 化は外部公開操作のため) |
| 4 | vault one-shot migration (§8): inventory → dry-run → cutover → post-check。rollback は backup からの復元手順を事前に文書化 | 事後検証 3 点 (skill scan 単一 / export 実走 / Obsidian 表示) 合格。changelog 記録 |

- Phase 0-3 は MyWorkspace の新 repo で作業 (並行委譲時は worktree 分離)。実装は Codex 主担当 (codex-task --write)、司令塔がレビュー・統合。commit は司令塔側で実施 (Codex は .git に書けない)。
- Phase 4 のみ vault に触れる。agent-changelog 必須。

## 11. スコープ外 (v1 で作らないもの)

- archify 式のレンダリング後 SVG 幾何検査 (交差・ラベル余白) は v2 スコープ。診断 code の namespace (`composition/*`) だけ予約する。
- MCP サーバー化・drawio 以外のバックエンド対応はしない (必要性が示されるまで作らない。reflection-cc の scope statement 方式)。
