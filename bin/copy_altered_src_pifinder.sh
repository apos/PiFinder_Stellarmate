#!/bin/bash

# Set source and destination directories
SRC_DIR="/home/pifinder/PiFinder"
DEST_DIR="/home/pifinder/PiFinder_Stellarmate/altered_src_pifinder"

# Ensure destination directory exists
mkdir -p "$DEST_DIR"

# Change into the source directory
cd "$SRC_DIR" || { echo "❌ Cannot access $SRC_DIR"; exit 1; }

# Get list of changed (modified and untracked) files
changed_files=$(git ls-files --modified --others --exclude-standard)

# Exit early if nothing changed
if [[ -z "$changed_files" ]]; then
    echo "✅ No modified or untracked files found in $SRC_DIR"
    exit 0
fi

echo "🔄 Copying changed files from $SRC_DIR to $DEST_DIR ..."

# Copy each file and preserve directory structure
while IFS= read -r file; do
    dest_path="$DEST_DIR/$file"
    mkdir -p "$(dirname "$dest_path")"
    cp "$file" "$dest_path" && echo "✔️  Copied: $file" || echo "❌ Failed to copy: $file"
done <<< "$changed_files"

echo "✅ All files copied to $DEST_DIR"