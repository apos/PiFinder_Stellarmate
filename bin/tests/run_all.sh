#!/usr/bin/env bash
set -euo pipefail
# Runs this project's bats-core unit-test suite for its own shell scripts -
# pure logic only (version comparison, argument parsing, OS detection), no
# real filesystem/network/package-manager side effects. See
# docs/concepts/setup_script_test_suite.md for what's deliberately NOT
# covered here (that stays live-tested, same as the rest of this project).
#
# bats-core is vendored as a git submodule (bin/tests/vendor/bats-core) -
# not a global/system install someone has to remember to set up on every
# machine that clones this repo, same reasoning as PiFinder's own tetra3
# submodule. Needs initializing once per fresh clone/worktree:
#   git submodule update --init bin/tests/vendor/bats-core

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BATS_BIN="${SCRIPT_DIR}/vendor/bats-core/bin/bats"

if [ ! -x "${BATS_BIN}" ]; then
    echo "❌ Vendored bats-core not found at ${BATS_BIN}." >&2
    echo "   Run this once per fresh clone/worktree:" >&2
    echo "   git submodule update --init bin/tests/vendor/bats-core" >&2
    exit 1
fi

"${BATS_BIN}" "${SCRIPT_DIR}"/*.bats
