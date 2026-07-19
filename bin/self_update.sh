#!/usr/bin/env bash
# Self-update PiFinder_Stellarmate before running anything else, so both entry
# points (pifinder_stellarmate_setup.sh, gui_installer/launch_setup_gui.sh)
# always act on the latest scripts/diffs - not just whatever commit happened
# to be checked out when this clone was first made. A third party who just
# keeps clicking "Update" (which only updates the PiFinder checkout, never
# this repo) would otherwise never see improvements made here.
#
# Usage: source this near the very top of an entry-point script, then call
#   self_update_pifinder_stellarmate "$SCRIPT_DIR" "$@"
# SCRIPT_DIR must be this repo's root (computed once by the caller, before
# any `cd`). "$@" must be the entry-point script's own original arguments -
# they're needed to re-exec it identically after a successful update.
#
# Safety model (explicit per-step verification, fail closed on real errors):
#   - Preconditions not met (not a git checkout, local changes present,
#     detached HEAD, no upstream configured) -> this is a deliberate, expected
#     SKIP, not a failure. Logs why and continues with the current checkout.
#     This is what protects active development: as long as the working tree
#     has uncommitted changes, self-update never touches it.
#   - Once an update is actually attempted (clean tree + tracked branch),
#     every git step's exit code AND the resulting repo state are checked
#     explicitly. Any mismatch aborts the whole script with a specific error
#     message rather than silently continuing on a possibly-inconsistent
#     checkout.

self_update_pifinder_stellarmate() {
    local repo_dir="$1"
    shift
    # Guard against re-exec looping back into this function forever.
    if [ -n "${PIFINDER_STELLARMATE_SELF_UPDATED:-}" ]; then
        return 0
    fi

    if ! git -C "$repo_dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        echo "ℹ️  Self-update: ${repo_dir} is not a git checkout - skipping." >&2
        return 0
    fi

    if [ -n "$(git -C "$repo_dir" status --porcelain 2>/dev/null)" ]; then
        echo "ℹ️  Self-update: local changes present in ${repo_dir} - skipping (dev mode)." >&2
        return 0
    fi

    local branch upstream
    branch="$(git -C "$repo_dir" symbolic-ref --short -q HEAD)"
    if [ -z "$branch" ]; then
        echo "ℹ️  Self-update: detached HEAD in ${repo_dir} - skipping." >&2
        return 0
    fi
    upstream="$(git -C "$repo_dir" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null)"
    if [ -z "$upstream" ]; then
        echo "ℹ️  Self-update: branch '${branch}' has no upstream configured - skipping." >&2
        return 0
    fi

    echo "🔄 Self-update: checking ${repo_dir} (${branch}) for updates ..."
    if ! git -C "$repo_dir" fetch --quiet; then
        echo "❌ Self-update FAILED: 'git fetch' in ${repo_dir} did not succeed" >&2
        echo "   (no network? remote unreachable?). Aborting rather than continuing" >&2
        echo "   with a checkout we can't confirm is current." >&2
        exit 1
    fi

    local before upstream_hash
    before="$(git -C "$repo_dir" rev-parse HEAD)"
    upstream_hash="$(git -C "$repo_dir" rev-parse "$upstream" 2>/dev/null)"
    if [ -z "$upstream_hash" ]; then
        echo "❌ Self-update FAILED: could not resolve upstream '${upstream}' after fetch." >&2
        exit 1
    fi
    if [ "$before" = "$upstream_hash" ]; then
        echo "✅ Self-update: already up to date (${branch} @ ${before:0:8})."
        return 0
    fi

    if ! git -C "$repo_dir" merge --ff-only --quiet "$upstream"; then
        echo "❌ Self-update FAILED: local '${branch}' has diverged from '${upstream}'" >&2
        echo "   (not a fast-forward - someone committed locally without pushing?)." >&2
        echo "   Resolve manually: cd ${repo_dir} && git status" >&2
        exit 1
    fi

    local after
    after="$(git -C "$repo_dir" rev-parse HEAD)"
    if [ "$after" != "$upstream_hash" ]; then
        echo "❌ Self-update FAILED: HEAD after merge (${after:0:8}) does not match" >&2
        echo "   upstream (${upstream_hash:0:8}). Please check manually:" >&2
        echo "   cd ${repo_dir} && git status" >&2
        exit 1
    fi

    echo "✅ Self-update: ${branch} updated ${before:0:8} -> ${after:0:8}."
    echo "🔁 Re-executing with the freshly updated code ..."
    exec env PIFINDER_STELLARMATE_SELF_UPDATED=1 "$0" "$@"
}
