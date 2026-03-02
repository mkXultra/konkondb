# 概念アーキテクチャ設計 (Conceptual Architecture)

本ドキュメントは `konkon db` の全体像を抽象的に定義し、システム内の責務の境界線（Bounded Contexts）と、コンポーネント間の関係性を明確にします。

## 1. 境界づけられたコンテキスト (Bounded Contexts)

`konkon db` は「Compute on Write（事前計算）」と「プラガブルなAI向けビュー」というコンセプトを実現するため、システムを **3つのコア/サポートコンテキスト** と **1つの外部コンテキスト** に分割します。

### 1.1 Ingestion Context (データ取り込みコンテキスト)
* **分類:** コア・ドメイン
* **責務:** 外部の生データを「Single Source of Truth（信頼できる唯一の情報源）」として取り込み、欠損なく永続化する。
* **所有するもの:** Raw DB（SQLite等）、データのパースロジック、投入メタデータ。
* **制約:** AI、ベクトル、コンテキストの構造に関する知識を**一切持たない**。純粋なデータの貯蔵庫である。

### 1.2 Transformation Context (変換・オーケストレーションコンテキスト)
* **分類:** コア・ドメイン
* **責務:** データ変換のパイプラインを管理し、開発者が定義した外部プラグイン（`konkon.py`）のライフサイクルと実行をオーケストレーションする。
* **所有するもの:** プラグイン・ホスト（実行環境）、ビルドのオーケストレーションロジック、プラグインとの「契約（Interface Contract）」。
* **制約:** 開発者がどのような Context DB（Vector DB等）を使うか、どういうスキーマにするかという**内部構造を知らない**。

### 1.3 Serving Context (提供コンテキスト)
* **分類:** サポート・ドメイン
* **責務:** REST API、MCPサーバーなどの外部プロトコルからの要求を受け付け、Application Layer へ中継し、結果をフォーマットして返す。
* **所有するもの:** 各種プロトコルアダプター、サーバーライフサイクル管理。
* **制約:** **完全にステートレス**。ビジネスロジックを持たず、Raw DB や Context DB に**直接アクセスすることは絶対にない**。

### 1.4 User Plugin Logic (ユーザー・プラグイン・ロジック)
* **分類:** 外部 / パートナー・コンテキスト
* **責務:** 開発者が記述する `konkon.py` (`build()`, `query()`) の振る舞い。
* **所有するもの:** 開発者が選定した **Context DB** （およびそのスキーマやView定義）、独自のデータ変換・検索ロジック。
* **制約:** Transformation Context が提示する「契約（関数のシグネチャと引数）」に完全に従う（Conformist）。

---

## 2. コンテキスト・マップ (Context Map と 依存関係)

各コンテキストがどのように連携し、どこに**腐敗防止層（ACL: Anti-Corruption Layer）**が設けられているかを示します。

```text
[External Data Sources]
       │
       ▼
┌───────────────────────┐
│ Ingestion Context     │ (Raw DB を所有)
└─────────┬─────────────┘
          │ (Upstream → Downstream)
          │ ACL: 読み取り専用の Raw Data Accessor
          ▼
┌───────────────────────┐                                    ┌───────────────────────┐
│ Transformation Context│ ◀── Application Layer 経由 ───────│ Serving Context       │
└─────────┬─────────────┘     ACL: query() の戻り値          └───────────────────────┘
          │
          │ Host → Partner (Published Language / Conformist)
          │ ACL: プラグイン・コントラクト (build/query の型定義)
          ▼
╔═══════════════════════╗
║ User Plugin Logic     ║ (External Context)
║ [Context DB を所有]   ║
╚═══════════════════════╝
```

> **注記:** Serving Context と Transformation Context の間には **Application Layer（Use Cases）** が介在する。Serving Context は Transformation Context を直接呼び出さず、Application Layer の Use Case を経由して Query Request を委譲する。上図では Bounded Context 間の論理的な関係を示しており、Application Layer の詳細は §3.5 および §4.1 C4 図を参照。

### 2.1 境界における厳密なルール (Anti-Corruption Layers)

アーキテクチャの脆さを防ぐため、以下の境界ルールを強制します。

1. **Raw DB の隔離 (Ingestion → Transformation):**
   Transformation 層および User Plugin は、Raw DB に直接 SQL を発行することはできません。システムが提供する「正規化されたデータリーダー（Accessor）」を通じてのみデータを読み取ります。
2. **Context DB の不透明性 (Transformation ↔ User Plugin):**
   システム側は、User Plugin が作成した Context DB の中身（テーブルやViewの定義）を一切知りません。「`build`関数にデータを渡し、`query`関数にリクエストを渡せば結果が返ってくる」という契約のみに依存します。
3. **Serving 層の無知 (Transformation → Application Layer → Serving):**
   Serving 層は Application Layer を経由して `query()` の実行結果（文字列やJSON）を受け取るだけであり、それがどのように検索されたか、元のデータが何であったかを知りません。これにより、特定のAIインターフェース（例: MCP）がシステムの内部構造に結合することを防ぎます。

---

## 3. ユビキタス言語 (Ubiquitous Language)

DDDの原則に従い、各コンテキスト内で使用される公式な用語（名詞と動詞）を定義します。
重要な設計ルールとして、**「データがコンテキストの境界（ACL）を越えるとき、その呼び名は必ず変わる」** ことを強制します。これにより、ドメインの漏出をコードレベルで防ぎます。

### 3.1 Ingestion Context
生データの「保管と管理」に関する言葉のみを使用します。AIや検索に関する用語は使用禁止です。

| 用語 (English) | 種類 | 定義 |
| :--- | :--- | :--- |
| **Document** | Noun | ユーザーから提供された入力テキストやペイロード。永続化される前の一時的な状態。 |
| **Raw Record** | Noun | `Raw DB` に永続化されたデータ。元のコンテンツにシステム管理のメタデータが付与されたもの。 |
| **Ingest Metadata** | Noun | `Raw Record` に付随するメタデータ（追記日時（システム管理）およびユーザー定義の任意メタデータ（JSON））。 |
| **Raw DB** | Noun | すべての `Raw Record` を格納する永続化ストア（例: SQLite）。システムの Single Source of Truth。 |
| **Ingest** | Verb | `Document` を受け取り、メタデータ（`meta`）を付与して `Raw Record` として `Raw DB` に保存する行為。 |

* **🚫 使用禁止用語:** Context, Build, Query, Plugin, Adapter, Store

### 3.2 Transformation Context
「オーケストレーションと契約（Contract）」に関する言葉を使用します。プラグイン内部のストレージ構造に関する用語は使用禁止です。

| 用語 (English) | 種類 | 定義 |
| :--- | :--- | :--- |
| **Plugin** | Noun | 開発者が提供するモジュール（例: `konkon.py`）。 |
| **Plugin Contract** | Noun | プラグインが満たすべき関数のシグネチャ（`build()`, `query()`）と型の定義。 |
| **Plugin Host** | Noun | `Plugin` をロードし、実行し、ライフサイクルを管理するフレームワーク側のランタイム。 |
| **Raw Data Accessor** | Noun | `Plugin` の `build()` に渡される読み取り専用のインターフェース。`Raw DB` のスキーマを隠蔽する。 |
| **Query Request** | Noun | Application Layer から渡される、プロトコルに依存しない正規化された検索リクエスト。 |
| **Query Result** | Noun | `Plugin` の `query()` から返される正規化された結果（文字列やJSON）。 |
| **Load** / **Invoke** | Verb | プラグインを読み込む行為 / プラグインの関数（契約）を呼び出す行為。 |

* **🚫 使用禁止用語:** Document, Raw DB (直接アクセスしないため), Context Store (内部を知らないため), Response

### 3.3 Serving Context
「プロトコルと転送」に関する言葉のみを使用します。ビジネスロジックやデータ構造に関する用語は使用禁止です。

| 用語 (English) | 種類 | 定義 |
| :--- | :--- | :--- |
| **Consumer** | Noun | コンテキストを要求する外部の存在（AIエージェント、MCPクライアント）。 |
| **Protocol Request** | Noun | 受信したプロトコル固有のリクエスト（HTTPボディ、MCPツールコール引数など）。 |
| **Protocol Response**| Noun | `Consumer` に返すプロトコル固有のフォーマットでラップされた結果。 |
| **Adapter** | Noun | リクエストの受信とレスポンスの返却を行うモジュール（REST Adapter, MCP Adapter）。 |
| **Translate** | Verb | `Protocol Request` を Application Layer が受理できる `Query Request` に変換する行為。 |
| **Render** | Verb | `Query Result` を `Protocol Response` にフォーマットする行為。 |

* **🚫 使用禁止用語:** Raw Record, Raw DB, Plugin, Context Store, Query Logic, Use Case（内部実装）

### 3.4 User Plugin Logic (External Context)
開発者の自由なドメインです。AIや変換、検索に関する具体的な言葉を使用します。

| 用語 (English) | 種類 | 定義 |
| :--- | :--- | :--- |
| **Builder** | Noun | 生データをAI向けに変換する開発者定義のロジック（`build()` の中身）。 |
| **Query Handler** | Noun | 検索要求を受け取り、データを引き出す開発者定義のロジック（`query()` の中身）。 |
| **Context Store** | Noun | 開発者が選定・構築したAI向けのデータストア（Vector DB、SQLiteビュー、Markdown群など）。 |
| **Context** | Noun | `Context Store` 内に保存されている、AI向けに最適化された（Materializedされた）データ。 |
| **Transform** | Verb | 生データをAIが理解しやすい形（Context）に変換・要約・ベクトル化する行為。 |
| **Retrieve** | Verb | `Context Store` から要件に合致する `Context` を抽出する行為。 |

### 3.5 Application Layer (ユースケース調停層)

> **Application Layer は Bounded Context ではない。** BC をまたぐユースケースの調停（オーケストレーション）を責務とする層であり、独自のドメインモデルを持たない。

「ユースケースの調停と公開」に関する言葉を使用します。各 Context の内部実装に関する用語は使用禁止です。

| 用語 (English) | 種類 | 定義 |
| :--- | :--- | :--- |
| **Use Case** | Noun | 1つのユーザー操作に対応するオーケストレーション単位。1つ以上の Context Facade を呼び出し、結果を返す。ドメインロジックを持たない。 |
| **Entry Point** | Noun | Use Case を外部に公開する入口。CLI Entry と Lib Entry の2種がある。 |
| **CLI Entry** | Noun | ターミナル入力（コマンド引数・stdin）を Use Case 呼び出しに変換するエントリポイント。 |
| **Lib Entry** | Noun | Python 関数呼び出しを Use Case 呼び出しに変換するエントリポイント（公開 Python API）。 |
| **Dispatch** | Verb | Entry Point が受け取った入力を適切な Use Case に振り分ける行為。 |
| **Orchestrate** | Verb | Use Case が複数の Context Facade を順序付けて呼び出し、結果を組み立てる行為。 |
| **Thin Orchestrator** | Principle | Application Layer はルーティング・入力正規化・エラー伝搬のみを担い、ドメイン計算や永続化ロジックを持たない設計原則。 |

* **🚫 使用禁止用語:** Raw DB, Plugin Host, Plugin Contract（Transformation 内部実装）, Context Store, Protocol Request, Protocol Response, Adapter（Serving 内部実装）

> **ACL 境界型との関係:** Application Layer は ACL 境界で定義された型（`QueryRequest`, `QueryResult`, `RawDataAccessor` 等）を **パススルー** で使用する。これらの型を独自に再定義・ラップしてはならない。

### 3.6 境界における用語の変換 (Boundary Translation)
データがシステム内を流れる際、コンテキストの境界（ACL）を越えるたびに以下のように「名前」が変わり、依存関係が断ち切られます。

| 元の概念 | Ingestion 層 | Application Layer | Transformation 層 | User Plugin 内 | Serving 層 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 外部からの入力データ | **Document** | (Ingestion Facade へパススルー) | (扱わない) | (扱わない) | (扱わない) |
| DBに保存されたデータ | **Raw Record** | (Ingestion Facade 経由で委譲) | **Raw Data Accessor** (背後に隠蔽) | `raw_data` (引数) | (扱わない) |
| クライアントからの検索要求 | (扱わない) | (Transformation Facade へパススルー) | **Query Request** | `request` (引数) | **Protocol Request** |
| 検索の最終結果 | (扱わない) | (Transformation Facade の戻り値をパススルー) | **Query Result** | (関数の戻り値) | **Protocol Response** |
| 開発者が作ったDB | (扱わない) | (扱わない) | (扱わない - 不透明) | **Context Store** | (扱わない) |

> **Application Layer 列の特徴:** Thin Orchestrator であるため、独自の境界型を定義しない。各 Context Facade の公開型をそのままパススルーする。

---

## 4. C4 モデル (Level 1 & Level 2)

前述のコンテキスト境界とユビキタス言語に基づき、システムの動的なコンテナ構成を定義します。

### 4.1 C4 Level 2: Container Diagram

この図は、`konkon db` の内部コンポーネント（コンテナ）と、それらがどの Bounded Context / Application Layer に属しているか、またそれらがどのようにデータをやり取りするか（ACLの遵守）を示しています。

```mermaid
C4Container
    title Container Diagram — konkon db (with Application Layer)

    Person(developer, "Developer", "開発者。プラグインを書き、CLIコマンドを実行する。")
    Person(consumer, "Consumer", "コンテキストを要求する AI Agent または Client。")
    System_Ext(pythonApps, "External Python App", "konkon を import して利用する外部 Python アプリケーション。")
    System_Ext(dataSources, "Data Sources", "外部の生データ（テキスト、stdin ストリーム等）。")
    System_Ext(pluginDeps, "Plugin Dependencies", "開発者がプラグイン内で利用する外部ライブラリやサービス（Vector DB, Graph DB, LLM APIs等）。")

    System_Boundary(konkon, "konkon db") {

        Boundary(appLayer, "Application Layer (NOT a Bounded Context)") {
            Container(cli, "CLI Entry", "Python / click", "ターミナル入力を Use Case 呼び出しに変換する Entry Point。")
            Container(appLib, "Lib Entry", "Python", "Python API として Use Case を公開する Entry Point。")
            Container(useCases, "Use Cases", "Python", "Context Facade の呼び出しを調停する Thin Orchestrator。ドメインロジックを持たない。")
        }

        Boundary(ingestion, "Ingestion Context") {
            Container(ingestFacade, "Ingestion Facade", "Python", "Ingestion Context の公開ポート。Raw DB への保存と読み出しを仲介する。")
            ContainerDb(rawDb, "Raw DB", "SQLite", "Single Source of Truth。Raw Record と Ingest Metadata を保存する。")
        }

        Boundary(transformation, "Transformation Context") {
            Container(transformFacade, "Transformation Facade", "Python (in-process)", "Transformation Context の公開ポート。プラグインのロード・実行と Plugin Contract の強制を担う。")
        }

        Boundary(serving, "Serving Context") {
            Container(server, "Adapter Server", "Python / HTTP / stdio", "REST Adapter と MCP Adapter をホストする。ステートレスなプロトコル変換器。")
        }

        Boundary(userPlugin, "User Plugin Logic (External Context)") {
            Container(plugin, "Plugin (konkon.py)", "Python (Developer-authored)", "Builder と Query Handler を実装したユーザーコード。")
            ContainerDb(contextStore, "Context Store", "Developer-defined", "AI向けに Materialize された Context を保存する。システムからは完全に不透明な（Opaque）存在。")
        }
    }

    %% 外界 → システム
    Rel(developer, cli, "コマンドの実行", "Terminal")
    Rel(dataSources, cli, "Document の提供", "stdin / CLI arg")
    Rel(pythonApps, appLib, "Python API 呼び出し", "import konkon")
    Rel(consumer, server, "Protocol Request の送信", "HTTP / MCP")

    %% Application Layer 内部
    Rel(cli, useCases, "Dispatch")
    Rel(appLib, useCases, "Dispatch")

    %% Serving → Application Layer（ランタイム: query 中継）
    Rel(server, useCases, "Translate → Use Case 呼び出し (runtime)")

    %% Application Layer → Context Facades
    Rel(useCases, ingestFacade, "Ingest / Update / Raw List / Raw Get")
    Rel(useCases, transformFacade, "Invoke Build / forward Query Request")
    %% Ingestion Context 内部
    Rel(ingestFacade, rawDb, "Persist / Fetch Raw Record")

    %% Transformation ↔ Ingestion / Plugin (ACL)
    Rel(transformFacade, ingestFacade, "Read via Raw Data Accessor (読み取り専用)")
    Rel(transformFacade, plugin, "Load / Invoke per Plugin Contract")
    Rel(plugin, transformFacade, "Return Query Result")

    %% Plugin 内部処理
    Rel(plugin, contextStore, "Transform (Write) / Retrieve (Read)")
    Rel(plugin, pluginDeps, "外部サービスの呼び出し (任意)")
```

> **注記:** サーバーの起動制御は Application Layer の責務であるが、C4 図上のコンテナ間依存としては表現しない。起動はプロセスレベルのライフサイクル管理であり、ランタイムのデータフロー依存とは区別される。

### 4.2 アーキテクチャの重要ポイント (ACL の証明)

上記の C4 モデルは、アーキテクチャの脆さを防ぐための以下のルールを構造的に証明しています。

1. **Application Layer は Bounded Context ではない:**
   Application Layer は BC をまたぐ調停層として配置されており、独自のドメインモデルや永続化機構を持たない。Thin Orchestrator として、各 Context Facade を呼び出すだけである。

2. **CLI と Lib は対等な Entry Point:**
   `CLI Entry` と `Lib Entry` はいずれも `Use Cases` に対して `Dispatch` するだけであり、ビジネスロジックを持たない。入力の受け取り方（ターミナル vs Python API）のみが異なる。これにより、CLI で可能な操作はすべて Python API からも実行可能であることが構造的に保証される。

3. **依存方向の一方向性:**
   すべての依存は `Entry Point / Adapter → Application Layer (Use Cases) → Context Facade` の方向に流れる。

4. **Application Layer 🚫 Raw DB / Context Store 直接アクセス:**
   Application Layer は Raw DB や Context Store に直接アクセスする矢印を持たない。必ず Ingestion Facade または Transformation Facade を経由する。

5. **Serving 🚫 Raw DB / Context Store:**
   `Adapter Server` からは、どの DB にも矢印が伸びていない。サーバーは完全にステートレスであり、Application Layer の Use Case を経由してのみクエリを実行する。

6. **Transformation 🚫 Context Store / Plugin 🚫 Raw DB:**
   `Transformation Facade` は `Context Store` にアクセスできない。`Plugin` は `Raw DB` に直接アクセスできず、`Transformation Facade` が提供する `Raw Data Accessor` を通じて安全にデータを読み取る。

### 4.3 概念構成図（レイヤー図）

システム全体の構造をよりシンプルに視覚化するためのレイヤー図（ブロック図）です。Application Layer、コンテキストの階層（インターフェース層、エンジン層、データ層）と、フレームワークとユーザーロジックの境界を明確にしています。

```mermaid
block-beta
  columns 2

  %% --- L4 行 (Application Layer) ---
  block:L4_Physical
    columns 3
    CLI("CLI Entry")
    LibEntry("Lib Entry")
    UseCases("Use Cases (Thin Orchestrator)")
  end

  L4_Label("L4: Application Layer（BC ではない）")

  %% --- L3 行 ---
  block:L3_Physical
    columns 2
    Serving("L3: 出力・提供層 (Interface Layer)")
    block:L3_User
      columns 1
      UserPlugin("L3: 開発者ロジック (konkon.py)")
      ContextStore("L3: AI専用ビュー (Context DB)")
    end
  end

  block:L3_Logical
    columns 2
    BC_Serving("Serving Context")
    BC_User("User Plugin Logic (External)")
  end

  %% --- L2 行 ---
  block:L2_Physical
    columns 3
    Orchestrator("L2: パイプライン制御")
    Contract("L2: プラグイン契約")
    Accessor("L2: データ仲介")
  end

  BC_Trans("Transformation Context")

  %% --- L1 行 ---
  Ingestion("L1: 生データストア (Raw DB / SSoT)")
  BC_Ingest("Ingestion Context")
```
