# ADR-20260301: JSON ファイルバックエンドの導入（Raw DB マルチバックエンド化）

## ステータス

Accepted

## 日付

2026-03-01

## コンテキスト

### SQLite 固定の制約

Ingestion Context の Raw DB は SQLite 固定で実装されていた。しかし以下のユースケースにおいて、SQLite 以外の選択肢が求められた:

- **Git フレンドリー**: JSON は diff / merge が容易で、小規模プロジェクトでバージョン管理しやすい
- **デバッグ容易性**: 人間が `cat` / `jq` で直接確認可能。開発初期の素早いイテレーション
- **ポータビリティ**: 単一ファイルのコピーで移行可能
- **ゼロバイナリ依存**: SQLite バインディングが利用できない環境への対応

### 非ゴール

以下は本設計のスコープ外とする:

- 大規模データ（10 万件超）での高性能
- 並行書き込みの完全な ACID 保証
- SQLite を非推奨にすること

### 設計原則

マルチバックエンド化にあたり、以下の原則を設けた:

- **ACL #1 の保護**: バックエンド抽象化は Ingestion Context 内部に閉じる。Transformation Context / Plugin は `RawDataAccessor` Protocol のみに依存し、バックエンドの存在を知らない
- **Facade パターンの維持**: `core/ingestion/__init__.py` の公開 API シグネチャは変更しない
- **Plugin Contract 無変更**: `build()` / `query()` / `schema()` に影響なし
- **既存コードとの差分最小化**: `raw_db.py` を維持し、ファイル追加のみで実現する

### 設計プロセス

以下の多段階プロセスで設計を策定した:

1. **Phase 2**: Claude / Codex / Gemini の 3 エージェントが独立にドラフト作成
2. **Phase 3 R1**: 各エージェントがクロスレビュー
3. **Phase 3 R2**: R1 の相互レビューを踏まえた収束
4. **Phase 4**: 統合設計書の策定

## 決定

### RawDBBackend Protocol の導入

Ingestion Context 内部に `RawDBBackend` Protocol を定義し、SQLite と JSON の両実装がこれを構造的に満たす設計とする。

- Protocol は `backend.py` に配置し、`insert`, `update`, `get_record`, `list_records`, `accessor`, `close` の 6 メソッドを定義
- 既存の `RawDB`（SQLite 実装）は変更なしでこの Protocol を構造的に満たす
- `modified_since()` は内部 Protocol としては定義せず、docstring 要件とテスト担保で保証する（R2 で合意）
- UUID v7 生成・datetime フォーマット等の共有ユーティリティも `backend.py` に集約し、`raw_db.py` は import 元を変更するのみ

### Backend 選択ロジック

バックエンドの決定は以下の優先順位に従う:

| 優先度 | ソース | 例 |
| :--- | :--- | :--- |
| 1 | 環境変数 `KONKON_RAW_BACKEND` | `KONKON_RAW_BACKEND=json konkon insert ...` |
| 2 | `.konkon/config.toml` の `raw_backend` キー | `raw_backend = 'json'` |
| 3 | 自動検出（env / config いずれも未設定時のみ） | ファイル存在に基づく推定 |

自動検出の振る舞い:

- `raw.db` のみ存在 → `sqlite`
- `raw.json` のみ存在 → `json`
- 両方存在 → CONFIG_ERROR (exit 3) で fail-fast
- どちらもなし → `sqlite`（デフォルト）

明示指定が "Explicit is better than implicit" の原則に基づき最優先。両ファイル存在時の fail-fast は silent data corruption 防止のため（R2 で 3 者合意）。明示指定と既存ファイルの不一致は警告（エラーではない。新規作成や移行中の過渡状態がありうるため）。

### JSON 物理フォーマット

ファイルパスは `.konkon/raw.json`（SQLite の `.konkon/raw.db` と同じ命名規則）。

- `version: 2`（SQLite `PRAGMA user_version` と同一セマンティクス）
- `records` 配列は `(created_at ASC, id ASC)` でソート済みを保証
- `meta` の空表現は `{}`（空オブジェクト）。`null` やキー省略は使用しない
- インデント 2 スペース（Git diff の可読性のため）
- 書き込みは一時ファイル + `os.replace()` でアトミック性を確保
- MVP ではファイルロック不導入。単一プロセスでの使用を前提とする
- レコード数が閾値（10,000）を超えた場合、`insert()` 時に stderr 警告を出す
- 不正 JSON のパースエラー時は CONFIG_ERROR (exit 3) で即座に終了（自動修復は行わない）

### モジュール構成

新規 2 ファイル追加、既存 2 ファイルの内部変更で実現する:

| ファイル | 責務 | 外部からの可視性 |
| :--- | :--- | :--- |
| `backend.py`（新規） | `RawDBBackend` Protocol、共有ユーティリティ | Ingestion 内部のみ |
| `json_db.py`（新規） | JSON バックエンド実装 | Facade のみ |
| `__init__.py`（変更） | Facade。Backend 解決ロジック追加 | 公開 API（シグネチャ変更なし） |
| `raw_db.py`（変更） | import 元の変更のみ | Facade のみ |

`tach.toml` で ACL 境界を維持: `backend.py`, `raw_db.py`, `json_db.py` はいずれも Facade 外部から import 不可。

### CLI 変更

`konkon init` に `--raw-backend` オプションを追加する（`init` 専用。グローバルオプションではない）。

- `--raw-backend json` / `--raw-backend sqlite` 指定時: `.konkon/config.toml` に値を永続化
- 未指定時: `raw_backend` キーを書かない（後方互換性）
- 不正値: 終了コード 2 (USAGE_ERROR)
- DB ファイルは `init` 時に作成しない（初回 `ingest` 時に遅延作成）

### ConfigError の追加

`konkon.core.models` に `ConfigError(KonkonError)` を新規追加する。設定不整合（不正な backend 値、両ファイル同時存在、不正な JSON フォーマット等）を表現する例外クラス。

## 却下した代替案

### `raw_db.py` をリネームする案

| 観点 | 評価 |
| :--- | :--- |
| 概要 | `raw_db.py` を `sqlite_db.py` 等にリネームして命名を統一する |
| 見送り理由 | `05_project_structure.md` の確定レイアウトとの整合性が崩れる。リネームは設計書の「変更」となり波及が大きい。`raw_db.py` を維持しファイル追加のみで実現する方が差分が最小 |

### `modified_since()` を内部 Protocol として正式定義する案

| 観点 | 評価 |
| :--- | :--- |
| 概要 | `RawDBBackend` Protocol または別の内部 Protocol に `modified_since()` を含める |
| 見送り理由 | R2 で合意の上、docstring 要件 + テスト担保の方針を採用。公開 `RawDataAccessor` Protocol には含まれない内部メソッドであり、Protocol の形式的定義よりもテストによる実質的担保が適切と判断 |

### MVP でファイルロックを導入する案

| 観点 | 評価 |
| :--- | :--- |
| 概要 | JSON バックエンドの並行書き込み安全性のために初期実装からロックファイルを導入する |
| 見送り理由 | JSON バックエンドの主要ユースケース（小規模プロジェクト、開発初期）では単一プロセス使用が前提。YAGNI 原則に基づき、マルチプロセス書き込みの需要が発生した時点で導入する |

## 影響

### 波及する設計ドキュメント

| ドキュメント | 変更内容 |
| :--- | :--- |
| `02_interface_contracts.md` | `ConfigError(KonkonError)` を例外クラス一覧に追加 |
| `03_data_model.md` | JSON Backend の物理フォーマット章を追加 |
| `04_cli_conventions.md` | `commands/init.md` に `--raw-backend` オプション仕様を追記 |
| `05_project_structure.md` | ディレクトリレイアウトに `backend.py`, `json_db.py` を追記 |

### 公開 API への影響

| 公開 API | 影響 |
| :--- | :--- |
| `konkon.types` | なし（`RawDBBackend` は公開しない） |
| Ingestion Facade | シグネチャ変更なし |
| Plugin Contract | 変更なし |

### メリット

| メリット | 説明 |
| :--- | :--- |
| **バックエンド選択の柔軟性** | ユースケースに応じて SQLite / JSON を選択可能 |
| **ACL 境界の維持** | Protocol と Facade パターンにより、バックエンド追加が外部に波及しない |
| **既存コードへの影響最小** | `raw_db.py` の import 変更のみ。既存テストは Phase A 完了時点で全パス |
| **将来の拡張性** | `RawDBBackend` Protocol により、新しいバックエンド追加が容易 |

### デメリットとリスク

| デメリット / リスク | 緩和策 |
| :--- | :--- |
| JSON の並行書き込み時のデータ喪失 | ドキュメントに単一プロセス前提を明記。将来ロックファイルで対応 |
| 大規模データでのメモリ圧迫（全件インメモリ） | 件数閾値での stderr 警告。SQLite への切り替えを推奨 |
| Backend 不一致（config と実ファイルのずれ） | 両ファイル存在時は CONFIG_ERROR で fail-fast。不一致は警告で通知 |
