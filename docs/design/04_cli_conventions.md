# CLI 共通規約 (CLI Conventions)

本ドキュメントは `konkon db` の CLI 共通規約を定義する。個別コマンドの仕様は [commands/](./commands/) を参照。

設計の前提:
- `prd.md` のコマンド体系（help, init, insert, update, build, search, raw, serve）
- `01_conceptual_architecture.md` の境界設計（Bounded Contexts / ACL）
- `02_interface_contracts.md` の Plugin Contract（`build()`, `query()`, 型定義）
- `03_data_model.md` の Raw DB スキーマ（UUID v7, RFC3339 UTC, DELETE なし）

---

## 1. 目的と CLI の位置づけ

### 1.1 目的

- 開発者のイテレーションを高速化する CLI のインターフェースを明確化する
- `01` の境界設計（ACL）を CLI レベルの責務分離として具体化する
- `02/03` で確定した契約・データモデルと矛盾しない入出力・終了コードを定義する

### 1.2 スコープ

- CLI 共通規約（stdout/stderr 分離、出力フォーマット、終了コード、Plugin Host）
- serve 共通仕様（ライフサイクル、共通オプション）
- サブコマンドグループの共通制約
- Plugin Contract（[02_interface_contracts.md](./02_interface_contracts.md)）/ Raw DB（[03_data_model.md](./03_data_model.md)）との接続点

### 1.3 非スコープ

- 個別コマンドの構文・引数・オプション → [commands/](./commands/)
- Python 実装（argparse/typer/click 等の選定）
- REST API の完全な OpenAPI 仕様
- MCP ツールの完全なスキーマ仕様
- User Plugin 内部の Context Store スキーマ

### 1.4 CLI のアーキテクチャ上の役割

`01_conceptual_architecture.md` の C4 モデルで定義されている通り、**CLI はどの Bounded Context にも属さない「オーケストレーター」**である。

```text
Developer ──▶ [konkon CLI] ──▶ Ingestion Context  (insert, update)
                            ──▶ Transformation Context (build, search)
                            ──▶ Serving Context  (serve)
```

境界ルール（MUST）:
- CLI は各コンテキストの公開インターフェースを叩くだけであり、Raw DB や Context Store に直接アクセスしない
- CLI は User Plugin に Raw DB の接続オブジェクトを渡してはならない
- `serve` 起動時も CLI はサーバープロセスの起動・停止のみを行い、プロトコル変換は Serving Context に委譲する

---

## 2. グローバル規約

### 2.1 stdout / stderr の使い分け

| ストリーム | 用途 | 例 |
| :--- | :--- | :--- |
| **stdout** | **データ出力のみ**。パイプ・リダイレクト可能な構造化出力 | `search` の結果、`insert` の Record ID |
| **stderr** | ログ、進捗、診断メッセージ、エラー。人間向けの情報すべて | `[INFO] Build completed in 2.3s`、エラートレースバック |

**設計根拠:** `konkon search "query" | jq .` のようなパイプライン利用を安全にするため、stdout をデータ専用に厳格に分離する。

**安定性契約:**
- `--format text` の出力は人間向けであり、後方互換性を保証しない
- `--format json` の出力は安定 API とし、セマンティックバージョニングに従って管理する

**Plugin の print() 出力（MUST）:**
Plugin はフレームワーク内で in-process 実行されるため、Plugin の `print()` 出力は CLI の stdout 契約を破壊しうる。CLI は Plugin の stdout を **stderr にリダイレクトしなければならない（MUST）**。

### 2.2 出力フォーマット

`insert`, `build`, `search` は `--format` オプションをサポートする。`build` は json モードでのみ stdout にステータス情報を出力する（text モードではサマリーは stderr に出力される）。`init` と `serve` は stdout にデータ出力を行わないため、`--format` が指定された場合は無視される（エラーとしない）。

| 値 | 説明 | デフォルト |
| :--- | :--- | :--- |
| `text` | 人間可読なプレーンテキスト | stdout が TTY の場合 |
| `json` | 機械可読な JSON | stdout が TTY でない場合（パイプ・リダイレクト） |

**TTY 自動検出ルール:**
- stdout が TTY の場合: デフォルトは `text`
- stdout が TTY でない場合（パイプ・リダイレクト）: デフォルトは `json`
- `--format` が明示された場合: 常にそちらを優先

**設計根拠:** `konkon search "query"` は人間向け表示、`konkon search "query" | jq .` は自動で JSON。開発者の日常的なパイプ利用を自然にサポートする。スクリプトでは `--format` を常に明示することを推奨する。

### 2.3 終了コード

| コード | 名前 | 意味 |
| :--- | :--- | :--- |
| `0` | `SUCCESS` | 正常終了 |
| `1` | `GENERAL_ERROR` | 上記のいずれにも分類されない一般エラー（未捕捉例外、想定外クラッシュを含む） |
| `2` | `USAGE_ERROR` | 引数・オプションの誤り、コマンドの誤用 |
| `3` | `CONFIG_ERROR` | プロジェクト未初期化、`konkon.py` の欠損・ロード失敗、Plugin Contract 不適合、Raw DB スキーマ不一致、サーバー起動失敗 |
| `4` | `BUILD_ERROR` | `build()` 実行中のエラー（`BuildError` + Plugin 内未捕捉例外） |
| `5` | `QUERY_ERROR` | `query()` 実行中のエラー（`QueryError` + Plugin 内未捕捉例外、戻り値型不正） |

**設計根拠:**
- `2` は UNIX 慣習（`sysexits.h` の `EX_USAGE` 相当）に従う
- `02_interface_contracts.md` で `BuildError` / `QueryError` が明確に分離されている以上、CLI でも `4` / `5` で区別する
- `3` は「Plugin のロジックのエラー」ではなく「プロジェクト構成・環境のエラー」を表す
- `serve` 実行中の個々の `QueryError` はプロセス終了コードに直結しない（HTTP/MCP エラー応答に翻訳される）

**SIGINT の扱い:**
- **one-shot コマンド**（`init`, `insert`, `build`, `search`）: シェル慣習に従い `128 + signal_number`（通常 `130`）が返る。CLI 側で明示的に `sys.exit(130)` する必要はない
- **`serve`**: SIGINT / SIGTERM をハンドリングしグレースフルシャットダウンを行った場合は終了コード `0`（正常停止）

### 2.4 プロジェクト・ディスカバリ

`init` 以外のすべてのコマンドは、実行前にプロジェクトルートを特定する必要がある。

**解決順序:**
1. `--project-dir` オプションが指定されている場合、そのパスを使用
2. カレントディレクトリから親方向に `konkon.py` を探索（ファイルシステム root まで）
3. 見つからない場合、終了コード `3` で以下のメッセージを stderr に出力:

```
Error: konkon.py not found. Run 'konkon init' to create a project, or use '--project-dir' to specify the project root.
```

**プロジェクトルートの構成:**
```
<project-root>/
├── konkon.py          # Plugin（build() / query()）
└── .konkon/
    └── raw.db         # Raw DB（初回 insert 時に遅延作成）
```

### 2.5 グローバルオプション

すべてのコマンドで共通して使用可能なオプション。

| オプション | 短縮形 | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- | :--- |
| `--project-dir` | `-C` | `PATH` | (自動検出) | プロジェクトルートのパスを明示指定 |
| `--verbose` | `-v` | flag | `false` | stderr への詳細ログ出力を有効化 |
| `--quiet` | `-q` | flag | `false` | stderr への出力を抑制（エラーを除く） |
| `--format` | | `text\|json` | (TTY 自動検出) | データ出力のフォーマット |
| `--no-color` | | flag | `false` | stderr の色付き表示を無効化 |
| `--help` | `-h` | flag | — | ヘルプ表示 |
| `--version` | | flag | — | CLI バージョン表示 |

`--verbose` と `--quiet` は排他。両方指定された場合は終了コード `2`。

### 2.6 Plugin Host の共通振る舞い

`build`, `search`, `serve` はいずれも Plugin Host を経由して `konkon.py` の関数を呼び出す。以下の振る舞いは全コマンドで共通である。

#### Load と Contract 検証

1. `konkon.py` をインポートし、`build` と `query` の両関数が**存在し呼び出し可能**であることを検証する（[02_interface_contracts.md §1](./02_interface_contracts.md)）。型注釈の有無や引数名は検証しない
2. いずれかの関数が欠落している場合、終了コード `3` (CONFIG_ERROR) でエラー

#### CWD 保証

Plugin の Invoke 前に、カレントディレクトリを Plugin ファイルが存在するディレクトリに設定する（`02_interface_contracts.md` のフレームワーク保証: 「CWD は `konkon.py` があるディレクトリ」）。デフォルト（`--plugin` 未指定）ではプロジェクトルートと一致する。`--plugin` で別パスの Plugin を指定した場合、CWD はその Plugin ファイルの親ディレクトリに設定される。

#### sync / async 両対応

Plugin 関数の呼び出し時、`inspect.iscoroutinefunction()` で非同期判定を行う。非同期の場合は one-shot コマンド（`build`, `search`）では `asyncio.run()` で実行する。戻り値が awaitable の場合（`inspect.isawaitable(result)`）も同様に await する。

サーバーモード（`serve`）では、同期 `query()` は `asyncio.to_thread()` でオフロードされる（`02_interface_contracts.md` セクション 2.1）。

---

## 3. 例外とエラーメッセージの翻訳方針

### 3.1 例外翻訳表

| 発生源 | 例外 | `build` | `search` | `serve api` | `serve mcp` |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Plugin | `BuildError` | stderr メッセージ + exit `4` | — | — | — |
| Plugin | `QueryError` | — | stderr メッセージ + exit `5` | HTTP `422` | MCP エラー応答 |
| Plugin | 未捕捉例外 | stderr トレースバック + exit `4` | stderr トレースバック + exit `5` | HTTP `500` | MCP エラー応答 |
| Host/CLI | Plugin ロード失敗 | exit `3` | exit `3` | 起動せず exit `3` | 起動せず exit `3` |
| Host/CLI | フレームワーク内部エラー | exit `1` | exit `1` | プロセス crash exit `1` | プロセス crash exit `1` |
| CLI Parser | 入力不正 | exit `2` | exit `2` | exit `2` | exit `2` |

### 3.2 エラーメッセージの方針

- `KonkonError` サブクラス（想定エラー）: `[ERROR] <ExceptionClass>: <message>` の形式。トレースバックは `--verbose` 時のみ
- 未捕捉例外（予期しないクラッシュ）: `[ERROR] Unexpected error: <message>` + フルトレースバック
- Plugin の `print()` 出力は stderr にリダイレクトされる（stdout のデータ純度を保護するため）

### 3.3 代表的なエラーメッセージ

```
# konkon.py が見つからない (exit 3)
Error: konkon.py not found. Run 'konkon init' to create a project, or use '--project-dir' to specify the project root.

# konkon.py に build() がない (exit 3)
Error: Plugin contract violation — konkon.py must define both 'build()' and 'query()' functions. Missing: build

# build() 中の BuildError (exit 4)
[ERROR] BuildError: Failed to initialize vector store: connection refused

# build() 中の未捕捉例外 (exit 4)
[ERROR] Unexpected plugin error during build:
Traceback (most recent call last):
  File "/path/to/konkon.py", line 12, in build
    ...
KeyError: 'missing_key'

# query() が None を返した (exit 5)
[ERROR] Plugin contract violation: query() returned None. Must return str or QueryResult.

# Raw DB スキーマ不一致 (exit 3)
Error: Raw DB schema version mismatch (expected: 2, found: 1). Please update konkon.
```

---

## 4. serve 共通仕様

`serve api` と `serve mcp` で共有される仕様を定義する。モード固有の仕様は各 Command Spec（[commands/serve-api.md](./commands/serve-api.md)、[commands/serve-mcp.md](./commands/serve-mcp.md)）を参照。

### 4.1 シグネチャとモード選択

```
konkon serve api [OPTIONS]
konkon serve mcp [OPTIONS]
```

PRD 互換のエイリアス:
- `konkon serve --api` は `konkon serve api` と等価
- `konkon serve --mcp` は `konkon serve mcp` と等価

`api` / `mcp` のどちらも指定されていない、または両方指定された場合は終了コード `2`。

### 4.2 共通オプション

| オプション | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `--plugin` | `PATH` | `<project-dir>/konkon.py` | Plugin ファイルパス |
| `--log-level` | `ENUM` | `info` | ログレベル（`error`, `warn`, `info`, `debug`） |

### 4.3 サーバーのライフサイクル

1. **起動時**: Plugin Host が `konkon.py` をロードし、Contract を検証する（セクション 2.6）。検証失敗時はサーバーを起動せず終了コード `3` で終了
2. **実行中**: 各リクエストごとに `query()` を Invoke する。同期 `query()` は `asyncio.to_thread()` でオフロードされる（セクション 2.6）。**注意:** サーバーモードでは `query()` が同時に複数回呼ばれる可能性がある（`02_interface_contracts.md` セクション 2.1）。Context Store への同時アクセスに対するスレッドセーフ性・非同期安全性の確保は開発者の責任となる
3. **停止**: `SIGINT` (Ctrl+C) / `SIGTERM` を受信した場合、実行中のリクエストの完了を待ち（グレースフルシャットダウン）、終了コード `0` で終了する（正常停止として扱う）

### 4.4 stderr 出力

| レベル | 出力例 |
| :--- | :--- |
| INFO | `[INFO] Starting API server on 127.0.0.1:8080` |
| INFO | `[INFO] Plugin loaded: /path/to/konkon.py` |
| INFO | `[INFO] POST /query — 200 (45ms)` |
| ERROR | `[ERROR] POST /query — 422: QueryError: ...` |

### 4.5 終了コード

共通終了コード（`0`, `1`, `2`）は §2.3 参照。serve 共通の終了コード:

| コード | 条件 |
| :--- | :--- |
| `3` | `konkon.py` 未検出 / ロード失敗 / Contract 不適合 / ポート競合等の起動失敗 |

**補足:** リクエスト単位の `QueryError` はサーバーを停止させない。HTTP 422 / MCP エラー応答に翻訳されてプロセスは継続する。

---

## 5. サブコマンドグループ共通規約

### 5.1 raw グループ

`konkon raw` はデバッグ・運用向けの**読み取り専用**サブコマンドグループである。

共通制約:
- **Ingestion Context** を読み取り専用で呼び出す
- いずれのサブコマンドも **Raw DB を新規作成しない**（Raw DB ファイルが存在しない場合は空結果を返す）

個別コマンドの仕様は [commands/raw-list.md](./commands/raw-list.md)、[commands/raw-get.md](./commands/raw-get.md) を参照。
