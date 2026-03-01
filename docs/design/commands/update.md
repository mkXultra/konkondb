# konkon update — Raw Record の更新

## 概要

既存の Raw Record の content や meta を更新する。

## Bounded Context

**呼び出すコンテキスト:** Ingestion Context
**レイヤー:** L1（Raw DB / Ingestion）

## シグネチャ

```
konkon update [OPTIONS] RECORD_ID
```

## 引数

| 引数 | 必須 | 説明 |
| :--- | :--- | :--- |
| `RECORD_ID` | Yes | 更新対象の Raw Record の ID |

## オプション

| オプション | 短縮形 | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- | :--- |
| `--content` | | `TEXT` | — | 新しい content |
| `--meta` | `-m` | `KEY=VALUE` | — | meta に設定するキーと値。複数回指定可 |

## バリデーション

`--content` と `--meta` の少なくとも一方が必須。両方省略時は終了コード `2`。

## 振る舞い

1. `RECORD_ID` に一致するレコードが存在しない場合、終了コード `1`
2. 成功時、更新されたレコードの ID を stdout に出力
3. `updated_at` が現在時刻に更新される

## 終了コード

共通終了コード（`0`, `1`, `2`）は [04_cli_conventions.md §2.3](../04_cli_conventions.md) 参照。コマンド固有の終了コード:

| コード | 条件 |
| :--- | :--- |
| `3` | プロジェクト未初期化 |
