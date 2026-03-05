# 06 BuildContext 設計 (BuildContext & Tombstone)

本ドキュメントは、Plugin Contract の `build()` シグネチャを拡張する `BuildContext` の導入と、削除追跡のための Tombstone テーブル設計を定義する。

設計の前提:
- `01_conceptual_architecture.md` の境界設計（ACL / Bounded Contexts）
- `02_interface_contracts.md` で確定した Plugin Contract（`build()`, `query()`, 型定義）
- `03_data_model.md` の Raw DB スキーマ（Version 2）
- `commands/delete.md` の削除コマンド仕様

---

## 1. 背景と動機

### 1.1 現行 Contract の構造的欠陥

現在の `build(raw_data: RawDataAccessor) -> None` では以下の情報が Plugin に伝わらない。

| # | 問題 | 影響 |
| :--- | :--- | :--- |
| P1 | **フル/インクリメンタルの区別不能** | Accessor のレコードが全件なのか差分なのか不明。Plugin が Context Store の stale エントリを除去する根拠がない |
| P2 | **削除の検知不能** | ハードデリートでレコードが物理消滅すると、Plugin の Context Store に残った古いエントリを掃除する手段がない |
| P3 | **チェックポイント管理の前提崩壊** | P2 により「Plugin 側でチェックポイント管理を推奨」が実現不可能 |

### 1.2 本設計の目的

P1〜P3 を包括的に解決するため、以下の2つの変更を導入する:

1. **`BuildContext`** — `build()` の第2引数としてビルドモードと削除情報を提供する
2. **Tombstone テーブル** — ハードデリート時に削除イベントを記録し、次回ビルドで Plugin に伝達する

---

## 2. BuildContext 型定義

`core/models.py` に追加する。

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping, Sequence

from konkon.core.types import JSONValue

@dataclass(frozen=True)
class DeletedRecord:
    """Tombstone から復元された削除済みレコードの情報。"""
    id: str
    meta: Mapping[str, JSONValue]

@dataclass(frozen=True)
class BuildContext:
    """
    build() に渡されるビルドのメタデータ。

    Attributes:
        mode: ビルドの種類。
            "full" — raw_data は全レコード。Context Store を全再構築すべき。
            "incremental" — raw_data は前回ビルド以降の変更分のみ。
        deleted_records: 前回ビルド以降に削除された Record の情報。
            mode="full" の場合は空。
            mode="incremental" の場合は該当レコードのリスト。
            各要素は id と meta を持つ。Plugin はこれらを Context Store から除去すべき。
    """
    mode: Literal["full", "incremental"]
    deleted_records: Sequence[DeletedRecord] = field(default_factory=tuple)
```

**設計判断:**

| 項目 | 決定 | 根拠 |
| :--- | :--- | :--- |
| `raw_data` の位置 | `build()` の第1引数に維持（`BuildContext` に内包しない） | Accessor とメタデータの関心事分離。`query(request)` との非対称性は「データストリーム + メタデータ」という build の特性で正当化 |
| ビルドモード | `mode: Literal["full", "incremental"]` | `is_full_build: bool` より拡張性が高い（将来の第3モードに対応可能）。型安全で自己文書化 |
| `deleted_records` | `Sequence[DeletedRecord]` | ID のみの `Sequence[str]` から拡張。Plugin が meta に基づいて Context Store を更新できる（例: `source_uri` ベースの管理）。`DeletedRecord` は frozen dataclass で immutable |
| `frozen=True` | 採用 | `RawRecord`, `QueryRequest`, `QueryResult` と同じパターン。Plugin が値を変更することを防ぐ |

### 2.1 公開 API

`konkon/types.py` に `BuildContext` を re-export に追加する:

```python
from konkon.core.models import BuildContext, DeletedRecord
```

Plugin 開発者は以下のインポートパスを使用する:

```python
from konkon.types import BuildContext, DeletedRecord
```

---

## 3. Plugin Contract: build() シグネチャ

> `build(raw_data, context)` が唯一のシグネチャである。

### 3.1 build() シグネチャ

```python
def build(raw_data: RawDataAccessor, context: BuildContext) -> None:
    """
    [Transform (Write) フェーズ]

    raw_data: ビルド対象のレコード
      - mode="full": 全レコード
      - mode="incremental": 前回ビルド以降に追加・更新されたレコードのみ

    context: ビルドのメタデータ
      - context.mode: "full" or "incremental"
      - context.deleted_records: 前回ビルド以降に削除された Record 情報
        （各要素は id と meta を持つ DeletedRecord）

    mode="full" の場合:
      Context Store を全再構築する。deleted_records は空。

    mode="incremental" の場合:
      1. context.deleted_records の各レコードを Context Store から除去する
         （id だけでなく meta も参照可能。例: source_uri ベースの管理）
      2. raw_data に含まれるレコードを Context Store に追加・更新する

    deleted_records の冪等性:
      build() が途中で失敗した場合、次回ビルドで同じ deleted_records が
      再送される。Plugin は deleted_records の処理を冪等に実装すること
      （存在しない ID の削除を無視する等）。
    """
    pass
```

`query()` と `schema()` のシグネチャは **変更なし**。

### 3.2 Plugin Host の Contract 検証

Plugin Host はロード時に `build` が **必須引数を正確に2個（positional のみ）** 持つことを検証する。必須 keyword-only 引数が存在する場合も Contract 不適合とする。不適合の場合は終了コード `3`（ConfigError）で終了する。

```python
import inspect

sig = inspect.signature(plugin.build)
required_positional = [
    p for p in sig.parameters.values()
    if p.kind in (
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    )
    and p.default is inspect.Parameter.empty
]
required_keyword_only = [
    p for p in sig.parameters.values()
    if p.kind == inspect.Parameter.KEYWORD_ONLY
    and p.default is inspect.Parameter.empty
]

if len(required_positional) != 2 or required_keyword_only:
    raise ContractError(
        f"build() must have exactly 2 required positional parameters "
        f"(raw_data, context) and no required keyword-only parameters, "
        f"got {len(required_positional)} positional, "
        f"{len(required_keyword_only)} keyword-only. "
        f"Update your plugin: def build(raw_data, context): ..."
    )

plugin.build(raw_data, build_context)
```

> **SSOT 注記:** Plugin の Contract 検証（必須関数の存在チェック、ロード時の検証フロー）の正規な要件定義は [04_cli_conventions.md §2.6](04_cli_conventions.md) を参照。本ドキュメントの `_REQUIRED_FUNCTIONS` はその実装上の名称であり、04 側の定義が SSOT である。検証仕様（`build` の必須引数2個・keyword-only 引数なし + `query` の存在・呼び出し可能性）は 04_cli_conventions.md §2.6 と整合済み。

### 3.3 Contract 不適合時のエラー

`build()` の必須引数が `(raw_data, context)` の2個でない、または必須 keyword-only 引数を持つ Plugin はロード時にエラーとなる。

**エラーメッセージ:**

```
[ERROR] Contract violation: build() must have exactly 2 required positional
parameters (raw_data, context) and no required keyword-only parameters,
got N positional, M keyword-only.
Update your plugin: def build(raw_data, context): ...
```

`konkon init` テンプレートは `build(raw_data, context)` シグネチャで生成される。

---

## 4. Tombstone テーブル設計

### 4.1 設計方針: ハードデリート + Tombstone

| 方式 | 評価 |
| :--- | :--- |
| ソフトデリート（`deleted_at` 列追加） | **不採用。** `RawRecord` への `deleted_at` 追加は ACL #2 の破壊的変更。Accessor が削除済みを含めて返す場合、セマンティクスが変わり全クエリに影響する。3レビュー全てが不採用と判定 |
| Change Feed（全ミューテーションのイベントログ） | **不採用。** insert/update にも event append が追加され影響範囲が過大。event の無制限成長と compaction の設計が必要。MVP として過剰。3レビューが「将来拡張として記録」を推奨 |
| **ハードデリート + Tombstone テーブル** | **採用。** `raw_records` からは物理削除。別テーブル `raw_deletions` に削除イベントを記録。既存の insert/update パスに影響なし。Tombstone はビルド成功後に purge され長期的なストレージコストなし |

### 4.2 `raw_deletions` テーブル

```sql
CREATE TABLE IF NOT EXISTS raw_deletions (
    record_id   TEXT NOT NULL,
    deleted_at  TEXT NOT NULL,
    meta        TEXT NOT NULL DEFAULT '{}',

    CHECK (record_id <> ''),

    -- meta: JSON オブジェクト（raw_records.meta と同一制約）
    CHECK (json_valid(meta)),
    CHECK (json_type(meta) = 'object'),

    -- Canonical RFC3339 UTC fixed-width (raw_records と同一制約)
    CHECK (length(deleted_at) = 27),
    CHECK (substr(deleted_at, 5, 1)  = '-'),
    CHECK (substr(deleted_at, 8, 1)  = '-'),
    CHECK (substr(deleted_at, 11, 1) = 'T'),
    CHECK (substr(deleted_at, 14, 1) = ':'),
    CHECK (substr(deleted_at, 17, 1) = ':'),
    CHECK (substr(deleted_at, 20, 1) = '.'),
    CHECK (substr(deleted_at, 27, 1) = 'Z')
) STRICT;

CREATE INDEX IF NOT EXISTS idx_raw_deletions_deleted_at
    ON raw_deletions (deleted_at ASC, record_id ASC);
```

| 項目 | 判断 | 理由 |
| :--- | :--- | :--- |
| PRIMARY KEY / UNIQUE | なし | Tombstone は transient（ビルド後に purge）。同一 `record_id` の重複は理論上ないが（ハードデリートで物理消滅済みのレコードを再度削除できない）、制約を課すメリットがない |
| `record_id` の型 | `TEXT NOT NULL` | `raw_records.id` と同一型。FOREIGN KEY は張らない（削除済みなので参照先がない） |
| `deleted_at` の形式 | RFC3339 UTC 固定長（27文字） | `raw_records.created_at` / `updated_at` と同一形式。辞書順比較で時系列フィルタ可能 |
| `meta` の保存 | **する** | Plugin の Context Store は ID だけでインデックスされているとは限らない。meta のキーで Context Store を管理しているケース（例: `source_uri` ベースの管理）があり、削除時に meta に基づいて Context Store を更新する必要がある。`raw_records.meta` と同一の JSON オブジェクト制約を適用 |
| `content` の保存 | **しない** | 削除されたレコードの content を tombstone に複製するのはストレージの浪費。Plugin が必要とするのは「何が消えたか」の識別情報（ID + meta）のみ |

### 4.3 Tombstone のライフサイクル

```text
   konkon delete       Ingestion Context      konkon build           Ingestion Context
   ──────────────── →  ────────────────── →   ─────────────────── →  ────────────────────
   CLI 操作             raw_records DELETE     BuildContext 構築       tombstone purge
                        + raw_deletions        deleted_records に      deleted_at <= build_start
                          INSERT (id+meta)      tombstone を格納       の tombstone を削除
```

**Purge ルール:**

ビルド成功後、`deleted_at <= build_start` の tombstone を削除する。

- **フルビルド後:** Plugin が全再構築するため tombstone は不要。purge する
- **インクリメンタルビルド後:** Plugin が `deleted_records` を受領済みのため purge する
- **ビルド失敗時:** purge しない。次回ビルドで同じ `deleted_records` が再送される（冪等性が前提）
- **Purge 失敗:** ビルド全体の失敗にしない（best-effort）。`--verbose` 時に stderr で診断出力する

### 4.4 SQL 操作マッピング

| 操作 | SQL | インデックス |
| :--- | :--- | :--- |
| 削除 + Tombstone 記録 | `SELECT COALESCE(meta, '{}') FROM raw_records WHERE id = ?` → `DELETE FROM raw_records WHERE id = ?` + `INSERT INTO raw_deletions (record_id, deleted_at, meta) VALUES (?, ?, ?)` （同一トランザクション。meta は削除前に取得し、NULL は `'{}'` に正規化） | PK |
| 削除レコードの取得 | `SELECT record_id, meta FROM raw_deletions WHERE deleted_at > ? ORDER BY deleted_at ASC, record_id ASC` | `idx_raw_deletions_deleted_at` |
| Tombstone の purge | `DELETE FROM raw_deletions WHERE deleted_at <= ?` | `idx_raw_deletions_deleted_at` |

### 4.5 JSON バックエンドへの影響

JSON バックエンド（`json_db.py`）にも同等の tombstone 機構を実装する。

```json
{
  "records": [...],
  "deletions": [
    {"record_id": "019516a0-...", "deleted_at": "2026-03-01T12:00:00.000000Z", "meta": {"source_uri": "file:///path/to/doc.md"}}
  ]
}
```

`deletions` キーが既存ファイルに存在しない場合は空配列として扱う（後方互換）。

---

## 5. Build フロー改訂

### 5.1 ビルドモード決定ロジック

```text
konkon build          → last_build あり → mode="incremental"
konkon build          → last_build なし → mode="full"
konkon build --full   → last_build 無視 → mode="full"
```

### 5.2 フルビルド

```text
Developer ──▶ konkon build --full
                 │
                 ▼
        ┌─ build_start = now(UTC) ─────────────────────────────┐
        │                                                       │
        │  accessor = get_accessor(project_root)  ← 全レコード      │
        │  deleted_records = ()                    ← 空             │
        │  context = BuildContext(mode="full", deleted_records=())  │
        │                                                       │
        │  plugin.build(accessor, context)                      │
        │    └─ Plugin は Context Store を全再構築               │
        │                                                       │
        │  write_last_build(build_start)                        │
        │  purge_tombstones(before=build_start)  ← best-effort │
        └───────────────────────────────────────────────────────┘
```

### 5.3 インクリメンタルビルド

```text
Developer ──▶ konkon build
                 │
                 ▼
        ┌─ build_start = now(UTC) ──────────────────────────────────────┐
        │  last_build = read_last_build()                               │
        │                                                               │
        │  accessor = get_accessor(                                     │
        │    project_root, modified_since=last_build                    │
        │  )                                   ← 更新分のみ            │
        │                                                               │
        │  deleted_records = get_deleted_records_since(                    │
        │    project_root, since=last_build                             │
        │  )                                   ← 削除分                 │
        │                                                               │
        │  context = BuildContext(                                       │
        │    mode="incremental", deleted_records=deleted_records        │
        │  )                                                            │
        │                                                               │
        │  plugin.build(accessor, context)                              │
        │    ├─ context.deleted_records のレコードを Context Store から除去│
        │    └─ raw_data のレコードを Context Store に追加・更新         │
        │                                                               │
        │  write_last_build(build_start)                                │
        │  purge_tombstones(before=build_start) ← best-effort          │
        └───────────────────────────────────────────────────────────────┘
```

### 5.4 ビルド失敗時の動作

ビルドが途中で失敗した場合:

1. **`write_last_build()` は実行されない** — チェックポイントは更新されない
2. **Tombstone は purge されない** — 次回ビルドで同じ `deleted_records` が再送される
3. **Plugin は `deleted_records` の処理を冪等に実装する必要がある** — 存在しない ID の削除を無視する等

この設計により、ビルド失敗後の再ビルドで削除情報が欠落することはない。ただし、Plugin 側が `deleted_records` の処理を冪等にしていない場合（例: 既に除去した ID を再度除去しようとしてエラーを投げる等）、再ビルド時にエラーが発生する可能性がある。Plugin 実装ガイド（§9）でこの冪等性要件を明示する。

### 5.5 チェックポイント方式

現行のタイムスタンプベース（`.konkon/last_build`）を維持する。cursor ベースへの移行は将来拡張とする（§10 参照）。

チェックポイントにビルド完了時刻ではなく **開始時刻** を使用することで、ビルド実行中に発生した更新が次回ビルドで確実に拾われることを保証する（既存の設計を踏襲）。

---

## 6. 各レイヤーへの影響

### 6.1 Ingestion Context

#### backend.py — `RawDBBackend` Protocol 追加メソッド

```python
class RawDBBackend(Protocol):
    # ... 既存メソッド (insert, update, get_record, list_records, accessor, close) ...

    def delete(self, record_id: str) -> None:
        """Delete record from raw_records and create tombstone in raw_deletions.
        Both operations in a single transaction.
        Raises KeyError if record_id not found."""
        ...

    def get_deleted_records_since(self, timestamp: datetime) -> list[DeletedRecord]:
        """Return DeletedRecords with deleted_at > timestamp. Order: deleted_at ASC, record_id ASC."""
        ...

    def purge_tombstones(self, before: datetime) -> int:
        """Remove tombstones with deleted_at <= before. Returns count purged."""
        ...
```

#### __init__.py — Ingestion Facade 追加関数

```python
def delete(record_id: str, project_root: Path) -> None:
    """Delete a record and create a tombstone.
    Raises KeyError if not found. Does NOT create DB if missing."""

def get_deleted_records_since(project_root: Path, since: datetime) -> list[DeletedRecord]:
    """Return DeletedRecords deleted after timestamp. Empty list if DB missing."""

def purge_tombstones(project_root: Path, before: datetime) -> int:
    """Remove old tombstones. Returns 0 if DB missing."""
```

### 6.2 Transformation Context

| コンポーネント | 変更内容 |
| :--- | :--- |
| `plugin_host.py` | `invoke_build()` のシグネチャに `context: BuildContext` を追加。必須 positional パラメータ2個の Contract 検証（不適合は exit 3） |
| `__init__.py` | `run_build()` に BuildContext 構築ロジック。`ingestion.get_deleted_records_since()` 呼び出し。ビルド成功後の tombstone purge (best-effort) |

### 6.3 Application Layer

`delete()` ユースケースを追加（Ingestion Facade への委譲のみ）。`.konkon/last_build` の削除は **不要**（tombstone + BuildContext でインクリメンタルビルドが対処するため）。

### 6.4 Core Models / Public Types

- `core/models.py`: `DeletedRecord`, `BuildContext` dataclass 追加
- `konkon/types.py`: `DeletedRecord`, `BuildContext` の re-export 追加

### 6.5 RawDataAccessor

**変更なし。** 削除情報は `BuildContext.deleted_records` で別経路提供される。`RawDataAccessor` は「Raw DB のレコードを読む」ACL #1 インターフェースとして、その単純性を維持する。

### 6.6 Serving Context

**変更なし。** `query()` のシグネチャは変更されない。

---

## 7. スキーマバージョンとマイグレーション

### 7.1 スキーマバージョン: 2 → 3

`raw_deletions` テーブルの追加に伴い、`PRAGMA user_version` を `3` に変更する。

### 7.2 マイグレーション (Version 2 → 3)

```sql
CREATE TABLE IF NOT EXISTS raw_deletions (
    record_id   TEXT NOT NULL,
    deleted_at  TEXT NOT NULL,
    meta        TEXT NOT NULL DEFAULT '{}',
    CHECK (record_id <> ''),
    CHECK (json_valid(meta)),
    CHECK (json_type(meta) = 'object'),
    CHECK (length(deleted_at) = 27),
    CHECK (substr(deleted_at, 5, 1)  = '-'),
    CHECK (substr(deleted_at, 8, 1)  = '-'),
    CHECK (substr(deleted_at, 11, 1) = 'T'),
    CHECK (substr(deleted_at, 14, 1) = ':'),
    CHECK (substr(deleted_at, 17, 1) = ':'),
    CHECK (substr(deleted_at, 20, 1) = '.'),
    CHECK (substr(deleted_at, 27, 1) = 'Z')
) STRICT;

CREATE INDEX IF NOT EXISTS idx_raw_deletions_deleted_at
    ON raw_deletions (deleted_at ASC, record_id ASC);

PRAGMA user_version = 3;
```

自動適用（03_data_model.md §10 の手順に準拠）。既存データへの影響なし（テーブル追加のみ）。

### 7.3 段階マイグレーション

| From | To | 操作 |
| :--- | :--- | :--- |
| Version 2 | Version 3 | `raw_deletions` テーブル + インデックス作成 |
| Version 1 | Version 3 | Version 1 → 2（既存）→ 3（新規）の段階適用 |

### 7.4 JSON バックエンド

`deletions` キー未存在時は空配列扱い。マイグレーション不要。

---

## 8. 既存設計書への反映

本仕様確定後に反映が必要な箇所:

| 文書 | セクション | 変更内容 |
| :--- | :--- | :--- |
| **02_interface_contracts.md** | §1 (型定義) | `BuildContext` 型定義を追加 |
| | §3.2 (build) | シグネチャを `build(raw_data, context)` に更新（破壊的変更）。`deleted_records` の冪等性要件 |
| | §2.2 (差分ビルド) | Tombstone と `deleted_records` の伝達を追記 |
| **03_data_model.md** | §2.1 (MUST ルール) | 「DELETE は MVP では行わない」→「DELETE はレコード単位の物理削除 + tombstone 記録として許容」 |
| | §3 (ER図) | `raw_deletions` テーブルを追加 |
| | §7 (物理スキーマ) | `raw_deletions` テーブルの DDL を追加 |
| | §7.2 (インデックス) | `idx_raw_deletions_deleted_at` を追加 |
| | §9 (バージョニング) | スキーマバージョン `2` → `3` |
| | §10 (マイグレーション) | Version 2 → 3 マイグレーション手順を追加 |
| | §11 (SQL マッピング) | Tombstone 関連の SQL マッピングを追加 |
| | §12 (完全 DDL) | `raw_deletions` テーブルと `PRAGMA user_version = 3` を追加 |
| | §15 (将来拡張) | 「削除/アーカイブ機構」を実装済みとして更新 |
| **04_cli_conventions.md** | §1.4 (フロー図) | `delete` をフローに追加 |
| | コマンド体系テーブル | `konkon delete` を追加 |
| **05_project_structure.md** | ディレクトリレイアウト | `cli/delete.py` を追加 |
| | Ingestion facade | `delete()`, `get_deleted_records_since()`, `purge_tombstones()` を追加 |
| | backend.py | `RawDBBackend` に3メソッド追加（`delete`, `get_deleted_records_since`, `purge_tombstones`） |
| | types.py | `BuildContext` を追加 |
| **commands/build.md** | 振る舞い | シグネチャを `build(raw_data, context)` に更新。BuildContext の構築フローを追記 |
| | 設計判断 | BuildContext への参照を追加 |
| **commands/init.md** | テンプレート | `konkon.py` テンプレートの `build()` を `build(raw_data, context)` シグネチャに更新 |

---

## 9. Plugin 実装ガイド

### 9.1 基本パターン

```python
"""konkon.py — Plugin 実装例"""
import json
from pathlib import Path
from konkon.types import RawDataAccessor, BuildContext, QueryRequest

STORE = Path("context_store.json")

def schema():
    return {"description": "Example plugin", "params": {}}

def build(raw_data: RawDataAccessor, context: BuildContext) -> None:
    if context.mode == "full":
        # フルリビルド: Context Store を全再構築
        store = {}
        for record in raw_data:
            store[record.id] = record.content
    else:
        # インクリメンタル: 差分適用
        store = json.loads(STORE.read_text()) if STORE.exists() else {}
        # 1. 削除されたエントリを除去（冪等: 存在しない ID は無視）
        for rec in context.deleted_records:
            store.pop(rec.id, None)
        # 2. 新規・更新レコードを追加
        for record in raw_data:
            store[record.id] = record.content

    STORE.write_text(json.dumps(store, ensure_ascii=False))

def query(request: QueryRequest) -> str:
    store = json.loads(STORE.read_text()) if STORE.exists() else {}
    return "\n".join(store.values())
```

### 9.2 大規模向きパターン（フルビルド最適化）

```python
def build(raw_data: RawDataAccessor, context: BuildContext) -> None:
    if context.mode == "full":
        # 差分検出でフルビルドを最適化（LLM API 呼び出し等の高コスト処理向け）
        current_ids = set()
        for record in raw_data:
            current_ids.add(record.id)
            if needs_update(record):
                my_store.upsert(record.id, expensive_transform(record))
        # stale エントリの除去
        for stale_id in my_store.all_ids() - current_ids:
            my_store.delete(stale_id)
    else:
        # インクリメンタル（冪等な削除処理）
        for rec in context.deleted_records:
            my_store.delete_if_exists(rec.id)
        for record in raw_data:
            my_store.upsert(record.id, expensive_transform(record))
```

---

## 10. 将来拡張

本設計で対応しないが、拡張ポイントとして記録するもの:

| 項目 | 説明 |
| :--- | :--- |
| `BuildContext` フィールド追加 | `reason: str`（"initial", "manual_full" 等）、`build_id: str`、`total_record_count: int` 等。frozen dataclass へのフィールド追加は後方互換（default 値） |
| cursor ベースチェックポイント | タイムスタンプ精度衝突の根本解決として、`raw_events` テーブルと sequence ID による差分走査。既存プロジェクトへの移行コストが大きいため現時点では見送り |
| Event sourcing | `raw_deletions` を `raw_events` に一般化し、insert/update/delete の全イベントを記録する形への拡張 |
| バルク削除 | `konkon delete --all`, `--query "..."` 等。Tombstone 機構はバルクに対応可能（各 ID ごとに tombstone を挿入） |
| 削除内容の保存 | Tombstone に `content` を追加し、Plugin に削除前のコンテンツを提供（`meta` は実装済み） |

---

## 設計判断ログ

| # | 判断 | 採用元 | 根拠 |
| :--- | :--- | :--- | :--- |
| D1 | ハードデリート + Tombstone（ハイブリッド方式）を採用 | Claude | ソフトデリートは ACL #1/#2 を破壊する（Gemini 案の問題、3レビュー全てが不採用）。Change Feed は全ミューテーションへの影響が過大で MVP として過剰（Codex 案、3レビューが将来拡張を推奨）。Tombstone は `raw_records` に影響を与えず、insert/update パスの変更なしで削除情報を独立管理できる |
| D2 | `BuildContext` を `build()` の第2引数として追加 | Claude | `raw_data` を `BuildContext` に内包する案と比べ、Accessor とメタデータの関心事分離が明確。3レビュー全てが Claude 案のシグネチャを推奨 |
| D3 | `mode: Literal["full", "incremental"]` を採用 | Claude | `is_full_build: bool`（Gemini）より拡張性が高い。Codex の `BuildMode` と同等。3レビューが Literal を推奨 |
| D4 | `deleted_records` を即座に実装（将来スコープにしない） | Claude | P2/P3 が本設計の出発点。先送りでは問題が解決しない。Tombstone と組み合わせて真のインクリメンタル削除を実現 |
| D5 | 削除後のフルリビルド強制を廃止 | Claude | Plugin は `BuildContext.deleted_records` をインクリメンタルに処理できるため、`.konkon/last_build` の削除によるフルリビルド強制は不要 |
| D6 | 必須 positional パラメータ2個の Contract 検証 | Claude + Codex R2 | `build(raw_data, context)` が唯一のシグネチャ。必須パラメータが2個でない場合は Contract 不適合として exit 3（ConfigError） |
| D7 | `build(raw_data, context)` を唯一の Contract とする | 設計方針 | 旧シグネチャの後方互換ロジックを持たず、`build(raw_data, context)` のみをサポート。Plugin Host の実装が簡素 |
| D8 | `deleted_records` の冪等性を明示 | Claude レビュー C5 | build 失敗後の再ビルドで同じ `deleted_records` が再送される。Plugin 側の冪等な処理が必要であることをドキュメントする。High 指摘の解消 |
| D9 | Tombstone に `meta` を含める。`content` は含めない | Claude | Plugin の Context Store は ID だけでインデックスされているとは限らず、meta のキー（例: `source_uri`）で管理しているケースがある。削除時に meta に基づいて Context Store を更新する必要があるため `meta` を Tombstone に保存する。`content` はストレージ効率の観点から含めない |
| D10 | Tombstone purge は best-effort + 診断出力 | Claude + Codex レビュー | purge 失敗でビルド全体を失敗にするのは過剰。次回ビルドで再度 purge される。Codex レビュー指摘の可視化は `--verbose` 時の診断出力で対応 |
| D11 | cursor ベースチェックポイントは将来拡張 | Codex + 3レビュー合意 | Codex 案の cursor は将来性が高いが、既存プロジェクトへの移行コストが大きい。3レビューが「Phase 2 で必要時に導入」を推奨 |
| D12 | `reason` フィールドは将来拡張 | Codex + Claude レビュー C3 | Codex 案の `reason`（"initial", "manual_full" 等）は診断用途で有用だが、frozen dataclass への default 付きフィールド追加で後方互換に導入可能なため、必要になった時点で追加する |
