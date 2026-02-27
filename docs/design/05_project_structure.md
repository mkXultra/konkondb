# 05 プロジェクト構成・技術選定 (Project Structure & Technology Choices)

本ドキュメントは `konkon db` の実装基盤に関する技術選定とプロジェクト構成を定義する。

ステータス: **TODO（未着手）**

---

## 確定済み

| 項目 | 決定内容 | 根拠 |
| :--- | :--- | :--- |
| 言語 | Python | PRD / concept.md |
| DB | SQLite 3.38+ | 03_data_model.md（`json_valid()` に 3.38+ が必要） |
| コマンド体系 | `help`, `init`, `insert`, `build`, `search`, `serve` | 04_cli_design.md |
| Plugin 契約 | `build(raw_data: RawDataAccessor) -> None`, `query(request: QueryRequest) -> str \| QueryResult` | 02_interface_contracts.md |
| Raw DB スキーマ | `raw_records` テーブル（`id`, `created_at`, `content`, `meta`） | 03_data_model.md |
| 出力形式 | `text` / `json`、TTY 自動検出 | 04_cli_design.md |

---

## 未決定（要選定）

### 1. CLI フレームワーク

`konkon` CLI のコマンドパーサ・ヘルプ生成・オプション処理に使用するライブラリ。

| 候補 | 概要 |
| :--- | :--- |
| `argparse` | 標準ライブラリ。依存ゼロ。機能は最小限 |
| `click` | デコレータベース。豊富な機能。広く採用 |
| `typer` | click ベース + 型ヒント駆動。モダン |

**選定観点:** 依存の少なさ、`--format` / TTY 自動検出の実装容易性、サブコマンド構成との相性

### 2. プロジェクトマネージャ

依存管理・仮想環境・ビルド・パブリッシュを担うツール。

| 候補 | 概要 |
| :--- | :--- |
| `uv` | Rust 製。高速。pip/venv/pip-tools 互換 |
| `poetry` | 依存解決・ロックファイル・パブリッシュ一体型 |
| `pip` + `setuptools` | 標準。最小構成 |

**選定観点:** 開発速度、CI との相性、ロックファイルの有無

### 3. パッケージ構成

`pyproject.toml` のプロジェクト定義とディレクトリレイアウト。

```
# 候補 A: src レイアウト
konkondb/
├── pyproject.toml
├── src/
│   └── konkon/
│       ├── __init__.py
│       ├── cli/
│       ├── ingestion/
│       ├── transformation/
│       └── serving/
└── tests/

# 候補 B: フラットレイアウト
konkondb/
├── pyproject.toml
├── konkon/
│   ├── __init__.py
│   ├── cli/
│   └── ...
└── tests/
```

**選定観点:** src レイアウトの import 安全性 vs フラットの簡潔さ

### 4. Python バージョン要件

| 候補 | 根拠 |
| :--- | :--- |
| 3.11+ | `tomllib` 標準搭載、`TaskGroup`、パフォーマンス改善 |
| 3.12+ | 型ヒント改善（`type` 文）、f-string の制約緩和 |
| 3.13+ | 最新。Free-threaded mode（実験的） |

**選定観点:** Plugin 開発者の環境を狭めすぎないバランス

### 5. テストフレームワーク

| 候補 | 概要 |
| :--- | :--- |
| `pytest` | デファクトスタンダード。fixture、パラメタライズ |
| `unittest` | 標準ライブラリ。依存ゼロ |

**選定観点:** CLI の統合テスト（subprocess / click.testing）との相性

### 6. 配布方法

| 候補 | 概要 |
| :--- | :--- |
| PyPI + `pip install konkondb` | 標準。最も広い到達範囲 |
| PyPI + `pipx install konkondb` | CLI ツール向け。環境汚染なし |
| Homebrew | macOS 向け。tap 運用が必要 |

**選定観点:** ターゲットユーザー（AI エンジニア / データエンジニア）の環境

### 7. Serving 実装

REST API / MCP サーバーの HTTP フレームワーク。06_serving_adapters.md で詳細設計予定。

| 候補 | 概要 |
| :--- | :--- |
| `FastAPI` | async 対応。OpenAPI 自動生成。広く採用 |
| `Starlette` | FastAPI の基盤。軽量 |
| `http.server` | 標準ライブラリ。依存ゼロ。機能最小限 |

### 8. MCP SDK

MCP (Model Context Protocol) サーバーの実装に使用するライブラリ。

| 候補 | 概要 |
| :--- | :--- |
| `mcp` (公式 Python SDK) | Anthropic 公式。stdio / SSE 対応 |
| 自前実装 | JSON-RPC over stdio。依存ゼロ |

---

## 次のアクション

1. 上記 8 項目を選定する
2. `pyproject.toml` を作成する
3. 06_serving_adapters.md の設計に進む
