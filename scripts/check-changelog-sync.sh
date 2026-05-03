#!/bin/sh
# Pre-commit guard: API-changing files must be accompanied by a CHANGELOG.md edit.
#
# Triggers on staged changes in:
#   - src/api/v1/**            (HTTP routes / response shapes)
#   - src/modules/*/schemas.py (request / response Pydantic models)
#   - src/modules/*/enums.py   (string enum values are part of the contract)
#   - alembic/versions/*.py    (DB schema may surface in API responses)
#
# Also verifies that frontend/CHANGELOG.md is a symlink to ../CHANGELOG.md
# (so the frontend submodule sees the same file).

set -e

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# 1. Symlink integrity — only checked once frontend/ is a real git submodule
#    (until migrate-frontend-to-submodule.sh has been run, frontend/ is an
#    independent repo and its CHANGELOG.md is its own concern).
if [ -f .gitmodules ] && grep -q 'path = frontend' .gitmodules; then
    if [ -e frontend/CHANGELOG.md ]; then
        if [ ! -L frontend/CHANGELOG.md ]; then
            echo "❌ frontend/CHANGELOG.md must be a symlink to ../CHANGELOG.md" >&2
            echo "   Run inside frontend/: ln -sf ../CHANGELOG.md CHANGELOG.md" >&2
            exit 1
        fi
        target="$(readlink frontend/CHANGELOG.md)"
        if [ "$target" != "../CHANGELOG.md" ]; then
            echo "❌ frontend/CHANGELOG.md points to '$target', expected '../CHANGELOG.md'" >&2
            exit 1
        fi
    fi
fi

# 2. Contract-changing files in this commit?
contract_changes="$(git diff --cached --name-only --diff-filter=ACMR \
    | grep -E '^(src/api/v1/.*\.py|src/modules/[^/]+/(schemas|enums)\.py|alembic/versions/.*\.py)$' || true)"

if [ -z "$contract_changes" ]; then
    exit 0
fi

# 3. Was CHANGELOG.md updated in the same commit?
changelog_updated="$(git diff --cached --name-only --diff-filter=ACMR \
    | grep -E '^CHANGELOG\.md$' || true)"

if [ -z "$changelog_updated" ]; then
    echo "❌ Public-contract changes detected without CHANGELOG.md update:" >&2
    echo "$contract_changes" | sed 's/^/    /' >&2
    echo "" >&2
    echo "   Add an [Unreleased] entry in /CHANGELOG.md describing the change." >&2
    echo "   Bypass (only if change is truly internal): git commit --no-verify" >&2
    exit 1
fi

exit 0
