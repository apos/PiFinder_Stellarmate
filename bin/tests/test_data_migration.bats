#!/usr/bin/env bats
# run_pifinder_data_migrations() from bin/functions.sh: PiFinder's v2.6.0 config.json migration, run by PFSM because
# upstream's own post-update script is not used. A fake migration script and a systemctl stand-in replace the real ones.

setup() {
    TMP="$(mktemp -d)"
    export pifinder_home="$TMP"
    export pifinder_dir="$TMP/PiFinder"
    export pifinder_data_dir="$TMP/PiFinder_data"
    mkdir -p "$pifinder_dir/python/PiFinder/migrations" "$pifinder_data_dir" "$TMP/bin"
    MIG="$pifinder_dir/python/PiFinder/migrations/v2_6_0_dob_flop.py"
    # stand-in: replaces OLD by NEW in the given file, like the real script changes only the old record
    cat > "$MIG" <<'PY'
import sys
p = sys.argv[1]
s = open(p).read()
n = s.count("OLD")
open(p, "w").write(s.replace("OLD", "NEW"))
print(f"corrected {n} record(s)")
PY
    cat > "$TMP/bin/systemctl" <<'SH'
#!/bin/bash
[ "${SHIM_ACTIVE:-0}" = "1" ]
SH
    chmod +x "$TMP/bin/systemctl"
    export PATH="$TMP/bin:$PATH"
    CFG="$pifinder_data_dir/config.json"
    source <(sed -n '/^run_pifinder_data_migrations() {/,/^}/p' "${BATS_TEST_DIRNAME}/../functions.sh")
}

teardown() {
    rm -rf "$TMP"
}

backups() { ls "$pifinder_data_dir" | grep -c "pfsm-before-migration" || true; }

@test "no migration script (PiFinder older than 2.6.0): nothing happens" {
    rm "$MIG"; echo '{"a":"OLD"}' > "$CFG"
    run run_pifinder_data_migrations
    [ "$status" -eq 0 ]
    [ "$(cat "$CFG")" = '{"a":"OLD"}' ]
    [ "$(backups)" = "0" ]
}

@test "no config.json yet: nothing happens" {
    run run_pifinder_data_migrations
    [ "$status" -eq 0 ]
    [ ! -e "$CFG" ]
}

@test "PiFinder is running: skipped, the file is not touched" {
    echo '{"a":"OLD"}' > "$CFG"
    SHIM_ACTIVE=1 run run_pifinder_data_migrations
    [ "$status" -eq 0 ]
    [[ "$output" == *"skipped"* ]]
    [ "$(cat "$CFG")" = '{"a":"OLD"}' ]
    [ "$(backups)" = "0" ]
}

@test "nothing to change: the backup is removed again" {
    echo '{"a":"fine"}' > "$CFG"
    run run_pifinder_data_migrations
    [ "$status" -eq 0 ]
    [[ "$output" == *"nothing to change"* ]]
    [ "$(cat "$CFG")" = '{"a":"fine"}' ]
    [ "$(backups)" = "0" ]
}

@test "data changed: the migrated file is in place and the old copy is kept" {
    echo '{"a":"OLD"}' > "$CFG"
    run run_pifinder_data_migrations
    [ "$status" -eq 0 ]
    [ "$(cat "$CFG")" = '{"a":"NEW"}' ]
    [ "$(backups)" = "1" ]
    [ "$(cat "$pifinder_data_dir"/config.json.pfsm-before-migration-*)" = '{"a":"OLD"}' ]
}

@test "the migration script fails: config.json is restored, the run goes on" {
    echo '{"a":"OLD"}' > "$CFG"
    echo 'import sys; open(sys.argv[1], "w").write("broken"); sys.exit(1)' > "$MIG"
    run run_pifinder_data_migrations
    [ "$status" -eq 0 ]
    [[ "$output" == *"restored"* ]]
    [ "$(cat "$CFG")" = '{"a":"OLD"}' ]
}

@test "two runs in the same second: the kept backup of the first run survives the second" {
    echo '{"a":"OLD"}' > "$CFG"
    run run_pifinder_data_migrations
    [ "$(backups)" = "1" ]
    run run_pifinder_data_migrations
    [[ "$output" == *"nothing to change"* ]]
    [ "$(backups)" = "1" ]
    [ "$(cat "$pifinder_data_dir"/config.json.pfsm-before-migration-*)" = '{"a":"OLD"}' ]
}
