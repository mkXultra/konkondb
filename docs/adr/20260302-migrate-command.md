# ADR-20260302: migrate コマンドの導入（Raw DB バックエンド間データ移行）

## ステータス

Accepted

## 日付

2026-03-02

## コンテキスト

### バックエンド間移行の必要性

ADR-20260301 で JSON ファイルバックエンドを導入し、Raw DB がマルチバックエンド化（SQLite / JSON）された。しかし、既存プロジェクトがバックエンドを切り替える手段がなかった。ユーザーが手動でデータを変換するのは `id`, `created_at`, `updated_at` 等のフィールド保持が困難で、エラーを招きやすい。公式の移行コマンドが必要とされた。

### 技術的な制約

`RawDBBackend` Protocol の `insert()` は新しい ID とタイムスタンプを生成するため、既存レコードの完全な複製には使用できない。移行には、元のフィールド値をそのまま書き込む専用のパスが必要となる。

### 設計プロセス

JSON バックエンド統合設計書（§13.1）で移行ユーティリティが予定されていた。本設計は Phase 2（3 エージェント独立ドラフト）→ Phase 3 R1（クロスレビュー）→ Phase 4（統合）の多段階プロセスで策定した。

## 決定

### コマンド仕様

`konkon migrate --to {sqlite|json} [--force]` を新規 CLI サブコマンドとして追加する。

- 全レコードの `id`, `created_at`, `updated_at`, `content`, `meta` を完全に保持して移行する
- 移行元ファイルは削除しない（安全な移行）
- 出力は stderr のみ（診断情報であり、パイプに流すデータではない。`init` / `serve` と同一カテゴリ）
- 終了コードは `04_cli_conventions.md` に準拠（0: 成功、1: 一般エラー、2: 不正引数、3: 設定エラー）

### `_write_record()` private メソッド方式（3 者合意）

各 Backend クラス（`RawDB`, `JsonDB`）に `_write_record()` private メソッドを追加し、Protocol 外の移行専用書き込みパスとする。

- **Protocol に追加しない理由**: Protocol は CRUD + accessor の公開契約であり、移行は特殊操作。private メソッドのため ACL 境界を越えない。将来 Backend を追加する場合も `_write_record()` を実装すれば自動対応する
- **Backend クラスに置く理由**: ストレージ形式の知識（SQLite DDL/CHECK 制約、JSON ソート規約・アトミック書き出し）は Backend クラスにカプセル化されるべき。migration モジュールで直接 `sqlite3` や `json` を操作すると知識が漏洩し二重管理になる
- **トランザクション制御**: `_write_record()` 自体は永続化を行わない。呼び出し側がバッチ処理として一括制御する（SQLite: 1 トランザクションで commit、JSON: 全件追加後に sort + save を 1 回）

### migration.py の分離（2:1 多数決）

移行ロジックを `core/ingestion/migration.py` に分離する。

- **分離の理由**: Facade（`__init__.py`）は既に Backend 解決ロジックで約 200 行。移行は通常の CRUD と異なる特殊操作であり、分離することで Facade の責務を明確に保つ
- **Facade との責務分離**: Facade が「何を」「どこへ」を解決し、`migration.py` が「どうやって」を実行する。`migration.py` は Facade の private ヘルパーを直接 import せず、必要な値（Backend インスタンス等）を引数として受け取る
- **具象型の使用**: `run_migration()` は `RawDB | JsonDB` の具象型を引数に取る。`_write_record()` 等が Protocol 外の private API であるため。Ingestion Context 内部の実装詳細であり、ACL 境界を越えない

### `--force` オプション（2:1 多数決）

MVP に `--force` を含める。移行先ファイルが既に存在する場合、`--force` なしではエラー終了（exit 1）し、`--force` ありで移行先を削除して再作成する。ユーザーの明示的な意思なしにデータを上書きしない。

### config 更新の責務分離（3 者合意）

データ移行（Ingestion Context）と config.toml 更新（Application Layer）を分離する。

- **Application Layer に置く理由**: `config.toml` はプロジェクト全体の設定であり、特定の BC が所有するものではない。Application Layer は「BC をまたぐユースケースの調停」を担う
- **順序の保証**: データ移行が成功してから config を更新する。移行中にエラーが発生した場合、config は変更されず元の Backend 設定が維持される
- **既存パターンとの整合**: `use_cases.init()` が `instance.init_project()` に委譲し config を作成するパターンと同一

### 同一 Backend 指定の扱い（3 者合意）

`--to` が現在の Backend と同一の場合は `ConfigError`（exit 3）で即座にエラー終了する。

## 却下した代替案

### `insert()` を移行に再利用する案

| 観点 | 評価 |
| :--- | :--- |
| 概要 | 既存の `insert()` メソッドで移行先にレコードを書き込む |
| 見送り理由 | `insert()` は新しい UUID v7 とタイムスタンプを生成するため、元の `id`, `created_at`, `updated_at` を保持できない。移行の基本要件を満たさない |

### RawDBBackend Protocol に移行メソッドを追加する案

| 観点 | 評価 |
| :--- | :--- |
| 概要 | `_write_record()` を Protocol の正式メソッドとして定義する |
| 見送り理由 | Protocol は CRUD + accessor の公開契約であり、移行は特殊操作。Protocol に含めると全 Backend 実装者に移行サポートを強制することになり、契約が肥大化する |

### 移行ロジックを Facade に直接配置する案

| 観点 | 評価 |
| :--- | :--- |
| 概要 | `migration.py` を分離せず、Facade（`__init__.py`）内に移行ロジックを実装する |
| 見送り理由 | Facade は既に約 200 行。移行は通常の CRUD と異なる特殊操作であり、Facade の責務が曖昧になる。R1 で 2:1 の多数決により分離を採用 |

### config 更新を Ingestion Context 内で行う案

| 観点 | 評価 |
| :--- | :--- |
| 概要 | Facade の `migrate()` 内で `config.toml` を直接更新する |
| 見送り理由 | `config.toml` は特定の BC が所有するものではなく、Ingestion Context が直接操作すると境界が曖昧になる。Application Layer による調停が適切 |

## 影響

### 波及する設計ドキュメント

| ドキュメント | 変更内容 |
| :--- | :--- |
| `04_cli_conventions.md` | コマンド体系の表に `migrate` を追記 |
| `05_project_structure.md` | ディレクトリレイアウトに `migration.py` を追記 |
| `commands/migrate.md` | 新規。コマンド仕様書の作成 |

### 公開 API への影響

| 公開 API | 影響 |
| :--- | :--- |
| Ingestion Facade | `migrate()` 公開関数を追加。既存 API シグネチャへの変更なし |
| `RawDBBackend` Protocol | 変更なし |
| `RawDataAccessor` Protocol | 変更なし |
| Plugin Contract | 変更なし |

### モジュール構成の変更

| ファイル | 種別 | 概要 |
| :--- | :--- | :--- |
| `core/ingestion/migration.py` | 新規 | 移行ロジック本体 |
| `cli/migrate.py` | 新規 | CLI サブコマンド定義 |
| `core/ingestion/raw_db.py` | 変更 | `_write_record()` private メソッド追加 |
| `core/ingestion/json_db.py` | 変更 | `_write_record()` private メソッド追加 |
| `core/ingestion/__init__.py` | 変更 | `migrate()` 公開関数追加 |
| `application/use_cases.py` | 変更 | `migrate()` Use Case 追加 |
| `tach.toml` | 変更 | `migration.py` モジュール追加、visibility 更新 |

### ACL 境界の維持

- `migration.py` は Facade（`konkon.core.ingestion`）からのみ import 可能
- `raw_db.py` / `json_db.py` への可視性は `migration.py` に限定的に付与。Ingestion Context 外部への漏洩なし
- Transformation Context / Serving Context からは参照不可
