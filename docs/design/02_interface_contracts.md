# インターフェース・コントラクト仕様 (Interface Contracts)

本ドキュメントは、`konkon db` のアーキテクチャ境界（ACL）を越えるデータの型と、開発者が実装すべき関数のシグネチャを定義します。

## 1. Plugin Contract (開発者向けAPI)

開発者はプロジェクトのルートにある `konkon.py` に、以下の関数とロジックを実装します。これが「Transformation Context」と「User Plugin Logic」をつなぐ唯一の接点（ACL #2）となります。

> **両関数の実装は必須。** Plugin Host はモジュールの Load 時に `build()` と `query()` の両関数の存在を検証し、欠けている場合は明確なエラーメッセージで起動を中断する。

```python
from __future__ import annotations

from typing import Iterator, Mapping, Protocol, TypeAlias
from dataclasses import dataclass, field
from datetime import datetime

# ---------------------------------------------------------
# 0. JSON安全な型定義 (ACL境界の安全性確保)
# ---------------------------------------------------------
JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]

# ---------------------------------------------------------
# 1. エラーハンドリング (Exceptions)
# ---------------------------------------------------------
class KonkonError(Exception):
    """konkon db のベース例外クラス"""
    pass

class BuildError(KonkonError):
    """ビルドフェーズで発生したエラー。Plugin Hostはこれを捕捉し、診断ログを出力して安全に終了する。"""
    pass

class QueryError(KonkonError):
    """クエリフェーズで発生したエラー。Serving層には適切なHTTP/MCPエラーとして翻訳される。"""
    pass

# Plugin Host は任意の未捕捉例外を捕捉し、Build/Query のフェーズに応じて
# 診断ログ（トレースバック含む）を出力する。KonkonError のサブクラスは
# 「想定されたエラー」としてクリーンなメッセージが表示され、
# それ以外の例外は「予期しないクラッシュ」として完全なトレースバックが記録される。

# ---------------------------------------------------------
# 2. データの型定義 (Data Models)
# ---------------------------------------------------------

@dataclass(frozen=True)
class RawRecord:
    """
    Raw DB から読み出された1件の生データ（frozen=True による浅いイミュータビリティ）。
    DX向上のため、メタデータはネストさせずフラットに配置する。

    注意: frozen=True はトップレベルの属性への再代入を防ぐが、
    ネストされた dict 等の中身は変更可能（shallow immutability）。
    """
    id: str
    source_uri: str | None       # データの出所（ファイルパス、URL等）。stdin等で不明な場合は None
    ingested_at: datetime         # UTC-aware な datetime
    content_type: str | None     # MIME type 等。不明な場合は None
    content: str                  # PRDの通り、テキスト/JSON等の文字列データを想定

class RawDataAccessor(Protocol):
    """
    ACL #1: Raw DB のスキーマを隠蔽し、安全にデータを供給するインターフェース。
    メモリ安全性を保つためイテラブルとして振る舞うが、再イテレート可能でなければならない。

    イテレーション順序は決定的: ORDER BY ingested_at ASC, id ASC（since() と同一）。
    """
    def __iter__(self) -> Iterator[RawRecord]: ...
    def __len__(self) -> int:
        """レコードの総数。O(1) を想定するが、バックエンドによっては COUNT(*) が
        必要になる場合がある。ホットループ内での呼び出しは避けること。"""
        ...

    def since(self, timestamp: datetime) -> 'RawDataAccessor':
        """
        インクリメンタルビルド（差分更新）用。
        指定された日時以降に取り込まれたレコードのみを返す新しいAccessorを生成する。
        （DBレベルの WHERE 句として最適化されて実行される）

        セマンティクス:
        - timestamp は UTC-aware な datetime でなければならない。
        - フィルタリングは **exclusive**（`ingested_at > timestamp`）。
        - 返却順序は決定的: `ORDER BY ingested_at ASC, id ASC`。
        - 返却される Accessor は完全な RawDataAccessor であり、__iter__, __len__, since() をサポートする。

        注意: since() は DX 優先の利便性メソッドである。
        タイムスタンプの精度衝突下で厳密な正確性が必要な場合、プラグイン側で
        (last_ingested_at, last_id) のペアをチェックポイントとして保存し、
        重複を排除するロジックを組むことを推奨する。
        将来的に opaque cursor ベースのアクセサが導入される可能性がある。
        """
        ...

@dataclass(frozen=True)
class QueryRequest:
    """ACL #3: Serving層から渡される正規化された検索リクエスト"""
    query: str
    params: Mapping[str, JSONValue] = field(default_factory=dict)

@dataclass(frozen=True)
class QueryResult:
    """
    ACL #3: Serving層へ返す正規化された結果（メタデータが必要な場合）。

    注意: frozen=True による浅いイミュータビリティ。Mapping 型を使用することで
    読み取り専用の意図を明示している。
    """
    content: str
    metadata: Mapping[str, JSONValue] = field(default_factory=dict)

# ---------------------------------------------------------
# 3. プラグイン関数のシグネチャ (The Contract)
# ---------------------------------------------------------
# 備考: 開発者は `def` (同期) と `async def` (非同期) のどちらを使ってもよい。
# Plugin Host 側が inspect.iscoroutinefunction() で判定し、適切にルーティングする。
# さらに、関数実行結果に対して inspect.isawaitable(result) を確認し、
# await 可能であれば await する（デコレータやラッパー関数への対応）。
#
# 同期版:   def build(raw_data: RawDataAccessor) -> None: ...
# 非同期版: async def build(raw_data: RawDataAccessor) -> None: ...
# 同期版:   def query(request: QueryRequest) -> str | QueryResult: ...
# 非同期版: async def query(request: QueryRequest) -> str | QueryResult: ...

def build(raw_data: RawDataAccessor) -> None:
    """
    [Transform (Write) フェーズ]
    Raw DB からストリームでデータを読み出し、開発者独自の Context DB を構築・更新する。

    フレームワーク保証: 実行時のカレントディレクトリはプロジェクトルート
    （konkon.py があるディレクトリ）に設定される。
    """
    pass

def query(request: QueryRequest) -> str | QueryResult:
    """
    [Retrieve (Read) フェーズ]
    Serving層からの検索要求を受け取り、Context DB から情報を引き出して返す。

    戻り値に None は不可。結果がない場合は空文字列 "" または
    QueryResult(content="") を返すこと。

    フレームワーク保証: 実行時のカレントディレクトリはプロジェクトルート
    （konkon.py があるディレクトリ）に設定される。
    """
    pass
```

## 2. 設計の意図とベストプラクティス (DX と 安全性)

### 2.1 非同期 (Async) と同期 (Sync) の両対応
RAG構築において、LLM API の呼び出しや外部 Vector DB へのクエリは I/O バウンドな処理です。特に `query()` は API サーバー（Serving Context）から呼ばれるため、同期関数を強制するとサーバー全体がブロックしてしまいます。
そのため、本システムでは `async def` をフルサポートしつつ、初心者向けには単なる `def` で書いても動く（内部で `asyncio.to_thread` 等でラップされる） FastAPI ライクな親切な設計を採用しています。

**Plugin Host の呼び出しルール:**
1. `inspect.iscoroutinefunction()` で非同期関数かどうかを Load 時に判定する。
2. 関数実行後、戻り値に対して `inspect.isawaitable(result)` を確認し、await 可能であれば await する（デコレータやラッパー関数への堅牢な対応）。
3. サーバーモードにおいて同期 `query()` は `asyncio.to_thread()` でスレッドプールにオフロードされる。

> **注意: サーバーモードでは `query()` が同時に複数回呼ばれる可能性がある。** Context Store への同時アクセスに対するスレッドセーフ性・非同期安全性の確保は開発者の責任となる。

### 2.2 差分ビルドと DBレベルのフィルタリング (`since`)
Pythonのループ内で `if record.ingested_at > last_build:` と書くと、毎回数百万件のレコードをメモリにロードする O(N) のコストがかかります。`raw_data.since()` を提供することで、内部の SQLite に対して `WHERE ingested_at > ?` を発行でき、極めて高速なインクリメンタルビルドが可能になります。

`since()` のセマンティクスは以下の通り厳密に定義されます:
- 引数は **UTC-aware な `datetime`** でなければならない。
- フィルタリングは **exclusive**（`ingested_at > timestamp`、指定時刻を含まない）。
- 返却順序は **決定的**: `ORDER BY ingested_at ASC, id ASC`。

> **将来の拡張:** `since()` は利便性優先のメソッドである。タイムスタンプの精度衝突が問題となる大規模運用では、opaque cursor ベースのアクセサ（`iter_records(after_cursor=...)` 等）を将来導入する可能性がある。

### 2.3 ビルドの失敗とアトミック性 (Atomic Updates)
Context DB の中身はシステムから「不透明（Opaque）」であるため、`build()` 実行中にエラー（10GBの処理中、5GB時点でAPIが落ちるなど）が起きても、システム側では Context DB をロールバックできません。
**ベストプラクティス:**
開発者は `build()` の中で、現在の Context DB を直接上書きするのではなく、「テンポラリのDB/ディレクトリに書き込み、全処理が成功した最後にリネーム（アトミックな入れ替え）を行う」実装をすることが強く推奨されます。

### 2.4 キャンセル・中断のセマンティクス
`build()` が Ctrl+C、サーバーシャットダウン、タイムアウト、`asyncio.CancelledError` 等により中断された場合、そのビルドは**失敗（またはキャンセル）**として扱われる。フレームワークによる Context Store のロールバックは一切行われない。開発者は 2.3 のアトミック更新パターンに従うことで、中断時にも Context Store の一貫性を保つことができる。

### 2.5 型安全性と ACL 境界の保護
`QueryRequest.params` と `QueryResult.metadata` には `Mapping[str, JSONValue]` 型を使用し、`Any` を排除している。これにより:
- シリアライズ不可能なオブジェクト（DBセッション、例外オブジェクト等）の ACL 境界越えを型レベルで防止する。
- CLI / REST API / MCP のいずれの出力フォーマットでも安全にレンダリング可能であることを保証する。
- `Mapping`（`dict` ではなく）を使用することで、読み取り専用の意図を型で明示する。
