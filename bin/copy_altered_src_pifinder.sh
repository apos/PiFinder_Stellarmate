#!/bin/bash

# Set source and destination directories

############################################################
# Get some important vars and functinons
source /home/stellarmate/PiFinder_Stellarmate/bin/functions.sh

SRC_DIR="$pifinder_dir"
DEST_DIR="$pifinder_stellarmate_dir/src_pifinder"

# Ensure destination directory exists
mkdir -p "$DEST_DIR"

# Change into the source directory
cd "$SRC_DIR" || { echo "❌ Cannot access $SRC_DIR"; exit 1; }

# Get list of changed (modified and untracked) files
changed_files=$(git ls-files --modified --others --exclude-standard)

# Add explicitly required files even if not changed
extra_files=(
  "python/PiFinder/tetra3/tetra3/__init__.py"
  "python/PiFinder/tetra3/tetra3/main.py"  # renamed from tetra3.py
)

# Merge changed + extra files, avoid duplicates
all_files=$(printf "%s\n%s\n" "$changed_files" "${extra_files[@]}" | sort -u)

# Exit early if nothing to copy
if [[ -z "$all_files" ]]; then
    echo "✅ No files to copy from $SRC_DIR"
    exit 0
fi

echo "🔄 Copying files to $DEST_DIR ..."

# Copy each file and preserve directory structure
while IFS= read -r file; do
    src_path="$SRC_DIR/$file"
    dest_path="$DEST_DIR/$file"
    if [[ -f "$src_path" ]]; then
        mkdir -p "$(dirname "$dest_path")"
        cp "$src_path" "$dest_path" && echo "✔️  Copied: $file" || echo "❌ Failed: $file"
    else
        echo "⚠️  Skipped missing file: $file"
    fi
done <<< "$all_files"

echo "✅ All files copied to $DEST_DIR"
