# 05 プロジェクト構成・技術選定 (Project Structure & Technology Choices)

本ドキュメントは `konkon db` の実装基盤に関する技術選定とプロジェクト構成を定義する。

ステータス: **確定（1〜5 選定済み / 6〜8 は後日選定）**

---

## 確定済み

| # | 項目 | 決定内容 | 根拠 |
| :--- | :--- | :--- | :--- |
| — | 言語 | Python | PRD / concept.md |
| — | DB | SQLite 3.38+ | 03_data_model.md（`json_valid()` に 3.38+ が必要） |
| — | コマンド体系 | `help`, `init`, `insert`, `update`, `build`, `search`, `raw`, `serve` | 04_cli_design.md（`ask` は MVP 外・将来拡張） |
| — | Plugin 契約 | `build(raw_data: RawDataAccessor) -> None`, `query(request: QueryRequest) -> str \| QueryResult` | 02_interface_contracts.md |
| — | Raw DB スキーマ | `raw_records` テーブル（`id`, `created_at`, `updated_at`, `content`, `meta`） | 03_data_model.md |
| — | 出力形式 | `text` / `json`、TTY 自動検出 | 04_cli_design.md |
| 1 | CLI フレームワーク | `click` | サブコマンド構成との相性、`CliRunner` によるテスト容易性、Datasette 等の採用実績 |
| 2 | プロジェクトマネージャ | `uv` | Rust 製で高速、ロックファイルあり、pip 互換、`uv run` で Poetry 相当の DX |
| 3 | パッケージ構成 | src レイアウト | import 安全性（未インストール時の誤 import 防止） |
| 4 | Python バージョン | 3.11+ | `tomllib` 標準搭載、Plugin 開発者の門戸を狭めすぎないバランス |
| 5 | テストフレームワーク | `pytest` | デファクトスタンダード、`click.testing.CliRunner` との相性 |

---

## エントリポイント

```toml
[project.scripts]
konkon = "konkon.cli:main"
```

`uv sync` により `.venv/bin/konkon` が生成され、`uv run konkon <command>` で実行可能。

---

## ディレクトリレイアウト

```
konkondb/                       # プロジェクトルート (git root)
├── pyproject.toml
├── uv.lock
├── src/
│   └── konkon/
│       ├── __init__.py
│       ├── types.py            # 公開型の re-export (Plugin 開発者向け API)
│       │                       #   RawDataAccessor, RawRecord,
│       │                       #   QueryRequest, QueryResult,
│       │                       #   KonkonError, BuildError, QueryError
│       ├── cli/                # CLI層 (click)
│       │   ├── __init__.py     #   main group + エントリポイント
│       │   ├── init.py
│       │   ├── insert.py
│       │   ├── update.py
│       │   ├── build.py
│       │   ├── search.py
│       │   ├── raw.py          #   raw サブコマンドグループ (raw list 等)
│       │   └── serve.py        #   serve api / serve mcp サブコマンド
│       ├── core/               # コアロジック
│       │   ├── __init__.py
│       │   ├── models.py       #   RawRecord, QueryRequest, QueryResult 等の定義
│       │   ├── instance.py     #   プロジェクトルート解決、パス定数
│       │   ├── ingestion/      #   Ingestion Context (Raw DB)
│       │   │   ├── __init__.py #     facade (ingest, update, list_records, get_accessor)
│       │   │   └── raw_db.py   #     Raw DB アクセス (RawDataAccessor 実装)
│       │   └── transformation/ #   Transformation Context (Plugin Host)
│       │       ├── __init__.py #     facade (run_build, run_query)
│       │       └── plugin_host.py  # Plugin ロード・実行
│       └── serving/            # Serving層 (注1)
│           ├── __init__.py
│           ├── api.py          #   REST API サーバー
│           └── mcp.py          #   MCP サーバー
└── tests/
    ├── conftest.py
    ├── test_cli/
    ├── test_core/
    └── test_serving/
```

参考: [Datasette](https://github.com/simonw/datasette) — SQLite ベースの CLI + API サーバー (click 採用)

### `core/` パッケージと Bounded Context

`core/` は 01_conceptual_architecture.md で定義された Bounded Context に対応し、`ingestion/` と `transformation/` の2サブパッケージに分割されている:

- **`core/ingestion/`**: Ingestion Context。Raw DB へのアクセスを担う。facade（`__init__.py`）が `ingest`, `update`, `list_records`, `get_accessor` を公開
- **`core/transformation/`**: Transformation Context。Plugin Host と build/query のオーケストレーションを担う。facade（`__init__.py`）が `run_build`, `run_query` を公開
- **`core/instance.py`**: プロジェクトルートの解決（`resolve_project()`）やパス定数（`KONKON_DIR`, `RAW_DB_FILE` 等）を提供するシステムレベルのモジュール

ACL の担保:
- `transformation/` は `ingestion/` の facade 経由でのみ Raw DB にアクセスする（`raw_db.py` の内部実装に直接依存しない）
- 両者間のデータ受け渡しは `RawDataAccessor` プロトコル（ACL #1）を経由する
- モジュール境界は `tach.toml` で静的に検証される

### 注1: `serving/` パッケージの確定範囲

`serving/` のディレクトリ名とファイル名（`api.py`, `mcp.py`）は仮確定。01_conceptual_architecture.md の Serving Context に対応し、ステートレスなプロトコルアダプターとして機能する。内部で使用する HTTP フレームワーク（7. Serving 実装）と MCP SDK（8. MCP SDK）は未選定であり、06_serving_adapters.md の設計時に確定する。

### Plugin 開発者の公開 API (`konkon.types`)

`types.py` は `core/models.py` で定義された型と例外を re-export する薄いモジュール。Plugin 開発者は以下のインポートパスを使用する（04_cli_design.md の `konkon init` テンプレートと一致）:

```python
from konkon.types import RawDataAccessor, QueryRequest, QueryResult
from konkon.types import BuildError, QueryError
```

内部実装の配置（`core/models.py`）が変更されても、`konkon.types` の公開 API は安定する。

---

## 未決定（後日選定）

以下は `konkon serve` の実装時に選定する。06_serving_adapters.md と合わせて決定予定。

### 6. 配布方法

| 候補 | 概要 |
| :--- | :--- |
| PyPI + `pip install konkondb` | 標準。最も広い到達範囲 |
| PyPI + `pipx install konkondb` / `uv tool install konkondb` | CLI ツール向け。環境汚染なし |
| Homebrew | macOS 向け。tap 運用が必要 |

**選定観点:** ターゲットユーザー（AI エンジニア / データエンジニア）の環境

### 7. Serving 実装

REST API / MCP サーバーの HTTP フレームワーク。

| 候補 | 概要 |
| :--- | :--- |
| `FastAPI` | async 対応。OpenAPI 自動生成。広く採用 |
| `Starlette` | FastAPI の基盤。軽量 |
| `http.server` | 標準ライブラリ。依存ゼロ。機能最小限 |

### 8. MCP SDK

| 候補 | 概要 |
| :--- | :--- |
| `mcp` (公式 Python SDK) | Anthropic 公式。stdio / SSE 対応 |
| 自前実装 | JSON-RPC over stdio。依存ゼロ |

---

## 次のアクション

1. ~~上記 8 項目を選定する~~ → 1〜5 選定済み
2. `pyproject.toml` を作成し、プロジェクト骨格をセットアップする
3. CLI (help / init / insert) を実装する
4. 06_serving_adapters.md の設計に進む（serve 実装時に 6〜8 を選定）
