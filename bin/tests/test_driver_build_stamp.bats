#!/usr/bin/env bats
# record_driver_build_stamp() from bin/functions.sh: remembers the libindi version the drivers were built against.

setup() {
    TMP="$(mktemp -d)"
    export pifinder_home="$TMP/home"
    mkdir -p "$pifinder_home" "$TMP/bin"
    source <(sed -n '/^record_driver_build_stamp() {/,/^}/p' "${BATS_TEST_DIRNAME}/../functions.sh")
}

teardown() {
    rm -rf "$TMP"
}

@test "writes the libindi version without the package release" {
    printf '#!/bin/bash\necho "libindi 2.2.5-1"\n' > "$TMP/bin/pacman"; chmod +x "$TMP/bin/pacman"
    PATH="$TMP/bin:$PATH" run record_driver_build_stamp
    [ "$status" -eq 0 ]
    [[ "$(cat "$pifinder_home/.pfsm/driver_build.json")" == *'"libindi": "2.2.5"'* ]]
}

@test "no way to find the version: no file, no error" {
    PATH="$TMP/bin:/nonexistent" run record_driver_build_stamp
    [ "$status" -eq 0 ]
    [ ! -e "$pifinder_home/.pfsm/driver_build.json" ]
}
