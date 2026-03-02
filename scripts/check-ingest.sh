#!/usr/bin/env bash
# Check that all project files are ingested into konkon Raw DB.
#
# - Exits 0 if all files match (hash identical, no missing files)
# - Exits 1 if any file is missing or has a different hash
#
# Usage:
#   ./scripts/check-ingest.sh [ROOT_DIR]
#
# Dependencies: jq, shasum

set -euo pipefail

ROOT_DIR="${1:-.}"
ROOT_DIR="$(cd "$ROOT_DIR" && pwd)"

EXCLUDE_DIRS=".git|.konkon|__pycache__|.venv|.mypy_cache|.pytest_cache|.ruff_cache|.tox|build|dist|node_modules|.bk_docs|.egg-info|docs/design/claude|docs/design/codex|docs/design/gemini"
INCLUDE_EXT='\.py$|\.md$|\.toml$|\.cfg$|\.txt$|\.yml$|\.yaml$|\.json$|\.rst$|\.ini$|\.sh$'

# Files that only need to exist (hash changes are ignored)
INSERT_ONLY_FILES="examples/konkondb/context.json|examples/konkondb/llm_cache.json"

# --- Step 1: Build lookup of existing records ---
RECORDS_FILE=$(mktemp)
trap 'rm -f "$RECORDS_FILE"' EXIT

uv run konkon raw list --format json --limit 100000 2>/dev/null > "$RECORDS_FILE" || true

lookup_record() {
  local fp="$1"
  jq -r --arg fp "$fp" 'select(.meta.file_path == $fp) | "\(.id)\t\(.meta.file_hash // "")"' "$RECORDS_FILE"
}

# --- Step 2: Scan and check ---
missing=0
changed=0
ok=0

while IFS= read -r filepath; do
  [ ! -s "$filepath" ] && continue
  rel_path="${filepath#"$ROOT_DIR"/}"

  file_hash=$(shasum -a 256 "$filepath" | cut -d' ' -f1)

  match=$(lookup_record "$rel_path")

  if [ -z "$match" ]; then
    echo "  MISSING $rel_path" >&2
    missing=$((missing + 1))
  elif echo "$rel_path" | grep -qE "^(${INSERT_ONLY_FILES})$"; then
    # insert-only: exists is enough, skip hash check
    ok=$((ok + 1))
  else
    old_hash=$(echo "$match" | cut -f2)

    if [ "$old_hash" != "$file_hash" ]; then
      echo "  CHANGED $rel_path" >&2
      changed=$((changed + 1))
    else
      ok=$((ok + 1))
    fi
  fi
done < <(
  find "$ROOT_DIR" -type f \
    | grep -vE "/(${EXCLUDE_DIRS})/" \
    | grep -E "$INCLUDE_EXT" \
    | sort
)

echo "check-ingest: $ok ok, $missing missing, $changed changed"

if [ $((missing + changed)) -gt 0 ]; then
  echo "FAIL: Run scripts/ingest.sh to sync Raw DB." >&2
  exit 1
fi
