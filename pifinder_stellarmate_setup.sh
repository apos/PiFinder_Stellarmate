#! /usr/bin/bash

# This script is an altered script of https://raw.githubusercontent.com/brickbots/PiFinder/release/pifinder_setup.sh 
# See: https://github.com/apos/PiFinder_Stellarmate/tree/main

# This script is known to work with
pifinder_stellarmate_version_stable="2.6.3"

# This script is actually tested against this version
pifinder_stellarmate_version_testing="2.6.1"

# StellarMate OS version this script was tested with (rolling release — changes matter!)
smos_version_stable="2.3.0"
smos_version_testing="2.2.1"


############################################################
# MAIN
############################################################

# --action=reinstall|update|cancel: drive the existing-install menu and the
# venv bootstrap non-interactively (used by gui_installer/server.py). Without
# it, behavior is unchanged — the script still prompts on a terminal.
# --branch=<name>: switch this repo (PiFinder_Stellarmate itself, not the
# PiFinder checkout) to a different branch (e.g. "dev") before anything else
# runs - see bin/switch_branch.sh. Optional; a no-op when omitted, same as
# --action.
# --mode=full|indi_only: full (default) is this script's existing, unchanged
# behavior. indi_only skips everything PiFinder-hardware/application-specific
# (clone/patch, venv, star catalog, GPIO/udev) and only installs the INDI
# build dependencies + drivers + Control Center - see
# docs/concepts/setup_indi_only_install_mode.md (R1-R3).
ACTION=""
BRANCH=""
MODE="full"
for arg in "$@"; do
    case "$arg" in
        --action=*)
            ACTION="${arg#--action=}"
            ;;
        --branch=*)
            BRANCH="${arg#--branch=}"
            ;;
        --mode=*)
            MODE="${arg#--mode=}"
            ;;
    esac
done

case "$MODE" in
    full|indi_only) ;;
    *)
        echo "❌ Unknown --mode='$MODE' (expected full|indi_only)." >&2
        exit 1
        ;;
esac

# Captured once, up front: the script itself does `cd "${pifinder_home}"` etc.
# further down, which permanently changes this process's cwd. The automated
# re-execs below rely on `$(pwd)` (via `source $(pwd)/bin/functions.sh`) being
# the repo root again, so they must `cd` back here first.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Absolute path to this script itself, for the venv re-exec calls below -
# using bare $0 there breaks when invoked as "bash pifinder_stellarmate_setup.sh"
# (no "/" in the name, so bash's `exec` does a $PATH lookup and fails to
# find it) instead of "./pifinder_stellarmate_setup.sh" or an absolute path.
SCRIPT_PATH="${SCRIPT_DIR}/$(basename "$0")"

# Branch switch (if requested) runs before self-update, which only ever
# fast-forwards whichever branch is already checked out - it has no notion
# of switching to a different one. See bin/switch_branch.sh for the safety
# model (mirrors self_update.sh: skip cleanly when there's nothing to do,
# abort loudly rather than risk a dirty tree).
source "${SCRIPT_DIR}/bin/switch_branch.sh"
switch_pifinder_stellarmate_branch "$SCRIPT_DIR" "$BRANCH"

# Pull the latest PiFinder_Stellarmate before anything else runs - see
# bin/self_update.sh for the safety model (skips cleanly during active
# development, aborts loudly on a real failure instead of continuing on an
# uncertain checkout).
source "${SCRIPT_DIR}/bin/self_update.sh"
self_update_pifinder_stellarmate "$SCRIPT_DIR" "$@"

SETUP_START=$SECONDS

############################################################
# Get some important vars and functinons
source $(pwd)/bin/functions.sh
source "${SCRIPT_DIR}/bin/os_detect.sh"
source "${SCRIPT_DIR}/bin/build_and_install_indi_drivers.sh"

# Define a lock file for resuming the script after venv activation
lock_file="${pifinder_stellarmate_dir}/.resume_from_venv"

# warnings_file and add_warning() come from functions.sh now (shared with
# patch_PiFinder_installation_files.sh, which runs as its own bash process).
# Clear warnings on first run only (no lock file = first run) - a resumed
# run (after manual venv activation) should keep whatever the first pass
# already found.
[ ! -f "$lock_file" ] && > "$warnings_file"

# Machine-readable phase marker for gui_installer/server.py's progress bar.
# Because the venv bootstrap re-execs this whole script from the top (see
# below), phases 1-4 print again on the second pass — the GUI tracks the
# furthest phase reached so far rather than the latest one, so that's harmless.
phase() {
    echo "###PHASE### $1"
}

# --mode=indi_only: a self-contained, additive path that never touches any
# of the PiFinder-hardware/application-specific code below (clone/patch,
# venv, star catalog, GPIO/udev, PiFinder's own systemd services) - see
# docs/concepts/setup_indi_only_install_mode.md's Overview for why none of
# that applies when there's no PiFinder hardware attached at all. Exits
# before any "full" mode code runs, so this can never change "full" mode's
# behavior.
if [ "$MODE" = "indi_only" ]; then
    phase "Installing INDI build dependencies"
    if ! os_install_packages cmake build-tools libindi-dev git; then
        echo "❌ Failed to install required packages for --mode=indi_only. See messages above." >&2
        exit 1
    fi

    phase "Building INDI drivers"
    build_and_install_indi_drivers

    echo ""
    echo "##############################################"
    echo "  PiFinder Setup — INDI-Only Installation Summary"
    echo "##############################################"
    echo "  Mode:                 indi_only (no PiFinder hardware/application installed)"
    echo "  SM Scripts branch:    $(git -C "$SCRIPT_DIR" symbolic-ref --short -q HEAD || echo unknown)"
    _elapsed=$(( SECONDS - SETUP_START ))
    echo "  Setup time:           $(( _elapsed / 60 ))m $(( _elapsed % 60 ))s"
    echo "##############################################"

    if [ -f "$warnings_file" ] && [ -s "$warnings_file" ]; then
        echo ""
        echo "  ⚠️  CRITICAL WARNINGS — ACTION REQUIRED:"
        echo "##############################################"
        while IFS= read -r line; do
            echo "  ❌ $line"
        done < "$warnings_file"
        echo "##############################################"
    else
        echo "  ✅ No critical warnings — setup completed cleanly."
    fi
    echo "##############################################"
    echo "###REBOOT_NEEDED### false"
    rm -f "$warnings_file"
    exit 0
fi

# Source python venv if it exists
if [ -f "${python_venv}/bin/activate" ]; then
    source "${python_venv}/bin/activate"
fi

phase "Checking versions"

############################################################
# VERSION CHECK (informational only)
#
# PiFinder is pinned to a fixed release tag (v${pifinder_stellarmate_version_stable},
# see the git clone/checkout calls below) - this project never installs
# whatever the upstream release branch's HEAD happens to be at the moment,
# on purpose, for stability. This check used to compare against the live
# release-branch HEAD and hard-abort if it had moved past
# pifinder_stellarmate_version_stable/_testing - found live 2026-08-04 that
# this made the script permanently refuse to install/update the moment
# upstream cut a new release, even though the actual clone/checkout below
# was never going to touch that newer version anyway (it always targeted
# the pinned tag). Kept as a pure heads-up now, never blocks.

# Read local PiFinder version
pifinder_local_version=$(cat "$(pwd)/version.txt" 2>/dev/null)

# Fetch the upstream release branch's current version - informational only,
# does not influence which version actually gets installed below.
github_version=$(curl -s https://raw.githubusercontent.com/brickbots/PiFinder/release/version.txt | tr -d '\r')

echo "ℹ️  Local PiFinder version: $pifinder_local_version"
echo "ℹ️  Pinned PiFinder version (this run installs/updates to this): v${pifinder_stellarmate_version_stable}"
echo "ℹ️  Latest PiFinder version on GitHub's release branch: $github_version"

# version_gt()/version_eq() - see bin/version_compare.sh for why these live
# in their own sourceable file (unit-testable in isolation, see
# bin/tests/test_version_compare.bats).
source "${SCRIPT_DIR}/bin/version_compare.sh"

if version_gt "$github_version" "$pifinder_stellarmate_version_stable"; then
    echo "ℹ️  A newer PiFinder release ($github_version) exists upstream - this run still installs"
    echo "ℹ️  the pinned v${pifinder_stellarmate_version_stable} for stability. Bump"
    echo "ℹ️  pifinder_stellarmate_version_stable in this script (after verifying the newer version)"
    echo "ℹ️  to move the pin forward."
fi

echo "$pifinder_stellarmate_version_stable" > "$(pwd)/version.txt"

############################################################
# SMOS VERSION CHECK

current_smos_version=$(curl -s http://localhost:8624/api/info/version 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['version'])" 2>/dev/null)

if [ -z "$current_smos_version" ]; then
    echo "⚠️  SMOS version could not be determined (API not reachable). Proceeding anyway."
elif version_eq "$current_smos_version" "$smos_version_stable"; then
    echo "✅ SMOS version $current_smos_version matches tested STABLE version. Proceeding..."
elif version_gt "$current_smos_version" "$smos_version_stable"; then
    echo "⚠️  SMOS $current_smos_version is NEWER than tested version ($smos_version_stable)."
    echo "⚠️  Arch is rolling release — package versions may differ. Proceed with caution."
    # Same interactive-vs-scripted distinction the reinstall/update menu
    # above already uses (empty $ACTION = a human running this directly in
    # a terminal; the Control Center GUI always passes --action=...).
    # Found live 2026-09-04 on stellarmate-utm (SMOS 2.3.0 vs. the
    # 2.2.1 pin): every GUI-triggered run silently hit "Installation
    # cancelled by user" here, every single time, with no way to answer
    # this prompt - the GUI spawns this script as a systemd service's
    # subprocess (stdin inherited from pifinder-control-center.service,
    # i.e. /dev/null), so `read` sees immediate EOF, `confirm_smos` comes
    # back empty, and the "not yes" branch always fires. A confirmation
    # prompt nobody running through the GUI can ever answer isn't a safety
    # gate, it's a silent, permanent block - so a scripted run just gets
    # the same warning already printed above and proceeds, exactly like the
    # OLDER-than-tested branch below already does unconditionally.
    if [ -z "$ACTION" ]; then
        read -p "⚠️⚠️⚠️  Continue anyway? (yes/no): " confirm_smos
        confirm_smos="${confirm_smos//[$'\r\n']}"
        if [[ "$confirm_smos" != "yes" ]]; then
            echo "ℹ️  Installation cancelled by user."
            exit 0
        fi
    else
        echo "ℹ️  Running non-interactively (--action=$ACTION) - proceeding despite the newer SMOS version."
    fi
else
    echo "⚠️  SMOS $current_smos_version is OLDER than tested version ($smos_version_stable). Proceeding anyway."
fi

############################################################
phase "Setting up hardware access"

echo "ℹ️ INFO: running as user <<$(whoami)>> – assuming this is the correct Stellarmate setup user."

# groupadd/usermod require /etc/group and /etc/passwd to be well-formed,
# newline-terminated files. A missing trailing newline on the last line makes
# shadow-utils misreport "Non-text file" / "cannot open ...: Cannot allocate
# memory" (not a real ENOMEM - verified via strace, no syscall actually
# fails) and silently no-op instead of creating the group/updating the user.
# Found live on a fresh SMOS 2.3.0 x86 image (2026-09-05): both files were
# missing it, spi/gpio were never created, and pifinder.service could never
# start (systemd exit 216/GROUP - SupplementaryGroups= couldn't resolve
# gpio/spi). Ensuring this here is a correctness precondition for the calls
# below, not a defensive workaround.
for f in /etc/group /etc/passwd; do
    if [ -n "$(sudo tail -c 1 "$f")" ]; then
        echo "⚠️  $f is missing its trailing newline - fixing before groupadd/usermod."
        sudo bash -c "printf '\n' >> '$f'"
    fi
done

# Create hardware groups if missing (Arch/SMOS does not create these by default).
# PiFinder cannot start at all without these (pifinder.service's
# SupplementaryGroups=), so a failure here must hard-abort the script, not
# just warn and continue.
for grp in spi gpio i2c kmem input; do
    if ! getent group "$grp" > /dev/null 2>&1; then
        sudo groupadd "$grp"
        if ! getent group "$grp" > /dev/null 2>&1; then
            echo "❌ FATAL: groupadd '$grp' failed - PiFinder cannot start without it (see pifinder.service's SupplementaryGroups=)."
            exit 1
        fi
    fi
done

# Add rights accessing hardware to user
sudo usermod -a -G spi,gpio,i2c,video,kmem,input ${USER}
for grp in spi gpio i2c video kmem input; do
    if ! id -nG "${USER}" | tr ' ' '\n' | grep -qx "$grp"; then
        echo "❌ FATAL: user '${USER}' is not in group '$grp' after usermod - PiFinder cannot access the required hardware."
        exit 1
    fi
done

# udev rule for /dev/gpiomem access (Arch Linux). Pi5's RP1 chip exposes
# several numbered nodes (/dev/gpiomem0..4), each its OWN subsystem
# (SUBSYSTEM=gpiomem0, gpiomem1, ...) - not a shared "gpiomem" subsystem,
# and not the single unnumbered /dev/gpiomem Pi4 has. The old exact-match
# SUBSYSTEM=="gpiomem"/KERNEL=="gpiomem" rule silently matched nothing on
# Pi5, leaving gpiomem0-4 at their root:root 0600 default and printing
# "Failed to open the device '/dev/gpiomem': No such device" from the old
# --action=change /dev/gpiomem below (that hardcoded path doesn't exist on
# Pi5 either). Currently harmless in practice - PiFinder's actual GPIO
# access goes through /dev/gpiochip* (rpi-lgpio/lgpio), already group=uucp
# which stellarmate is also in - but the rule should still do what it says
# on both Pi4 and Pi5. Verified live: --subsystem-match='gpiomem*' (one
# glob argument) reaches all of gpiomem0-4 in a single trigger; passing
# each subsystem name as its own --subsystem-match flag does not (some
# devices silently keep their old permissions).
echo 'SUBSYSTEM=="gpiomem*", KERNEL=="gpiomem*", GROUP="gpio", MODE="0660"' | sudo tee /etc/udev/rules.d/99-gpiomem.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match='gpiomem*' --action=change

sudo chown -R ${USER}:${USER} ${pifinder_stellarmate_dir}

############################################################
phase "Cloning or updating PiFinder"

# Check if a PiFinder installation already exists.
if [ -d "${pifinder_home}/PiFinder" ]; then
    # If resuming, skip the prompt
    if [ -f "$lock_file" ] && is_venv_active "${python_venv}"; then
        echo "✅ Resuming installation after virtual environment activation."
    else
        echo "⚠️  An existing PiFinder installation was found at ${pifinder_home}/PiFinder."
        echo "❓ Please choose an action:"
        echo "   1. Delete the existing installation and reinstall from scratch."
        echo "   2. Update the existing installation to pinned PiFinder v${pifinder_stellarmate_version_stable}."
        echo "   3. Cancel the installation."
        echo "   4. Uninstall PiFinder completely (removes services, INDI drivers, ~/PiFinder)."
        echo "   5. Reset (keep data/config, wipe venv/build only, ready to re-run setup)."

        case "$ACTION" in
            reinstall) choice="1" ;;
            update)    choice="2" ;;
            cancel)    choice="3" ;;
            uninstall) choice="4" ;;
            reset)     choice="5" ;;
            "")
                read -p "Enter your choice (1-5): " choice
                choice="${choice//[$'\r\n']}"
                ;;
            *)
                echo "❌ Unknown --action='$ACTION' (expected reinstall|update|cancel|uninstall|reset)."
                exit 1
                ;;
        esac

        case "$choice" in
            1)
                echo "➡️  Selected: 1. Delete the existing installation and reinstall from scratch."
                stop_fake_mode_if_running
                sudo systemctl stop pifinder
                echo "🗑️  Deleting the existing PiFinder installation directory..."
                sudo rm -rf "${pifinder_home}/PiFinder"
                sleep 2 # Give some time for the deletion to complete
                if [ -n "$VIRTUAL_ENV" ]; then
                    # The directory we just deleted is what $VIRTUAL_ENV
                    # (sourced at script start, line ~70) points into — left
                    # alone, this goes stale and later trips the "Creating
                    # Python venv" phase's activation check, aborting the run
                    # deep in after the deletion + package installs already
                    # happened. Clear it here, right where it becomes stale,
                    # so the later check simply sees "not active" and creates
                    # a fresh venv normally.
                    echo "🔁 Deactivating the now-deleted venv reference ..."
                    type deactivate >/dev/null 2>&1 && deactivate
                    unset VIRTUAL_ENV
                fi
                if [ -d "${pifinder_home}/PiFinder" ]; then
                    echo "❌ ERROR: The PiFinder folder still exists after deletion. Aborting setup."
                    exit 1
                fi
                echo "Installation from scratch ..."
                cd "${pifinder_home}"
                if ! git clone --recursive --branch "v${pifinder_stellarmate_version_stable}" https://github.com/brickbots/PiFinder.git; then
                    echo "❌ ERROR: 'git clone' of PiFinder failed (network issue or GitHub unreachable?)."
                    echo "❌ Aborting setup rather than patching/building against an incomplete checkout."
                    exit 1
                fi
                if [ ! -f "${pifinder_home}/PiFinder/version.txt" ]; then
                    # Belt-and-suspenders: seen live where the clone command
                    # itself returned success but still left an incomplete
                    # checkout behind (missing files, no error surfaced) -
                    # every later step (patching, building, chown) silently
                    # operated on that partial tree instead of catching it,
                    # so the run "finished" looking mostly fine while
                    # PiFinder itself was actually broken.
                    echo "❌ ERROR: git clone did not produce a usable PiFinder checkout (no version.txt)."
                    echo "❌ Aborting setup rather than patching/building against an incomplete checkout."
                    exit 1
                fi
                sudo chown -R ${USER}:${USER} "${pifinder_home}/PiFinder"
                echo "python/.venv/" >> "${pifinder_home}/PiFinder/.gitignore"
                bash ${pifinder_stellarmate_bin}/patch_PiFinder_installation_files.sh
                find "${pifinder_home}/PiFinder" -type f -name "*.pyc" -delete
                find "${pifinder_home}/PiFinder" -type d -name "__pycache__" -delete
                cp "${pifinder_stellarmate_dir}/src_pifinder/python/PiFinder/gps_stellarmate.py" "${pifinder_home}/PiFinder/python/PiFinder/"
                cp "${pifinder_stellarmate_dir}/src_pifinder/python/views/smos.html" "${pifinder_home}/PiFinder/python/views/"
                mkdir -p "${pifinder_home}/PiFinder/python/views/images"
                cp "${pifinder_stellarmate_dir}/src_pifinder/python/views/images/webmanager_profile.png" "${pifinder_home}/PiFinder/python/views/images/"
                cp "${pifinder_stellarmate_dir}/src_pifinder/python/views/images/webmanager_profile_thumb.png" "${pifinder_home}/PiFinder/python/views/images/"
                cp "${pifinder_stellarmate_dir}/src_pifinder/python/views/images/control_center.png" "${pifinder_home}/PiFinder/python/views/images/"
                cp "${pifinder_stellarmate_dir}/src_pifinder/python/views/images/control_center_thumb.png" "${pifinder_home}/PiFinder/python/views/images/"
                mkdir -p "${pifinder_home}/PiFinder/.claude/skills/pifinder-remote/scripts"
                cp "${pifinder_stellarmate_dir}/src_pifinder/.claude/skills/pifinder-remote/SKILL.md" "${pifinder_home}/PiFinder/.claude/skills/pifinder-remote/"
                cp "${pifinder_stellarmate_dir}/src_pifinder/.claude/skills/pifinder-remote/scripts/pf_remote.py" "${pifinder_home}/PiFinder/.claude/skills/pifinder-remote/scripts/"
                ;;
            2)
                echo "➡️  Selected: 2. Update the existing installation to pinned PiFinder v${pifinder_stellarmate_version_stable}."
                stop_fake_mode_if_running
                sudo systemctl stop pifinder
                echo "🔄 Updating the existing installation to pinned PiFinder v${pifinder_stellarmate_version_stable}..."
                cd "${pifinder_home}/PiFinder"
                # Tags aren't guaranteed to be present after a --branch=<tag>
                # clone (implies --single-branch, restricting the default
                # fetch refspec to that one ref) - --tags explicitly
                # overrides that restriction and fetches every tag
                # regardless, so this also picks up a NEWER pin (a future
                # bump of pifinder_stellarmate_version_stable itself), not
                # just re-fetching the one already checked out.
                if ! git fetch origin --tags; then
                    echo "❌ ERROR: 'git fetch origin --tags' failed - aborting rather than"
                    echo "❌ patching/building against a checkout left in an unknown state."
                    exit 1
                fi
                # The existing checkout always has local modifications at
                # this point - every diffs/*.diff patch this script applies
                # is a tracked-file modification, still present from the
                # previous run. `git checkout <different-tag>` refuses to
                # switch refs while those would be overwritten (found live
                # 2026-08-09, #190: updating from a pinned v2.6.0 checkout to
                # v2.6.1 failed with "Your local changes... would be
                # overwritten by checkout" on every previously-patched
                # file). They're fully reproducible (re-applied by
                # patch_PiFinder_installation_files.sh a few lines below),
                # so discarding them here is always safe - reset to the
                # *current* HEAD first, before switching to the new tag.
                if ! git reset --hard HEAD; then
                    echo "❌ ERROR: 'git reset --hard HEAD' failed - aborting rather than"
                    echo "❌ patching/building against a checkout left in an unknown state."
                    exit 1
                fi
                if ! git checkout "v${pifinder_stellarmate_version_stable}"; then
                    echo "❌ ERROR: 'git checkout v${pifinder_stellarmate_version_stable}' failed - tag not"
                    echo "❌ found after fetch. Aborting rather than patching/building against a"
                    echo "❌ checkout left in an unknown state."
                    exit 1
                fi
                if ! git reset --hard "v${pifinder_stellarmate_version_stable}"; then
                    echo "❌ ERROR: 'git reset --hard' failed - aborting rather than patching/building"
                    echo "❌ against a possibly-stale checkout."
                    exit 1
                fi
                sudo chown -R ${USER}:${USER} "${pifinder_home}/PiFinder"
                echo "python/.venv/" >> "${pifinder_home}/PiFinder/.gitignore"
                bash ${pifinder_stellarmate_bin}/patch_PiFinder_installation_files.sh
                cp "${pifinder_stellarmate_dir}/src_pifinder/python/PiFinder/gps_stellarmate.py" "${pifinder_home}/PiFinder/python/PiFinder/"
                cp "${pifinder_stellarmate_dir}/src_pifinder/python/views/smos.html" "${pifinder_home}/PiFinder/python/views/"
                mkdir -p "${pifinder_home}/PiFinder/python/views/images"
                cp "${pifinder_stellarmate_dir}/src_pifinder/python/views/images/webmanager_profile.png" "${pifinder_home}/PiFinder/python/views/images/"
                cp "${pifinder_stellarmate_dir}/src_pifinder/python/views/images/webmanager_profile_thumb.png" "${pifinder_home}/PiFinder/python/views/images/"
                cp "${pifinder_stellarmate_dir}/src_pifinder/python/views/images/control_center.png" "${pifinder_home}/PiFinder/python/views/images/"
                cp "${pifinder_stellarmate_dir}/src_pifinder/python/views/images/control_center_thumb.png" "${pifinder_home}/PiFinder/python/views/images/"
                mkdir -p "${pifinder_home}/PiFinder/.claude/skills/pifinder-remote/scripts"
                cp "${pifinder_stellarmate_dir}/src_pifinder/.claude/skills/pifinder-remote/SKILL.md" "${pifinder_home}/PiFinder/.claude/skills/pifinder-remote/"
                cp "${pifinder_stellarmate_dir}/src_pifinder/.claude/skills/pifinder-remote/scripts/pf_remote.py" "${pifinder_home}/PiFinder/.claude/skills/pifinder-remote/scripts/"
                ;;
            3)
                echo "➡️  Selected: 3. Cancel the installation."
                echo "ℹ️  Installation cancelled by user."
                exit 0
                ;;
            4)
                echo "➡️  Selected: 4. Uninstall PiFinder completely."
                # Plain (non-selfmove) invocation: safe to run directly here,
                # this is a bash-level call, not the Control Center's own
                # long-running Python server serving out of this directory -
                # see bin/uninstall_pifinder_stellarmate.sh's own --selfmove
                # comment for why that distinction matters.
                bash "${pifinder_stellarmate_bin}/uninstall_pifinder_stellarmate.sh"
                exit 0
                ;;
            5)
                echo "➡️  Selected: 5. Reset (keep data/config, wipe venv/build only)."
                bash "${pifinder_stellarmate_bin}/uninstall_pifinder_stellarmate.sh" --reset
                exit 0
                ;;
            *)
                echo "➡️  Selected: $choice (invalid)"
                echo "❌ Invalid choice. Please run the script again and select 1-5."
                exit 1
                ;;
        esac
    fi
else
    echo "🚀 No existing installation found. Starting fresh..."
    cd "${pifinder_home}"
    git clone --recursive --branch "v${pifinder_stellarmate_version_stable}" https://github.com/brickbots/PiFinder.git
    sudo chown -R ${USER}:${USER} "${pifinder_home}/PiFinder"
    echo "python/.venv/" >> "${pifinder_home}/PiFinder/.gitignore"
    bash ${pifinder_stellarmate_bin}/patch_PiFinder_installation_files.sh
    find "${pifinder_home}/PiFinder" -type f -name "*.pyc" -delete
    find "${pifinder_home}/PiFinder" -type d -name "__pycache__" -delete
fi

phase "Installing system packages"

# Temporarily disable StellarMate's Atomic Updates protection (official
# mechanism) if it's currently active, reusing the same pacman/apt/nix
# abstraction layer (bin/os_detect.sh) that os_install_packages() already
# uses for --mode=indi_only above, rather than a second, ad-hoc lock/unlock
# here. No-op on a device where it's already unlocked (e.g. the Pi4/Pi5 dev
# units, unlocked in an earlier session) - this only actually engages on a
# freshly provisioned system (e.g. stellarmate-utm right after a clean SMOS
# install), which is also the only place the raw `pacman -S` calls below were
# ever observed to fail ("target not found" / core+extra+alarm unreachable,
# only StellarMate's own [smos] repo active).
relock_atomic_updates=0
if os_pacman_has_atomic_updates_script && os_pacman_check_atomic_updates; then
    echo "ℹ️  Temporarily disabling StellarMate's Atomic Updates protection (official mechanism) to reach core/extra/alarm ..."
    if os_pacman_atomic_updates_disable; then
        relock_atomic_updates=1
    else
        add_warning "Could not disable StellarMate's Atomic Updates protection - system package installs below may fail."
    fi
fi

# Arch/SMOS: add core, extra, alarm repos if missing (pacman.conf resets after reboot).
# aarch64-only fallback - archlinuxarm.org has no x86_64 packages. On
# stellarmate-utm (x86_64) the unlock above already leaves [core]/[extra]
# wired to the correct arch-native mirror (via StellarMate's own script,
# which reads /etc/pacman.d/mirrorlist), so this would 404 unconditionally
# if it ever ran there instead.
if [ "$(uname -m)" != "x86_64" ]; then
    grep -q "^\[core\]" /etc/pacman.conf || printf '\n[core]\nSigLevel = Optional TrustAll\nServer = http://mirror.archlinuxarm.org/aarch64/core\n\n[extra]\nSigLevel = Optional TrustAll\nServer = http://mirror.archlinuxarm.org/aarch64/extra\n\n[alarm]\nSigLevel = Optional TrustAll\nServer = http://mirror.archlinuxarm.org/aarch64/alarm\n' | sudo tee -a /etc/pacman.conf > /dev/null
fi
sudo pacman -Sy --noconfirm

# Install system package requirements (Arch/SMOS)
# libcamera 0.7.1+ uses pybind11 smart_holder — incompatible with picamera2 from pip.
# python-libcamera must stay at 0.7.0 — use cached package if available, then pin.
# nlohmann-json: header-only C++ JSON lib the INDI drivers' CMakeLists.txt
# require (pkg_check_modules 'nlohmann_json') - was missing from this list,
# so all three driver builds failed with "package 'nlohmann_json' not found".
sudo pacman -S --noconfirm --needed \
    git python-pip python-virtualenv libcap \
    openexr nlohmann-json
# libcamera + libcamera-ipa are pre-installed by SMOS — only install if missing.
# Never upgrade: repo may carry a newer pkgrel with incompatible soname (SMOS packaging bug:
# libcamera 0.7.1-64 breaks libcamera-ipa 0.7.1-1 soname dependency).
if ! pacman -Q libcamera &>/dev/null || ! pacman -Q libcamera-ipa &>/dev/null; then
    sudo pacman -S --noconfirm libcamera libcamera-ipa
    echo "  ✅ libcamera installed"
else
    echo "  ℹ️  libcamera $(pacman -Q libcamera | awk '{print $2}') already present (SMOS base)"
fi
# Prefer pinned package from repo, fall back to pacman cache.
# The cached package is aarch64-only (built for Pi) - on x86 it's still found
# by the ls glob (same git checkout), but `pacman -U` on it can never work
# and used to fail silently: no add_warning, and the summary below claimed
# "pinned" regardless of the pacman error, leaving python-libcamera not
# installed at all with "No critical warnings" shown to the user.
if [ "$(uname -m)" = "x86_64" ]; then
    echo "ℹ️  x86_64 host — skipping aarch64 python-libcamera pin (not applicable; no real camera hardware here anyway)."
    PYLIBCAM_METHOD="skipped (x86_64 host, aarch64-only pin not applicable)"
else
    PYLIBCAM_PKG=$(ls "${pifinder_stellarmate_dir}/packages/python-libcamera-0.7.0-"*"-aarch64.pkg.tar.xz" 2>/dev/null | head -1)
    [ -z "$PYLIBCAM_PKG" ] && PYLIBCAM_PKG=$(ls /var/cache/pacman/pkg/python-libcamera-0.7.0-*-aarch64.pkg.tar.xz 2>/dev/null | head -1)
    if [ -n "$PYLIBCAM_PKG" ]; then
        echo "ℹ️  Installing python-libcamera 0.7.0 from cache (smart_holder fix) ..."
        if sudo pacman -U --noconfirm "$PYLIBCAM_PKG"; then
            PYLIBCAM_METHOD="pinned 0.7.0 from $(basename $PYLIBCAM_PKG)"
        else
            add_warning "python-libcamera 0.7.0 cached package failed to install (see log above) - camera may fail (smart_holder)!"
            PYLIBCAM_METHOD="FAILED to pin 0.7.0 (see warnings above)"
        fi
    else
        add_warning "python-libcamera 0.7.0 not found — installed current version. Camera may fail (smart_holder)!"
        sudo pacman -S --noconfirm --needed python-libcamera
        PYLIBCAM_METHOD="current version (UNPINNED — may cause smart_holder error!)"
    fi
fi
grep -q "IgnorePkg.*python-libcamera" /etc/pacman.conf || \
    sudo sed -i '/^\[options\]/a IgnorePkg = python-libcamera' /etc/pacman.conf

# Risk 1: check libcamera major version - python-libcamera 0.7.0 is only compatible with 0.7.x
LIBCAM_VER=$(pacman -Q libcamera 2>/dev/null | awk '{print $2}' | cut -d. -f1,2)
LIBCAM_MAJOR=$(pacman -Q libcamera 2>/dev/null | awk '{print $2}' | cut -d. -f1)
if [ -n "$LIBCAM_MAJOR" ] && [ "$LIBCAM_MAJOR" -gt 0 ] 2>/dev/null; then
    add_warning "libcamera $LIBCAM_VER detected — python-libcamera 0.7.0 may be incompatible! Update packages/ in SM repo if camera fails."
else
    echo "ℹ️  libcamera version $LIBCAM_VER — compatible with python-libcamera 0.7.0"
fi

if [ "${relock_atomic_updates}" = "1" ]; then
    echo "ℹ️  Restoring StellarMate's Atomic Updates protection ..."
    os_pacman_atomic_updates_enable
fi




#########################################################################
# Make some Changes to the downloaded local installation files of PiFinder 
cd ${pifinder_home}/PiFinder

# Replace patched service files with the correct Stellarmate versions
cp ${pifinder_stellarmate_dir}/pi_config_files/pifinder.service ${pifinder_home}/PiFinder/pi_config_files/pifinder.service
cp ${pifinder_stellarmate_dir}/pi_config_files/pifinder_splash.service ${pifinder_home}/PiFinder/pi_config_files/pifinder_splash.service
cp ${pifinder_stellarmate_dir}/pi_config_files/pifinder-setup.service ${pifinder_home}/PiFinder/pi_config_files/pifinder-setup.service

############################################
# Create swapfile BEFORE pip install — pip builds (numpy, pandas, picamera2)
# consume huge amounts of RAM and will kill the system without swap on Pi4
if [ ! -f /swapfile ]; then
    echo "🔧 Creating 2GB swapfile (btrfs-compatible, needed before pip install) ..."
    sudo touch /swapfile
    sudo chattr +C /swapfile 2>/dev/null || true
    sudo dd if=/dev/zero of=/swapfile bs=1M count=2048 status=progress
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    grep -q "/swapfile" /etc/fstab || echo "/swapfile none swap defaults 0 0" | sudo tee -a /etc/fstab
    echo "✅ Swapfile ready."
else
    # Ensure swap is active even if file exists (e.g. after reboot without fstab)
    swapon --show | grep -q /swapfile || sudo swapon /swapfile 2>/dev/null || true
    echo "ℹ️  Swapfile already exists and active."
fi

phase "Creating Python venv"

############################################
# Python version check: delete venv if system Python changed (e.g. after SMOS update)
if [ -f "${python_venv}/bin/python" ]; then
    venv_ver=$("${python_venv}/bin/python" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
    sys_ver=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
    if [ -n "$venv_ver" ] && [ "$venv_ver" != "$sys_ver" ]; then
        echo "⚠️  Python version mismatch: venv=$venv_ver, system=$sys_ver — deleting venv for rebuild."
        rm -rf "${python_venv}"
        if [ -n "$VIRTUAL_ENV" ]; then
            # Same staleness as the reinstall branch above: $VIRTUAL_ENV
            # (sourced at script start) now points into what we just
            # deleted. is_venv_active() only string-compares $VIRTUAL_ENV
            # against the path, so without this it would still report
            # "active", fall into the "directory missing" abort path below,
            # and demand a manual deactivate+re-run — for every install mode
            # (fresh/reinstall/update), not just reinstall, since this runs
            # after they've all merged back into one flow.
            echo "🔁 Deactivating the now-deleted venv reference ..."
            type deactivate >/dev/null 2>&1 && deactivate
            unset VIRTUAL_ENV
        fi
    else
        echo "ℹ️  Python version OK: venv=$venv_ver, system=$sys_ver"
    fi
fi

############################################
# Create an activate3 VENV

# Check if venv is active and install requirements
if ! is_venv_active "${python_venv}"; then
  echo "Python venv is not active."

  # Check if venv directory exists
  if ! check_venv_exists "${python_venv}"; then
    echo "Python venv directory does not exist."
    # Create venv
    if create_venv "${python_venv}"; then
      touch "${lock_file}"
      if [ -n "$ACTION" ]; then
        echo "🔁 Virtual environment created — re-executing inside it automatically ..."
        cd "$SCRIPT_DIR"
        exec bash -c "source '${python_venv}/bin/activate' && exec '${SCRIPT_PATH}' \"\$@\"" -- "$@"
      fi
      echo " "
      echo "##### STOP ##########################################################"
      echo "##### DO NOT CLOSE THIS TERMINAL !!! MANUAL INPUT REQUIRED !!! ######"
      echo "The Python virtual environment was successfully created and MUST be activated manually."
      echo "Please run the following command in this terminal to activate the virtual environment."
      echo "Then rerun the scipt from within the new virtual environment (you see somthing like (.venv) after activation:"
      echo ""
      echo "vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv"
      echo "source ${python_venv}/bin/activate"
      echo "./pifinder_stellarmate_setup.sh"
      echo ""
      # Exit the script, because venv must be activated   manually for Requirements installation
      exit 1
    else
      echo "Error creating Python venv. Aborting."
      exit 1
    fi
  else
    if [ -n "$ACTION" ]; then
      # touch lock_file here too (not just the create_venv success path
      # above) - this branch is actually the common case for Update/
      # Reinstall on an install that already has a venv from a previous
      # run: it's just not active in *this* fresh shell invocation. Without
      # this, the resume guard at the top of the script (`[ -f "$lock_file"
      # ] && is_venv_active ...`) never sees the lock file after the
      # re-exec below, so it re-runs the ENTIRE script from the top again -
      # including the menu prompt/choice and the actual git checkout +
      # patch application a second time. Found live 2026-08-03 testing
      # PR #154's Update path: the whole log (checkout, file list, patch
      # diffs) appeared twice.
      touch "${lock_file}"
      echo "🔁 Virtual environment directory exists but isn't active — re-executing inside it automatically ..."
      cd "$SCRIPT_DIR"
      exec bash -c "source '${python_venv}/bin/activate' && exec '${SCRIPT_PATH}' \"\$@\"" -- "$@"
    fi
    echo -e "STOP: Python venv directory exists. Please activate the venv manually with:\n vvvvvvvv"
    echo "source ${python_venv}/bin/activate"
    echo -e "\nTHEN: run the script again to install the Requirements."
    exit 1 # Exit script because venv must be activated manually for Requirements installation
  fi
else
  # Venv seems active, but let's double-check if the directory is actually there
  if ! check_venv_exists "${python_venv}"; then
    if [ -n "$ACTION" ]; then
      # Happens when the top-of-script `source .venv/bin/activate` picked up a
      # venv that a reinstall then deleted+recreated later in this same run —
      # $VIRTUAL_ENV is now stale. Drop it and re-exec cleanly so the script
      # re-detects the (missing) venv and goes through the normal create path.
      echo "🔁 Stale venv reference (directory was removed) — re-executing cleanly ..."
      cd "$SCRIPT_DIR"
      exec env -u VIRTUAL_ENV bash "${SCRIPT_PATH}" "$@"
    fi
    echo "###################################################################"
    echo "WARNING: Your shell thinks a virtual environment is active,"
    echo "but the directory has been removed (likely during reinstallation)."
    echo "Please run 'deactivate' and then re-run this setup script."
    echo "###################################################################"
    exit 1
  else
    # Clean up the lock file if it exists, as we are now proceeding
    rm -f "${lock_file}"
    phase "Installing Python requirements"
    echo "Python venv is active. Installing Requirements."
    install_requirements "${python_requirements}"
    find "${pifinder_home}/PiFinder" -type f -name "*.pyc" -delete
    find "${pifinder_home}/PiFinder" -type d -name "__pycache__" -delete

    # Pin picamera2 to a known-good version - PiFinder's own requirements.txt
    # leaves it unpinned, so a fresh install can silently pull a newer
    # release whose drm_preview.py has drifted from
    # diffs/drm_preview_smos.diff's expected context, breaking the patch
    # applied below (found live 2026-08-09: a fresh Pi5 install pulled
    # 0.3.37, which added an FMT_MAP entry the diff's hunks didn't account
    # for - same fragility class as the pandas/#190 patch-drift issues).
    # Same reasoning as python-libcamera's pin above - keep this version and
    # the diff in sync; if drm_preview.py's patch ever needs regenerating
    # for a newer picamera2, bump this pin to match in the same change.
    echo "🔧 Pinning picamera2 to 0.3.37 (matches diffs/drm_preview_smos.diff) ..."
    pip install picamera2==0.3.37

    # Install python-libinput 0.1.0 manually (0.3.0a0 unavailable; setup.py uses removed 'imp')
    echo "🔧 Installing python-libinput 0.1.0 (patched for Python 3.12+) ..."
    LIBINPUT_TMP=$(mktemp -d)
    curl -sL https://files.pythonhosted.org/packages/source/p/python-libinput/python-libinput-0.1.0.tar.gz \
        -o "${LIBINPUT_TMP}/python-libinput-0.1.0.tar.gz"
    tar xzf "${LIBINPUT_TMP}/python-libinput-0.1.0.tar.gz" -C "${LIBINPUT_TMP}"
    # Patch setup.py: replace removed 'imp' module with importlib.util
    sed -i 's/from imp import load_source/import importlib.util\ndef load_source(name, path):\n    spec = importlib.util.spec_from_file_location(name, path)\n    mod = importlib.util.module_from_spec(spec)\n    spec.loader.exec_module(mod)\n    return mod/' \
        "${LIBINPUT_TMP}/python-libinput-0.1.0/setup.py"
    nice -n 15 ionice -c 3 pip install "${LIBINPUT_TMP}/python-libinput-0.1.0/"
    rm -rf "${LIBINPUT_TMP}"
    echo "✅ python-libinput 0.1.0 installed."

    # Patch skyfield starlib.py for numpy 2.0 compatibility (Risiko 3)
    echo "🔧 Patching skyfield starlib.py for numpy 2.0 compatibility ..."
    SKYFIELD_VER=$("${python_venv}/bin/python" -c "import skyfield; print(skyfield.__version__)" 2>/dev/null || echo "unknown")
    STARLIB_PY=$(find "${python_venv}" -name "starlib.py" -path "*/skyfield/*" 2>/dev/null | head -1)
    if [ -n "$STARLIB_PY" ]; then
        if grep -q "numpy 2.0" "$STARLIB_PY"; then
            echo "  ℹ️  starlib.py already patched (skyfield $SKYFIELD_VER)"
        else
            patch -N "$STARLIB_PY" < "${pifinder_stellarmate_dir}/diffs/starlib_numpy2_smos.diff" && \
                echo "  ✅ starlib.py patched for skyfield $SKYFIELD_VER" || \
                add_warning "starlib.py patch FAILED for skyfield $SKYFIELD_VER — update diffs/starlib_numpy2_smos.diff! Star charts may crash."
        fi
    else
        echo "  ⚠️  skyfield not found in venv — skipping"
    fi

    # Patch skyfield keplerlib.py: batch-propagating N>1 comets to one shared
    # observation time drops the per-orbit dimension in propagate()'s output
    # shape, raising "cannot reshape array of size 3*N into shape (3,)" (hit
    # in PiFinder's _calc_comets_vectorized(), see comets.py). Also reported
    # upstream to skyfielders/python-skyfield (PR #1138). Requirements.txt
    # now pins skyfield==1.50, which predates this bug (introduced in 1.51),
    # so this is a defensive no-op for the normal case — only kicks in if
    # skyfield ever ends up unpinned/newer again.
    echo "🔧 Patching skyfield keplerlib.py (batch comet propagation) ..."
    KEPLERLIB_PY=$(find "${python_venv}" -name "keplerlib.py" -path "*/skyfield/*" 2>/dev/null | head -1)
    if [ -n "$KEPLERLIB_PY" ]; then
        if grep -q "n_orbits" "$KEPLERLIB_PY"; then
            echo "  ℹ️  keplerlib.py already patched (skyfield $SKYFIELD_VER)"
        elif ! grep -q "output_shape = (3,) + t1.shape" "$KEPLERLIB_PY"; then
            echo "  ℹ️  keplerlib.py: bug pattern not present in skyfield $SKYFIELD_VER (<1.51 or already fixed upstream) — no patch needed"
        else
            patch -N "$KEPLERLIB_PY" < "${pifinder_stellarmate_dir}/diffs/keplerlib_batch_propagate_smos.diff" && \
                echo "  ✅ keplerlib.py patched for skyfield $SKYFIELD_VER" || \
                add_warning "keplerlib.py patch FAILED for skyfield $SKYFIELD_VER — update diffs/keplerlib_batch_propagate_smos.diff! Comet display may crash/hang."
        fi
    else
        echo "  ⚠️  skyfield not found in venv — skipping"
    fi

    # Patch picamera2 drm_preview.py (pykms not available on Arch) (Risiko 2)
    echo "🔧 Applying drm_preview.py patch post pip-install ..."
    PICAM_VER=$("${python_venv}/bin/python" -c "import importlib.metadata; print(importlib.metadata.version('picamera2'))" 2>/dev/null || echo "unknown")
    DRM_PY=$(find "${python_venv}" -name "drm_preview.py" 2>/dev/null | head -1)
    if [ -n "$DRM_PY" ]; then
        if grep -q "_pykms_available" "$DRM_PY"; then
            echo "  ℹ️  drm_preview.py already patched (picamera2 $PICAM_VER)"
        else
            patch -N "$DRM_PY" < "${pifinder_stellarmate_dir}/diffs/drm_preview_smos.diff" && \
                echo "  ✅ drm_preview.py patched for picamera2 $PICAM_VER" || \
                add_warning "drm_preview.py patch FAILED for picamera2 $PICAM_VER — update diffs/drm_preview_smos.diff! Camera import will fail."
        fi
    else
        echo "  ⚠️  picamera2 not found in venv — skipping"
    fi

    # Pi5: lgpio C library + rpi-lgpio (RPi.GPIO drop-in for the Pi5 RP1 GPIO)
    hw_model_setup=$(get_hw_model)
    if echo "$hw_model_setup" | grep -q "Raspberry Pi 5"; then
        echo "🔧 [Pi5] lgpio / rpi-lgpio Setup ..."

        # Install swig (build dep for the lgpio Python bindings)
        if ! command -v swig &>/dev/null; then
            echo "  Installing swig ..."
            sudo pacman -S --noconfirm swig 2>/dev/null && echo "  ✅ swig installed." || echo "  ⚠️  swig install failed — lgpio Python bindings may not build."
        fi

        # Clone the lgpio source if not present
        LGPIO_SRC="${pifinder_home}/lgpio-src"
        if [ ! -d "$LGPIO_SRC" ]; then
            echo "  Cloning lgpio source to $LGPIO_SRC ..."
            git clone --depth=1 https://github.com/joan2937/lg "$LGPIO_SRC" \
                && echo "  ✅ lgpio source cloned." \
                || add_warning "[Pi5] lgpio clone failed — GPIO will not work! Retry: git clone https://github.com/joan2937/lg $LGPIO_SRC"
        else
            echo "  ✅ lgpio source: already present ($LGPIO_SRC)"
        fi

        # Build and install liblgpio.so
        if [ ! -f /usr/local/lib/liblgpio.so ]; then
            echo "  Building liblgpio.so ..."
            make -C "$LGPIO_SRC" -s && sudo make -C "$LGPIO_SRC" install -s && sudo ldconfig \
                && echo "  ✅ liblgpio.so built and installed." \
                || add_warning "[Pi5] liblgpio.so build failed — GPIO will not work!"
        else
            echo "  ✅ liblgpio.so: already installed."
        fi

        # rpi-lgpio + lgpio aus lokalem packages/ installieren
        echo "  Installing rpi-lgpio + lgpio ..."
        LGPIO_WHL=$(ls "${pifinder_stellarmate_dir}/packages/lgpio-"*.whl 2>/dev/null | head -1)
        if [ -n "$LGPIO_WHL" ]; then
            pip install --quiet --no-index \
                --find-links="${pifinder_stellarmate_dir}/packages/" \
                rpi-lgpio lgpio \
                && echo "  ✅ rpi-lgpio installed from packages/." \
                || add_warning "[Pi5] rpi-lgpio install from packages/ failed."
        else
            pip install --quiet rpi-lgpio \
                && echo "  ✅ rpi-lgpio installed from PyPI." \
                || add_warning "[Pi5] rpi-lgpio install failed — GPIO will not work!"
        fi
    fi
  fi
fi

# ensure, correct rights are set
sudo chown -R ${USER}:${USER} ${pifinder_home}/PiFinder

# NOT USED, PART OF STELLARMATE-OS: samba samba-common-bin dnsmasq hostapd dhcpd gpsd
# NOT USED, PART OF STELLARMATE-OS: Setup GPSD
# NOT USED, PART OF STELLARMATE-OS: sudo dpkg-reconfigure -plow gpsd
# NOT USED, PART OF STELLARMATE-OS: sudo cp ~/PiFinder/pi_config_files/gpsd.conf /etc/default/gpsd

# data dirs
mkdir -p ~/PiFinder_data
mkdir -p ~/PiFinder_data/captures
mkdir -p ~/PiFinder_data/obslists
mkdir -p ~/PiFinder_data/screenshots
mkdir -p ~/PiFinder_data/solver_debug_dumps
mkdir -p ~/PiFinder_data/logs
chmod -R 777 ~/PiFinder_data

phase "Downloading star catalog"

# Hipparcos catalog — check file exists AND is non-empty (>1MB)
HIP_DAT="${pifinder_dir}/astro_data/hip_main.dat"
HIP_MIN_SIZE=1000000
if [ -f "$HIP_DAT" ] && [ "$(stat -c%s "$HIP_DAT" 2>/dev/null)" -gt "$HIP_MIN_SIZE" ]; then
    echo "ℹ️  hip_main.dat already installed"
else
    [ -f "$HIP_DAT" ] && rm -f "$HIP_DAT"  # remove empty/partial file
    echo "🔧 Downloading Hipparcos catalog..."
    HIP_URLS=(
        "https://cdsarc.cds.unistra.fr/ftp/cats/I/239/hip_main.dat"
        "http://vizier.cds.unistra.fr/ftp/cats/I/239/hip_main.dat"
        "http://cdsarc.u-strasbg.fr/ftp/cats/I/239/hip_main.dat"
    )
    HIP_OK=false
    HIP_METHOD="not downloaded"
    for url in "${HIP_URLS[@]}"; do
        echo "  Trying: $url"
        wget -q --timeout=30 -L -O "$HIP_DAT" "$url" 2>/dev/null
        if [ -f "$HIP_DAT" ] && [ "$(stat -c%s "$HIP_DAT" 2>/dev/null)" -gt "$HIP_MIN_SIZE" ]; then
            echo "✅ hip_main.dat downloaded from $url"
            HIP_OK=true
            HIP_METHOD="downloaded from $url"
            break
        else
            rm -f "$HIP_DAT"
        fi
    done
    if [ "$HIP_OK" = false ]; then
        # Last resort: use bundled compressed copy from the SM repo
        HIP_GZ="${pifinder_stellarmate_dir}/src_pifinder/astro_data/hip_main.dat.gz"
        if [ -f "$HIP_GZ" ]; then
            echo "ℹ️  Using bundled hip_main.dat.gz from PiFinder_Stellarmate repo ..."
            gunzip -c "$HIP_GZ" > "$HIP_DAT"
            echo "✅ hip_main.dat extracted from bundled copy ($(stat -c%s "$HIP_DAT") bytes)"
            HIP_OK=true
            HIP_METHOD="extracted from bundled src_pifinder/astro_data/hip_main.dat.gz"
        else
            add_warning "hip_main.dat not available — star charts will fail! Retry: wget -O ${HIP_DAT} https://cdsarc.cds.unistra.fr/ftp/cats/I/239/hip_main.dat"
            HIP_METHOD="FAILED — not available!"
        fi
    fi
fi

# ensure, correct rights are set
sudo chown -R ${USER}:${USER} ${pifinder_home}/PiFinder


###########################
# Not used: tf already installed (also service)
###########################

# Wifi config
# NOT USED, PART OF STELLARMATE-OS: sudo cp ~/PiFinder/pi_config_files/dhcpcd.* /etc
# NOT USED, PART OF STELLARMATE-OS: sudo cp ~/PiFinder/pi_config_files/dhcpcd.conf.sta /etc/dhcpcd.conf
# NOT USED, PART OF STELLARMATE-OS: sudo cp ~/PiFinder/pi_config_files/dnsmasq.conf /etc/dnsmasq.conf
# NOT USED, PART OF STELLARMATE-OS: sudo cp ~/PiFinder/pi_config_files/hostapd.conf /etc/hostapd/hostapd.conf
# NOT USED, PART OF STELLARMATE-OS: echo -n "Client" > ~/PiFinder/wifi_status.txt
# NOT USED, PART OF STELLARMATE-OS: sudo systemctl unmask hostapd

# NOT USED, PART OF STELLARMATE-OS:  open permissisons on wpa_supplicant file so we can adjust network config
# NOT USED, PART OF STELLARMATE-OS:  sudo chmod 666 /etc/wpa_supplicant/wpa_supplicant.conf

# NOT USED, PART OF STELLARMATE-OS:  Samba config
# NOT USED, PART OF STELLARMATE-OS:  sudo cp ~/PiFinder/pi_config_files/smb.conf /etc/samba/smb.conf

phase "Configuring hardware & services"

if [ -f "/boot/firmware/config.txt" ]; then
    CONFIG_FILE="/boot/firmware/config.txt"
elif [ -f "/boot/config.txt" ]; then
    CONFIG_FILE="/boot/config.txt"
else
    CONFIG_FILE=""
fi

# Tracks whether this run actually changed /boot/config.txt - the only thing
# in this script that needs a real reboot (Pi firmware overlays are only
# applied at boot). Everything else (code, services, INDI drivers) is already
# restarted live by the end of this script.
CONFIG_CHANGED=false

if [ -z "$CONFIG_FILE" ]; then
    # No Raspberry Pi firmware config.txt on this system - this is not real
    # Pi hardware (e.g. an x86 Control-host development machine, see
    # docs/concepts/setup_indi_only_install_mode.md and
    # basic-memory/pifinder-stellarmate/00098). There is nothing GPIO/SPI/I2C
    # related to configure here; skip instead of aborting the whole install.
    echo "ℹ️  No Raspberry Pi firmware config.txt found (not real Pi hardware) — skipping GPIO/SPI/I2C overlay setup."
else
    echo "🔧 Ensuring required config.txt entries are present ..."

    # Add a line globally if not already present anywhere in config.txt
    add_if_missing() {
        local line="$1"
        if ! grep -Fxq "$line" "$CONFIG_FILE"; then
            echo "$line" | sudo tee -a "$CONFIG_FILE" > /dev/null
            echo "✅ Added: $line"
            CONFIG_CHANGED=true
        else
            echo "ℹ️  Already present: $line"
        fi
    }

    # Add a line inside a specific [section] block; creates section if missing.
    # Lines are only added once per section (idempotent).
    add_to_section() {
        local section="$1"
        local line="$2"
        # Check if line already exists anywhere in file (avoid duplicates across sections)
        if grep -Fxq "$line" "$CONFIG_FILE"; then
            echo "ℹ️  Already present: $line"
            return
        fi
        # Insert section header + line if section missing, else append after last line of section
        if ! grep -Fxq "[$section]" "$CONFIG_FILE"; then
            printf '\n[%s]\n%s\n' "$section" "$line" | sudo tee -a "$CONFIG_FILE" > /dev/null
            echo "✅ Created [$section] and added: $line"
        else
            # Append line after the section header
            sudo sed -i "/^\[$section\]/a $line" "$CONFIG_FILE"
            echo "✅ Added to [$section]: $line"
        fi
        CONFIG_CHANGED=true
    }

    # Global entries (apply to all Pi models)
    add_if_missing "dtparam=spi=on"
    add_if_missing "dtparam=i2c_arm=on"

    # Detect Pi model for model-specific overlays
    hw_model=$(get_hw_model)
    if echo "$hw_model" | grep -q "Raspberry Pi 5"; then
        # Pi5: PWM on GPIO13 (ALT0), imx296
        # WARNING: dtoverlay=uart3 on Pi5/RP1 occupies GPIO9 (UART3-RX) = SPI0-MISO -> SPI conflict!
        # On Pi4/BCM2711, uart3 is on GPIO4/5 -> no conflict.
        # TODO Pi5 GPS dongle/UBLOX: determine SPI-free UART pins on RP1 and add them here.
        add_to_section "pi5" "dtparam=i2c_arm_baudrate=10000"
        add_to_section "pi5" "dtoverlay=pwm,pin=13,func=4"
        add_to_section "pi5" "dtoverlay=pwm-2chan"
        add_to_section "pi5" "dtoverlay=imx296"
    elif echo "$hw_model" | grep -q "Raspberry Pi 4"; then
        # Pi4: PWM on GPIO13 (ALT0), uart3, imx296 — NO pwm-2chan (would override to GPIO19)
        add_to_section "pi4" "dtparam=i2c_arm_baudrate=10000"
        add_to_section "pi4" "dtoverlay=pwm,pin=13,func=4"
        add_to_section "pi4" "dtoverlay=uart3"
        add_to_section "pi4" "dtoverlay=imx296"
    fi

    echo "✅ config.txt checks complete."
fi

# Swapfile is created earlier (before pip install) — see above



# System-Fixes anwenden (WirePlumber, Gruppen, PWM, Swap etc.)
echo "🔧 Running pifinder_pre_start.sh to apply system fixes ..."
sudo bash "${pifinder_stellarmate_bin}/pifinder_pre_start.sh" "${USER}"
echo "✅ System fixes applied"

# Enable service
sudo cp ${pifinder_stellarmate_dir}/pi_config_files/pifinder.service /etc/systemd/system/pifinder.service
sudo cp ${pifinder_stellarmate_dir}/pi_config_files/pifinder_splash.service /etc/systemd/system/pifinder_splash.service
sudo cp ${pifinder_stellarmate_dir}/pi_config_files/pifinder-setup.service /etc/systemd/system/pifinder-setup.service
# Stellarmate-specific units with no stock-PiFinder analogue (so not part of
# ~/PiFinder/pi_config_files/, only installed here) - see basic-memory/
# pifinder-stellarmate/00030.
sudo cp ${pifinder_stellarmate_dir}/pi_config_files/pifinder-fake-mode-autostart.service /etc/systemd/system/pifinder-fake-mode-autostart.service
sudo cp ${pifinder_stellarmate_dir}/pi_config_files/pifinder-control-center.service /etc/systemd/system/pifinder-control-center.service
sudo cp ${pifinder_stellarmate_dir}/pi_config_files/pifinder-numpad-bridge.service /etc/systemd/system/pifinder-numpad-bridge.service

sudo systemctl daemon-reexec
sudo systemctl daemon-reload

sudo systemctl enable pifinder
sudo systemctl enable pifinder_splash
sudo systemctl enable pifinder-setup
# Its own ConditionPathExists=/dev/fb1 gates whether it actually does
# anything at a given boot - always enabled, like pifinder itself.
sudo systemctl enable pifinder-fake-mode-autostart
# Deliberately NOT enabled here, for both of the below - the Control
# Center is only meant to run when the user explicitly starts it
# (launch_setup_gui.sh: `systemctl enable --now`) or stops it (server.py's
# /shutdown: `systemctl disable`); the numpad bridge is the same via the
# Control Center's own "Turn Numpad On/Off" button. Either way, systemd's
# own enabled-state is what makes "on" (or "off") persist correctly across
# a reboot, once the user has chosen it once.

echo "🔧 Starting PiFinder services ..."
sudo systemctl start pifinder-setup
# restart, not start: on an Update run (as opposed to a fresh install),
# pifinder.service is very likely already active from before this run - a
# plain `start` on an already-active unit is a no-op, silently leaving the
# OLD process running under whatever config was loaded before this run's
# daemon-reload above, even though the just-copied pi_config_files/
# pifinder.service (e.g. its Nice=/CPUWeight=, or any future change) is
# already on disk and loaded into systemd. `restart` makes an update
# actually take effect on an already-running instance too, same as a fresh
# start does for a first install.
sudo systemctl restart pifinder
sudo systemctl start pifinder_splash

# Always enable + start the Control Center at the end of a setup run - a
# user who just ran this script (fresh install or otherwise) has no other
# way to discover/reach it than the URLs this prints below, and previously
# had to know to separately run gui_installer/launch_setup_gui.sh
# afterwards. Enabling here also means a later reboot auto-starts it via
# systemd's own persistence, same as any other choice made through the
# Control Center itself.
#
# Only START if it's currently INACTIVE - if it's already active, this run
# was most likely started BY that very instance (the GUI's own Update
# button), which already restarts itself after a successful run on its
# own. A restart from here would kill that instance mid-run instead: found
# live 2026-08-01, the setup script survives (KillMode=process), but
# writes to the now-orphaned server.py's stdout pipe hit SIGPIPE and die
# silently, well before this script would otherwise reach the INDI driver
# build. `enable` itself is idempotent and safe to run either way.
sudo systemctl enable pifinder-control-center
if ! systemctl is-active --quiet pifinder-control-center; then
    echo "🔧 Starting PiFinder Control Center ..."
    sudo systemctl start pifinder-control-center
fi

phase "Building INDI drivers"

# See Readme_PiFinder_LX200.md for what these drivers do and how to use them.
# build_and_install_indi_drivers() is shared with the --mode=indi_only path
# below - see bin/build_and_install_indi_drivers.sh.
build_and_install_indi_drivers

# Detect Pi and OS versions for the final summary message
hw_model=$(get_hw_model)
if echo "$hw_model" | grep -q "Raspberry Pi 5"; then
    current_pi="Pi 5"
elif echo "$hw_model" | grep -q "Raspberry Pi 4"; then
    current_pi="Pi 4"
elif [ -z "$hw_model" ]; then
    current_pi="Not a Pi (e.g. x86 Control host)"
else
    current_pi="Unknown Pi"
fi
current_os=$(lsb_release -sc 2>/dev/null || grep "^ID=" /etc/os-release | cut -d= -f2)

LIBCAM_FULL=$(pacman -Q libcamera 2>/dev/null | awk '{print $2}')
PYLIBCAM_FULL=$(pacman -Q python-libcamera 2>/dev/null | awk '{print $2}')
PICAM_FULL=$("${python_venv}/bin/python" -c "import importlib.metadata; print(importlib.metadata.version('picamera2'))" 2>/dev/null || echo "unknown")
SKYFIELD_FULL=$("${python_venv}/bin/python" -c "import skyfield; print(skyfield.__version__)" 2>/dev/null || echo "unknown")
NUMPY_FULL=$("${python_venv}/bin/python" -c "import numpy; print(numpy.__version__)" 2>/dev/null || echo "unknown")
PYTHON_FULL=$("${python_venv}/bin/python" --version 2>&1 | awk '{print $2}')

echo ""
echo "##############################################"
echo "  PiFinder Setup — Installation Summary"
echo "##############################################"
echo "  PiFinder:             v${pifinder_stellarmate_version_stable}  [latest upstream: $github_version]"
echo "  SM Scripts:           $pifinder_local_version  [branch: $(git -C "$SCRIPT_DIR" symbolic-ref --short -q HEAD || echo unknown)]"
echo "  SMOS:                 ${current_smos_version:-unknown}  [tested: $smos_version_stable]"
echo "  Hardware:             $current_pi"
echo "  OS:                   $current_os"
echo "  Python (venv):        $PYTHON_FULL"
echo "  numpy:                $NUMPY_FULL"
echo "  skyfield:             $SKYFIELD_FULL"
echo "  picamera2:            $PICAM_FULL"
echo "  libcamera:            $LIBCAM_FULL"
echo "  python-libcamera:     $PYLIBCAM_FULL  [${PYLIBCAM_METHOD:-pinned}]"
echo "  hip_main.dat:         ${HIP_METHOD:-already present}"
_elapsed=$(( SECONDS - SETUP_START ))
echo "  Setup time:           $(( _elapsed / 60 ))m $(( _elapsed % 60 ))s"
echo "##############################################"

if [ -f "$warnings_file" ] && [ -s "$warnings_file" ]; then
    echo ""
    echo "  ⚠️  CRITICAL WARNINGS — ACTION REQUIRED:"
    echo "##############################################"
    while IFS= read -r line; do
        echo "  ❌ $line"
    done < "$warnings_file"
    echo "##############################################"
    echo "  PiFinder may not work correctly until"
    echo "  the above issues are resolved."
else
    echo "  ✅ No critical warnings — setup completed cleanly."
fi
echo "##############################################"
echo ""
if [ "$CONFIG_CHANGED" = true ]; then
    echo "###REBOOT_NEEDED### true"
    echo "  ➡️  /boot/config.txt was changed — please reboot now to activate it:"
    echo "     sudo reboot"
else
    echo "###REBOOT_NEEDED### false"
    echo "  ✅ No reboot needed — /boot/config.txt was already up to date."
    echo "     (Services, INDI drivers, and code were already restarted live.)"
fi
echo "##############################################"
echo ""

# Control Center was enabled+started above (before the INDI driver build) -
# tell the user where to actually reach it, reusing the same /state-derived
# IP list gui_installer/launch_setup_gui.sh prints, instead of leaving them
# to go find/run that script themselves. A few retries: the service was
# just started and may not have bound its port yet.
_cc_state=""
for _ in $(seq 1 20); do
    _cc_state="$(curl -s -m 2 "http://localhost:8765/state" 2>/dev/null)"
    [ -n "$_cc_state" ] && break
    sleep 0.25
done
if [ -n "$_cc_state" ]; then
    python3 -c "
import json, sys
try:
    data = json.loads(sys.argv[1])
except Exception:
    sys.exit(0)
port = data.get('port', 8765)
ips = data.get('ips') or ['localhost']
print('  Control Center reachable at:')
for ip in ips:
    print(f'    http://{ip}:{port}/')
" "$_cc_state"
    echo "  Login: any username, password = your stellarmate system password"
else
    echo "  ⚠️  Control Center did not respond after 5s - check:"
    echo "     journalctl -u pifinder-control-center -n 50"
fi
echo "##############################################"
rm -f "$warnings_file"

phase "Setup complete"
