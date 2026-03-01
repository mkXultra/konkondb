# konkon db 詳細設計

## ドキュメント構成

本設計書は **Foundation（基盤）** と **Command Spec（機能）** の2層で構成される。
Foundation はアーキテクチャの不変ルールや共通規約を定義し、
Command Spec は個別コマンドの仕様を1コマンド1ファイルで管理する。

### Foundation（基盤ドキュメント）

| # | ドキュメント | スコープ | ステータス |
| :--- | :--- | :--- | :---: |
| 01 | [概念アーキテクチャ設計](./01_conceptual_architecture.md) | Bounded Contexts、レイヤー構成、コンポーネント間の責務境界 | 確定 |
| 02 | [インターフェース・コントラクト仕様](./02_interface_contracts.md) | ACL を越える型定義、Plugin Contract の関数シグネチャ | 確定 |
| 03 | [データモデル設計](./03_data_model.md) | Raw DB（SQLite）の物理スキーマ、マイグレーション戦略 | 確定 |
| 04 | [CLI 共通規約](./04_cli_conventions.md) | stdout/stderr 規約、終了コード、出力形式、Plugin Host、serve 共通仕様 | 確定 |
| 05 | [プロジェクト構成・技術選定](./05_project_structure.md) | CLI フレームワーク、パッケージ構成、Python バージョン、配布方法 | 確定（6〜8 後日） |
| 06 | Serving Adapters 設計 | REST API / MCP サーバーアダプターの詳細仕様 | 未着手 |

### Command Spec（コマンド個別仕様）

コマンドごとに1ファイルで仕様を管理する。一覧は [commands/](./commands/) を参照。
新コマンド追加時は [_template.md](./commands/_template.md) をコピーして作成する。

### 原典資料

| ドキュメント | 位置づけ |
| :--- | :--- |
| [concept.md](../../concept.md) | プロジェクトコンセプト（基本設計相当） |
| [prd.md](../../prd.md) | プロダクト要件定義 |

### メタドキュメント

| ドキュメント | 内容 |
| :--- | :--- |
| [DESIGN_GUIDELINES.md](./DESIGN_GUIDELINES.md) | 設計ドキュメントの記述規約（SSOT ルール） |
| [DESIGN_PROCESS.md](../llm/DESIGN_PROCESS.md) | マルチエージェント設計・レビュープロセス |
| [doc_structure_proposal.md](./doc_structure_proposal.md) | 本構造の設計根拠 |
