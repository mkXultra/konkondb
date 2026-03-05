# konkon build — Context DB の構築

## 概要

開発者が `konkon.py` に定義した `build()` 関数を実行し、Raw Data から Context DB を構築・更新する。

## Bounded Context

**呼び出すコンテキスト:** Transformation Context → User Plugin
**レイヤー:** L2（Orchestrator/Contract/Accessor）+ L1 + L3

```text
Developer ──▶ CLI ──▶ Transformation Context (Plugin Host)
                          │
                          ├──▶ Ingestion Context (RawDataAccessor: 読み取り専用)
                          │
                          └──▶ User Plugin Logic (build() の実行)
                                   │
                                   └──▶ Context Store (開発者定義の書き込み先)
```

## シグネチャ

```
konkon build [OPTIONS]
```

## オプション

| オプション | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `--full` | flag | `false` | フルビルド。`build()` に全 Raw Record を渡す（デフォルト: 前回ビルド以降の変更分のみ） |
| `--plugin` | `PATH` | `<project-dir>/konkon.py` | Plugin ファイルパス |
| `--raw-db` | `PATH` | `<project-dir>/.konkon/raw.db` | Raw DB ファイルパス |

デフォルトの差分ビルド: `konkon build` は `.konkon/last_build` ファイルに記録された前回のビルド開始時刻と、各レコードの `updated_at` を比較し、変更されたレコードのみを `build()` に渡す。チェックポイントにビルド完了時刻ではなく開始時刻を使用することで、ビルド実行中に発生した更新が次回ビルドで取りこぼされることを防ぐ。初回ビルド（`last_build` ファイルが存在しない場合）は自動的にフルビルドとなる。`--full` を指定すると、すべてのレコードが渡される。

## 振る舞い

[04_cli_conventions.md §2.6](../04_cli_conventions.md) の共通振る舞いに加え、以下の手順で実行する。

1. **Load / Contract 検証**: [04_cli_conventions.md §2.6](../04_cli_conventions.md) に従う
2. **CWD 設定**: [04_cli_conventions.md §2.6](../04_cli_conventions.md) の CWD 保証に従い、Plugin ファイルのディレクトリに設定する
3. **Invoke**: `build(raw_data, context)` を呼び出す（sync/async 処理は [04_cli_conventions.md §2.6](../04_cli_conventions.md) に従う）。`context` は [BuildContext](../06_build_context.md) であり、ビルドモードと削除情報を含む
4. **エラーハンドリング**: `BuildError` は診断メッセージ付きで stderr に出力。未捕捉例外はトレースバック付きで stderr に出力

### 中断時の振る舞い

`build()` が SIGINT / SIGTERM により中断された場合、ビルドは失敗として扱われる。フレームワークは Context Store のロールバックを **一切行わない**（[02_interface_contracts.md](../02_interface_contracts.md) セクション 2.3, 2.4）。開発者は Context Store のアトミック更新パターン（テンポラリファイル → リネーム）を採用することを推奨する。

## stdout 出力

- **text モード**: stdout には何も出力しない。サマリーは stderr に出力する
- **json モード**: ビルド結果のステータス JSON を stdout に出力する

### json 成功時

```json
{
  "status": "ok",
  "mode": "full",
  "plugin": "/path/to/konkon.py",
  "raw_db": "/path/to/.konkon/raw.db",
  "duration_ms": 1234
}
```

### json 失敗時（exit `4`）

```json
{
  "status": "error",
  "error": "BuildError",
  "message": "Failed to connect to vector DB"
}
```

未捕捉例外の場合は `"error": "UnexpectedError"` とする。text モードでは引き続き stdout は空（エラーは stderr のみ）。

## stderr 出力

| レベル | 出力例 |
| :--- | :--- |
| INFO | `[INFO] Loading plugin: /path/to/konkon.py` |
| INFO | `[INFO] Raw records: 1,234 (full build)` |
| INFO | `[INFO] Build completed in 2.3s` |
| ERROR | `[ERROR] BuildError: Failed to connect to vector DB` |

`--verbose` 指定時は DEBUG レベルのログも表示される。

## 終了コード

共通終了コード（`0`, `1`, `2`）は [04_cli_conventions.md §2.3](../04_cli_conventions.md) 参照。コマンド固有の終了コード:

| コード | 条件 |
| :--- | :--- |
| `3` | `konkon.py` 未検出 / ロード失敗 / Contract 不適合 / Raw DB スキーマ不一致 |
| `4` | `build()` 実行中のエラー（`BuildError` または Plugin 内の未捕捉例外） |

## 設計判断・補足

**Plugin Contract との関連:**
- `build(raw_data: RawDataAccessor, context: BuildContext) -> None` の契約に厳密に従う（sync/async 両対応）→ [02_interface_contracts.md §1](../02_interface_contracts.md)、[06_build_context.md](../06_build_context.md)
- `context` には `mode`（`"full"` / `"incremental"`）と `deleted_records`（前回ビルド以降に削除された Record の情報。各要素は `DeletedRecord(id, meta)`）が含まれる
- 差分ビルドでは `.konkon/last_build` の時刻を基準に `updated_at` でフィルタする
- Accessor の順序契約（`ORDER BY created_at ASC, id ASC`）を変更しない
- Plugin に Raw DB 接続や `raw_records` テーブル名を露出しない（ACL #1）
