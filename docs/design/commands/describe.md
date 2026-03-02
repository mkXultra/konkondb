# konkon describe — Plugin スキーマの表示

## 概要

`konkon.py` に定義された `schema()` 関数を実行し、Plugin のクエリインターフェース（パラメータ定義・説明）を表示する。

## Bounded Context

**呼び出すコンテキスト:** Transformation Context → User Plugin
**レイヤー:** L2（Contract/Host）+ L3

```text
Developer ──▶ CLI ──▶ Transformation Context (Plugin Host)
                          │
                          └──▶ User Plugin Logic (schema() の実行)
```

## シグネチャ

```
konkon describe [OPTIONS]
```

## オプション

| オプション | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `--plugin` | `PATH` | `<project-dir>/konkon.py` | Plugin ファイルパス |

## 振る舞い

[04_cli_conventions.md §2.6](../04_cli_conventions.md) の共通振る舞いに従う。

1. **プロジェクト解決**: プロジェクトルートを特定する（§2.4）
2. **Plugin 解決**: `--plugin` が指定されていればそのパスを使用、なければ [04_cli_conventions.md §2.6](../04_cli_conventions.md) の Plugin パス解決に従う
3. **Load / Contract 検証**: Plugin をロードし `schema()` が存在し呼び出し可能であることを検証する
4. **CWD 設定**: [04_cli_conventions.md §2.6](../04_cli_conventions.md) の CWD 保証に従う
5. **Invoke**: `schema()` を呼び出し、戻り値が `dict` であることを検証する

### schema() の戻り値検証

- `schema()` が `dict` 以外を返した場合、終了コード `3`（CONFIG_ERROR）
- `schema()` の実行中に例外が発生した場合、終了コード `3`（CONFIG_ERROR）

## stdout 出力

### text フォーマット

```
Description: A semantic search over your notes

Params:
  top_k    integer  Number of results to return (enum: 1, 5, 10; default: 5)

Result: Matching notes with relevance scores
```

- `description` キーがあれば先頭に表示
- `params` キーがあれば各パラメータを `name`, `type`, `description` の順で表示。`enum` / `default` があれば括弧内に追記
- `result` キーがあれば `result.description` を表示

### json フォーマット

`schema()` の戻り値 `dict` をインデント付き JSON で出力する。

```json
{
  "description": "A semantic search over your notes",
  "params": {
    "top_k": {
      "type": "integer",
      "description": "Number of results to return",
      "default": 5
    }
  },
  "result": {
    "description": "Matching notes with relevance scores"
  }
}
```

## 終了コード

共通終了コード（`0`, `1`, `2`）は [04_cli_conventions.md §2.3](../04_cli_conventions.md) 参照。コマンド固有の終了コード:

| コード | 条件 |
| :--- | :--- |
| `3` | `konkon.py` 未検出 / ロード失敗 / `schema()` 未定義 / `schema()` の戻り値が `dict` でない / `schema()` 実行中の例外 |

## 設計判断・補足

**Plugin Contract との関連:**
- `schema() -> dict` の契約に準拠 → [02_interface_contracts.md §1](../02_interface_contracts.md)
- `schema()` のエラーは Plugin ロジックのエラーではなくプロジェクト構成・契約エラーとして扱い、終了コード `3` を返す（`4` / `5` ではない）
- `describe` の出力は `serve mcp` のツール定義や将来的な `search --param` のバリデーションで活用される
