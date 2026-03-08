#!/usr/bin/env bash
# Context Retention Experiment — Setup / Reset
#
# 実験ディレクトリを (再)構築する。
# プロジェクトルートから実行すること。
#
# Usage:
#   ./experiments/ctx_retention/setup.sh
#
# 実行後の構造:
#   work/<pattern>/<model>/
#     ├── .konkon/           ← DB コピー
#     └── examples/konkondb/ ← カナリア注入版プラグイン
#
#   Pattern B: + ctx_full.md
#   Pattern C: + ctx_full.md + ctx_parts/part_{01..05}.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WORK_DIR="$SCRIPT_DIR/work"

cd "$PROJECT_ROOT"

# --- Clean ---
echo "Cleaning $WORK_DIR ..."
rm -rf "$WORK_DIR"

# --- Create directories + copy ---
echo "Creating experiment directories ..."
for pattern in a b c; do
  for model in claude codex gemini; do
    dest="$WORK_DIR/$pattern/$model"
    mkdir -p "$dest/examples"
    cp -r examples/konkondb "$dest/examples/konkondb"
    cp -r .konkon "$dest/.konkon"
    echo "  $pattern/$model done"
  done
done

# --- Pattern B: generate ctx_full.md ---
echo ""
echo "Pattern B: generating ctx_full.md ..."
for model in claude codex gemini; do
  dir="$WORK_DIR/b/$model"
  cd "$dir"
  uv run konkon search "" -p view=dev-full > ctx_full.md 2>/dev/null
  lines=$(wc -l < ctx_full.md | tr -d ' ')
  echo "  b/$model/ctx_full.md: $lines lines"
done

# --- Pattern C: generate ctx_full.md + split into 5 parts ---
echo ""
echo "Pattern C: generating ctx_full.md + splitting into 5 parts ..."
for model in claude codex gemini; do
  dir="$WORK_DIR/c/$model"
  cd "$dir"
  uv run konkon search "" -p view=dev-full > ctx_full.md 2>/dev/null
  mkdir -p ctx_parts

  python3 -c "
import pathlib
text = pathlib.Path('ctx_full.md').read_text()
lines = text.splitlines(keepends=True)
total = len(lines)
chunk = total // 5
for i in range(5):
    start = i * chunk
    end = (i + 1) * chunk if i < 4 else total
    part = ''.join(lines[start:end])
    pathlib.Path(f'ctx_parts/part_{i+1:02d}.md').write_text(part)
    print(f'  c/$model/part_{i+1:02d}.md: {part.count(chr(10))} lines')
"
done

# --- Verify ---
echo ""
echo "Verifying canary injection ..."
cd "$WORK_DIR/a/claude"
count=$(uv run konkon search "" -p view=dev-full 2>/dev/null | grep -c "@@CANARY_" || true)
echo "  Pattern A canaries: $count"

count=$(grep -c "@@CANARY_" "$WORK_DIR/b/claude/ctx_full.md" || true)
echo "  Pattern B canaries: $count"

count=$(grep -r "@@CANARY_" "$WORK_DIR/c/claude/ctx_parts/" | wc -l | tr -d ' ')
echo "  Pattern C canaries (across parts): $count"

echo ""
echo "Setup complete."
