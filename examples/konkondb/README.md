# konkondb self-index example

konkon db 自身のプロジェクトコンテキストを構築するプラグイン実装例。
AI コーディングエージェントに構造化されたプロジェクト情報を提供する。

## ファイル構成

| ファイル | 役割 |
|---|---|
| `konkon.py` | Plugin Contract (`build`, `query`, `schema`)。BUILDS/QUERIES 宣言を汎用的に処理するエンジン |
| `targets.py` | ビルド宣言 (`BUILDS`) とクエリ宣言 (`QUERIES`) の定義。ビュー・セクション・フィルタを宣言的に記述 |
| `llm.py` | Gemini CLI ラッパー。インメモリキャッシュ + キュー書き込み、リトライ、JSON出力パース |
| `context.json` | ビルド済みコンテキストストア（生成物） |
| `llm_cache.json` | LLM 呼び出しキャッシュ（生成物） |

## ビュー

### implementation（実装用コンテキスト）

AI が実装タスクを遂行するためのコンテキスト。

- **L0 凝縮コンテキスト**: 設計ドキュメントを LLM で凝縮し、実装に必要なルール・シグネチャ・制約に絞る
- **実装ファイルマップ**: `src/` `tests/` 配下のファイル一覧 + 1行要約 + WIP ステータス

### design（設計用コンテキスト）

AI が設計判断を理解するためのコンテキスト。

- **設計ドキュメント（raw）**: 設計ドキュメントをそのまま提供（ニュアンスを保持）
- **設計ドキュメント一覧**: `docs/` 配下のファイル一覧 + 1行要約

## アーキテクチャ

```
targets.py                   konkon.py                    context.json
┌─────────────┐              ┌──────────────┐             ┌──────────┐
│ BUILDS      │──build()────▶│ _build_*()   │────────────▶│ views    │
│ (何を入れるか) │              │              │             │ tables   │
└─────────────┘              └──────────────┘             └──────────┘
┌─────────────┐              ┌──────────────┐             ┌──────────┐
│ QUERIES     │──query()────▶│ _render_*()  │◀────────────│ views    │
│ (どう組み立てるか)│              │              │             │ tables   │
└─────────────┘              └──────────────┘             └──────────┘
```

BUILDS と QUERIES は `store_path` 文字列だけで接続される。build と query は互いを知らない。

## 使い方

```bash
# Raw DB にプロジェクトファイルを投入
bash scripts/ingest.sh

# コンテキストをビルド（全件）
uv run konkon build --full

# 実装用コンテキストを取得
uv run konkon search "" --param view=implementation

# 設計用コンテキストを取得
uv run konkon search "" --param view=design

# ソースファイルで絞り込み
uv run konkon search "" --param view=implementation --param source=cli
```

## セクション type

| type | build | query |
|---|---|---|
| `condensed` | LLM でドキュメントを凝縮（`prompt`）または raw 保存（`raw: True`） | ターゲット定義順にセクション見出し付きで出力 |
| `file_map` | 全ファイルのフィールドを LLM 生成（`fields`）+ ルール検出（`computed_fields`） | `filter` で選択、`format` で整形、`file_path` ソート |
| `table_filter` | （build なし。file_map で構築されたテーブルを参照） | テーブルから `filter` で選択して出力 |

## LLM キャッシュ

- `model + prompt` の SHA-256 ハッシュをキーにキャッシュ
- ビルド中はインメモリ dict で高速ヒット判定（スレッドセーフ）
- 書き込みはキューに投入、ビルド完了時に `flush_cache()` で一括ディスク書き込み
- モデル変更時はキャッシュキーが変わるため自動的に再生成
