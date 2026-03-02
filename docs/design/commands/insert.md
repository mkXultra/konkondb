# konkon insert — 生データの投入

## 概要

外部の生データを Raw DB に `Raw Record` として永続化する。

## Bounded Context

**呼び出すコンテキスト:** Ingestion Context
**レイヤー:** L1（Raw DB / Ingestion）

```text
Developer ──▶ CLI ──▶ Ingestion Context ──▶ Raw DB (INSERT)
```

## シグネチャ

```
konkon insert [OPTIONS] [TEXT]
```

## 引数

| 引数 | 必須 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `TEXT` | No | — | 投入するテキスト（省略時は stdin から取得） |

## オプション

| オプション | 短縮形 | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- | :--- |
| `--source-uri` | `-s` | `TEXT` | `NULL` | `meta.source_uri` に記録する。`--meta source_uri=...` のショートカット |
| `--content-type` | `-t` | `TEXT` | `NULL` | `meta.content_type` に記録する。`-s` に拡張子があれば推定、なければ `NULL` |
| `--meta` | `-m` | `KEY=VALUE` | — | `meta` JSON に任意のキーを追加。複数回指定可 |
| `--encoding` | | `TEXT` | `utf-8` | 標準入力のデコード方式 |
| `--raw-db` | | `PATH` | `<project-dir>/.konkon/raw.db` | Raw DB ファイルパス |

## バリデーション

- `TEXT` と stdin（非TTY）が同時に与えられた場合は終了コード `2`
- 入力ソースの優先順位:
  1. `TEXT` 引数がある場合は `TEXT` を `content` として使用
  2. `TEXT` 引数がなく stdin が非TTYの場合は stdin を EOF まで読み取り使用
  3. `TEXT` も stdin もない場合は終了コード `2`
- `-s` / `-t` と `--meta` が同名キーで競合した場合は `-s` / `-t` を優先する

## 振る舞い

- `konkon insert` は **1回の実行で1レコード** を投入する
- `id`: システムが UUID v7 を生成（[03_data_model.md §5](../03_data_model.md) 準拠）
- `created_at`: 投入時刻を UTC で記録（RFC3339 固定長 27 文字、[03_data_model.md §6](../03_data_model.md) 準拠）
- `meta` の組み立て:
  - `--meta KEY=VALUE` で任意キーを追加（複数指定可）
  - `-s/--source-uri` は `meta.source_uri` に設定
  - `-t/--content-type` は `meta.content_type` に設定（未指定時は `-s` の拡張子から推定できる場合のみ設定）

## stdout 出力

投入された `Raw Record` の情報を出力する。text フォーマットは簡潔さを優先し、`meta` の詳細は省略する。全フィールドを確認するには `--format json` を使用する。

### text フォーマット

```
Ingested: 019516a0-3b40-7f8a-b12c-4e5f6a7b8c9d
```

### json フォーマット

```json
{"id": "019516a0-3b40-7f8a-b12c-4e5f6a7b8c9d", "created_at": "2026-02-27T12:34:56.789012Z", "meta": {"source_uri": "/path/to/notes.md", "content_type": "text/markdown"}}
```

JSON フォーマットは JSON オブジェクトを1行で出力する。

## 終了コード

共通終了コード（`0`, `1`, `2`）は [04_cli_conventions.md §2.3](../04_cli_conventions.md) 参照。コマンド固有の終了コード:

| コード | 条件 |
| :--- | :--- |
| `3` | プロジェクト未初期化、Raw DB スキーマ不一致 |

## 設計判断・補足

### Raw DB の遅延作成

Raw DB ファイル（`.konkon/raw.db`）が存在しない場合、`insert` コマンドの初回実行時に [03_data_model.md §12](../03_data_model.md) の完全 DDL を実行してスキーマを自動作成する。DB 接続時には [03_data_model.md §8](../03_data_model.md) で規定された PRAGMA を毎回適用し、`PRAGMA user_version` でスキーマバージョンを検証する。既知のバージョン差に対しては自動マイグレーションを適用する。未知のバージョン（CLI より新しいスキーマ等）の場合のみ終了コード `3` でエラーとする。

### 03 との整合性

- ID 生成・日時保存は [03_data_model.md](../03_data_model.md) §5, §6 に準拠
- `meta` JSON の正規化は [03_data_model.md](../03_data_model.md) §7 の CHECK 制約に適合
- DELETE なし（MVP）
- 内容重複の排除（dedup）は行わない
