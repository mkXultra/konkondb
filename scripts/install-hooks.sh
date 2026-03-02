#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK_DIR="$REPO_ROOT/.git/hooks"

mkdir -p "$HOOK_DIR"
ln -sf "$REPO_ROOT/scripts/pre-commit" "$HOOK_DIR/pre-commit"

echo "[OK] pre-commit hook installed."
