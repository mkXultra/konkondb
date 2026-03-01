# 設計ドキュメント記述規約 (Design Guidelines)

設計ドキュメントの記述規約。ドキュメント数が増えても一貫性を保つためのルール。

## 1. Single Source of Truth (SSOT)

- すべての設計情報は、**ただ1つのドキュメント**に定義される
- 他のドキュメントからは**参照（リンク）**のみ。値の再掲・コピーは禁止

## 2. 許容される参照パターン

- `「03_data_model.md §7 参照」` — リンクのみ
- マッピング表（SSOT 間の関係を記述するもの）— 値の再定義ではなく接続点の記述として許容
- **Dependency Inversion（自己宣言）:** 中央マッピング表で全体を一覧管理するよりも、各ドキュメントが自身の属性（Bounded Context、レイヤー等）を冒頭で宣言する方式を優先する。これにより、ドキュメント追加時に既存ファイルの更新が不要になる

## 3. レビュー観点

- 変更が SSOT 以外のドキュメントに値を再掲していないか

## 4. ドキュメントアーキテクチャ

設計ドキュメントは **Foundation + Command Spec** の2層構造で管理する（決定の経緯は [ADR-20260301](../adr/20260301-doc-structure-foundation-command-spec.md) を参照）。

### 4.1 2層構造

| 概念層 | 役割 | 該当ファイル | 更新パターン |
| :--- | :--- | :--- | :--- |
| **Foundation（基盤）** | アーキテクチャの不変ルール、型契約、スキーマ、共通規約 | 01〜05（ルート直下） | まれに更新 |
| **Command Spec（機能）** | 個別コマンドの仕様 | `commands/*.md` | 追加中心 |

### 4.2 コマンド追加ルール

- **コマンド追加 = `commands/` に新ファイル1つを追加するのみ。既存ファイルの更新ゼロ。**
- 新コマンド追加時は [`commands/_template.md`](./commands/_template.md) をコピーして作成する
- 各 Command Spec は自身の Bounded Context とレイヤー対応を冒頭で宣言する（§2 Dependency Inversion）

### 4.3 共通規約の配置

- CLI 全体に適用される規約（stdout/stderr、終了コード、出力形式等）は [`04_cli_conventions.md`](./04_cli_conventions.md) に配置する
- サブコマンドグループの共通制約（`serve` 共通仕様、`raw` グループ制約等）も Foundation に属する
