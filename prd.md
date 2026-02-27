# Step 1: プロダクト要件定義書 (PRD)

**プロジェクト名:** konkon db
**概要:** Rawデータの管理とAI向けContext出力を分離し、その中間に位置する「内部データのCRUD（変換・保存・検索ロジック）」を開発者が自由に定義・構築できる、AI向けコンテキストDBミドルウェア。

## 1. 目的とゴール

* **Raw Dataの確実な管理:** AIに渡すコンテキストの源泉となる生データを、欠損や構造の縛りなく一元管理する。
* **Context出力の標準化:** AI（MCP等）や開発者（CLI）に対する「コンテキストの渡し口」を統一し、外部システムとの結合をシンプルにする。
* **内部データCRUDの完全な自由化:** RawからContextを生成するプロセスにおいて、開発者が任意の技術（RAG/Vector DB、GraphDB、リレーショナルDBのビュー、カスタムPythonスクリプト等）を自由に組み込めるプラガブルな基盤を提供する。

## 2. システムアーキテクチャ概要

「konkon db」は、外殻（入出力）と内殻（CRUDエンジン）が完全に分離されたアーキテクチャを持ちます。

1. **Raw DB層 (生データストア):** 投入されたデータを元の形のまま永続化する「Single Source of Truth（信頼できる唯一の情報源）」。
2. **Internal Context Engine (内部CRUDの自由領域):** * 開発者が自由にロジックを注入できるブラックボックス領域。
* **C/U/D (Build):** Raw DBからデータを読み出し、内部のContext DB（SQLite, Vector DB等なんでも可）を構築・更新するロジック。
* **R (Query):** AIからのリクエストを受け、内部Context DBからデータを抽出し、最終的なContext文字列（またはJSON）を生成するロジック。


3. **Interface層 (出力):** Context Engineが生成した出力を、CLI、API、MCPの各プロトコルに合わせてラップし、外部へ提供する層。

## 3. 機能要件 (Functional Requirements)

### A. Raw Data 管理機能

* `konkon insert` コマンド等を通じて、任意のテキストデータ（stdin / コマンドライン引数経由）をRaw DB（デフォルトはSQLite等を想定）に安全に格納する。
* 追記日時のシステム管理と、ユーザー定義メタデータ（JSON）の任意付与。

### B. 内部CRUDインターフェース (The Pluggable Engine)

* 開発者は、以下の2つの関数（またはクラスメソッド）を記述した設定ファイル（例: `konkon.py`）を用意するだけでよい。
1. `build(raw_data)`: Rawデータを読み込み、開発者独自のContext DB（ベクトル化、要約、パースなど自由）を作成・更新する関数。
2. `query(request)`: 検索要求を受け取り、開発者独自のContext DBから情報を引き出し、AIに渡すContextを出力する関数。


* フレームワーク依存の排除（内部でLlamaIndexを使おうが、生のSQLを書こうが、システム側は干渉しない）。

### C. Context 出力・提供機能 (Serving)

* 開発者が定義した `query()` の出力を、以下のインターフェースでシームレスに提供する。
* **CLI (`search`, `ask`):** ローカル開発・デバッグ用の標準出力。
* **API Server (`serve --api`):** 外部システムからのRESTアクセス。
* **MCP Server (`serve --mcp`):** CursorやClaude等からの直接的なツール呼び出し（Tool Calling）対応。



## 4. CLIコマンド体系（ユーザーインターフェース）

開発者が「内部CRUDの調整」というイテレーションを高速に回すためのコマンド群です。

| コマンド | 役割 | 対象レイヤー・処理 |
| --- | --- | --- |
| `konkon init` | プロジェクト初期化（`konkon.py`テンプレート生成等） | 全体 |
| `konkon insert [TEXT]` | 生データ（テキスト / stdin）の投入 | Raw DBへの書き込み |
| `konkon build` | 開発者定義の `build()` を実行 | Internal Engine (C/U/D) |
| `konkon search "query"` | 開発者定義の `query()` を実行し結果を確認 | Internal Engine (R) -> CLI出力 |
| `konkon serve --api` | APIサーバー起動 | Internal Engine (R) -> HTTP |
| `konkon serve --mcp` | MCPサーバー起動 | Internal Engine (R) -> stdio/SSE |

## 5. 開発体験 (DX) の定義

* **サーバーレス検証:** `build` と `search` はファイルベースで完結し、バックグラウンドのサーバー起動を一切必要としない。
* **トライ＆エラーの極小化:** AIの回答結果が気に入らない場合、開発者は `konkon.py` のCRUDロジックを書き換え、`konkon build` を叩くだけでデータ構造全体を刷新できる。
