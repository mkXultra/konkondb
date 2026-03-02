# konkon migrate — Raw DB バックエンド間のデータ移行

## 概要

Raw DB の全レコードを現在のバックエンドから別のバックエンドにコピーし、`config.toml` のバックエンド設定を更新する。

## Bounded Context

**呼び出すコンテキスト:** Ingestion Context + Instance（設定管理）
**レイヤー:** L1（Raw DB / Ingestion）

```text
Developer ──▶ CLI ──▶ Application Layer
                          │
                          ├──▶ Ingestion Context (Raw DB 読み取り → 移行先 DB 書き込み)
                          │
                          └──▶ Instance (config.toml 更新)
```

## シグネチャ

```
konkon migrate [OPTIONS]
```

## オプション

| オプション | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `--to` | `sqlite\|json` | （必須） | 移行先のバックエンド |
| `--force` | flag | `false` | 移行先ファイルが既に存在する場合に上書きする |

## バリデーション

- `--to` が未指定の場合は終了コード `2`（USAGE_ERROR）
- 現在のバックエンドと `--to` が同一の場合は終了コード `3`（CONFIG_ERROR）: `Already using '<backend>' backend. Nothing to migrate.`
- 移行元の DB ファイルが存在しない場合は終了コード `3`（CONFIG_ERROR）: `Source database .konkon/<file> does not exist. Nothing to migrate.`
- 移行先ファイルが既に存在し `--force` が未指定の場合は終了コード `1`: `Target file .konkon/<file> already exists. Use --force to overwrite.`

## 振る舞い

1. **プロジェクト解決**: プロジェクトルートを特定する（[04_cli_conventions.md §2.4](../04_cli_conventions.md)）
2. **バックエンド解決**: `.konkon/config.toml` の `raw_backend` キーから現在のバックエンドを特定する
3. **バリデーション**: 上記のバリデーション条件を検証する
4. **移行実行**: 移行元 DB の全レコードを移行先 DB にコピーする。`id`, `created_at`, `updated_at`, `content`, `meta` をすべて保持する
5. **設定更新**: `.konkon/config.toml` の `raw_backend` を移行先バックエンドに更新する
6. **移行元保持**: 移行元ファイルは削除しない（安全のため保持する）

### --force 指定時の振る舞い

移行先ファイルが既に存在する場合、`--force` を指定すると:
- 既存の移行先ファイルを削除する
- SQLite の場合は WAL/SHM 補助ファイルも削除する（[03_data_model.md §8](../03_data_model.md)）
- stderr に `[WARN] Removing existing .konkon/<file> (--force)` を出力する

## stdout 出力

`migrate` コマンドは stdout にデータ出力を行わない。すべての出力は stderr に行う。

## stderr 出力

| レベル | 出力例 |
| :--- | :--- |
| INFO | `[INFO] Migrated 42 records: sqlite -> json` |
| INFO | `[INFO] Updated .konkon/config.toml: raw_backend = 'json'` |
| INFO | `[INFO] Source file .konkon/raw.db preserved` |
| WARN | `[WARN] Removing existing .konkon/raw.json (--force)` |

## 終了コード

共通終了コード（`0`, `1`, `2`）は [04_cli_conventions.md §2.3](../04_cli_conventions.md) 参照。コマンド固有の終了コード:

| コード | 条件 |
| :--- | :--- |
| `1` | 移行先ファイル既存（`--force` なし）、その他の一般エラー |
| `3` | プロジェクト未初期化、移行元 DB 未検出、同一バックエンドへの移行、`config.toml` パースエラー |

## 設計判断・補足

- `migrate` は Plugin Contract を利用しない（Ingestion Context のみ）。Plugin のロード・検証は行わない
- 移行元ファイルを保持するのは、移行後に問題が発覚した場合のロールバックを容易にするため
- `--format` オプションは互換性のために受け付けるが、効果はない（stdout へのデータ出力がないため）
- 移行はトランザクション的に行われる: 移行先 DB にすべてのレコードを書き込んだ後に config を更新する。移行中にエラーが発生した場合、config は更新されない
