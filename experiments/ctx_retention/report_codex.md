# Context Retention Experiment — codex-ultra Report

## Experiment Date
2026-03-05

## Setup

- Model: codex-ultra
- Context: `konkon search "" -p view=dev-full` (2664 lines)
- Canaries: 19 (content hash based, deterministic)
- Patterns:
  - A: コマンド実行 (`uv run konkon search ...`)
  - B: 単一ファイル読み込み (`ctx_full.md`)
  - C: 5ファイル分割読み込み (`ctx_parts/part_01..05.md`, ~530行/file)

## Phase 1 — Context Loading

| Pattern | Tool calls | 読み込み方法 |
|---|---|---|
| A | N/A | Bash実行 (codex内部でシェル実行) |
| B | N/A | ファイル読み込み |
| C | N/A | 5ファイル順次読み込み |

### Session IDs

| Pattern | Phase 1 (load) | Phase 2 (verify) |
|---|---|---|
| A | `019cbc83-237a-7611-9cd0-582a5b4893c1` | same (session継続) |
| B | `019cbc83-2f68-7953-acaf-b4ba52ecf6bc` | same |
| C | `019cbc83-3f50-7c92-a332-81a46919bb08` | same |

## Phase 2 — Verification Results

### Canary Detection

| Metric | A | B | C |
|---|---|---|---|
| Canary count (正解: 19) | 19 | 19 | 19 |
| Canary recall | 19/19 (100%) | 19/19 (100%) | 19/19 (100%) |
| Canary precision | 19/19 (100%) | 19/19 (100%) | 19/19 (100%) |

全パターンで全カナリアを正確に列挙。hex部分も完全一致。

### Comprehension Test (5問)

| 質問 | A | B | C |
|---|---|---|---|
| 1. 根本的な課題意識 | 正答 | 正答 | 正答 |
| 2. build() の役割 | 正答 | 正答 | 正答 |
| 3. raw_records カラム構成 | 正答 | 正答 | 正答 |
| 4. インクリメンタルビルド | 正答 | 正答 | 正答 |
| 5. MCP サーバー公開 | 正答 | 正答 | 正答 |
| **Score** | **5/5** | **5/5** | **5/5** |

### Detail Precision

| 質問 | A | B | C |
|---|---|---|---|
| 1. raw_deletions CHECK制約 | 全11制約列挙 | 全11制約列挙 | 全11制約列挙 |
| 2. build() 型付き引数 | 正確 | 正確 | 正確 |
| **Score** | **2/2** | **2/2** | **2/2** |

## Weighted Score

```
Score = count×0.1 + recall×0.3 + precision×0.1 + comprehension×0.3 + detail×0.2
```

| Pattern | count | recall | precision | comprehension | detail | **Total** |
|---|---|---|---|---|---|---|
| A | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | **1.0** |
| B | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | **1.0** |
| C | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | **1.0** |

## Observations

1. **全パターンで完全スコア** — claude-ultra と同様、2664行のコンテキスト量では方式による差は検出されなかった。

2. **Session 継続性** — codex-ultra は長寿命セッションのため、Phase 1 と Phase 2 で同一 session_id を維持。context overflow なし。

3. **回答スタイル** — claude-ultra と比較してやや簡潔。Pattern B で `async def build(...)` にも言及する追加情報あり（設計書に記載あり、誤りではない）。

4. **パターン間の回答一貫性** — A/B/C 全て同一の内容・構造で回答しており、方式による理解の偏りは見られなかった。
