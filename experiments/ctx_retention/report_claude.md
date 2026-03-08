# Context Retention Experiment — claude-ultra Report

## Experiment Date
2026-03-05

## Setup

- Model: claude-ultra
- Context: `konkon search "" -p view=dev-full` (2664 lines)
- Canaries: 19 (content hash based, deterministic)
- Patterns:
  - A: コマンド実行 (`uv run konkon search ...`)
  - B: 単一ファイル読み込み (`ctx_full.md`)
  - C: 5ファイル分割読み込み (`ctx_parts/part_01..05.md`, ~530行/file)

## Phase 1 — Context Loading

| Pattern | Tool calls | 読み込み方法 |
|---|---|---|
| A | 10 | Bash実行 → 出力がtool result上限超え → ファイル保存 → 500行ずつ6回Read |
| B | 8 | ctx_full.md を500行ずつ7回Read (2000行制限で分割) |
| C | 6 | 5ファイルを各1回Read (~530行/file、制限内で一括読み) |

### Session IDs

| Pattern | Phase 1 (load) | Phase 2 (verify) |
|---|---|---|
| A | `78a941c6-650f-4984-b85b-605eae7db4ec` | `c30c2d25-416e-42e0-9a6d-483d6c52ed40` |
| B | `d74bcebe-0c34-48b1-a77d-93c847673471` | `8c067597-fb3e-4a4e-8f31-b4bd96769536` |
| C | `24d08194-afcc-4c1c-8d93-670d711d3972` | `6cf55190-4381-4dc2-9f12-f797b5732c04` |

## Phase 2 — Verification Results

### Canary Detection (Phase 1)

| Metric | A | B | C |
|---|---|---|---|
| Canary count (正解: 19) | 19 | 19 | 19 |
| Canary recall | 19/19 (100%) | 19/19 (100%) | 19/19 (100%) |
| Canary precision | 19/19 (100%) | 19/19 (100%) | 19/19 (100%) |

全パターンで全カナリアを正確に列挙。hex部分も完全一致。

### Comprehension Test (Phase 2 — 5問)

| 質問 | A | B | C |
|---|---|---|---|
| 1. 根本的な課題意識 | 正答 | 正答 | 正答 |
| 2. build() の役割 | 正答 | 正答 | 正答 |
| 3. raw_records カラム構成 | 正答 | 正答 | 正答 |
| 4. インクリメンタルビルド | 正答 | 正答 | 正答 |
| 5. MCP サーバー公開 | 正答 | 正答 | 正答 |
| **Score** | **5/5** | **5/5** | **5/5** |

### Detail Precision (Phase 3)

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

1. **全パターンで完全スコア** — 2664行 / 19カナリアのコンテキスト量では、claude-ultra のコンテキストウィンドウに十分な余裕があり、方式による差は検出されなかった。

2. **Tool call 数の差異は存在する** — A(10), B(8), C(6) と方式によりAPI呼び出し回数が異なる。理論的には API call が多いほど同じコンテキストに対するアテンションが繰り返されるが、今回の結果からは保持率への影響は確認できなかった。

3. **回答の質にも有意差なし** — 3パターンとも同様の構造・深さで回答しており、理解の粒度にも差は見られなかった。

## Cross-Model Comparison

同一実験条件での他モデル結果: [report_codex.md](report_codex.md), [report_gemini.md](report_gemini.md)

| Model | A | B | C | 特記事項 |
|---|---|---|---|---|
| claude-ultra | 1.0 | 1.0 | 1.0 | 全パターン完全。tool callは最多(10/8/6) |
| codex-ultra | 1.0 | 1.0 | 1.0 | 全パターン完全 |
| gemini-ultra | 0.92 | 1.0 | 1.0 | Pattern A でツール出力 truncation により5カナリア欠落 |

## Next Steps

- [ ] コンテキスト量を増やして再実験（context window の限界付近）
- [ ] 複数回実行による統計的検証
