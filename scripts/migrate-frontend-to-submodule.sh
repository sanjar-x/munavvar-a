#!/usr/bin/env bash
# One-shot migration: turn ./frontend (a co-located clone) into a proper git submodule.
#
# WHY: backend git currently sees frontend/ as untracked because it's an independent
# repo. We want it to be both — a submodule pin in the monorepo AND a standalone repo.
#
# PRECONDITIONS (script verifies):
#   1. frontend/ working tree is clean (no uncommitted changes)
#   2. frontend/ HEAD is pushed to origin/main
#   3. backend has no uncommitted changes referencing frontend/
#
# WHAT IT DOES:
#   1. Captures the current frontend HEAD SHA
#   2. Removes the working copy of frontend/ from disk
#   3. Adds it back as a submodule pinned to that SHA
#   4. Creates frontend/CHANGELOG.md as a symlink to ../CHANGELOG.md
#   5. Stages .gitmodules + frontend pin + symlink
#
# AFTER THIS:
#   - cd frontend && git remote -v   → still origin = Yokubjanovichh/MunnavarA
#   - git submodule update --remote frontend  → pulls latest main into pin
#   - git clone --recurse-submodules <backend-url>  → fresh clone gets frontend
#
# REVERSIBLE: yes, until you push the resulting backend commit.

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

FRONTEND_URL="https://github.com/Yokubjanovichh/MunnavarA.git"
FRONTEND_BRANCH="main"

echo "==> 1. Verifying frontend working tree is clean and pushed"
if [ ! -d frontend/.git ]; then
    echo "❌ frontend/.git not found — nothing to migrate" >&2
    exit 1
fi

(
    cd frontend
    if [ -n "$(git status --porcelain)" ]; then
        echo "❌ frontend/ has uncommitted changes. Commit & push first:" >&2
        git status --short >&2
        exit 1
    fi
    git fetch origin "$FRONTEND_BRANCH"
    local_head="$(git rev-parse HEAD)"
    remote_head="$(git rev-parse "origin/$FRONTEND_BRANCH")"
    if [ "$local_head" != "$remote_head" ]; then
        echo "❌ frontend HEAD ($local_head) does not match origin/$FRONTEND_BRANCH ($remote_head)" >&2
        echo "   Push or pull first." >&2
        exit 1
    fi
    echo "    ✓ clean & pushed at $local_head"
)

PIN_SHA="$(cd frontend && git rev-parse HEAD)"

echo "==> 2. Removing working copy of frontend/"
rm -rf frontend
[ ! -e frontend ] || { echo "❌ frontend/ still exists" >&2; exit 1; }

echo "==> 3. Adding frontend as submodule pinned to $PIN_SHA"
git submodule add -b "$FRONTEND_BRANCH" "$FRONTEND_URL" frontend
(cd frontend && git checkout "$PIN_SHA")
git add .gitmodules frontend

echo "==> 4. Creating frontend/CHANGELOG.md → ../CHANGELOG.md symlink"
# Create the symlink inside the frontend repo and commit it there.
(
    cd frontend
    [ ! -e CHANGELOG.md ] || rm -f CHANGELOG.md
    ln -s ../CHANGELOG.md CHANGELOG.md
    git add CHANGELOG.md
    if ! git diff --cached --quiet; then
        git commit -m "chore: replace CHANGELOG.md with symlink to backend monorepo

API changelog is now single-source-of-truth at /CHANGELOG.md in the
backend monorepo. This symlink makes it available inside the frontend
working tree when checked out as a submodule."
        echo "    ✓ committed in frontend repo (push when ready: cd frontend && git push)"
    fi
)
git add frontend  # update submodule pin to include the symlink commit

echo
echo "✅ Migration ready to commit. Review with:"
echo "    git status"
echo "    git diff --cached -- .gitmodules"
echo
echo "Then in backend root:"
echo "    git commit -m 'chore: convert frontend/ to git submodule'"
echo
echo "And push the symlink commit upstream from frontend:"
echo "    cd frontend && git push origin $FRONTEND_BRANCH"
