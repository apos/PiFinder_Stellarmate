#!/usr/bin/env bats
# Unit tests for bin/version_compare.sh - pure logic, no filesystem/network/
# root access needed. See docs/concepts/setup_script_test_suite.md.

setup() {
    source "${BATS_TEST_DIRNAME}/../version_compare.sh"
}

@test "version_eq: identical versions are equal" {
    run version_eq "1.1.0" "1.1.0"
    [ "$status" -eq 0 ]
}

@test "version_eq: different versions are not equal" {
    run version_eq "1.1.0" "1.2.0"
    [ "$status" -ne 0 ]
}

@test "version_gt: newer major version is greater" {
    run version_gt "2.0.0" "1.9.9"
    [ "$status" -eq 0 ]
}

@test "version_gt: newer minor version is greater" {
    run version_gt "1.2.0" "1.1.9"
    [ "$status" -eq 0 ]
}

@test "version_gt: newer patch version is greater" {
    run version_gt "1.1.1" "1.1.0"
    [ "$status" -eq 0 ]
}

@test "version_gt: older version is not greater" {
    run version_gt "1.1.0" "1.2.0"
    [ "$status" -ne 0 ]
}

@test "version_gt: equal versions are not greater" {
    run version_gt "1.1.0" "1.1.0"
    [ "$status" -ne 0 ]
}

@test "version_gt: two-digit version segments sort numerically, not lexically" {
    # A naive string/lexical sort would put "1.9.0" after "1.10.0" (since "9" >
    # "1" as the first character) - sort -V (the mechanism version_gt relies
    # on) must get this right, or the driver's own STABLE/TESTING version
    # gates in pifinder_stellarmate_setup.sh would misfire on any project
    # that reaches double-digit minor/patch numbers.
    run version_gt "1.10.0" "1.9.0"
    [ "$status" -eq 0 ]
}

@test "version_gt: regression case - the exact args from a real setup.sh call" {
    # Guards the actual call site in pifinder_stellarmate_setup.sh:
    # version_gt "$github_version" "$pifinder_stellarmate_version_stable"
    run version_gt "2.6.0" "2.6.0"
    [ "$status" -ne 0 ]
    run version_gt "2.7.0" "2.6.0"
    [ "$status" -eq 0 ]
}
