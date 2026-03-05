#!/usr/bin/env bash
# Ingest project files into konkon Raw DB.
#
# - New files       → konkon insert
# - Changed files   → konkon update (same file_path, different hash)
# - Deleted files   → konkon delete (record exists but file is gone)
# - Unchanged files → skip
#
# Usage:
#   ./scripts/ingest.sh [--dry-run] [ROOT_DIR]
#
# Options:
#   --dry-run  Show what would be done without executing
#
# Dependencies: jq, shasum

set -euo pipefail

DRY_RUN=false
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=true
  shift
fi

ROOT_DIR="${1:-.}"
ROOT_DIR="$(cd "$ROOT_DIR" && pwd)"

if $DRY_RUN; then
  echo "[DRY RUN] No changes will be made."
fi

EXCLUDE_DIRS=".git|.konkon|__pycache__|.venv|.mypy_cache|.pytest_cache|.ruff_cache|.tox|build|dist|node_modules|.bk_docs|.egg-info|docs/design/claude|docs/design/codex|docs/design/gemini"
INCLUDE_EXT='\.py$|\.md$|\.toml$|\.cfg$|\.txt$|\.yml$|\.yaml$|\.json$|\.rst$|\.ini$|\.sh$'

# Files to insert once but never update (fixed entries in file_map)
INSERT_ONLY_FILES="examples/konkondb/context.json|examples/konkondb/llm_cache.json"

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
deleted=0
skipped=0
errors=0

while IFS= read -r filepath; do
  [ ! -s "$filepath" ] && continue
  rel_path="${filepath#"$ROOT_DIR"/}"

  file_hash=$(shasum -a 256 "$filepath" | cut -d' ' -f1)

  match=$(lookup_record "$rel_path")

  if [ -n "$match" ]; then
    # insert-only files: skip if already exists
    if echo "$rel_path" | grep -qE "^(${INSERT_ONLY_FILES})$"; then
      skipped=$((skipped + 1))
      continue
    fi

    record_id=$(echo "$match" | cut -f1)
    old_hash=$(echo "$match" | cut -f2)

    if [ "$old_hash" = "$file_hash" ]; then
      skipped=$((skipped + 1))
      continue
    fi

    echo "  UPDATE $rel_path"
    if $DRY_RUN; then
      updated=$((updated + 1))
    elif uv run konkon update "$record_id" \
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
    if $DRY_RUN; then
      inserted=$((inserted + 1))
    elif uv run konkon insert \
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

# --- Step 3: Detect deleted files ---
echo "Checking for deleted files ..."

while IFS=$'\t' read -r record_id file_path; do
  [ -z "$file_path" ] && continue
  if [ ! -f "$ROOT_DIR/$file_path" ]; then
    echo "  DELETE $file_path"
    if $DRY_RUN; then
      deleted=$((deleted + 1))
    elif uv run konkon delete "$record_id" --force > /dev/null 2>&1; then
      deleted=$((deleted + 1))
    else
      echo "  ERROR delete $file_path" >&2
      errors=$((errors + 1))
    fi
  fi
done < <(jq -r '"\(.id)\t\(.meta.file_path // "")"' "$RECORDS_FILE")

echo ""
if $DRY_RUN; then
  echo "[DRY RUN] Would: $inserted insert, $updated update, $deleted delete, $skipped skip"
else
  echo "Done: $inserted inserted, $updated updated, $deleted deleted, $skipped skipped, $errors errors"
fi
