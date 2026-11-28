#!/usr/bin/env bats
# PiFinder's own updater is not used on StellarMate: the two scripts copied into ~/PiFinder only point to the Control Center.

setup() {
  REPO_DIR="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
}

@test "pifinder_update.sh: refuses, points to the Control Center, changes nothing" {
  run bash "$REPO_DIR/pifinder_update.sh"
  [ "$status" -eq 1 ]
  [[ "$output" == *"Control Center"* ]]
  [[ "$output" == *"Nothing was changed"* ]]
}

@test "pifinder_update.sh: runs no git command" {
  ! grep -qE '^[^#]*\bgit\b' "$REPO_DIR/pifinder_update.sh"
}

@test "pifinder_post_update.sh: refuses when run" {
  run bash "$REPO_DIR/pifinder_post_update.sh"
  [ "$status" -eq 1 ]
  [[ "$output" == *"Control Center"* ]]
}

@test "pifinder_post_update.sh: sourced, it returns and does not end the calling shell" {
  run bash -c 'source "$1"; echo "caller alive"' _ "$REPO_DIR/pifinder_post_update.sh"
  [[ "$output" == *"caller alive"* ]]
}
