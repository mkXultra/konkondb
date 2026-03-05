"""konkon plugin — konkon db 実装用コンテキスト.

build() は BUILDS 宣言に従いストアにデータを書き込む。
query() は QUERIES 宣言に従いストアからレスポンスを組み立てる。
両者は store_path だけで接続される。

Context Store: context.json (plugin dir)
"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from konkon.types import BuildContext, RawDataAccessor, QueryRequest, QueryResult

import llm
from targets import BUILDS, QUERIES

MAX_WORKERS = 4

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PLUGIN_DIR = Path(__file__).parent
CONTEXT_FILE = PLUGIN_DIR / "context.json"
CACHE_FILE = PLUGIN_DIR / "llm_cache.json"

# ---------------------------------------------------------------------------
# Store helpers
# ---------------------------------------------------------------------------


def _load_store() -> dict:
    if CONTEXT_FILE.exists():
        return json.loads(CONTEXT_FILE.read_text())
    return {"version": 1, "views": {}, "tables": {}}


def _save_store(store: dict) -> None:
    CONTEXT_FILE.write_text(json.dumps(store, ensure_ascii=False, indent=2) + "\n")


def _store_get(store: dict, path: str):
    """store_path (e.g. 'views.implementation.l0') からネストした値を取得."""
    node = store
    for key in path.split("."):
        node = node.get(key, {})
    return node


def _store_merge(store: dict, path: str, value) -> None:
    """store_path に差分マージで書き込む.

    - dict: 既存 dict に update（差分ビルドで一部キーだけ更新）
    - list[dict]: file_path キーで既存エントリを更新、新規は追加
    - その他: 上書き
    """
    keys = path.split(".")
    node = store
    for key in keys[:-1]:
        node = node.setdefault(key, {})

    existing = node.get(keys[-1])

    if isinstance(value, dict) and isinstance(existing, dict):
        existing.update(value)
    elif isinstance(value, list) and isinstance(existing, list):
        # list[dict] を file_path キーでマージ
        index = {r["file_path"]: i for i, r in enumerate(existing) if "file_path" in r}
        for entry in value:
            fp = entry.get("file_path")
            if fp and fp in index:
                existing[index[fp]] = entry
            else:
                existing.append(entry)
    else:
        node[keys[-1]] = value


# ---------------------------------------------------------------------------
# Build — BUILDS 宣言を処理
# ---------------------------------------------------------------------------


def _extract_one(fp: str, prompt: str, content: str) -> tuple[str, str]:
    """1ファイルのLLM凝縮（スレッドプール用）."""
    result = llm.extract(prompt, content, cache_file=CACHE_FILE)
    return fp, result


def _build_condensed(decl: dict, records: list, pool: ThreadPoolExecutor) -> dict[str, str]:
    """type=condensed: LLM凝縮ターゲットを並列ビルド."""
    targets = decl["targets"]
    result: dict[str, str] = {}
    futures = []

    for record in records:
        fp = record.meta.get("file_path", "")
        if not isinstance(fp, str) or fp not in targets:
            continue

        target = targets[fp]
        if target.get("raw"):
            result[fp] = record.content
            print(f"  RAW {fp} ({len(record.content)} chars)", file=sys.stderr)
        else:
            print(f"  BUILD {fp} ...", file=sys.stderr)
            fut = pool.submit(_extract_one, fp, target["prompt"], record.content)
            futures.append(fut)

    for fut in as_completed(futures):
        fp, content = fut.result()
        result[fp] = content
        print(f"  DONE {fp} ({len(content)} chars)", file=sys.stderr)

    return result


def _extract_fields(fp: str, content: str, fields: dict, computed_fields: dict) -> dict[str, str]:
    """1ファイルの全フィールドをLLM生成 + computed_fields 適用（スレッドプール用）."""
    entry: dict[str, str] = {"file_path": fp}
    for field_name, field_def in fields.items():
        entry[field_name] = llm.extract(field_def["prompt"], content, cache_file=CACHE_FILE)
    for field_name, fn in computed_fields.items():
        entry[field_name] = fn(content)
    return entry


def _build_file_map(decl: dict, records: list, pool: ThreadPoolExecutor) -> list[dict[str, str]]:
    """type=file_map: 全ファイルのフィールドを並列LLM生成."""
    fields = decl["fields"]
    computed_fields = decl.get("computed_fields", {})
    fixed_entries = decl.get("fixed_entries", [])
    fixed_paths = {e["file_path"] for e in fixed_entries}
    futures = {}

    for record in records:
        fp = record.meta.get("file_path", "")
        if not isinstance(fp, str) or not fp:
            continue
        if fp in fixed_paths:
            continue

        print(f"  FILEMAP {fp} ...", file=sys.stderr)
        fut = pool.submit(_extract_fields, fp, record.content, fields, computed_fields)
        futures[fut] = fp

    file_map: list[dict[str, str]] = []
    for fut in as_completed(futures):
        entry = fut.result()
        file_map.append(entry)
        print(f"  DONE {futures[fut]} ({len(fields)} fields)", file=sys.stderr)

    for entry in fixed_entries:
        file_map.append(dict(entry))
        print(f"  FIXED {entry['file_path']}", file=sys.stderr)

    return file_map


_BUILD_HANDLERS = {
    "condensed": _build_condensed,
    "file_map": _build_file_map,
}


# ---------------------------------------------------------------------------
# Query — QUERIES 宣言を処理
# ---------------------------------------------------------------------------


def _render_condensed(section: dict, store: dict, source_filter: str) -> tuple[list[str], list[str]]:
    """type=condensed セクションをレンダリング."""
    targets = section["targets"]
    data = _store_get(store, section["store_path"])

    parts = []
    sources = []

    for fp in targets:
        if fp not in data:
            continue
        if source_filter and source_filter not in fp:
            continue
        label = targets[fp].get("label", fp)
        parts.append(f"## {label}\n\n{data[fp]}")
        sources.append(fp)

    return parts, sources


def _render_table_filter(section: dict, store: dict) -> list[str]:
    """type=table_filter セクションをレンダリング."""
    records = _store_get(store, section["store_path"])
    if not isinstance(records, list):
        return []

    filtered = [r for r in records if section["filter"](r)]
    if not filtered:
        return []

    filtered.sort(key=lambda r: r.get("file_path", ""))

    fmt = section["format"]
    lines = [" ".join(fmt.format(**r).split()) for r in filtered]
    return [f"## {section['label']}\n\n" + "\n".join(lines)]


_RENDER_HANDLERS = {
    "condensed": _render_condensed,
    "table_filter": _render_table_filter,
}


# ---------------------------------------------------------------------------
# Plugin Contract
# ---------------------------------------------------------------------------


def schema():
    """Declare the query interface."""
    return {
        "description": (
            "konkon db プロジェクトコンテキスト。"
            "view パラメータで取得するコンテキストの種類を指定する。"
        ),
        "params": {
            "view": {
                "type": "string",
                "description": "コンテキストのビュー種別",
                "enum": list(QUERIES.keys()),
                "default": "implementation",
            },
            "source": {
                "type": "string",
                "description": "ソースファイルパスで絞り込み（部分一致）",
            },
        },
        "result": {
            "description": "指定ビューのコンテキスト（凝縮済み Markdown）",
            "metadata_keys": ["view", "sources", "total_sources"],
        },
    }


def _purge_deleted(store: dict, deleted_paths: set[str]) -> int:
    """削除されたファイルのデータを store から除去する.

    condensed store (dict): 該当 file_path のキーを削除
    file_map store (list[dict]): 該当 file_path の entry を除去

    Returns: 除去されたエントリ数
    """
    count = 0
    for decl in BUILDS:
        data = _store_get(store, decl["store_path"])
        if isinstance(data, dict):
            for fp in deleted_paths:
                if fp in data:
                    del data[fp]
                    count += 1
        elif isinstance(data, list):
            before = len(data)
            data[:] = [e for e in data if e.get("file_path") not in deleted_paths]
            count += before - len(data)
    return count


def build(raw_data: RawDataAccessor, context: BuildContext) -> None:
    """BUILDS 宣言に従いストアにデータを書き込む."""
    store = _load_store()

    # インクリメンタルビルド時: 削除レコードを store から除去
    if context.mode == "incremental" and context.deleted_records:
        deleted_paths = {
            rec.meta.get("file_path")
            for rec in context.deleted_records
            if isinstance(rec.meta.get("file_path"), str) and rec.meta.get("file_path")
        }
        if deleted_paths:
            removed = _purge_deleted(store, deleted_paths)
            for fp in sorted(deleted_paths):
                print(f"  DELETE {fp}", file=sys.stderr)
            print(f"  Purged {removed} entries", file=sys.stderr)

    records = list(raw_data)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for decl in BUILDS:
            handler = _BUILD_HANDLERS[decl["type"]]
            result = handler(decl, records, pool)
            _store_merge(store, decl["store_path"], result)
            print(f"  {decl['store_path']}: {len(result)} entries", file=sys.stderr)

    llm.flush_cache()
    _save_store(store)
    print("\nBuild complete.", file=sys.stderr)


def query(request: QueryRequest) -> QueryResult:
    """QUERIES 宣言に従いストアからレスポンスを組み立てる."""
    view_name = request.params.get("view", "implementation")
    view = QUERIES.get(view_name)
    if not view:
        return QueryResult(
            content=f"未知のビュー: '{view_name}'。利用可能: {', '.join(QUERIES)}"
        )

    store = _load_store()
    source_filter = request.params.get("source", "")

    parts = []
    sources = []

    for section in view["sections"]:
        handler = _RENDER_HANDLERS[section["type"]]
        if section["type"] == "condensed":
            p, s = handler(section, store, source_filter)
            parts.extend(p)
            sources.extend(s)
        else:
            p = handler(section, store)
            parts.extend(p)

    if not parts:
        return QueryResult(
            content=f"'{view_name}' コンテキスト未構築。`konkon build --full` を実行してください。"
        )

    header = f"# {view['title']}\n\n"
    body = "\n\n---\n\n".join(parts)

    return QueryResult(
        content=header + body,
        metadata={"view": view_name, "sources": sources, "total_sources": len(sources)},
    )
