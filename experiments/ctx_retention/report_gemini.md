# Context Retention Experiment — gemini-ultra Report

## Experiment Date
2026-03-05

## Setup

- Model: gemini-ultra (gemini-3.1-pro-preview)
- Context: `konkon search "" -p view=dev-full` (2664 lines)
- Canaries: 19 (content hash based, deterministic)
- Patterns:
  - A: コマンド実行 (`uv run konkon search ...`)
  - B: 単一ファイル読み込み (`ctx_full.md`)
  - C: 5ファイル分割読み込み (`ctx_parts/part_01..05.md`, ~530行/file)

## Phase 1 — Context Loading

| Pattern | API calls | Tool calls | Input tokens | 読み込み方法 |
|---|---|---|---|---|
| A | 2 | 1 (shell) | 22,438 | シェルコマンド実行 |
| B | 3 | 2 (read_file) | 58,352 | ctx_full.md を2回読み |
| C | 2 | 5 (read_file) | 51,778 | 5ファイル順次読み |

**注目: Pattern A の input tokens が著しく少ない (22K vs 58K/52K)**

### Session IDs

| Pattern | Phase 1 (load) | Phase 2 (verify) |
|---|---|---|
| A | `a8f92145-8a97-40ac-b374-5511dec5f6a1` | same |
| B | `3a6f823b-7109-4750-82c1-7c6f508469fc` | same |
| C | `b747aaa8-1464-487d-8f98-b24fb09394ae` | same |

## Phase 2 — Verification Results

### Canary Detection

| Metric | A | B | C |
|---|---|---|---|
| Canary count (正解: 19) | 19 (※) | 19 | 19 |
| Canary recall | **14/19 (74%)** | 19/19 (100%) | 19/19 (100%) |
| Canary precision | 14/14 (100%) | 19/19 (100%) | 19/19 (100%) |

**※ Pattern A: agent は「合計19個と記載されていたが、中間が省略されたため14個しか読めなかった」と正直に報告。**

#### Pattern A 欠落カナリア

| # | Canary | Status |
|---|--------|--------|
| 1-3 | CANARY_001〜003 | 検出 |
| 4-8 | CANARY_004〜008 | **欠落** (省略部分に該当) |
| 9-19 | CANARY_009〜019 | 検出 |

原因: シェルコマンド出力が `... [56,330 characters omitted] ...` として中間部分が省略された。

### Comprehension Test (5問)

| 質問 | A | B | C |
|---|---|---|---|
| 1. 根本的な課題意識 | 正答 | 正答 | 正答 |
| 2. build() の役割 | 正答 | 正答 | 正答 |
| 3. raw_records カラム構成 | 正答 | 正答 | 正答 |
| 4. インクリメンタルビルド | 正答 | 正答 | 正答 |
| 5. MCP サーバー公開 | 正答 | 正答 | 正答 |
| **Score** | **5/5** | **5/5** | **5/5** |

注: Pattern A でも理解度テストは全問正答。省略されなかった冒頭・末尾の内容は正確に理解されていた。

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
| A | 1.0 | 0.74 | 1.0 | 1.0 | 1.0 | **0.92** |
| B | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | **1.0** |
| C | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | **1.0** |

## Detailed Stats (from Gemini API)

### Phase 1 (Context Loading)

| Metric | A | B | C |
|---|---|---|---|
| API requests | 2 | 3 | 2 |
| Input tokens | 22,438 | 58,352 | 51,778 |
| Prompt tokens | 29,453 | 88,408 | 51,778 |
| Cached tokens | 7,015 | 30,056 | 0 |
| Candidate tokens | 57 | 40 | 119 |
| Thought tokens | 393 | 493 | 498 |
| Total latency (ms) | 12,348 | 21,648 | 15,967 |

### Phase 2 (Verification)

| Metric | A | B | C |
|---|---|---|---|
| API requests | 1 | 1 | 1 |
| Input tokens | 15,750 | 44,922 | 44,962 |
| Candidate tokens | 1,216 | 1,373 | 1,433 |
| Thought tokens | 2,811 | 2,931 | 2,480 |
| Total latency (ms) | 34,504 | 48,288 | 44,334 |

## Observations

1. **Pattern A でコンテキスト欠損が発生** — シェルコマンドの出力が大きすぎて、Gemini CLI のツール結果に `[56,330 characters omitted]` という省略が入った。これにより CANARY_004〜008 の5個が失われた。

2. **省略はモデルの問題ではなくツールの問題** — Gemini の attention や context window の制約ではなく、CLI ツールがコマンド出力を truncate したことが原因。Phase 1 の input tokens (22K) が B/C (58K/52K) より大幅に少ないことから裏付けられる。

3. **Pattern B/C は完全スコア** — ファイル読み込みでは truncation が発生せず、全カナリアを正確に検出。

4. **B vs C で差なし** — 単一ファイルでも5分割でも結果は同等。ただし B は read_file を2回呼んでいる (おそらくファイルサイズ制限で分割読み) のに対し、C は各ファイルが小さいため1回ずつ。

5. **理解度テストは Pattern A でも全問正答** — 省略されなかった冒頭・末尾の内容に関する質問には正確に回答。省略は中間部分のみに影響。

6. **Gemini の正直さ** — Pattern A で「14個しか読めなかった」と正直に報告した点は注目に値する。数を19と知っていながら実際に読めた分だけを列挙する誠実さがあった。

## Key Finding

**Gemini でのコマンド実行パターン (A) は、出力が大きい場合にツールレベルで truncation が発生するリスクがある。** ファイル読み込みパターン (B/C) を推奨する。
