#!/usr/bin/env bash
# Ingest staged files into konkon Raw DB.
#
# - Added files    → konkon insert
# - Modified files → konkon update
# - Deleted files  → konkon delete
#
# Designed for use as a pre-commit hook.
#
# Usage:
#   ./scripts/ingest-staged.sh [--dry-run]
#
# Dependencies: jq

set -euo pipefail

DRY_RUN=false
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=true
fi

INCLUDE_EXT='\.py$|\.md$|\.toml$|\.cfg$|\.txt$|\.yml$|\.yaml$|\.json$|\.rst$|\.ini$|\.sh$'

# Files to insert once but never update (fixed entries in file_map)
INSERT_ONLY_FILES="examples/konkondb/context.json|examples/konkondb/llm_cache.json"

if $DRY_RUN; then
  echo "[DRY RUN] No changes will be made."
fi

# --- Build lookup of existing records ---
RECORDS_FILE=$(mktemp)
trap 'rm -f "$RECORDS_FILE"' EXIT

uv run konkon raw list --format json --limit 100000 2>/dev/null > "$RECORDS_FILE" || true

lookup_record() {
  local fp="$1"
  jq -r --arg fp "$fp" 'select(.meta.file_path == $fp) | "\(.id)\t\(.meta.file_hash // "")"' "$RECORDS_FILE"
}

# --- Process staged changes ---
inserted=0
updated=0
deleted=0
skipped=0
errors=0

while IFS=$'\t' read -r status file; do
  # Filter by extension
  echo "$file" | grep -qE "$INCLUDE_EXT" || continue

  case "$status" in
    A)
      echo "  INSERT $file"
      file_hash=$(git show ":$file" | shasum -a 256 | cut -d' ' -f1)
      if $DRY_RUN; then
        inserted=$((inserted + 1))
      elif git show ":$file" | uv run konkon insert \
          -m "file_path=$file" \
          -m "file_hash=$file_hash" \
          > /dev/null 2>&1; then
        inserted=$((inserted + 1))
      else
        echo "  ERROR insert $file" >&2
        errors=$((errors + 1))
      fi
      ;;
    M)
      # insert-only files: skip
      if echo "$file" | grep -qE "^(${INSERT_ONLY_FILES})$"; then
        skipped=$((skipped + 1))
        continue
      fi

      match=$(lookup_record "$file")
      if [ -z "$match" ]; then
        echo "  WARN $file: no record found, inserting instead" >&2
        file_hash=$(git show ":$file" | shasum -a 256 | cut -d' ' -f1)
        if $DRY_RUN; then
          inserted=$((inserted + 1))
        elif git show ":$file" | uv run konkon insert \
            -m "file_path=$file" \
            -m "file_hash=$file_hash" \
            > /dev/null 2>&1; then
          inserted=$((inserted + 1))
        else
          echo "  ERROR insert $file" >&2
          errors=$((errors + 1))
        fi
        continue
      fi

      record_id=$(echo "$match" | cut -f1)
      file_hash=$(git show ":$file" | shasum -a 256 | cut -d' ' -f1)

      echo "  UPDATE $file"
      if $DRY_RUN; then
        updated=$((updated + 1))
      elif uv run konkon update "$record_id" \
          --content "$(git show ":$file")" \
          -m "file_path=$file" \
          -m "file_hash=$file_hash" \
          > /dev/null 2>&1; then
        updated=$((updated + 1))
      else
        echo "  ERROR update $file" >&2
        errors=$((errors + 1))
      fi
      ;;
    D)
      match=$(lookup_record "$file")
      if [ -z "$match" ]; then
        skipped=$((skipped + 1))
        continue
      fi

      record_id=$(echo "$match" | cut -f1)
      echo "  DELETE $file"
      if $DRY_RUN; then
        deleted=$((deleted + 1))
      elif uv run konkon delete "$record_id" --force > /dev/null 2>&1; then
        deleted=$((deleted + 1))
      else
        echo "  ERROR delete $file" >&2
        errors=$((errors + 1))
      fi
      ;;
  esac
done < <(git diff --cached --name-status | sed 's/\t/\t/')

echo ""
if $DRY_RUN; then
  echo "[DRY RUN] Would: $inserted insert, $updated update, $deleted delete, $skipped skip"
else
  echo "Done: $inserted inserted, $updated updated, $deleted deleted, $skipped skipped, $errors errors"
fi
