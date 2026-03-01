# konkon <command> — <概要>

## 概要

（1〜2文のコマンド説明）

## Bounded Context

**呼び出すコンテキスト:** <Ingestion | Transformation → User Plugin | Serving → ...>
**レイヤー:** <L1 | L2 | L3>

```text
（ASCII フロー図: CLI → Context → ...）
```

## シグネチャ

```
konkon <command> [OPTIONS] [ARGS]
```

## 引数

| 引数 | 必須 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |

## オプション

| オプション | 短縮形 | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- | :--- |

## 振る舞い

（順序付きの振る舞い記述）

## stdout 出力

### text フォーマット

### json フォーマット

## stderr 出力

（ログレベルごとの出力例。`--verbose` 時の追加出力があれば記載）

| レベル | 出力例 |
| :--- | :--- |

## バリデーション（該当する場合のみ記載）

（入力不正時の判定条件と、そのときの振る舞い — 終了コード / HTTP ステータス / MCP エラー等）

## エラーレスポンス（serve 系コマンドのみ — 該当しない場合は削除）

（HTTP ステータスコードや MCP エラー応答のマッピング）

## 終了コード

共通終了コードは [04_cli_conventions.md §2.3](../04_cli_conventions.md) 参照。

| コード | 条件 |
| :--- | :--- |

## 設計判断・補足

（SSOT ドキュメントへのクロスリファレンス、このコマンド固有の設計意図）

**Plugin Contract との関連（該当する場合のみ記載）:**
- build/query/schema のどの関数を利用するか → [02_interface_contracts.md §1](../02_interface_contracts.md)
- （query 系コマンドの場合）schema() の宣言がこのコマンドの振る舞いにどう影響するか
- Ingestion 系コマンド等、Plugin Contract を利用しない場合はこのセクションを省略してよい
