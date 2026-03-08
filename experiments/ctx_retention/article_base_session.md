# Claude / Codex / Gemini に毎回同じ説明をするのをやめた — 「ベースセッション」という考え方

## TL;DR

- **ベースセッション** = Agent にプロジェクトのコンテキストを1回読み込ませ、session_id で何度でも再開できるセッション
- Agent 固有の設定ファイル（CLAUDE.md 等）とは別に、**全 Agent 共通で使える「知識の注入口」** として機能する
- マルチ Agent / Agent in Agent 時代に、コンテキスト共有のボトルネックを解消する実用パターン

## はじめに

自分は Claude Code・Codex CLI・Gemini CLI の3つの Agent を使い分けて開発しています。

ある日気づきました。**毎回同じことを説明している**。

「このプロジェクトは append-only なデータベースで、設計書は docs/design にあって、ビルドは〜」。新しいタスクを始めるたびに、この前置きを3つの Agent それぞれに繰り返す。数千行の設計書を読ませるだけで数分かかる。3 Agent なら3回分。

しかも Agent ごとにコンテキストの渡し方が違います。`CLAUDE.md` は Claude 専用、`.cursorrules` は Cursor 専用。同じ知識を別々の形式で管理するのは面倒です。

この2つの問題を解決するために、自分が使い始めたのが**ベースセッション**というパターンです。

## ベースセッションとは

Agent にプロジェクトのコンテキスト（設計書、コード構造、規約など）を**事前に読み込ませたセッション**です。

```
┌─────────────────────────────────────┐
│  Phase 1: ベースセッション構築        │
│                                     │
│  「この設計書を読んで理解して」        │
│  → Agent がコンテキストを読み込む     │
│  → session_id を記録                │
└──────────────┬──────────────────────┘
               │ session_id
               ▼
┌─────────────────────────────────────┐
│  Phase 2〜N: 作業指示（何度でも）     │
│                                     │
│  session_id でセッションを再開        │
│  「delete 機能を実装して」            │
│  「テストを書いて」                   │
│  「リファクタリングして」              │
│  → Agent はプロジェクトを理解済み     │
└─────────────────────────────────────┘
```

構築は1回だけ。以降は `session_id` で再開するだけで、Agent はプロジェクトを理解した状態で作業を始められます。

## 利点1: セッションを使い回せる

ベースセッションの最も直接的な利点は**再利用性**です。

自分のプロジェクト（設計書 約4,000行 / 約50,000トークン）での実測を示します。

### Before: ベースセッションなし

```
タスクA開始 → 設計書読み込み（約2分, 50,000 input tokens）→ 作業
タスクB開始 → 設計書読み込み（約2分, 50,000 input tokens）→ 作業
タスクC開始 → 設計書読み込み（約2分, 50,000 input tokens）→ 作業
────────────────────────────────────────
合計: 読み込み 約6分, 150,000 input tokens
```

### After: ベースセッションあり

```
ベースセッション構築（約2分, 50,000 input tokens）→ session_id 記録

タスクA開始 → session_id で再開（数秒, Prompt Cache適用）→ 作業
タスクB開始 → session_id で再開（数秒, Prompt Cache適用）→ 作業
タスクC開始 → session_id で再開（数秒, Prompt Cache適用）→ 作業
────────────────────────────────────────
合計: 読み込み 約2分, 50,000 input tokens + キャッシュ読み出し分
```

セッション再開時は前のコンテキストが **Prompt Cache** に乗るため、入力トークンのコストが最大90%削減されます（Anthropic API の場合、キャッシュ読み出しは通常入力の1/10の料金）。タスクが増えるほど差が開きます。

```
base_session ─┬─ 実装タスク A
              ├─ 実装タスク B
              └─ レビュータスク C
```

## 利点2: 全 Agent で同じプロンプトを使える

`CLAUDE.md` は Claude 専用、`.cursorrules` は Cursor 専用。3つの Agent を使い分けるなら、3つの形式でコンテキストを管理する必要があります。

ベースセッションなら、**1つのファイルを全 Agent 共通で使えます**。

```
ctx_full.md  ──→  Claude:  「ctx_full.md を読んで」→ session_id
             ──→  Codex:   「ctx_full.md を読んで」→ session_id
             ──→  Gemini:  「ctx_full.md を読んで」→ session_id
```

同じファイル、同じ指示。Agent ごとの設定ファイル形式を気にする必要がありません。

### 「振る舞い」と「知識」の分離

ここで重要なのは、CLAUDE.md 等の Agent 固有設定とベースセッションは**対立するものではなく、役割が異なる**ということです。

| | Agent 固有設定（CLAUDE.md 等） | ベースセッション |
|---|---|---|
| **役割** | 振る舞い（ルール・スタイル） | 知識（設計・構造・コンテキスト） |
| **対象 Agent** | 特定 Agent 専用 | 全 Agent 共通 |
| **更新頻度** | プロジェクト設定変更時 | タスク開始前 / 設計変更時 |
| **保持場所** | ファイル（リポジトリ内） | セッション（session_id） |
| **例** | 「コミットは conventional commits で」 | 「このDBは append-only 設計で…」 |

**振る舞いはルールファイル、知識はベースセッション。** この分離により、Agent を切り替えても同じ知識ベースで作業できます。

## 利点3: Agent in Agent の時代に効く

Agent から別の Agent を並列起動する「Agent in Agent」パターンが現実的になってきました。

オーケストレーター Agent が複数の子 Agent を起動して実装・レビュー・テストを並列実行する — こういった構成では、各子 Agent にプロジェクトのコンテキストを渡す必要があります。

```
Orchestrator
  ├─ Agent A (実装)   ← コンテキストが必要
  ├─ Agent B (レビュー) ← 同じコンテキストが必要
  └─ Agent C (テスト)  ← 同じコンテキストが必要
```

ベースセッションがなければ、子 Agent を起動するたびに数千行の設計書を読み込ませることになります。3 Agent 並列なら3回分の読み込みコスト。

ベースセッションを **Agent ごとに事前構築** しておけば、各子 Agent は session_id で即座に作業開始できます。初回の構築コストはかかりますが、同じ Agent でタスクを繰り返すたびに元が取れます。

## 構築方法

### Step 1: コンテキストを準備する

Agent に読ませたい情報を**汎用的なファイル**（Markdown など）にまとめます。Agent 固有の形式ではなく、どの Agent でも読める形にするのがポイントです。

```bash
# 例: 設計書をまとめる
cat docs/design/*.md > ctx_full.md

# 例: ツールでコンテキストを生成
uv run konkon search "" -p view=dev-full > ctx_full.md
```

### Step 2: Agent にコンテキストを読み込ませてセッションを記録する

各 Agent の CLI でセッションを作成し、コンテキストを読ませます。

**Claude Code の場合:**

```bash
claude --output-format stream-json \
  -p "ctx_full.md を読んで内容を理解してください"
# → JSON 出力から session_id を取得（例: jq '.session_id' で抽出）
```

**Codex CLI の場合:**

```bash
codex exec --full-auto --json \
  "ctx_full.md を読んで内容を理解してください"
# → JSON 出力から session_id を取得（例: jq '.session_id' で抽出）
```

**Gemini CLI の場合:**

```bash
gemini --output-format json \
  "ctx_full.md を読んで内容を理解してください"
# → JSON 出力から session_id を取得（例: jq '.session_id' で抽出）
```

> **注意**: 上記コマンドは各 CLI のバージョンによってオプション名が異なる場合があります。`--help` で確認してください。また、Agent in Agent パターンでプログラムから操作する場合は、後述のツール（ai-cli-mcp）のような統一インターフェースが便利です。

### Step 3: セッションを再開して作業させる

記録した session_id を使ってセッションを再開し、作業を指示します。Agent はプロジェクトを理解した状態で即座に作業を始められます。

ベースセッション上で直接作業するとコンテキストが汚れるため、`--fork-session`（Claude）のようなオプションでセッションを**分岐**させ、ベースセッションを常にクリーンに保つのがポイントです。

インタラクティブモードで再開する場合:

```bash
# Claude: -r で再開、--fork-session でベースセッションを汚さず分岐
claude -r <session_id> --fork-session

# Codex: resume で再開
codex resume <session_id>

# Gemini: -r で再開
gemini -r <session_id>
```

```
あなた: delete 機能を実装してください。
Agent:  設計書によると、物理削除 + Tombstone のハイブリッド方式ですね。
        raw_deletions テーブルに...（プロジェクトを理解した上で作業開始）
```

ノンインタラクティブ（スクリプトや自動化）で実行する場合:

```bash
# Claude: -r で再開、--fork-session でベースセッションを汚さず分岐
claude -r <session_id> --fork-session \
  --output-format stream-json \
  -p "delete 機能を実装してください"

# Codex: exec resume で再開
codex exec resume <session_id> \
  --full-auto --json \
  "delete 機能を実装してください"

# Gemini: -r で再開
gemini -r <session_id> --output-format json \
  "delete 機能を実装してください"
```

## ハマりどころと Agent ごとの特性

ベースセッションは便利ですが、いくつか注意点があります。（2026年3月時点の検証結果）

| Agent | Session 寿命 | 主なハマりどころ | 対処法 |
|---|---|---|---|
| Claude | 短め | Context window が埋まりやすい。長い作業で session が使えなくなる | 作業が長くなったら新しい session を作り直す。ベースセッション自体は短く保つ |
| Codex | 長め | 比較的安定だが、長期放置で session が失効することがある | 失効したら再構築。session_id に日付を入れて管理すると楽 |
| Gemini | 長め | キャッシュで**古いファイル内容**を返すことがある | コンテキスト再読み込みを明示的に指示する（「ctx_full.md を再度読み直して」） |

### よくある失敗パターン

- **コンテキストが古くなる**: 設計書を更新したのにベースセッションが古いまま → 設計変更時はベースセッションも再構築する
- **セッションに作業を積みすぎる**: ベースセッション上で作業を続けると、次の再開時にゴミが混ざる → タスクごとにベースセッションから新しく分岐させる
- **全部を読ませようとする**: コンテキストが大きすぎると Agent の性能が落ちる → 必要な情報だけに絞った ctx ファイルを作る

## ツール紹介

このワークフローをプログラムから実行するために [ai-cli-mcp](https://github.com/mkXultra/ai-cli-mcp) を作りました。Claude / Codex / Gemini を統一インターフェースで操作できる MCP サーバーです。

- `run(model, prompt, session_id)` でどの Agent も同じ形式で起動・再開
- `wait(pids)` で複数 Agent の結果をまとめて取得
- Agent in Agent パターンのオーケストレーションに対応

```bash
claude mcp add ai-cli '{"name":"ai-cli","command":"npx","args":["-y","ai-cli-mcp@latest"]}'
```

詳細は [GitHub リポジトリ](https://github.com/mkXultra/ai-cli-mcp) を参照してください。

## まとめ

- **ベースセッション** = Agent にコンテキストを1回読み込ませ、session_id で何度でも再開できるセッション
- **使い回せる**: 読み込みは1回、以降は再開するだけ。各社のキャッシュ機構でコスト削減も見込める
- **Agent 非依存**: 同じファイル・同じプロンプトで Claude / Codex / Gemini 全てに使える
- **振る舞いはルールファイル、知識はベースセッション**。この分離がマルチ Agent 運用の鍵
- **Agent in Agent 時代に必須**: 子 Agent の並列起動時に、事前のベースセッション構築がボトルネック解消になる
