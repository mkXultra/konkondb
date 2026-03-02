# konkon serve mcp — MCP サーバー起動

## 概要

Context Engine の `query()` 出力を MCP (Model Context Protocol) サーバーとして外部に公開する。

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
konkon serve mcp [OPTIONS]
```

共通仕様（シグネチャ概要、共通オプション、ライフサイクル、終了コード）は [04_cli_conventions.md §4](../04_cli_conventions.md) 参照。

## オプション

共通オプション（`--plugin`, `--log-level`）は [04_cli_conventions.md §4.2](../04_cli_conventions.md) 参照。MCP モード固有のオプション:

| オプション | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `--transport` | `stdio\|sse` | `stdio` | MCP のトランスポート方式 |
| `--host` | `TEXT` | `127.0.0.1` | バインドするホスト（`sse` 時のみ有効） |
| `--port` | `INT` | `8765` | バインドするポート（`sse` 時のみ有効） |
| `--sse-path` | `TEXT` | `/mcp` | SSE エンドポイントパス（`sse` 時のみ有効） |

## トランスポート

| 方式 | 説明 |
| :--- | :--- |
| `stdio` | 標準入出力経由の JSON-RPC。Cursor, Claude Desktop 等のローカル接続用。デフォルト |
| `sse` | HTTP Server-Sent Events。リモート接続用 |

## 公開 Tool

| Tool 名 | 説明 | パラメータ |
| :--- | :--- | :--- |
| `query` | Context Store を検索する | `query: string` (必須), `params: object` (任意) |

Tool の引数は `QueryRequest` にマッピングされ、結果は `QueryResult.content` がテキストとして返される。

## 標準入出力

- `stdio` transport: `stdin` / `stdout` は MCP プロトコル専用。ログは **stderr のみ**に出力される
- `sse` transport: `stdout` は使用しない（予約）。ログは stderr に出力される

## 終了コード

共通終了コードは [04_cli_conventions.md §2.3](../04_cli_conventions.md)、serve 共通の終了コードは [04_cli_conventions.md §4.5](../04_cli_conventions.md) 参照。

## 設計判断・補足

**Plugin Contract との関連:**
- `query(request: QueryRequest) -> str | QueryResult` を各 tool call で Invoke → [02_interface_contracts.md §1](../02_interface_contracts.md)
- `schema()` の `params` 定義は MCP の `tool.inputSchema` にそのまま変換される
