# ADR-20260301: Application Layer の導入（Python App Lib のための概念設計拡張）

## ステータス

Accepted

## 日付

2026-03-01

## コンテキスト

### Python App Lib の追加ニーズ

PRD の拡張として、`konkon db` を CLI だけでなく **Python ライブラリとしても公開** する要件が発生した。外部の Python アプリケーションが `import konkon` で konkon の機能を利用できるようにする必要がある。

### 既存設計の課題

既存の `01_conceptual_architecture.md` では、CLI は「どの Bounded Context にも属さないオーケストレーター」として定義されていた。この設計には以下の問題があった:

1. **CLI と Python App Lib のロジック共有場所がない:** CLI のオーケストレーションロジックを Python API からも利用するには、共有層が必要
2. **CLI の位置づけが曖昧:** 「BC に属さない」としながらも、各 Context を直接呼び出す存在として C4 図に配置されており、アーキテクチャ上の責務が暗黙的
3. **Serving Context との責務境界が不明確:** CLI を Serving Context の Adapter として扱うと、PRD の Interface Layer 定義（「プロトコル変換のみ」）と矛盾する

### 設計プロセス

この課題に対し、以下の多段階プロセスで設計を策定した:

1. **Phase 2 — 並行ドラフト作成:** Claude / Gemini / Codex の3エージェントが独立して `01_app_layer_draft.md` を作成
2. **Phase 3 — クロスレビュー (R1):** 各エージェントが他2案をレビューし、合意事項への準拠・既存設計との整合性・用語の妥当性を評価
3. **Phase 4 — 統合:** レビュー結果を基に3案を統合し `01_app_layer_unified.md` を作成
4. **Phase 5 — 検証レビュー:** 統合版の最終検証と承認

Phase 2 の開始前に、4つの前提事項について3エージェントが合意した:

1. Application Layer は Bounded Context ではない
2. CLI と Python App Lib を Application Layer に配置する
3. Thin Orchestrator 原則（ドメインロジックを持たない）
4. 依存方向の固定: Adapter → Application Layer → Context Facade

## 決定

### Application Layer を BC とは別の調停層として導入する

Application Layer は Bounded Context をまたぐユースケースの調停（オーケストレーション）を責務とする層であり、独自のドメインモデルを持たない。3つの BC（Ingestion / Transformation / Serving）とは別種の概念として定義する。

### Thin Orchestrator 原則

Application Layer はルーティング・入力正規化・エラー伝搬のみを担い、ドメイン計算や永続化ロジックを持たない。各 Context Facade の公開型（`QueryRequest`, `QueryResult`, `RawDataAccessor` 等）をパススルーで使用し、独自の境界型を再定義・ラップしない。

### 依存方向の一方向性

すべての依存は `Entry Point / Adapter → Application Layer (Use Cases) → Context Facade` の方向に流れる。逆依存は禁止。

- **CLI Entry** と **Lib Entry** は Application Layer 内の Entry Point として、Use Cases に Dispatch する
- **Serving Context** の Adapter はランタイム時に Application Layer の Use Case を経由してクエリを実行する
- Application Layer は Raw DB や Context Store に直接アクセスせず、必ず Ingestion Facade / Transformation Facade を経由する

### CLI Entry / Lib Entry / Use Cases の3コンテナ構造

Application Layer 内部を以下の3コンテナに分離する:

| コンテナ | 責務 |
| :--- | :--- |
| **CLI Entry** | ターミナル入力（コマンド引数・stdin）を Use Case 呼び出しに変換 |
| **Lib Entry** | Python 関数呼び出しを Use Case 呼び出しに変換（公開 Python API） |
| **Use Cases** | Context Facade の呼び出しを調停する Thin Orchestrator |

CLI Entry と Lib Entry は対等な Entry Point であり、ビジネスロジックを持たない。これにより、CLI で可能な操作はすべて Python API からも実行可能であることが構造的に保証される。

### パススルー方針（独自の境界型を持たない）

Application Layer は ACL 境界で定義された型をそのままパススルーする。§3.6 の境界変換表では、Application Layer の列はすべて「Facade へパススルー」「Facade 経由で委譲」「Facade の戻り値をパススルー」として表現される。

## 却下した代替案

### Python App Lib を Serving Context に配置する案

| 観点 | 評価 |
| :--- | :--- |
| 提案者 | 初期検討段階で浮上 |
| 見送り理由 | PRD の Serving Context は「プロトコル変換のみ」を責務とする Interface Layer として定義されている。Python API はプロトコル変換ではなく直接的なプログラム呼び出しであり、Serving Context の責務と不整合。また、CLI も Serving Context に入れると「書き込み操作（insert, build）を行う Adapter」という矛盾が生じる |

### Codex 案: CLI / Lib を Adapter Layer に分離する構造

| 観点 | 評価 |
| :--- | :--- |
| 概要 | L4: Adapter Layer（CLI, Lib, REST, MCP）→ L3: Application Layer（Use Cases）という2層構造 |
| 強み | クリーンアーキテクチャ的に美しい依存関係の可視化。Ingestion Facade / Transformation Facade をコンテナとして明示 |
| 見送り理由 | 合意事項 (2)「CLI と Python App Lib を Application Layer に配置する」に違反。C4 図では Application Layer 内に配置しているが、レイヤー図では Application Layer の外（上位 Adapter Layer）に分離しており、同一ドラフト内で自己矛盾が発生。また CLI/Lib を Adapter と呼ぶ用語上の問題もあった |

### Codex 案: Use Case Input / Use Case Output の導入

| 観点 | 評価 |
| :--- | :--- |
| 概要 | Application Layer 専用の正規化オブジェクト（`Use Case Input` / `Use Case Output`）を ACL 境界型として定義 |
| 見送り理由 | Thin Orchestrator 原則に反する。Application Layer は Context Facade の既存型をパススルーすべきであり、独自の境界型は過剰な抽象化。Claude 案のパススルー方式が3エージェントのレビューで支持された |

### Gemini 案: Serving Context から Transformation Context への直接接続を維持

| 観点 | 評価 |
| :--- | :--- |
| 概要 | 既存の Serving → Plugin Host の直接接続を残し、Application Layer は CLI/Lib 側のみに適用 |
| 強み | 変更量が最小。既存構造を大きく壊さない |
| 見送り理由 | 合意事項 (4)「Adapter → Application Layer → Context Facade」に違反。Serving Context が Application Layer をバイパスして Transformation Context に直接接続しており、依存方向の一方向性が崩れる。§3.3 / §3.6 の更新も漏れており、文書内の整合性が不足 |

### 各ドラフトの主要な差異と統合の方針

R1 クロスレビューの結果、以下の方針で3案を統合した:

| セクション | 採用元 | 根拠 |
| :--- | :--- | :--- |
| §3.2 (Query Request 出自) | Codex | 唯一「Application Layer から」に正確に更新 |
| §3.3 (Serving Context 更新) | Claude | Consumer / Adapter / Translate の3項目を網羅的に更新 |
| §3.5 (Application Layer 用語) | Claude + Codex | Claude の用語体系（Entry Point, Use Case, Dispatch）をベースに、Codex の Thin Orchestrator を Principle として追記 |
| §3.6 (境界変換表) | Claude | パススルー方式を採用。表記を抽象化して統一 |
| §4.1 (C4 図) | Codex + Claude | Codex の Context Facade 明示 + Claude の Boot/Runtime 二相分離ラベル |
| §4.2 (重要ポイント) | Claude | 6項目構成で依存方向の意図を文章で補完 |
| §4.3 (レイヤー図) | Claude + Gemini | Claude の2列方式を維持。レイヤー番号は Gemini の L4 加算方式を採用 |

## 影響

### 波及した設計ドキュメントの変更

| ドキュメント | 変更箇所 | 内容 |
| :--- | :--- | :--- |
| `01_conceptual_architecture.md` | §1.3, §2, §3.2, §3.3, §3.5(NEW), §3.5→§3.6, §4.1, §4.2, §4.3 | Application Layer の追加に伴う全面的な更新 |
| `02_interface_contracts.md` | ACL #3 `QueryRequest` docstring, `query()` docstring | 出自を「Serving層から」→「Application Layer（Serving Adapter 経由を含む）から」に更新 |
| `04_cli_conventions.md` | §1.4 CLI の位置づけ | 「BC に属さないオーケストレーター」→「Application Layer 内の Entry Point」に更新。依存方向図と境界ルールを Application Layer → Context Facade に整合 |
| `05_project_structure.md` | ディレクトリレイアウト | `src/konkon/application/` パッケージ（Use Case 実装）と `tests/test_application/` を追加。依存方向 `cli/` → `application/` → `core/` を明記 |

### メリット

| メリット | 説明 |
| :--- | :--- |
| **CLI / Lib の対称性** | CLI で可能な操作はすべて Python API からも実行可能であることが構造的に保証される |
| **暗黙的オーケストレーションの明示化** | 旧 CLI が暗黙的に担っていたオーケストレーション責務が Application Layer として正式に可視化された |
| **Serving Context の純粋化** | CLI が Serving Context から移動したことで、Serving Context は「プロトコル変換のみ」という PRD 定義に完全に一致 |
| **依存方向の明確化** | Entry Point / Adapter → Application Layer → Context Facade の一方向依存がすべての図と文書で一貫 |

### デメリット

| デメリット | 緩和策 |
| :--- | :--- |
| 概念の増加（Use Case, Entry Point 等の新用語） | ユビキタス言語テーブルで定義を明確化。禁止用語で誤用を防止 |
| 波及更新の範囲が大きい（01, 02, 04, 05 の4ファイル） | 統合版に波及更新計画を含め、一括で適用 |
| Application Layer のモジュール（`src/konkon/application/`）が薄くなりすぎるリスク | Thin Orchestrator は設計意図。薄いことが正しい状態であり、ロジックが厚くなった場合は Context Facade への委譲漏れとして検出する |
