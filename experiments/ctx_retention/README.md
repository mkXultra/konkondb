# Context Retention Experiment

## Purpose

LLM agent にコンテキストを渡す方法 (A/B/C) でどれが最も記憶保持率が高いかを検証する。

## Directory Structure

```
experiments/ctx_retention/
├── README.md
├── work/
│   ├── a/                       ← Pattern A (command execution)
│   │   ├── claude/              ← claude-ultra run 1, 2, 3...
│   │   ├── codex/
│   │   └── gemini/
│   ├── b/                       ← Pattern B (single file read)
│   │   ├── claude/
│   │   ├── codex/
│   │   └── gemini/
│   └── c/                       ← Pattern C (multiple file read)
│       ├── claude/
│       ├── codex/
│       └── gemini/
│
│   各ディレクトリに examples/konkondb/ をディレクトリごとコピー:
│   ├── .konkon/                 ← DB コピー
│   ├── konkon.py                ← カナリア注入版 → 後で元版に差し替え
│   ├── targets.py, llm.py      ← plugin 依存ファイル
│   ├── context.json             ← Context Store
│   └── llm_cache.json           ← LLM キャッシュ

/Users/mk/dev/personal-pj/konkondb/canaries.md  ← 正解データ (agent から見えない)
```

## Canary Design

### Injection Strategy

query() の出力はセクション区切りで構成されている。各セクション境界にユニークなカナリア文字列を挿入する。

```
@@CANARY_001_<random_hex>@@   ← セクション 1 の前
[セクション 1 の内容]
@@CANARY_002_<random_hex>@@   ← セクション 2 の前
[セクション 2 の内容]
...
@@CANARY_N_<random_hex>@@     ← 最後のセクションの後
```

- 各カナリアはユニークな連番 + ランダム hex を含む
- カナリアの数・値は実行時に動的に決まる（agent には事前に教えない）
- query() 実行時に `/Users/mk/dev/personal-pj/konkondb/canaries.md` に正解データを書き出す:
  - カナリアの総数
  - 各カナリアの値
  - 各カナリアの挿入位置（行番号）

### Why This Works

- agent はカナリアの数も値も知らない
- 正解を教えずに「いくつあった？」「全部列挙して」と聞く
- 検出できた数・正確さで context window 内の保持率を客観測定できる
- セクション単位の粒度で「どこまで届いたか」が分かる

## Setup

### 1. Create experiment directories + copy DB

```bash
for pattern in a b c; do
  for model in claude codex gemini; do
    dir="experiments/ctx_retention/work/$pattern/$model"
    cp -r examples/konkondb "$dir"
    cp -r .konkon "$dir/"
  done
done
```

### 2. Create canary-injected konkon.py

- `query()` 内の各セクション境界でカナリア文字列を出力に挿入
- 同時に `/Users/mk/dev/personal-pj/konkondb/canaries.md` に正解データを書き出し
- カナリア形式: `@@CANARY_NNN_<8桁hex>@@`

### 3. Measure output size

```bash
cd experiments/ctx_retention/work/a/claude && uv run konkon search "" -p view=dev-full | wc -l
```

## Patterns

### Pattern A: Direct Command Execution

workdir: `work/a/<model>/`

1. agent を workdir で起動、`uv run konkon search "" -p view=dev-full` を実行させる
2. session_id を記録
3. workdir の `konkon.py` を元版（カナリアなし）に差し替え
4. session_id で再開 → 検証クエリを投げる

### Pattern B: Single File Read

workdir: `work/b/<model>/`

1. カナリア入り出力を生成:
   ```bash
   cd work/b/<model> && uv run konkon search "" -p view=dev-full > ctx_full.md
   ```
2. agent を workdir で起動、`ctx_full.md` を read させる
3. session_id を記録
4. `ctx_full.md` を削除 + `konkon.py` を元版に差し替え
5. session_id で再開 → 検証クエリ

### Pattern C: Multiple File Read

workdir: `work/c/<model>/`

1. カナリア入り出力を生成し、セクション区切り (---) で分割:
   ```bash
   cd work/c/<model> && uv run konkon search "" -p view=dev-full > ctx_full.md
   # --- 区切りでファイル分割（セクション単位）
   ```
2. agent を workdir で起動、各ファイルを順番に read させる
3. session_id を記録
4. 分割ファイル + `ctx_full.md` を削除 + `konkon.py` を元版に差し替え
5. session_id で再開 → 検証クエリ

## Verification Query (common to all patterns)

```
以下のルールに従って回答してください。
ファイルを読んだりコマンドを実行せず、記憶のみで回答してください。

Phase 1 — カナリア検出:
先ほど読んだコンテキストの中に @@CANARY_ で始まる目印文字列が埋め込まれていました。
1. カナリア文字列は合計いくつありましたか？
2. 覚えている全てのカナリア文字列を正確に列挙してください。

Phase 2 — 理解度テスト (5問):
1. [冒頭付近の内容に関する質問]
2. [前半の内容に関する質問]
3. [中盤の内容に関する質問]
4. [後半の内容に関する質問]
5. [末尾付近の内容に関する質問]

Phase 3 — 詳細精度:
1. raw_deletions テーブルの CHECK 制約を列挙して
2. build() の引数を型付きで書いて
```

## Evaluation

| Metric | Measurement | Weight |
|---|---|---|
| Canary count | 正解の総数との一致 | 0.1 |
| Canary recall | 列挙できたカナリア数 / 正解の総数 | 0.3 |
| Canary precision | 列挙の中で正確だったもの / 列挙数 | 0.1 |
| Comprehension | 5問正答率 (0-5) | 0.3 |
| Detail precision | 2問の正確さ (0-2) | 0.2 |

### Scoring per pattern

各パターンで上記指標を計測し、加重スコアを算出:
```
Score = count×0.1 + recall×0.3 + precision×0.1 + comprehension×0.3 + detail×0.2
```

## Reproducibility

- Run each pattern 2-3 times
- Compare with same model (claude-ultra)
- Optionally test with codex-ultra, gemini-ultra
- Record session_ids for all runs
