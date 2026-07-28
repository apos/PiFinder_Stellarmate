# Package-manager abstraction for the INDI-only install mode - see
# docs/concepts/setup_indi_only_install_mode.md for the full design
# (why pacman/apt/nix are the three planned cases, why Flatpak/Snap aren't,
# why this isn't a full OS-abstraction framework).
#
# Split deliberately into pure decision functions (os_pick_package_manager,
# os_package_name, os_pacman_atomic_updates_enabled - no filesystem/command
# access, fully unit-testable regardless of what's actually installed on the
# machine running the tests) and impure ones that gather real facts or
# perform real installs (os_detect_package_manager, os_install_packages,
# os_pacman_check_atomic_updates) - see bin/tests/test_os_detect.bats and
# docs/concepts/setup_script_test_suite.md for why that split matters.
#
# Only pacman is live-verified (the only hardware available so far). apt/nix
# are implemented from the same research this project already has (issue
# #37's draft, docs/concepts/remote_indi_coupling_split_host.md) but not yet
# run end-to-end on real Debian/Ubuntu/NixOS hardware - treat as
# design-verified, not field-verified, until that happens.

# Pure: given which package-manager commands exist (as "1"/"0" flags, not
# looked up here), decide which one to use. pacman > apt > nix priority -
# a system with more than one available (e.g. Nix installed on top of an
# apt-based distro) prefers its OS-native manager first.
os_pick_package_manager() {
    local has_pacman="$1" has_apt="$2" has_nix="$3"
    if [ "${has_pacman}" = "1" ]; then
        echo "pacman"
    elif [ "${has_apt}" = "1" ]; then
        echo "apt"
    elif [ "${has_nix}" = "1" ]; then
        echo "nix"
    else
        return 1
    fi
}

# Impure: gathers real facts about the machine this actually runs on, then
# defers the decision itself to the pure function above.
os_detect_package_manager() {
    local has_pacman=0 has_apt=0 has_nix=0
    command -v pacman >/dev/null 2>&1 && has_pacman=1
    command -v apt-get >/dev/null 2>&1 && has_apt=1
    { command -v nix >/dev/null 2>&1 || command -v nix-env >/dev/null 2>&1; } && has_nix=1
    os_pick_package_manager "${has_pacman}" "${has_apt}" "${has_nix}"
}

# Pure: generic package name -> the actual name/attribute this manager uses.
# Add a new row (and, if it's a genuinely new manager, a case in
# os_install_packages below) to extend - see the concept doc for why the
# package *set* stays deliberately small (only what INDI-only mode needs).
os_package_name() {
    local generic="$1"
    local manager="$2"
    case "${generic}:${manager}" in
        cmake:pacman) echo "cmake" ;;
        cmake:apt) echo "cmake" ;;
        cmake:nix) echo "cmake" ;;
        build-tools:pacman) echo "base-devel" ;;
        build-tools:apt) echo "build-essential" ;;
        # NixOS/nix builds normally get a C toolchain via stdenv implicitly -
        # not yet verified whether an explicit package is actually needed
        # here too. See docs/concepts/setup_indi_only_install_mode.md.
        build-tools:nix) echo "" ;;
        libindi-dev:pacman) echo "libindi" ;;
        libindi-dev:apt) echo "libindi-dev" ;;
        # Not yet verified against the real nixpkgs package search - see
        # the concept doc's Known Risks section.
        libindi-dev:nix) echo "libindi" ;;
        git:pacman) echo "git" ;;
        git:apt) echo "git" ;;
        git:nix) echo "git" ;;
        *) echo "" ;;
    esac
}

# Pure: StellarMate's own "Atomic Updates" root-access gate (see
# /etc/stellarmate/atomic-updates.sh, StellarMate's own tool) tracks its state
# in a one-line file that's either absent (never touched - defaults to
# enabled, matching that script's own get_state()) or contains "enabled"/
# "disabled" verbatim. Direct pacman access to core/extra/alarm - where
# cmake/git/libindi-dev/build-tools actually live - is blocked while this is
# enabled; only StellarMate's own [smos] repo stays reachable. Decouples the
# parsing rule from actually reading the file so this is unit-testable
# without a real StellarMate install.
os_pacman_atomic_updates_enabled() {
    local state_file_content="$1"
    [ "${state_file_content}" != "disabled" ]
}

# Impure: reads the real state file (absent -> empty string, same as
# StellarMate's own script treating a missing file as "enabled").
os_pacman_check_atomic_updates() {
    local state_file="/etc/stellarmate/.root-access-state"
    local content=""
    [ -f "${state_file}" ] && content="$(cat "${state_file}")"
    os_pacman_atomic_updates_enabled "${content}"
}

# Impure: detects the manager, maps every requested generic name, then
# dispatches to that manager's real install command. Not unit-tested itself
# (real side effects) - every decision it makes is delegated to the two pure
# functions above, which are.
os_install_packages() {
    local manager
    if ! manager="$(os_detect_package_manager)"; then
        echo "❌ No supported package manager found (looked for pacman, apt-get, nix)." >&2
        return 1
    fi

    local pkgs=()
    for generic in "$@"; do
        local name
        name="$(os_package_name "${generic}" "${manager}")"
        if [ -z "${name}" ]; then
            echo "❌ No known ${manager} package for '${generic}' - add it to os_package_name() in ${BASH_SOURCE[0]}." >&2
            return 1
        fi
        pkgs+=("${name}")
    done

    case "${manager}" in
        pacman)
            # On stock StellarMate, direct pacman access is blocked by design
            # (StellarMate's own warranty/stability protection, not a bug) -
            # walking the user through StellarMate's own official unlock
            # script, rather than silently invoking it ourselves, since it
            # voids the warranty and disables StellarMate's own auto-update
            # mechanism. That is the user's decision to make, not this
            # installer's.
            if [ -f /etc/stellarmate/atomic-updates.sh ] && os_pacman_check_atomic_updates; then
                echo "❌ This system has StellarMate's 'Atomic Updates' protection enabled, which blocks direct package installation." >&2
                echo "   To install packages, first run StellarMate's own unlock script (it will explain the tradeoffs and ask you to confirm):" >&2
                echo "" >&2
                echo "       sudo /etc/stellarmate/atomic-updates.sh --disable" >&2
                echo "" >&2
                echo "   Then run this installer again." >&2
                return 1
            fi
            # Restores pacman's own trust database to the distribution's
            # default state - the same remedy StellarMate's own factory-reset
            # tooling uses (reset_pacman_keys() in reset-factory-common.sh),
            # not a workaround invented here. Safe to run unconditionally:
            # a no-op if the keyring is already fine, and only ever restores
            # the OS's own default trust anchors (never StellarMate's own
            # [smos] signing key, which this mode never needs - cmake/git/
            # libindi-dev/build-tools all live in core/extra/alarm).
            sudo pacman-key --init
            sudo pacman-key --populate
            sudo pacman -Sy || true
            sudo pacman -S --noconfirm --needed "${pkgs[@]}"
            ;;
        apt)
            echo "⚠️  apt path not yet live-verified on real hardware - see docs/concepts/setup_indi_only_install_mode.md" >&2
            sudo apt-get install -y "${pkgs[@]}"
            ;;
        nix)
            echo "⚠️  nix path not yet live-verified on real hardware - see docs/concepts/setup_indi_only_install_mode.md" >&2
            local nix_pkgs=("${pkgs[@]/#/nixpkgs#}")
            nix profile install "${nix_pkgs[@]}"
            ;;
    esac
}
