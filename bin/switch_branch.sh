#!/usr/bin/env bash
# Switch PiFinder_Stellarmate to a different branch before self_update.sh
# runs - a distinct, deliberate step from self-update's own job (fast-
# forwarding whichever branch is ALREADY checked out). A pure no-op unless
# a branch is explicitly requested, so every existing entry point is
# unaffected when this isn't used.
#
# Usage: source this near the very top of an entry-point script (before
# self_update.sh runs), then call
#   switch_pifinder_stellarmate_branch "$SCRIPT_DIR" "$TARGET_BRANCH"
# TARGET_BRANCH may be empty (no-op) - this is what makes the --branch=
# flag optional everywhere it's accepted.
#
# Safety model (mirrors self_update.sh): a dirty working tree aborts loudly
# rather than risking losing local changes on a checkout - this is meant to
# be an explicit, occasional action, not something that silently discards
# work in progress.

switch_pifinder_stellarmate_branch() {
    local repo_dir="$1"
    local target_branch="$2"

    if [ -z "$target_branch" ]; then
        return 0
    fi

    if ! git -C "$repo_dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        echo "❌ Branch switch FAILED: ${repo_dir} is not a git checkout." >&2
        exit 1
    fi

    local current_branch
    current_branch="$(git -C "$repo_dir" symbolic-ref --short -q HEAD)"
    if [ "$current_branch" = "$target_branch" ]; then
        echo "✅ Branch: already on '${target_branch}'."
        return 0
    fi

    if [ -n "$(git -C "$repo_dir" status --porcelain 2>/dev/null)" ]; then
        echo "❌ Branch switch FAILED: local changes present in ${repo_dir} - commit, stash, or" >&2
        echo "   discard them first (same dev-mode safety as self_update.sh)." >&2
        exit 1
    fi

    echo "🔄 Switching ${repo_dir} from '${current_branch:-detached HEAD}' to '${target_branch}' ..."
    if ! git -C "$repo_dir" fetch --quiet origin "$target_branch"; then
        echo "❌ Branch switch FAILED: 'git fetch origin ${target_branch}' did not succeed" >&2
        echo "   (branch doesn't exist on origin? no network?)." >&2
        exit 1
    fi

    if git -C "$repo_dir" show-ref --verify --quiet "refs/heads/${target_branch}"; then
        # Local branch already exists (e.g. switching back to one used
        # before) - just fast-forward it, same guarantee self_update.sh
        # gives for the branch you started on.
        if ! git -C "$repo_dir" checkout --quiet "$target_branch"; then
            echo "❌ Branch switch FAILED: 'git checkout ${target_branch}' did not succeed." >&2
            exit 1
        fi
        if ! git -C "$repo_dir" merge --ff-only --quiet "origin/${target_branch}"; then
            echo "❌ Branch switch FAILED: local '${target_branch}' has diverged from" >&2
            echo "   'origin/${target_branch}' (not a fast-forward). Resolve manually:" >&2
            echo "   cd ${repo_dir} && git status" >&2
            exit 1
        fi
    else
        if ! git -C "$repo_dir" checkout --quiet -t "origin/${target_branch}"; then
            echo "❌ Branch switch FAILED: 'git checkout -t origin/${target_branch}' did not" >&2
            echo "   succeed - does that branch exist on origin? Check the name and try again." >&2
            exit 1
        fi
    fi

    echo "✅ Branch: now on '${target_branch}' (up to date with origin)."
}
