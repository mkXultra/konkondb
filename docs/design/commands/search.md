# konkon search — コンテキスト検索

## 概要

開発者が `konkon.py` に定義した `query()` 関数を実行し、Context Store から結果を取得して stdout に出力する。ローカル開発・デバッグ用の対話的コマンド。

## Bounded Context

**呼び出すコンテキスト:** Transformation Context → User Plugin
**レイヤー:** L2（Contract/Host）+ L3

`serve` と同じ内部パス（`query()` の Invoke）を CLI オーケストレーターから直接呼び出す（Serving Context を経由しない）。

```text
Developer ──▶ CLI ──▶ Transformation Context (Plugin Host)
                          │
                          └──▶ User Plugin Logic (query() の実行)
                                   │
                                   └──▶ Context Store (開発者定義の読み取り元)
```

## シグネチャ

```
konkon search [OPTIONS] QUERY
```

## 引数

| 引数 | 必須 | 説明 |
| :--- | :--- | :--- |
| `QUERY` | Yes | 検索クエリ文字列。`QueryRequest.query` にマッピングされる |

## オプション

| オプション | 短縮形 | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- | :--- |
| `--param` | `-p` | `KEY=VALUE` | — | `QueryRequest.params` に追加するパラメータ。複数回指定可 |
| `--params-file` | | `PATH` | — | JSON ファイルを読み込み `params` として利用 |
| `--plugin` | | `PATH` | `<project-dir>/konkon.py` | Plugin ファイルパス |

### `--param` の値パースルール

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

これにより `QueryRequest.params: Mapping[str, JSONValue]`（[02_interface_contracts.md](../02_interface_contracts.md)）の型契約が満たされる。

## 振る舞い

[04_cli_conventions.md §2.6](../04_cli_conventions.md) の共通振る舞いに従う。`query()` の sync/async 処理も [04_cli_conventions.md §2.6](../04_cli_conventions.md) の規定に従い、非同期の場合は `asyncio.run()` で実行する。

### `query()` の戻り値検証

- `query()` が `None` を返した場合、[02_interface_contracts.md](../02_interface_contracts.md) の契約違反として終了コード `5`（QUERY_ERROR）
- `query()` の戻り値が `str` でも `QueryResult` でもない場合、契約違反として終了コード `5`

## stdout 出力

### text フォーマット

`query()` が `str` を返した場合:
```
<そのまま文字列を出力>
```

`query()` が `QueryResult` を返した場合:
```
<QueryResult.content を出力>
```
`QueryResult.metadata` が空でない場合、`--verbose` 時のみ stderr にメタデータを表示する。

### json フォーマット

常に `content` + `metadata` の統一構造で出力する（`str` の場合は `metadata` を空オブジェクトで補完）。

```json
// query() が str を返した場合
{"content": "結果テキスト", "metadata": {}}

// query() が QueryResult を返した場合
{"content": "結果テキスト", "metadata": {"source": "notes.md", "score": 0.95}}
```

## 終了コード

共通終了コード（`0`, `1`, `2`）は [04_cli_conventions.md §2.3](../04_cli_conventions.md) 参照。コマンド固有の終了コード:

| コード | 条件 |
| :--- | :--- |
| `3` | `konkon.py` 未検出 / ロード失敗 / Contract 不適合 |
| `5` | `query()` 実行中のエラー（`QueryError`、戻り値型不正、Plugin 内の未捕捉例外） |

## 設計判断・補足

**Plugin Contract との関連:**
- `query(request: QueryRequest) -> str | QueryResult` の契約に準拠 → [02_interface_contracts.md §1](../02_interface_contracts.md)
- `schema()` が宣言する `params` 定義は、将来的に `--param` のバリデーションや補完に活用される可能性がある
