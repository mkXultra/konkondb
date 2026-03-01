# konkon raw get — Raw Record 個別取得

## 概要

ID を指定して Raw DB から1件のレコードを取得する。デバッグ・スクリプト連携向け。

## Bounded Context

**呼び出すコンテキスト:** Ingestion Context（読み取り専用）
**レイヤー:** L1（Raw DB / Ingestion）

`raw` グループの共通制約は [04_cli_conventions.md §5.1](../04_cli_conventions.md) 参照。

## シグネチャ

```
konkon raw get [OPTIONS] ID
```

## 引数

| 引数 | 必須 | 説明 |
| :--- | :--- | :--- |
| `ID` | Yes | 取得する Raw Record の ID |

## オプション

| オプション | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `--format` | `text\|json` | (TTY 自動検出) | 出力フォーマット |

## 振る舞い

1. ID に一致するレコードが見つかった場合、stdout に出力し正常終了（exit `0`）
2. Raw DB ファイルが存在しない場合、レコード未検出として扱う（exit `1`）
3. ID に一致するレコードが見つからない場合、stderr に `Error: Record not found: <ID>` を出力（exit `1`）

## stdout 出力

### text フォーマット

```
ID:         019516a0-3b40-7f8a-b12c-4e5f6a7b8c9d
Created:    2026-02-27T12:34:56.789012Z
Updated:    2026-02-27T12:34:56.789012Z
Content:    （全文表示、切り詰めない）
Meta:       {"source_uri": "/path/to/notes.md"}
```

### json フォーマット

```json
{"id": "...", "created_at": "...", "updated_at": "...", "content": "...", "meta": {}}
```

`raw list` の JSON と同一構造。1行で出力する。

## 終了コード

共通終了コード（`0`, `1`, `2`）は [04_cli_conventions.md §2.3](../04_cli_conventions.md) 参照。コマンド固有の終了コード:

| コード | 条件 |
| :--- | :--- |
| `3` | プロジェクト未初期化（`konkon.py` 未検出）、Raw DB スキーマ不一致 |
