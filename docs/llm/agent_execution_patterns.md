# Multi-Agent 実行パターン

## 1. Session Chain（セッションチェーン）

複数フェーズの直列実行で、各フェーズの session_id を次フェーズに引き継ぐパターン。
agent がプロジェクトコンテキスト + 前フェーズの作業内容を保持したまま次の作業に取りかかれる。

```
base session: <session_id_0>
  → Phase 1 実行 (session_id_0) → session_id_1 取得
    → Phase 2 実行 (session_id_1) → session_id_2 取得
      → Phase 3 実行 (session_id_2) → session_id_3 取得
```

### メリット
- agent がプロジェクト全体 + 前作業の文脈を保持
- 指示が簡潔で済む（「前のフェーズで作った XX を使って…」）

### 注意
- Claude Ultra は context overflow しやすいため、長い chain では途中で session が切れる可能性がある

## 2. Session Fallback（セッションフォールバック）

Session Chain で error が発生した場合の復旧戦略。
直前の session_id → その前 → ... → base session まで遡ってリトライする。

```
Phase N 実行 → session error?
  → Phase N-1 の session_id でリトライ
    → error? → Phase N-2 の session_id でリトライ
      → ...
        → error? → base session でリトライ
          → error? → ユーザーに報告して停止
```

### ポイント
- 各フェーズ完了時に session_id を必ず記録しておく
- fallback 時はコンテキストが失われるため、指示に前フェーズの成果物パスなど追加情報を含める
- base session まで全て失敗 = agent 環境の問題 → ユーザー判断を仰ぐ

## 3. 並列 Base Session + 遅延 Wait

実装 agent とレビュー agent の base session を同時に起動し、
実装 agent の wait 時にレビュー用 agent の wait も同時に行うパターン。

```
Time →

実装 Agent:      [base session] → wait → [実装] ─────────→ wait ─→ done
レビュー Agent A: [base session] ─────────────────────────→ wait ─→ done (実装waitと同時)
レビュー Agent B: [base session] ─────────────────────────→ wait ─→ done (実装waitと同時)
```

### 手順
1. 全 agent の base session を **並列起動**（`mcp__acm__run` を同時呼び出し）
2. 実装 agent だけ **wait** → session_id 取得
3. 実装 agent に作業指示（session_id 継続）
4. 実装の **wait** 時にレビュー agent の PID も含めて `mcp__acm__wait`
5. 全完了後、即レビュー開始

### メリット
- base session 生成の待ち時間をゼロに
- 実装完了 → レビュー開始のラグを最小化

## 4. 修正→レビューループ

修正は 1 agent、レビューは 3 agent 並列で、承認されるまで繰り返す。

```
while not all_approved:
    修正 agent (1体) で指摘事項を修正
    3 agent 並列でレビュー
    指摘があれば修正 agent に再依頼
```

### ポイント
- レビューで scope 外の指摘が出た場合はユーザー判断を仰ぐ（例: 既存の不整合）
- Gemini はキャッシュ問題があるため「read_file で実際に読み直してからレビュー」を指示に含める
