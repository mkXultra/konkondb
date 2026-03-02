# konkon serve api — REST API サーバー起動

## 概要

Context Engine の `query()` 出力を REST API サーバーとして外部に公開する。

## Bounded Context

**呼び出すコンテキスト:** Serving → Transformation → User Plugin
**レイヤー:** L3（Serving Adapter）+ L2 + L3

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

## シグネチャ

```
konkon serve api [OPTIONS]
```

共通仕様（シグネチャ概要、共通オプション、ライフサイクル、終了コード）は [04_cli_conventions.md §4](../04_cli_conventions.md) 参照。

## オプション

共通オプション（`--plugin`, `--log-level`）は [04_cli_conventions.md §4.2](../04_cli_conventions.md) 参照。API モード固有のオプション:

| オプション | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `--host` | `TEXT` | `127.0.0.1` | バインドするホスト |
| `--port` | `INT` | `8080` | バインドするポート |
| `--path-prefix` | `TEXT` | `/` | API パスプレフィックス |

## エンドポイント

| メソッド | パス | 説明 |
| :--- | :--- | :--- |
| `POST` | `{path-prefix}/query` | コンテキスト検索 |
| `GET` | `{path-prefix}/healthz` | ヘルスチェック |

`--path-prefix` の末尾スラッシュは正規化される。デフォルト（`/`）の場合は `/query` および `/healthz`。`--path-prefix /api/v1` の場合は `/api/v1/query` および `/api/v1/healthz`。

### `POST /query`

**Request Body:**
```json
{
  "query": "検索文字列",
  "params": {"key": "value"}
}
```

[02_interface_contracts.md](../02_interface_contracts.md) の `QueryRequest` に1対1でマッピングされる。`params` は省略可（デフォルト `{}`）。

**Response Body (200):**
```json
{
  "content": "...",
  "metadata": {}
}
```

`query()` が `str` を返した場合は `{"content": "...", "metadata": {}}` に正規化される。

### `GET /healthz`

**Response (200):**
```json
{
  "status": "ok"
}
```

Plugin のロードが成功しサーバーがリクエストを受付可能な状態を示す。

## バリデーション

以下の場合は HTTP `400` を返す:
- リクエストボディが有効な JSON でない
- `query` フィールドが欠落または `null`
- `query` が文字列型でない
- `params` が指定されているがオブジェクト型でない

## エラーレスポンス

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

## 終了コード

共通終了コードは [04_cli_conventions.md §2.3](../04_cli_conventions.md)、serve 共通の終了コードは [04_cli_conventions.md §4.5](../04_cli_conventions.md) 参照。

## 設計判断・補足

**Plugin Contract との関連:**
- `query(request: QueryRequest) -> str | QueryResult` を各リクエストで Invoke → [02_interface_contracts.md §1](../02_interface_contracts.md)
- `schema()` の宣言は将来的に OpenAPI スキーマの自動生成に活用される可能性がある
