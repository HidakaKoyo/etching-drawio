# host profile contract

- 正本: `docs/PLAN.md` §7.3
- 機械可読部の schema: `contracts/profile.schema.json`

profile は環境固有の規約を etching に渡す仕組みで、2 ファイルに分かれる。

| ファイル | 読む主体 | 内容 |
|---|---|---|
| `.etching/profile.json` | etch CLI | CLI が分岐に使う値だけ。schema で検証する |
| `.etching/profile.md` | エージェント | 置き場所の規約、埋め込みレシピ等。**CLI は解釈しない** |

YAML は使わない。python3 標準ライブラリに parser が無く、実行時依存を増やしたくないためである。

## 1. 解決順序

上が優先。最初に見つかったものを使い、以降は見ない。

1. `--profile <path>`
2. 環境変数 `ETCHING_PROFILE`
3. カレント project の固定 path `.etching/profile.json`
4. なし (host-neutral な既定動作)

**相対参照で vault 等を推測して探しにいかない。** 親ディレクトリを遡る探索もしない。3 は「カレントディレクトリ直下の `.etching/profile.json`」だけを見る。

## 2. fail-closed

profile を読むと決めた path について、次はいずれも exit 4 (usage error) で停止する。既定値へのフォールバックはしない。

- path が存在しない (1 と 2 で明示されたのに無い場合。3 は「無ければ 4 へ」なので該当しない)
- JSON として parse できない
- schema に合格しない (未知のキー、型不一致、`version` が 1 でない)

黙って既定に落ちると、proposal mode を期待した環境で正本が置換される事故になる。そこを塞ぐための fail-closed である。

## 3. v1 の許可キー

```json
{
  "version": 1,
  "proposal_mode": true
}
```

| キー | 型 | 既定 | 効果 |
|---|---|---|---|
| `version` | `1` (必須) | — | profile 形式の版数 |
| `proposal_mode` | boolean | `false` | 真なら正本を置換せず `current` も切り替えない。`contracts/delivery.md` §3 |

以上。v1 はこの 2 キーだけである。

**非圧縮強制は v1 では常時 ON であり、profile キーを持たない。** 圧縮された diagram 本文は常に exit 1 (`input/compressed-payload`) で拒否する。切り替え可能にすると「どちらのポリシーで検証されたのか」が receipt を読むまで分からなくなるため、v1 では固定する。

## 4. v1 に入れなかったもの (と、その理由)

YAGNI の記録として残す。将来これらが必要になったら、`version` を上げるか additive なキー追加として schema を改訂する。

| 検討したキー | 入れない理由 |
|---|---|
| 出力先ディレクトリの既定 | 出力先は CLI 引数で毎回決まる。profile で二重化すると優先順位の規則が増えるだけ |
| `DRAWIO_CMD` の指定 | 環境変数で解決する (`contracts/environment.md`)。profile と環境変数の両方から来ると解決順が 5 段になる |
| export 形式の既定 (svg/png/pdf) | 呼び出し側が毎回指定する。profile 既定があると receipt を読むまで何が出たか分からない |
| 検証の厳しさ / check の有効無効 | required check を profile で無効化できると、waiver 不可の規則 (§6.1) を迂回する裏口になる |
| Obsidian 埋め込みの記法、vault 内の置き場所 | CLI は分岐しない。エージェント向けなので `.etching/profile.md` 側に書く |
| 世代の保持数 / gc ポリシー | v1 は自動削除をしない (`contracts/delivery.md` §5)。保持数の概念がまだ無い |
| 非圧縮強制ポリシーの ON / OFF | v1 は常時 ON で固定する (§3 末尾) |
| 外部リソース参照の許可 | 実行ごとの `--allow-external` で足りる。profile に置くと環境全体で恒久的に緩む |

## 5. Koyo-HQ での配置

vault 直下に `.etching/profile.json` と `.etching/profile.md` を置く。Phase 4 の migration で作成する。vault は人間と同時編集が起きうる環境なので、`proposal_mode` の初期値は Phase 4 の判断事項とする (この contract では既定値を決めない)。
