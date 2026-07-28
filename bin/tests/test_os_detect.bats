#!/usr/bin/env bats
# Unit tests for bin/os_detect.sh's pure decision functions - no filesystem/
# command/network access, so these pass identically regardless of what's
# actually installed on the machine running the suite. See
# docs/concepts/setup_script_test_suite.md and
# docs/concepts/setup_indi_only_install_mode.md.
#
# os_detect_package_manager() and os_install_packages() (the impure
# fact-gathering/side-effecting halves) are deliberately NOT tested here -
# see the concept doc for why that stays live-tested instead.

setup() {
    source "${BATS_TEST_DIRNAME}/../os_detect.sh"
}

@test "os_pick_package_manager: pacman wins when present" {
    run os_pick_package_manager 1 0 0
    [ "$status" -eq 0 ]
    [ "$output" = "pacman" ]
}

@test "os_pick_package_manager: apt used when pacman absent" {
    run os_pick_package_manager 0 1 0
    [ "$status" -eq 0 ]
    [ "$output" = "apt" ]
}

@test "os_pick_package_manager: nix used when only nix present" {
    run os_pick_package_manager 0 0 1
    [ "$status" -eq 0 ]
    [ "$output" = "nix" ]
}

@test "os_pick_package_manager: pacman takes priority over apt and nix" {
    run os_pick_package_manager 1 1 1
    [ "$status" -eq 0 ]
    [ "$output" = "pacman" ]
}

@test "os_pick_package_manager: apt takes priority over nix" {
    run os_pick_package_manager 0 1 1
    [ "$status" -eq 0 ]
    [ "$output" = "apt" ]
}

@test "os_pick_package_manager: fails when none present" {
    run os_pick_package_manager 0 0 0
    [ "$status" -ne 0 ]
}

@test "os_package_name: cmake maps identically on pacman/apt/nix" {
    [ "$(os_package_name cmake pacman)" = "cmake" ]
    [ "$(os_package_name cmake apt)" = "cmake" ]
    [ "$(os_package_name cmake nix)" = "cmake" ]
}

@test "os_package_name: build-tools differs per manager" {
    [ "$(os_package_name build-tools pacman)" = "base-devel" ]
    [ "$(os_package_name build-tools apt)" = "build-essential" ]
}

@test "os_package_name: libindi-dev differs per manager" {
    [ "$(os_package_name libindi-dev pacman)" = "libindi" ]
    [ "$(os_package_name libindi-dev apt)" = "libindi-dev" ]
}

@test "os_package_name: unknown generic name returns empty, not a guess" {
    [ -z "$(os_package_name totally-unknown-package pacman)" ]
}

@test "os_package_name: known generic name on an unknown manager returns empty" {
    [ -z "$(os_package_name cmake dnf)" ]
}
