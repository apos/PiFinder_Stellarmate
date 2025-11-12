#!/bin/bash
# This script fetches the latest changes from the PiFinder release branch
# and resets the local repository to match it, discarding any local changes.

set -e
PIFINDER_DIR="/home/stellarmate/PiFinder"

if [ ! -d "$PIFINDER_DIR/.git" ]; then
    echo "Error: PiFinder repository not found at $PIFINDER_DIR"
    exit 1
fi

echo "Fetching latest updates for PiFinder..."
git -C "$PIFINDER_DIR" fetch origin release

echo "Resetting PiFinder to the latest release version..."
git -C "$PIFINDER_DIR" reset --hard origin/release

echo "PiFinder has been successfully updated and reset."
