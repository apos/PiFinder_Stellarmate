#!/usr/bin/env bash
set -euo pipefail
# Runs this project's bats-core unit-test suite for its own shell scripts -
# pure logic only (version comparison, argument parsing, OS detection), no
# real filesystem/network/package-manager side effects. See
# docs/concepts/setup_script_test_suite.md for what's deliberately NOT
# covered here (that stays live-tested, same as the rest of this project).
#
# Requires bats-core (https://github.com/bats-core/bats-core) on PATH.
# Not vendored/installed by this project's own setup script - a contributor/
# CI dependency, not an end-user one.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if ! command -v bats >/dev/null 2>&1; then
    echo "❌ 'bats' not found on PATH - install bats-core first:" >&2
    echo "   https://github.com/bats-core/bats-core#installation" >&2
    exit 1
fi

bats "${SCRIPT_DIR}"/*.bats
