# konkon db 詳細設計

## 設計書一覧

| # | ドキュメント | スコープ | ステータス |
| :--- | :--- | :--- | :---: |
| 01 | [概念アーキテクチャ設計](./01_conceptual_architecture.md) | Bounded Contexts、レイヤー構成、コンポーネント間の責務境界 | 確定 |
| 02 | [インターフェース・コントラクト仕様](./02_interface_contracts.md) | ACL を越える型定義、Plugin Contract の関数シグネチャ | 確定 |
| 03 | [データモデル設計](./03_data_model.md) | Raw DB（SQLite）の物理スキーマ、マイグレーション戦略 | 確定 |
| 04 | [CLI 詳細設計](./04_cli_design.md) | CLI コマンド体系、終了コード、出力形式、エッジケース | 確定 |
| 05 | [プロジェクト構成・技術選定](./05_project_structure.md) | CLI フレームワーク、パッケージ構成、Python バージョン、配布方法 | 確定（6〜8 後日） |
| 06 | Serving Adapters 設計 | REST API / MCP サーバーアダプターの詳細仕様 | 未着手 |

## 原典資料

| ドキュメント | 位置づけ |
| :--- | :--- |
| [concept.md](../../concept.md) | プロジェクトコンセプト（基本設計相当） |
| [prd.md](../../prd.md) | プロダクト要件定義 |

## 設計プロセス

本プロジェクトの設計書は、マルチエージェント（Claude Ultra / Codex Ultra / Gemini Ultra）による反復レビュープロセスで作成されている。詳細は [DESIGN_PROCESS.md](./DESIGN_PROCESS.md) を参照。

## ディレクトリ構成

```
docs/design/
├── README.md                      # 本ファイル（設計書インデックス）
├── DESIGN_PROCESS.md              # マルチエージェント設計プロセス
├── 01_conceptual_architecture.md  # 確定版
├── 02_interface_contracts.md      # 確定版
├── 03_data_model.md               # 確定版
├── 04_cli_design.md               # 確定版
├── 05_project_structure.md        # 確定（6〜8 後日）
├── claude/                        # Agent A ドラフト・レビュー（アーカイブ）
├── codex/                         # Agent B ドラフト・レビュー（アーカイブ）
└── gemini/                        # Agent C ドラフト・レビュー（アーカイブ）
```
