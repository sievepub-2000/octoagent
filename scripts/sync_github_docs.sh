#!/usr/bin/env bash
set -euo pipefail

# Configuration
SOURCE_DIR="octopusagent"
DEST_DIR="project_docs"

# Ensure destination exists
mkdir -p "$DEST_DIR"

# Find and copy *.md and *.txt files, preserving relative paths under DEST_DIR
echo "Synchronizing markdown and text files from $SOURCE_DIR..."
cd "$SOURCE_DIR"
find . -type f \( -name "*.md" -o -name "*.txt" \) -print0 | while IFS= read -r -d '' file; do
  rel_path="${file#./}"
  target_path="$PWD/../$DEST_DIR/$rel_path"
  mkdir -p "$(dirname "$target_path")"
  cp -u "$file" "$target_path"
done

echo "Sync completed."
