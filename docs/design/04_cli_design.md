# 04 CLI 詳細設計 (CLI Design)

本ドキュメントは `konkon db` の CLI コマンド体系の詳細仕様を定義する。

設計の前提:
- `prd.md` のコマンド体系（help, init, insert, update, build, search, raw, serve）
- `01_conceptual_architecture.md` の境界設計（Bounded Contexts / ACL）
- `02_interface_contracts.md` の Plugin Contract（`build()`, `query()`, 型定義）
- `03_data_model.md` の Raw DB スキーマ（UUID v7, RFC3339 UTC, DELETE なし）

---

## 1. 目的とスコープ

### 1.1 目的

- 開発者のイテレーションを高速化する CLI のインターフェースを明確化する
- `01` の境界設計（ACL）を CLI レベルの責務分離として具体化する
- `02/03` で確定した契約・データモデルと矛盾しない入出力・終了コードを定義する

### 1.2 スコープ

- CLI コマンドの構文、引数、オプション
- stdout / stderr の使い分けと出力フォーマット
- 終了コード体系
- コマンドごとの Bounded Context / レイヤー対応
- Plugin Contract / Raw DB との接続点

### 1.3 非スコープ

- Python 実装（argparse/typer/click 等の選定）
- REST API の完全な OpenAPI 仕様
- MCP ツールの完全なスキーマ仕様
- User Plugin 内部の Context Store スキーマ

---

## 2. CLI の位置づけとアーキテクチャ上の役割

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

## 3. グローバル規約

### 3.1 stdout / stderr の使い分け

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

### 3.2 出力フォーマット

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

### 3.3 終了コード

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

### 3.4 プロジェクト・ディスカバリ

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

### 3.5 グローバルオプション

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

### 3.6 Plugin Host の共通振る舞い

`build`, `search`, `serve` はいずれも Plugin Host を経由して `konkon.py` の関数を呼び出す。以下の振る舞いは全コマンドで共通である。

#### Load と Contract 検証

1. `konkon.py` をインポートし、`build` と `query` の両関数が**存在し呼び出し可能**であることを検証する（`02_interface_contracts.md` セクション 2.1）。型注釈の有無や引数名は検証しない
2. いずれかの関数が欠落している場合、終了コード `3` (CONFIG_ERROR) でエラー

#### CWD 保証

Plugin の Invoke 前に、カレントディレクトリを Plugin ファイルが存在するディレクトリに設定する（`02_interface_contracts.md` のフレームワーク保証: 「CWD は `konkon.py` があるディレクトリ」）。デフォルト（`--plugin` 未指定）ではプロジェクトルートと一致する。`--plugin` で別パスの Plugin を指定した場合、CWD はその Plugin ファイルの親ディレクトリに設定される。

#### sync / async 両対応

Plugin 関数の呼び出し時、`inspect.iscoroutinefunction()` で非同期判定を行う。非同期の場合は one-shot コマンド（`build`, `search`）では `asyncio.run()` で実行する。戻り値が awaitable の場合（`inspect.isawaitable(result)`）も同様に await する。

サーバーモード（`serve`）では、同期 `query()` は `asyncio.to_thread()` でオフロードされる（`02_interface_contracts.md` セクション 2.1）。

---

## 4. コマンド詳細仕様

### 4.0 `konkon help` — ヘルプ表示

#### 概要

コマンド一覧または個別コマンドの詳細ヘルプを表示する。`konkon --help` と同等。

#### シグネチャ

```
konkon help [COMMAND]
```

#### 引数

| 引数 | 必須 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `COMMAND` | No | — | ヘルプを表示するコマンド名（`init`, `insert`, `update`, `build`, `search`, `raw`, `serve`） |

#### 振る舞い

1. `COMMAND` 未指定時: 全コマンドの概要一覧を stdout に出力する
2. `COMMAND` 指定時: 該当コマンドの詳細ヘルプ（シグネチャ、オプション、説明）を stdout に出力する
3. 不明な `COMMAND` が指定された場合: stderr にエラーメッセージを出力し、終了コード `2`

#### 出力先

- ヘルプ本文は **stdout** に出力する（`konkon help | less` 等のパイプ利用を可能にするため）
- エラーメッセージは stderr に出力する

#### `--help` との関係

- `konkon --help` は `konkon help` と同等
- `konkon <command> --help` は `konkon help <command>` と同等
- `--help` はグローバルオプション（セクション 3.5）として全コマンドで利用可能

#### 終了コード

| コード | 条件 |
| :--- | :--- |
| `0` | 正常にヘルプを表示 |
| `2` | 不明なコマンド名が指定された |

---

### 4.1 `konkon init` — プロジェクト初期化

#### 概要

プロジェクトのひな形（`konkon.py` テンプレート、`.konkon/` ディレクトリ）を生成する。

#### Bounded Context の対応

**どのコンテキストにも属さない（システムレベル）。** ファイルシステムへのテンプレート書き込みのみを行う。Raw DB の作成はこの時点では行わない（初回 `insert` 時に遅延作成）。

#### シグネチャ

```
konkon init [OPTIONS] [DIRECTORY]
```

#### 引数

| 引数 | 必須 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `DIRECTORY` | No | `.` (カレントディレクトリ) | プロジェクトを初期化するディレクトリ |

#### オプション

| オプション | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `--force` | flag | `false` | 既存の `konkon.py` を上書きする |

#### 生成されるファイル

```
<DIRECTORY>/
├── konkon.py          # Plugin テンプレート（build() と query() のスケルトン）
└── .konkon/           # Raw DB 格納ディレクトリ（空）
```

#### `konkon.py` テンプレートの内容

`02_interface_contracts.md` の Plugin Contract に準拠したスケルトンコードを生成する。

```python
"""konkon db plugin — build() と query() を実装してください。"""

from konkon.types import RawDataAccessor, QueryRequest, QueryResult


def build(raw_data: RawDataAccessor) -> None:
    """
    Raw Data から Context Store を構築します。
    raw_data をイテレートして、あなた独自の Context DB を作成してください。
    """
    for record in raw_data:
        # record.id, record.content, record.created_at 等が利用可能
        pass


def query(request: QueryRequest) -> str | QueryResult:
    """
    検索リクエストを受け取り、Context Store から結果を返します。
    request.query に検索文字列、request.params に追加パラメータが入ります。
    """
    return ""
```

#### 振る舞い

1. `DIRECTORY` が存在しない場合、ディレクトリを作成する
2. `konkon.py` が既に存在し `--force` がない場合、終了コード `2` でエラー（`--force` を付けずに既存プロジェクトで実行した操作ミス）
3. `.konkon/` が既に存在する場合、そのまま維持（冪等）
4. 成功時、stderr に初期化完了メッセージを出力。stdout には何も出力しない

#### 終了コード

| コード | 条件 |
| :--- | :--- |
| `0` | 正常に初期化完了 |
| `2` | 引数エラー、`konkon.py` が既に存在（`--force` なし） |

---

### 4.2 `konkon insert` — 生データの投入

#### 概要

外部の生データを Raw DB に `Raw Record` として永続化する。

#### Bounded Context の対応

**Ingestion Context** を呼び出す。`03_data_model.md` で定義された Raw DB スキーマ（`raw_records` テーブル）への INSERT を行う。

```text
Developer ──▶ CLI ──▶ Ingestion Context ──▶ Raw DB (INSERT)
```

#### シグネチャ

```
konkon insert [OPTIONS] [TEXT]
```

#### 引数

| 引数 | 必須 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `TEXT` | No | — | 投入するテキスト（省略時は stdin から取得） |

#### オプション

| オプション | 短縮形 | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- | :--- |
| `--source-uri` | `-s` | `TEXT` | `NULL` | `meta.source_uri` に記録する。`--meta source_uri=...` のショートカット |
| `--content-type` | `-t` | `TEXT` | `NULL` | `meta.content_type` に記録する。`-s` に拡張子があれば推定、なければ `NULL` |
| `--meta` | `-m` | `KEY=VALUE` | — | `meta` JSON に任意のキーを追加。複数回指定可 |
| `--encoding` | | `TEXT` | `utf-8` | 標準入力のデコード方式 |
| `--raw-db` | | `PATH` | `<project-dir>/.konkon/raw.db` | Raw DB ファイルパス |

**バリデーション:**
- `TEXT` と stdin（非TTY）が同時に与えられた場合は終了コード `2`
- 入力ソースの優先順位:
  1. `TEXT` 引数がある場合は `TEXT` を `content` として使用
  2. `TEXT` 引数がなく stdin が非TTYの場合は stdin を EOF まで読み取り使用
  3. `TEXT` も stdin もない場合は終了コード `2`
- `-s` / `-t` と `--meta` が同名キーで競合した場合は `-s` / `-t` を優先する

#### 入力の受け取り

- `konkon insert` は **1回の実行で1レコード** を投入する
- `id`: システムが UUID v7 を生成（`03_data_model.md` セクション 5 準拠）
- `created_at`: 投入時刻を UTC で記録（RFC3339 固定長 27 文字、`03_data_model.md` セクション 6 準拠）
- `meta` の組み立て:
  - `--meta KEY=VALUE` で任意キーを追加（複数指定可）
  - `-s/--source-uri` は `meta.source_uri` に設定
  - `-t/--content-type` は `meta.content_type` に設定（未指定時は `-s` の拡張子から推定できる場合のみ設定）

#### stdout 出力

投入された `Raw Record` の情報を出力する。text フォーマットは簡潔さを優先し、`meta` の詳細は省略する。全フィールドを確認するには `--format json` を使用する。

**text フォーマット:**
```
Ingested: 019516a0-3b40-7f8a-b12c-4e5f6a7b8c9d
```

**json フォーマット:**
```json
{"id": "019516a0-3b40-7f8a-b12c-4e5f6a7b8c9d", "created_at": "2026-02-27T12:34:56.789012Z", "meta": {"source_uri": "/path/to/notes.md", "content_type": "text/markdown"}}
```

JSON フォーマットは JSON オブジェクトを1行で出力する。

#### 終了コード

| コード | 条件 |
| :--- | :--- |
| `0` | 正常に投入された |
| `1` | 一般エラー（DB アクセス失敗、入力読み取り失敗等） |
| `2` | 引数エラー |
| `3` | プロジェクト未初期化、Raw DB スキーマ不一致 |

#### Raw DB の遅延作成

Raw DB ファイル（`.konkon/raw.db`）が存在しない場合、`insert` コマンドの初回実行時に `03_data_model.md` セクション 12 の完全 DDL を実行してスキーマを自動作成する。DB 接続時には `03_data_model.md` で規定された PRAGMA（`journal_mode=WAL`, `busy_timeout=5000`, `foreign_keys=ON`, `synchronous=NORMAL`）を毎回適用し、`PRAGMA user_version` でスキーマバージョンを検証する。既知のバージョン差に対しては自動マイグレーションを適用する。未知のバージョン（CLI より新しいスキーマ等）の場合のみ終了コード `3` でエラーとする。

#### 03 との整合性

- `id`: UUID v7 生成（`03` セクション 5 準拠）
- `created_at`: RFC3339 UTC 固定長 27 文字（`03` セクション 6 準拠）
- `meta` JSON の正規化（空オブジェクト `{}` → `NULL`、`json_valid` + `json_type='object'` の CHECK 制約に適合）
- DELETE なし（MVP）
- 内容重複の排除（dedup）は行わない

---

### 4.3 `konkon build` — Context DB の構築

#### 概要

開発者が `konkon.py` に定義した `build()` 関数を実行し、Raw Data から Context DB を構築・更新する。

#### Bounded Context の対応

**Transformation Context** を呼び出す。Plugin Host が `konkon.py` をロードし、Plugin Contract（`02_interface_contracts.md`）に従って `build()` を Invoke する。

```text
Developer ──▶ CLI ──▶ Transformation Context (Plugin Host)
                          │
                          ├──▶ Ingestion Context (RawDataAccessor: 読み取り専用)
                          │
                          └──▶ User Plugin Logic (build() の実行)
                                   │
                                   └──▶ Context Store (開発者定義の書き込み先)
```

#### シグネチャ

```
konkon build [OPTIONS]
```

#### オプション

| オプション | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `--full` | flag | `false` | フルビルド。`build()` に全 Raw Record を渡す（デフォルト: 前回ビルド以降の変更分のみ） |
| `--plugin` | `PATH` | `<project-dir>/konkon.py` | Plugin ファイルパス |
| `--raw-db` | `PATH` | `<project-dir>/.konkon/raw.db` | Raw DB ファイルパス |

デフォルトの差分ビルド: `konkon build` は `.konkon/last_build` ファイルに記録された前回のビルド開始時刻と、各レコードの `updated_at` を比較し、変更されたレコードのみを `build()` に渡す。チェックポイントにビルド完了時刻ではなく開始時刻を使用することで、ビルド実行中に発生した更新が次回ビルドで取りこぼされることを防ぐ。初回ビルド（`last_build` ファイルが存在しない場合）は自動的にフルビルドとなる。`--full` を指定すると、すべてのレコードが渡される。

#### Plugin Host の振る舞い

セクション 3.6 の共通振る舞いに加え、以下の手順で実行する。

1. **Load / Contract 検証**: セクション 3.6 に従う
2. **CWD 設定**: セクション 3.6 の CWD 保証に従い、Plugin ファイルのディレクトリに設定する
3. **Invoke**: `build(raw_data)` を呼び出す（sync/async 処理はセクション 3.6 に従う）
4. **エラーハンドリング**: `BuildError` は診断メッセージ付きで stderr に出力。未捕捉例外はトレースバック付きで stderr に出力

#### 中断時の振る舞い

`build()` が SIGINT / SIGTERM により中断された場合、ビルドは失敗として扱われる。フレームワークは Context Store のロールバックを **一切行わない**（`02_interface_contracts.md` セクション 2.3, 2.4）。開発者は Context Store のアトミック更新パターン（テンポラリファイル → リネーム）を採用することを推奨する。

#### stdout 出力

- **text モード**: stdout には何も出力しない。サマリーは stderr に出力する
- **json モード**: ビルド結果のステータス JSON を stdout に出力する

**json 成功時:**
```json
{
  "status": "ok",
  "mode": "full",
  "plugin": "/path/to/konkon.py",
  "raw_db": "/path/to/.konkon/raw.db",
  "duration_ms": 1234
}
```

**json 失敗時（exit `4`）:**
```json
{
  "status": "error",
  "error": "BuildError",
  "message": "Failed to connect to vector DB"
}
```

未捕捉例外の場合は `"error": "UnexpectedError"` とする。text モードでは引き続き stdout は空（エラーは stderr のみ）。

#### stderr 出力

| レベル | 出力例 |
| :--- | :--- |
| INFO | `[INFO] Loading plugin: /path/to/konkon.py` |
| INFO | `[INFO] Raw records: 1,234 (full build)` |
| INFO | `[INFO] Build completed in 2.3s` |
| ERROR | `[ERROR] BuildError: Failed to connect to vector DB` |

`--verbose` 指定時は DEBUG レベルのログも表示される。

#### 終了コード

| コード | 条件 |
| :--- | :--- |
| `0` | `build()` が正常に完了 |
| `1` | 予期しないエラー（フレームワーク側） |
| `2` | 引数エラー |
| `3` | `konkon.py` 未検出 / ロード失敗 / Contract 不適合 / Raw DB スキーマ不一致 |
| `4` | `build()` 実行中のエラー（`BuildError` または Plugin 内の未捕捉例外） |

#### 02/03 との整合性

- `build(raw_data: RawDataAccessor) -> None` の契約に厳密に従う（sync/async 両対応）
- 差分ビルドでは `.konkon/last_build` の時刻を基準に `updated_at` でフィルタする
- Accessor の順序契約（`ORDER BY created_at ASC, id ASC`）を変更しない
- Plugin に Raw DB 接続や `raw_records` テーブル名を露出しない（ACL #1）

---

### 4.4 `konkon search` — コンテキスト検索

#### 概要

開発者が `konkon.py` に定義した `query()` 関数を実行し、Context Store から結果を取得して stdout に出力する。ローカル開発・デバッグ用の対話的コマンド。

#### Bounded Context の対応

**Transformation Context** → **User Plugin Logic** を呼び出す。`serve` と同じ内部パス（`query()` の Invoke）を CLI オーケストレーターから直接呼び出す（Serving Context を経由しない）。

```text
Developer ──▶ CLI ──▶ Transformation Context (Plugin Host)
                          │
                          └──▶ User Plugin Logic (query() の実行)
                                   │
                                   └──▶ Context Store (開発者定義の読み取り元)
```

#### シグネチャ

```
konkon search [OPTIONS] QUERY
```

#### 引数

| 引数 | 必須 | 説明 |
| :--- | :--- | :--- |
| `QUERY` | Yes | 検索クエリ文字列。`QueryRequest.query` にマッピングされる |

#### オプション

| オプション | 短縮形 | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- | :--- |
| `--param` | `-p` | `KEY=VALUE` | — | `QueryRequest.params` に追加するパラメータ。複数回指定可 |
| `--params-file` | | `PATH` | — | JSON ファイルを読み込み `params` として利用 |
| `--plugin` | | `PATH` | `<project-dir>/konkon.py` | Plugin ファイルパス |

#### `--param` の値パースルール

`--param KEY=VALUE` の `VALUE` は以下のルールで `JSONValue` に変換される:

1. `VALUE` を JSON (RFC 8259) としてパースを試みる
2. 有効な JSON の場合、パース結果をそのまま使用する
3. JSON パースに失敗した場合、`VALUE` を文字列として使用する

```bash
# 数値
konkon search "query" --param top_k=5          # → {"top_k": 5}

# 真偽値
konkon search "query" --param verbose=true     # → {"verbose": true}

# null
konkon search "query" --param x=null           # → {"x": null}

# 文字列（JSON として無効なのでフォールバック）
konkon search "query" --param name=hello       # → {"name": "hello"}

# ネストした JSON
konkon search "query" --param 'filters={"service":"api"}'  # → {"filters": {"service": "api"}}
```

**`--params-file` とのマージ:**
- `--params-file` の JSON オブジェクトを先に読み込む
- 後続の `--param` が同名キーを上書きする

これにより `QueryRequest.params: Mapping[str, JSONValue]`（`02_interface_contracts.md`）の型契約が満たされる。

#### Plugin Host の振る舞い

セクション 3.6 の共通振る舞いに従う。`query()` の sync/async 処理もセクション 3.6 の規定に従い、非同期の場合は `asyncio.run()` で実行する。

#### stdout 出力

**text フォーマット:**

`query()` が `str` を返した場合:
```
<そのまま文字列を出力>
```

`query()` が `QueryResult` を返した場合:
```
<QueryResult.content を出力>
```
`QueryResult.metadata` が空でない場合、`--verbose` 時のみ stderr にメタデータを表示する。

**json フォーマット:**

常に `content` + `metadata` の統一構造で出力する（`str` の場合は `metadata` を空オブジェクトで補完）。

```json
// query() が str を返した場合
{"content": "結果テキスト", "metadata": {}}

// query() が QueryResult を返した場合
{"content": "結果テキスト", "metadata": {"source": "notes.md", "score": 0.95}}
```

#### `query()` の戻り値検証

- `query()` が `None` を返した場合、`02_interface_contracts.md` の契約違反として終了コード `5`（QUERY_ERROR）
- `query()` の戻り値が `str` でも `QueryResult` でもない場合、契約違反として終了コード `5`

#### 終了コード

| コード | 条件 |
| :--- | :--- |
| `0` | `query()` が正常に完了（空文字列の返却も正常） |
| `1` | 予期しないエラー |
| `2` | 引数エラー（QUERY 未指定、`--param` / `--params-file` 形式不正等） |
| `3` | `konkon.py` 未検出 / ロード失敗 / Contract 不適合 |
| `5` | `query()` 実行中のエラー（`QueryError`、戻り値型不正、Plugin 内の未捕捉例外） |

---

### 4.5 `konkon serve` — サーバー起動

#### 概要

Context Engine の `query()` 出力を、REST API または MCP サーバーとして外部に公開する。

#### Bounded Context の対応

**Serving Context** を起動する。Adapter Server が Protocol Request を受信し、Transformation Context（Plugin Host）へ Query Request として中継する。

```text
Consumer ──▶ Adapter Server (Serving Context)
                 │
                 ├── Translate: Protocol Request → QueryRequest
                 │
                 ├──▶ Transformation Context (Plugin Host)
                 │        └──▶ User Plugin Logic (query())
                 │
                 └── Render: QueryResult → Protocol Response
```

#### シグネチャ

```
konkon serve api [OPTIONS]
konkon serve mcp [OPTIONS]
```

PRD 互換のエイリアス:
- `konkon serve --api` は `konkon serve api` と等価
- `konkon serve --mcp` は `konkon serve mcp` と等価

`api` / `mcp` のどちらも指定されていない、または両方指定された場合は終了コード `2`。

#### 共通オプション

| オプション | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `--plugin` | `PATH` | `<project-dir>/konkon.py` | Plugin ファイルパス |
| `--log-level` | `ENUM` | `info` | ログレベル（`error`, `warn`, `info`, `debug`） |

#### 4.5.1 REST API モード (`serve api`)

##### オプション

| オプション | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `--host` | `TEXT` | `127.0.0.1` | バインドするホスト |
| `--port` | `INT` | `8080` | バインドするポート |
| `--path-prefix` | `TEXT` | `/` | API パスプレフィックス |

##### エンドポイント

| メソッド | パス | 説明 |
| :--- | :--- | :--- |
| `POST` | `{path-prefix}/query` | コンテキスト検索 |
| `GET` | `{path-prefix}/healthz` | ヘルスチェック |

`--path-prefix` の末尾スラッシュは正規化される。デフォルト（`/`）の場合は `/query` および `/healthz`。`--path-prefix /api/v1` の場合は `/api/v1/query` および `/api/v1/healthz`。

##### `POST /query`

**Request Body:**
```json
{
  "query": "検索文字列",
  "params": {"key": "value"}
}
```

`02_interface_contracts.md` の `QueryRequest` に1対1でマッピングされる。`params` は省略可（デフォルト `{}`）。

**リクエストバリデーション — 以下の場合は HTTP `400` を返す:**
- リクエストボディが有効な JSON でない
- `query` フィールドが欠落または `null`
- `query` が文字列型でない
- `params` が指定されているがオブジェクト型でない

**Response Body (200):**
```json
{
  "content": "...",
  "metadata": {}
}
```

`query()` が `str` を返した場合は `{"content": "...", "metadata": {}}` に正規化される。

**Error Response:**

| HTTP Status | 条件 | 対応する例外 |
| :--- | :--- | :--- |
| `400` | リクエストの JSON パース / バリデーション失敗 | — |
| `422` | `query()` 実行中のエラー（検索失敗） | `QueryError` |
| `500` | 未捕捉例外（サーバー内部障害） | その他の例外 |

エラーレスポンスの形式:
```json
{
  "error": "QueryError",
  "message": "..."
}
```

##### `GET /healthz`

**Response (200):**
```json
{
  "status": "ok"
}
```

Plugin のロードが成功しサーバーがリクエストを受付可能な状態を示す。

#### 4.5.2 MCP モード (`serve mcp`)

MCP (Model Context Protocol) サーバーとして起動する。

##### オプション

| オプション | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `--transport` | `stdio\|sse` | `stdio` | MCP のトランスポート方式 |
| `--host` | `TEXT` | `127.0.0.1` | バインドするホスト（`sse` 時のみ有効） |
| `--port` | `INT` | `8765` | バインドするポート（`sse` 時のみ有効） |
| `--sse-path` | `TEXT` | `/mcp` | SSE エンドポイントパス（`sse` 時のみ有効） |

##### トランスポート

| 方式 | 説明 |
| :--- | :--- |
| `stdio` | 標準入出力経由の JSON-RPC。Cursor, Claude Desktop 等のローカル接続用。デフォルト |
| `sse` | HTTP Server-Sent Events。リモート接続用 |

##### 公開 Tool

| Tool 名 | 説明 | パラメータ |
| :--- | :--- | :--- |
| `query` | Context Store を検索する | `query: string` (必須), `params: object` (任意) |

Tool の引数は `QueryRequest` にマッピングされ、結果は `QueryResult.content` がテキストとして返される。

##### 標準入出力

- `stdio` transport: `stdin` / `stdout` は MCP プロトコル専用。ログは **stderr のみ**に出力される
- `sse` transport: `stdout` は使用しない（予約）。ログは stderr に出力される

#### サーバーのライフサイクル

1. **起動時**: Plugin Host が `konkon.py` をロードし、Contract を検証する（セクション 3.6）。検証失敗時はサーバーを起動せず終了コード `3` で終了
2. **実行中**: 各リクエストごとに `query()` を Invoke する。同期 `query()` は `asyncio.to_thread()` でオフロードされる（セクション 3.6）。**注意:** サーバーモードでは `query()` が同時に複数回呼ばれる可能性がある（`02_interface_contracts.md` セクション 2.1）。Context Store への同時アクセスに対するスレッドセーフ性・非同期安全性の確保は開発者の責任となる
3. **停止**: `SIGINT` (Ctrl+C) / `SIGTERM` を受信した場合、実行中のリクエストの完了を待ち（グレースフルシャットダウン）、終了コード `0` で終了する（正常停止として扱う）

#### stderr 出力

| レベル | 出力例 |
| :--- | :--- |
| INFO | `[INFO] Starting API server on 127.0.0.1:8080` |
| INFO | `[INFO] Plugin loaded: /path/to/konkon.py` |
| INFO | `[INFO] POST /query — 200 (45ms)` |
| ERROR | `[ERROR] POST /query — 422: QueryError: ...` |

#### 終了コード

| コード | 条件 |
| :--- | :--- |
| `0` | グレースフルシャットダウン完了（SIGINT/SIGTERM をハンドリングした正常停止） |
| `1` | 予期しないエラーによるクラッシュ |
| `2` | 引数エラー（モード未指定、`api` と `mcp` 併用等） |
| `3` | `konkon.py` 未検出 / ロード失敗 / Contract 不適合 / ポート競合等の起動失敗 |

**補足:** リクエスト単位の `QueryError` はサーバーを停止させない。HTTP 422 / MCP エラー応答に翻訳されてプロセスは継続する。

---

### 4.6 `konkon update` — Raw Record の更新

#### 概要

既存の Raw Record の content や meta を更新する。

#### Bounded Context の対応

**Ingestion Context** を呼び出す。

#### シグネチャ

```
konkon update [OPTIONS] RECORD_ID
```

#### 引数

| 引数 | 必須 | 説明 |
| :--- | :--- | :--- |
| `RECORD_ID` | Yes | 更新対象の Raw Record の ID |

#### オプション

| オプション | 短縮形 | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- | :--- |
| `--content` | | `TEXT` | — | 新しい content |
| `--meta` | `-m` | `KEY=VALUE` | — | meta に設定するキーと値。複数回指定可 |

`--content` と `--meta` の少なくとも一方が必須。両方省略時は終了コード `2`。

#### 振る舞い

1. `RECORD_ID` に一致するレコードが存在しない場合、終了コード `1`
2. 成功時、更新されたレコードの ID を stdout に出力
3. `updated_at` が現在時刻に更新される

#### 終了コード

| コード | 条件 |
| :--- | :--- |
| `0` | 正常に更新 |
| `1` | レコード未検出、一般エラー |
| `2` | 引数エラー（`--content` も `--meta` もなし） |
| `3` | プロジェクト未初期化 |

---

### 4.7 `konkon raw list` — Raw Record 一覧表示

#### 概要

Raw DB のレコード一覧を新しい順に表示する。デバッグ・運用向けの読み取り専用コマンド。

#### Bounded Context の対応

**Ingestion Context** を読み取り専用で呼び出す。Raw DB が存在しない場合は空の結果を返す（DB を新規作成しない）。

#### シグネチャ

```
konkon raw list [OPTIONS]
```

#### オプション

| オプション | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `--limit` | `INT` (>= 0) | `20` | 表示するレコードの最大数 |
| `--format` | `text\|json` | (TTY 自動検出) | 出力フォーマット |

#### stdout 出力

**text フォーマット:**

ヘッダー行 + 各レコードの ID、created_at、updated_at、content（先頭50文字に切り詰め）を表形式で出力する。

**json フォーマット:**

各レコードを JSON Lines（1行1オブジェクト）で出力する。content 全文と meta を含む。

```json
{"id": "...", "created_at": "...", "updated_at": "...", "content": "...", "meta": {}}
```

#### 振る舞い

1. Raw DB ファイルが存在しない場合、何も出力せず正常終了（exit `0`）
2. レコードが0件の場合も同様に何も出力せず正常終了（exit `0`）
3. レコードは `created_at DESC, id DESC` の順序（新しいものが先）

#### 終了コード

| コード | 条件 |
| :--- | :--- |
| `0` | 正常（空結果も含む） |
| `1` | 一般エラー（DB アクセス失敗等） |
| `2` | 引数エラー（`--limit` に負値等） |
| `3` | プロジェクト未初期化（`konkon.py` 未検出） |

---

## 5. コマンドと Bounded Context の対応一覧

### 5.1 Bounded Context 対応表

| コマンド | 呼び出す Bounded Context | 呼び出す関数・操作 | Raw DB | Context Store |
| :--- | :--- | :--- | :--- | :--- |
| `konkon help` | (なし — システムレベル) | ヘルプ表示 | — | — |
| `konkon init` | (なし — システムレベル) | ファイルテンプレート生成 | — | — |
| `konkon insert` | Ingestion Context | Raw Record の永続化 | **Write** | — |
| `konkon update` | Ingestion Context | Raw Record の更新 | **Write** | — |
| `konkon raw list` | Ingestion Context | Raw Record の一覧取得 | **Read** | — |
| `konkon build` | Transformation Context → User Plugin | `build(raw_data)` | Read (via Accessor) | Write (Plugin 内部) |
| `konkon search` | Transformation Context → User Plugin | `query(request)` | — | Read (Plugin 内部) |
| `konkon serve api` | Serving → Transformation → User Plugin | `query(request)` (per request) | — | Read (Plugin 内部) |
| `konkon serve mcp` | Serving → Transformation → User Plugin | `query(request)` (per tool call) | — | Read (Plugin 内部) |

### 5.2 レイヤー対応表

`01` の概念構成図（L1/L2/L3）に合わせた呼び出し対応:

| コマンド | 主に触るレイヤー | 補足 |
| :--- | :--- | :--- |
| `help` | L1-L3 外 | ヘルプ表示のみ |
| `init` | L1-L3 外 | ファイルシステム操作のみ |
| `insert` | L1（Raw DB / Ingestion） | Raw Record 永続化 |
| `raw list` | L1（Raw DB / Ingestion） | Raw Record 読み取り専用 |
| `build` | L2（Orchestrator/Contract/Accessor）+ L1 + L3 | `build(raw_data)` 実行。L1 読み取り、L3 書き込み |
| `search` | L2（Contract/Host）+ L3 | `query(request)` 実行。L3 読み取り |
| `serve` | L3（Serving Adapter）+ L2 + L3 | サーバー起動。Adapter → Plugin Host → User Plugin |

---

## 6. 例外とエラーメッセージの翻訳方針

### 6.1 例外翻訳表

| 発生源 | 例外 | `build` | `search` | `serve api` | `serve mcp` |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Plugin | `BuildError` | stderr メッセージ + exit `4` | — | — | — |
| Plugin | `QueryError` | — | stderr メッセージ + exit `5` | HTTP `422` | MCP エラー応答 |
| Plugin | 未捕捉例外 | stderr トレースバック + exit `4` | stderr トレースバック + exit `5` | HTTP `500` | MCP エラー応答 |
| Host/CLI | Plugin ロード失敗 | exit `3` | exit `3` | 起動せず exit `3` | 起動せず exit `3` |
| Host/CLI | フレームワーク内部エラー | exit `1` | exit `1` | プロセス crash exit `1` | プロセス crash exit `1` |
| CLI Parser | 入力不正 | exit `2` | exit `2` | exit `2` | exit `2` |

### 6.2 エラーメッセージの方針

- `KonkonError` サブクラス（想定エラー）: `[ERROR] <ExceptionClass>: <message>` の形式。トレースバックは `--verbose` 時のみ
- 未捕捉例外（予期しないクラッシュ）: `[ERROR] Unexpected error: <message>` + フルトレースバック
- Plugin の `print()` 出力は stderr にリダイレクトされる（stdout のデータ純度を保護するため）

### 6.3 代表的なエラーメッセージ

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

## 7. 契約との整合性チェックリスト

### 7.1 Plugin Contract（02_interface_contracts.md）との整合性

| 契約の要件 | CLI での実現 |
| :--- | :--- |
| `build()` と `query()` の両方が必須 | `build` / `search` / `serve` の Load 時に両関数の存在と呼び出し可能性を検証 → exit `3` |
| `build(raw_data: RawDataAccessor)` | `build` コマンドが `RawDataAccessor` を構築して渡す |
| `RawDataAccessor.since(timestamp)` | デフォルトの差分ビルドで `.konkon/last_build` の時刻を基に差分 Accessor を渡す |
| `query(request: QueryRequest)` | `search` の QUERY と `--param` / `--params-file` から `QueryRequest` を構築 |
| `query()` の戻り値が `str \| QueryResult` | 両方に対応した出力正規化（text/json）。`None` は契約違反 → exit `5` |
| sync / async 両対応 | Plugin Host が `iscoroutinefunction()` / `isawaitable()` で判定（セクション 3.6） |
| `BuildError` / `QueryError` | exit `4` / `5` にマッピング。想定エラーはクリーンメッセージで表示 |
| `KonkonError` 以外の未捕捉例外 | Plugin 内: build → exit `4`、query → exit `5`。フレームワーク側: exit `1` |
| `QueryRequest.params` は JSON 安全型 | `--param` / `--params-file` から `Mapping[str, JSONValue]` を構築 |
| サーバーモードの同期 `query()` | `asyncio.to_thread()` でオフロード（セクション 3.6） |
| CWD は Plugin ファイルのディレクトリに設定 | Plugin Invoke 前に CWD を設定（セクション 3.6） |
| `query()` の並行呼び出し | サーバーモードで警告を記載。スレッドセーフ性は開発者責任 |
| `build()` 中断時のロールバック不保証 | CLI は Context Store のロールバックを行わない。アトミック更新推奨 |

### 7.2 Raw DB データモデル（03_data_model.md）との整合性

| データモデルの要件 | CLI での実現 |
| :--- | :--- |
| UUID v7 による `id` 生成 | `insert` コマンドがシステム側で UUID v7 を生成 |
| RFC3339 UTC 固定長 27 文字 | `insert` コマンドが `created_at` を正規化して保存 |
| `meta` は NULL または JSON オブジェクト（`json_valid` + `json_type='object'`） | CLI が `meta` を正規化して保存 |
| DELETE なし（MVP） | MVP では `insert` と `update` を提供。削除コマンドは設計しない |
| Raw DB の遅延作成 | 初回 `insert` 時に DDL を実行 |
| PRAGMA 設定（WAL, busy_timeout 等） | DB 接続時に毎回セッション PRAGMA を設定 |
| `PRAGMA user_version` 検証 | DB 接続時にスキーマバージョンを確認。既知差分は自動マイグレーション、未知差分は exit `3` |
| `since()` の exclusive フィルタ | 差分ビルドが `updated_at > last_build` で実行される |
| `RawDataAccessor` の順序契約 | `ORDER BY created_at ASC, id ASC` を CLI / Accessor が保持 |

---

## 8. 将来拡張（MVP 外）

以下は現行仕様のスコープ外であるが、CLI 設計の拡張方向として記録する。

| 拡張 | 概要 |
| :--- | :--- |
| `konkon status` | Raw DB のレコード数、最終 insert 日時、Context Store の状態を表示 |
| `konkon raw get <id>` | Raw DB の個別レコード表示（デバッグ用） |
| `konkon serve api mcp` | API と MCP の同時起動 |
| `konkon build --watch` | ファイル変更を監視して自動リビルド |
| `konkon plugin validate` | Plugin Contract の事前検証（サーバー起動なし） |
| `serve --query-timeout-ms` | リクエスト単位のタイムアウト設定 |
| `ask` コマンド | `search` の UX 上位版（PRD で言及） |
