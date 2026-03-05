# konkon delete — Raw Record の削除

## 概要

指定した ID の Raw Record を Raw DB から物理削除（ハードデリート）し、Tombstone を記録する。次回 `konkon build` で Plugin に削除情報が伝達される。

## Bounded Context

**呼び出すコンテキスト:** Ingestion Context
**レイヤー:** L1（Ingestion — 物理削除 + Tombstone 記録）

```text
Developer ──▶ CLI ──▶ Use Case ──▶ Ingestion Context ──▶ Raw DB (SELECT meta → DELETE)
                                                       └──▶ raw_deletions (INSERT tombstone w/ meta)
```

> **注記:** Application Layer による `.konkon/last_build` の削除は不要。Tombstone + [BuildContext](../06_build_context.md) により、インクリメンタルビルドで削除情報が Plugin に伝達される。

## シグネチャ

```
konkon delete [OPTIONS] RECORD_ID
```

## 引数

| 引数 | 必須 | 説明 |
| :--- | :--- | :--- |
| `RECORD_ID` | Yes | 削除対象の Raw Record の ID |

## オプション

| オプション | 短縮形 | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- | :--- |
| `--force` | `-f` | flag | `false` | 確認プロンプトをスキップ |

## バリデーション

- `RECORD_ID` が未指定の場合は Click が自動でエラー（終了コード `2`）

## 振る舞い

1. プロジェクトルートを解決する（[04_cli_conventions.md §2.4](../04_cli_conventions.md)）
2. Raw DB ファイルが存在しない場合、終了コード `1`（レコード未検出として扱う。DB の遅延作成は行わない）
3. `--force` 未指定かつ **stdin と stderr がともに TTY** の場合、確認プロンプトを **stderr** に表示: `Delete record <RECORD_ID>? [y/N]`。入力は **stdin** から読み取る。`y` または `yes`（大文字小文字不問）で続行、それ以外（`N`、空入力、EOF）で終了コード `0`（アクション無し）。stdin または stderr が TTY でない場合は `--force` が暗黙的に適用される
4. `RECORD_ID` に一致するレコードが存在しない場合、終了コード `1`
5. **トランザクション内で以下を実行:**
   a. 削除対象レコードの `meta` を `raw_records` から取得する（`COALESCE(meta, '{}')` で NULL を正規化）
   b. レコードを `raw_records` から物理削除する
   c. `raw_deletions` に Tombstone を挿入する（`record_id`, `deleted_at = now(UTC)`, `meta`（正規化済み JSON オブジェクト））
6. 成功時、削除されたレコードの ID を stdout に出力する

## stdout 出力

削除されたレコードの ID を出力する（`update` と同様の簡潔なパターン）。

```
019516a0-3b40-7f8a-b12c-4e5f6a7b8c9d
```

> **注記:** `--format` オプションは提供しない（`update` と同じ方針。[04_cli_conventions.md §2.2](../04_cli_conventions.md) では `insert`, `build`, `search` のみ `--format` を定義）。

## stderr 出力

| レベル | 出力例 |
| :--- | :--- |
| INFO | `[INFO] Record deleted. Run 'konkon build' to update Context Store.` |

## 終了コード

共通終了コード（`0`, `1`, `2`）は [04_cli_conventions.md §2.3](../04_cli_conventions.md) 参照。コマンド固有の終了コード:

| コード | 条件 |
| :--- | :--- |
| `0` | 成功。またはユーザーが確認プロンプトでキャンセル |
| `1` | レコード未検出（ID が存在しない、または Raw DB ファイルが未作成） |
| `3` | プロジェクト未初期化、Raw DB スキーマ不一致 |

## 設計判断・補足

### 削除方式: ハードデリート + Tombstone（ハイブリッド方式）

`raw_records` からは物理削除（スキーマ変更なし）。別テーブル `raw_deletions` に削除イベントを記録する。

**理由:**

1. **Plugin Contract (ACL #2) の保護:** ソフトデリートで Accessor が削除済みレコードをフィルタする場合、Plugin は削除を検知できず、結局フルリビルドが必要になる（ハードデリートと同等）。Accessor が削除済みを含めて返す場合、`RawRecord` に `deleted_at` フィールドを追加する必要があり、ACL #1/#2 の破壊的変更となる。3レビュー全てが不採用と判定
2. **スキーマ変更最小:** `raw_records` テーブルのスキーマ変更なし。`RawDataAccessor` Protocol の変更なし。既存の insert/update パスに影響なし
3. **インクリメンタルビルドの維持:** Tombstone + [BuildContext](../06_build_context.md) により、削除後もフルリビルドを強制する必要がない
4. **一時的なストレージ:** Tombstone はビルド成功後に自動 purge される。長期的なストレージコストなし

**不採用とした代替案:**

| 代替案 | 不採用理由 |
| :--- | :--- |
| ソフトデリート（`deleted_at` 列追加） | `RawRecord` への `deleted_at` 追加は ACL #2 の破壊的変更。Accessor が削除済みを含めて返すとセマンティクスが変わり全クエリに影響する。3レビュー全てが不採用 |
| Change Feed（全ミューテーションのイベントログ） | insert/update にも event append が追加され影響範囲が過大。event の無制限成長と compaction の設計が必要。MVP として過剰。3レビューが「将来拡張として記録」を推奨 |

### `.konkon/last_build` を削除しない理由

Tombstone + BuildContext により削除情報がインクリメンタルビルドで Plugin に伝達されるため、`.konkon/last_build` を削除してフルリビルドを強制する必要はない:

- 次回 `konkon build` はインクリメンタルビルドとして実行される
- `BuildContext.deleted_records` に削除されたレコードの情報（ID + meta）が含まれる
- Plugin が Context Store から該当エントリを除去する（ID だけでなく meta も参照可能）

### 確認プロンプト

`update` コマンドには確認プロンプトがないが、`delete` では追加する。

- **根拠:** `update` はデータの変更（再度 `update` で戻せる）であり、`delete` はデータの喪失（不可逆）。UNIX の慣例でも `rm` 系コマンドは確認/`-f` パターンを採用する
- **スクリプト互換:** `--force` フラグと TTY 検出により、非対話環境（パイプ、CI）では自動実行される

### 冪等性の不採用

「既に削除済み」を成功（exit 0）として扱う冪等性設計は不採用とする。

- **根拠:** ハードデリートでは「削除済み」と「未存在」が区別不能であり、いずれも `KeyError`（"record not found"）として扱う。`update` の既存パターン（対象なしで exit 1）との一貫性を優先する
- **将来検討:** バルク操作やスクリプト用途で冪等性が必要になった場合、`--if-exists` フラグの追加を検討する

### Raw DB ファイル未存在時の動作

`update` は `_open_db()` で DB を遅延作成するが、`delete` では DB の遅延作成を行わない。

- **根拠:** 存在しないレコードの削除で空の DB ファイルが作成されるのは不自然。`_db_file_exists()` を事前チェックし、未存在なら `KeyError` 相当（exit 1）で即時終了する

### データモデル・マイグレーション

- Raw DB スキーマ: **Version 2 → 3**（`raw_deletions` テーブル追加。`record_id`, `deleted_at`, `meta` カラムを持つ。`meta` は削除前のレコードの meta を JSON オブジェクトとして保存）。詳細は [06_build_context.md §7](../06_build_context.md) 参照
- `RawRecord`: **変更なし**（新規フィールド不要）
- `RawDataAccessor` Protocol: **変更なし**
- `RawDBBackend` Protocol: `delete(record_id: str) -> None` メソッドを追加（`KeyError` if not found。削除前に meta を取得し Tombstone に保存）。加えて `get_deleted_records_since()`, `purge_tombstones()` を追加。詳細は [06_build_context.md §6.1](../06_build_context.md) 参照
- `konkon migrate`: **影響なし**（削除済みレコードは物理的に存在しないため転送対象にならない。Tombstone は transient データであり、マイグレーション対象外）

### 既存設計書への反映（本仕様確定後に適用）

| 文書 | 反映内容 |
| :--- | :--- |
| [03_data_model.md](../03_data_model.md) §2.1 | 「DELETE は MVP では行わない」→「DELETE はレコード単位の物理削除 + tombstone 記録として許容」 |
| [03_data_model.md](../03_data_model.md) §3, §7, §7.2, §9, §10, §11, §12, §15 | `raw_deletions` テーブル、インデックス、スキーマ v3 関連。詳細は [06_build_context.md §8](../06_build_context.md) 参照 |
| [04_cli_conventions.md](../04_cli_conventions.md) | コマンド体系の表に `konkon delete` を追加。フロー図に `delete` を追加 |
| [05_project_structure.md](../05_project_structure.md) | `cli/delete.py` を追加、Ingestion facade 公開 API に `delete`, `get_deleted_records_since`, `purge_tombstones` を追加 |

### 将来拡張（スコープ外）

- バルク削除（`konkon delete --all`, `--query "..."`）— Tombstone 機構はバルクに対応可能（各 ID ごとに tombstone を挿入）
- 削除内容の保存（Tombstone に `content` を追加し、Plugin に削除前のコンテンツを提供。`meta` は実装済み）
- 削除ログ / 監査トレイル
- Event sourcing（`raw_deletions` を `raw_events` に一般化し、全ミューテーションを記録する形への拡張）

---

## 設計判断ログ

本仕様の主要な設計判断と、その採用元・根拠を記録する。

| # | 判断 | 採用元 | 根拠 |
| :--- | :--- | :--- | :--- |
| D1 | ハードデリート + Tombstone（ハイブリッド方式）を採用 | Claude | ソフトデリートは ACL #1/#2 を破壊する（Gemini 案の問題、3レビュー全てが不採用）。Change Feed は全ミューテーションへの影響が過大で MVP として過剰（Codex 案、3レビューが将来拡張を推奨）。Tombstone は `raw_records` に影響を与えず、insert/update パスの変更なしで削除情報を独立管理できる |
| D2 | `.konkon/last_build` の削除を廃止 | Claude | Tombstone + BuildContext により削除情報がインクリメンタルビルドで伝達可能。フルリビルド強制は不要 |
| D3 | 確認プロンプト（`--force`） | Claude | 不可逆操作に対する安全策。`update` との非対称性は「データ変更 vs データ喪失」の本質的差異で正当化 |
| D4 | `--format` 不採用 | Codex レビュー指摘 | `update` が `--format` を持たない既存パターンとの一貫性。04_cli_conventions.md §2.2 は `insert/build/search` のみ `--format` を定義 |
| D5 | 冪等性（exit 0 for already deleted）不採用 | Claude レビュー | ハードデリートでは状態区別不能。`update` の既存パターン（対象なしで exit 1）との一貫性を優先 |
| D6 | DB ファイル未存在時は遅延作成しない | Claude レビュー | 削除で空 DB を作るのは不自然。`_db_file_exists()` 事前チェックで即時 exit 1 |
| D7 | 削除 + Tombstone をトランザクション内で実行 | Claude | 物理削除と Tombstone 挿入の原子性を保証。片方だけ成功するとデータ不整合が発生する |
| D8 | Use Case 層の簡素化（Ingestion Facade への委譲のみ） | Claude | Tombstone 方式により cross-context orchestration が不要。Application Layer の責務が軽量化 |
