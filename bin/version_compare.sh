# Pure version-comparison helpers used by pifinder_stellarmate_setup.sh's
# version checks. Extracted into their own sourceable file (no side effects,
# no dependency on any other script state) so they can be unit-tested in
# isolation - see bin/tests/test_version_compare.bats and
# docs/concepts/setup_script_test_suite.md for why.

# Returns 1 (bash false) if $1 > $2, sorting version strings the way `sort -V` does.
version_gt() {
    [ "$(printf '%s\n' "$@" | sort -V | head -n 1)" != "$1" ]
}

# Returns 0 (bash true) if $1 and $2 are exactly equal strings.
version_eq() {
    [ "$1" = "$2" ]
}
