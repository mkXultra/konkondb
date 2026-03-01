# konkon raw list — Raw Record 一覧表示

## 概要

Raw DB のレコード一覧を新しい順に表示する。

## Bounded Context

**呼び出すコンテキスト:** Ingestion Context（読み取り専用）
**レイヤー:** L1（Raw DB / Ingestion）

`raw` グループの共通制約は [04_cli_conventions.md §5.1](../04_cli_conventions.md) 参照。

## シグネチャ

```
konkon raw list [OPTIONS]
```

## オプション

| オプション | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `--limit` | `INT` (>= 0) | `20` | 表示するレコードの最大数 |
| `--format` | `text\|json` | (TTY 自動検出) | 出力フォーマット |

## 振る舞い

1. Raw DB ファイルが存在しない場合、何も出力せず正常終了（exit `0`）
2. レコードが0件の場合も同様に何も出力せず正常終了（exit `0`）
3. レコードは `created_at DESC, id DESC` の順序（新しいものが先）

## stdout 出力

### text フォーマット

ヘッダー行 + 各レコードの ID、created_at、updated_at、content（先頭50文字に切り詰め）を表形式で出力する。

### json フォーマット

各レコードを JSON Lines（1行1オブジェクト）で出力する。content 全文と meta を含む。

```json
{"id": "...", "created_at": "...", "updated_at": "...", "content": "...", "meta": {}}
```

## 終了コード

共通終了コード（`0`, `1`, `2`）は [04_cli_conventions.md §2.3](../04_cli_conventions.md) 参照。コマンド固有の終了コード:

| コード | 条件 |
| :--- | :--- |
| `3` | プロジェクト未初期化（`konkon.py` 未検出）、Raw DB スキーマ不一致 |
