# 納品 contract (staging / pointer / hash handoff)

- 正本: `docs/PLAN.md` §6.2 (修復ループと hash handoff) と §6.3 (納品規律)。本文書はそれを実装手順の粒度に展開したもの
- 関連: `contracts/exit-codes.md` (失敗時の code)、`contracts/diagnostics.schema.json` (報告形式)、`contracts/profile.md` (proposal mode の指定)

## 1. 用語と配置

| 名前 | 意味 |
|---|---|
| 正本 | エージェントが編集対象とする `.drawio` ファイルそのもの |
| 作業コピー | 修復ループが唯一書き換えてよい一時ファイル。正本と**同一 filesystem** 上に置く |
| 世代 (generation) | 1 回の納品で生成した成果物集合。`generations/<id>/` に入る immutable なディレクトリ |
| `current` | 最新世代を指す pointer。symlink または 1 行の manifest ファイル |
| receipt | 世代の内容証明。`generations/<id>/receipt.json` |

```
<出力ルート>/
  generations/
    <id>.tmp/        # 構築中。ここにしか書かない
    <id>/            # rename 後は immutable
      diagram.svg
      diagram.png
      receipt.json
  current            # -> generations/<id>
```

`<id>` は世代を一意に識別する文字列で、辞書順が生成順と一致するもの (例: `20260828T101530Z-<短縮 hash>`) を使う。同一 `<id>` が既に存在する場合は納品を行わず usage error 扱いにはせず、`<id>` を採り直す。

`generations/` と `current` は同一 filesystem 上に置く。rename と pointer の atomic replace が filesystem 境界をまたぐと成立しないため、跨ぐ配置を検出したら exit 4 で止める。

## 2. hash handoff の状態遷移

修復ループは正本に途中経過を一切書き戻さない。正本が変化する瞬間は 1 度きりで、そこを hash で挟む。

```
[S0] 開始
      正本を読む → 実測 SHA-256 を H0 として保持
      作業コピー := 正本の複製
        |
        v
[S1] 修復ループ (作業コピーのみを書き換える)
      検証 → 診断 → fix set を temp に適用 → 成功したら作業コピーを置換 → 再検証
      停止条件: (a) 全 required check passed → S2 へ
                (b) fingerprint が既出に戻った (循環) → S_FAIL
                (c) fix set 適用が 5 回に達した → S_FAIL
      fingerprint = 作業コピー自体の canonical hash
                    + canonical 化した (code, subject) の multiset
        |
        v
[S2] 正本置換の直前照合
      正本を再実測 → H0 と一致するか
        不一致 → 置換せず exit 3 (正本は他者の変更のまま無傷)
        一致   → 作業コピーの内容 Hfinal で正本を atomic に置換 (同一 fs 上の rename)
        |
        v
[S3] 世代の構築
      generations/<id>.tmp/ に全成果物を書く
      export と出力検証を行う (失敗なら exit 2。正本は Hfinal のまま残る)
        |
        v
[S4] receipt の書き込み
      成果物すべての SHA-256 を receipt に記録する
      receipt は自分自身を hash 対象に含めない
        |
        v
[S5] 世代の確定
      generations/<id>.tmp/ → generations/<id> に rename (atomic)
        |
        v
[S6] 納品 commit の直前照合
      正本を再実測 → Hfinal と一致するか
        不一致 → current を切り替えず exit 3 (世代ディレクトリは残り、診断に添付される)
        一致   → current を新世代へ atomic replace
        |
        v
[S7] 完了 (exit 0)

[S_FAIL] 納品禁止。正本は H0 のまま無傷。作業コピーを診断とともに failed 報告に添付し exit 1
```

`current` の atomic replace は、symlink なら一時 symlink を作って `rename()`、manifest ファイルなら一時ファイルを作って `rename()` で行う。既存を消してから作り直す実装は、窓を作るので禁止する。

### 2.1 lock を持たないこと

**v1 に出力 lock 機構は無い。** 旧 wrapper は出力ごとに `<出力>.lock` ディレクトリを取っていたが、世代 staging では成果物の書き込み先が世代ごとに分かれ、共有される可変資源は正本と `current` の 2 つだけになる。この 2 つは S2 と S6 の hash 照合で守られるため、lock は二重の防護になり、かつ stale lock の回収という別の失敗様式を持ち込む。

したがって**並行納品の競合は hash handoff に統合する**。同じ正本に対して 2 プロセスが同時に走った場合、遅れた側は S2 または S6 の照合で外れて exit 3 で止まる。世代ディレクトリは `<id>` が異なるので衝突しない。`current` の差し替えは atomic replace なので、後勝ちで一貫した世代を指す。

### 2.2 保護できる範囲

hash handoff が競合を**防止**できるのは、この contract に従う協調 writer (etch CLI、etching skill 経由のエージェント) 同士に限る。draw.io Desktop などこの手順を通らない writer に対しては、S2 の照合と S6 の照合の間の窓を閉じきれない。

この窓については**防止でなく検出**を保証する。

- receipt に入力正本の hash (`Hfinal`) を記録する
- `etch verify` が現行正本の実測 hash と receipt の `Hfinal` を比較し、不一致を診断 code 付きで報告する

## 3. proposal mode

人間との同時編集が予期される場面では、正本を直接置換せず並置する。profile の `proposal_mode` (`contracts/profile.md`) で選択する。

proposal mode が真のときの分岐は次の通り。

- S2 の正本置換を**行わない**。かわりに `<正本の basename>.agent-proposal.drawio` を同じディレクトリに書く。書き込みは temp + rename で atomic に行う
- `Hfinal` は「作業コピーの内容の hash」であることに変わりはないが、**receipt と `etch verify` の照合対象は正本ではなく proposal ファイル**になる
- S6 の照合対象も proposal ファイルにする。proposal ファイルが自分の書いた `Hfinal` から変化していたら exit 3
- `current` pointer の切替は**行わない**。世代ディレクトリと receipt だけを生成して終わる
- receipt には proposal mode であること、および照合対象の path を明記する

つまり proposal mode では、正本は最初から最後まで一切触られない。成果物は proposal ファイルと世代ディレクトリの 2 つで、それらを人間が確認してから正本へ取り込む。取り込み操作は CLI の責務ではない。

## 4. 読者 protocol

読者 (エージェント、後続ツール、人間) は次を守る。

1. `current` を**一度だけ**解決し、世代ディレクトリの path を得る
2. その path から全成果物と receipt を読む
3. `current/<file>` の形で成果物ごとに再解決してはならない

再解決を繰り返すと、途中で pointer が進んだときに複数世代のファイルが混ざる。世代ディレクトリは rename 後 immutable なので、一度解決してしまえば混在は起きない。

## 5. 回収 (gc)

- **v1 では旧世代を自動削除しない。**
- 自動回収の対象は **自プロセスが作った `.tmp` 世代のみ**。自プロセスの `.tmp` は成否によらず実行終了時に必ず消す。他プロセスの `.tmp` は経過時間だけを根拠に削除せず、v1 では一切触らない (所有者を判定する手段を持たないため)
- 完結した旧世代の削除は明示コマンド `etch gc` によるユーザー操作とする。`etch gc` は既定では候補を報告するだけで何も消さない。実際に消すのは `--delete` を明示したときだけ
- `etch gc` は `current` が指す世代と、`current` 自身を決して削除しない
- **reader lease を持たない以上、CLI は「その世代が読み取り中でない」ことを保証しない。** これは既知の制約として contract に明記する。読み取り中の世代を消す判断はユーザーが行う

## 6. receipt の内容

`generations/<id>/receipt.json` に次を記録する。

- 各成果物の path と SHA-256 (receipt 自身は含めない)
- etch CLI のバージョン
- draw.io Desktop のバージョンと実行オプション
- 入力 `.drawio` の hash (`Hfinal`)、および proposal mode の場合は照合対象が proposal ファイルである旨とその path
- `vendor.lock` の SHA
- 実行した checks とその status、および waiver
