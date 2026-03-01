#!/usr/bin/env bash
# Ingest project files into konkon Raw DB.
#
# - New files       → konkon insert
# - Changed files   → konkon update (same file_path, different hash)
# - Unchanged files → skip
#
# Usage:
#   ./scripts/ingest.sh [ROOT_DIR]
#
# Dependencies: jq, shasum

set -euo pipefail

ROOT_DIR="${1:-.}"
ROOT_DIR="$(cd "$ROOT_DIR" && pwd)"

EXCLUDE_DIRS=".git|.konkon|__pycache__|.venv|.mypy_cache|.pytest_cache|.ruff_cache|.tox|build|dist|node_modules|.bk_docs|.egg-info|docs/design/claude|docs/design/codex|docs/design/gemini"
INCLUDE_EXT='\.py$|\.md$|\.toml$|\.cfg$|\.txt$|\.yml$|\.yaml$|\.json$|\.rst$|\.ini$|\.sh$'

# --- Step 1: Build lookup of existing records as temp JSON ---
echo "Loading existing records ..."
RECORDS_FILE=$(mktemp)
trap 'rm -f "$RECORDS_FILE"' EXIT

uv run konkon raw list --format json --limit 100000 2>/dev/null > "$RECORDS_FILE" || true

record_count=$(wc -l < "$RECORDS_FILE" | tr -d ' ')
echo "Found $record_count existing records"

lookup_record() {
  local fp="$1"
  jq -r --arg fp "$fp" 'select(.meta.file_path == $fp) | "\(.id)\t\(.meta.file_hash // "")"' "$RECORDS_FILE"
}

# --- Step 2: Scan and process files ---
echo "Scanning $ROOT_DIR ..."

inserted=0
updated=0
skipped=0
errors=0

while IFS= read -r filepath; do
  [ ! -s "$filepath" ] && continue
  rel_path="${filepath#"$ROOT_DIR"/}"

  file_hash=$(shasum -a 256 "$filepath" | cut -d' ' -f1)

  match=$(lookup_record "$rel_path")

  if [ -n "$match" ]; then
    record_id=$(echo "$match" | cut -f1)
    old_hash=$(echo "$match" | cut -f2)

    if [ "$old_hash" = "$file_hash" ]; then
      skipped=$((skipped + 1))
      continue
    fi

    echo "  UPDATE $rel_path"
    if uv run konkon update "$record_id" \
        --content "$(cat "$filepath")" \
        -m "file_path=$rel_path" \
        -m "file_hash=$file_hash" \
        > /dev/null 2>&1; then
      updated=$((updated + 1))
    else
      echo "  ERROR update $rel_path" >&2
      errors=$((errors + 1))
    fi
  else
    echo "  INSERT $rel_path"
    if uv run konkon insert \
        -m "file_path=$rel_path" \
        -m "file_hash=$file_hash" \
        < "$filepath" \
        > /dev/null 2>&1; then
      inserted=$((inserted + 1))
    else
      echo "  ERROR insert $rel_path" >&2
      errors=$((errors + 1))
    fi
  fi
done < <(
  find "$ROOT_DIR" -type f \
    | grep -vE "/(${EXCLUDE_DIRS})/" \
    | grep -E "$INCLUDE_EXT" \
    | sort
)

echo ""
echo "Done: $inserted inserted, $updated updated, $skipped skipped, $errors errors"
