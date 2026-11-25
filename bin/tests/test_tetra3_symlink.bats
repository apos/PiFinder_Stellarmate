#!/usr/bin/env bats
# ensure_tetra3_symlink() from bin/functions.sh (PiFinder 2.6.4 stopped tracking
# python/tetra3). Only that one function is pulled out of functions.sh, so the
# test needs neither the rest of that file's side effects nor a real PiFinder.

setup() {
    TMP="$(mktemp -d)"
    export pifinder_home="$TMP"
    export pifinder_dir="$TMP/PiFinder"
    mkdir -p "$pifinder_dir/python"
    source <(sed -n '/^ensure_tetra3_symlink() {/,/^}/p' "${BATS_TEST_DIRNAME}/../functions.sh")
}

teardown() {
    rm -rf "$TMP"
}

@test "ensure_tetra3_symlink: creates the link when it is missing" {
    run ensure_tetra3_symlink
    [ "$status" -eq 0 ]
    [ "$(readlink "$pifinder_dir/python/tetra3")" = "PiFinder/tetra3/tetra3" ]
}

@test "ensure_tetra3_symlink: leaves a correct link alone" {
    ln -s PiFinder/tetra3/tetra3 "$pifinder_dir/python/tetra3"
    run ensure_tetra3_symlink
    [ "$status" -eq 0 ]
    [ -z "$output" ]
    [ "$(readlink "$pifinder_dir/python/tetra3")" = "PiFinder/tetra3/tetra3" ]
}

@test "ensure_tetra3_symlink: moves a plain folder aside and links" {
    mkdir "$pifinder_dir/python/tetra3"
    touch "$pifinder_dir/python/tetra3/old_file"
    run ensure_tetra3_symlink
    [ "$status" -eq 0 ]
    [ "$(readlink "$pifinder_dir/python/tetra3")" = "PiFinder/tetra3/tetra3" ]
    ls "$TMP"/tetra3_old_*/old_file
}

@test "ensure_tetra3_symlink: replaces a link that points elsewhere" {
    ln -s /somewhere/else "$pifinder_dir/python/tetra3"
    run ensure_tetra3_symlink
    [ "$status" -eq 0 ]
    [ "$(readlink "$pifinder_dir/python/tetra3")" = "PiFinder/tetra3/tetra3" ]
}
