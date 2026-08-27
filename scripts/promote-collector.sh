#!/usr/bin/env bash
# DM3.2 — Promote a reviewed ref into the COLLECTOR's production checkout.
#
# WHY THIS EXISTS
# ---------------
# The Mac collector used to run from ~/Projects/deadman/.venv, whose install was
# EDITABLE (__editable__.deadman-0.1.0.pth -> ~/Projects/deadman/src). So the
# collector executed whatever branch the dev checkout happened to be standing
# on: `git checkout` was a production deploy, silently, with no signal.
#
# Found while shipping DM3.1 (2026-08-27): the probe fix appeared live only
# because the checkout was still on the fix branch. Switching branches would
# have reverted the outside watcher to crashing code and told nobody.
#
# Third instance of the same shape in this estate:
#   1. kai-studio devpost series lived inside the checkout; every promote reset
#      it — "six green cron runs, one surviving row" (HACKRUN.3).
#   2. kai-studio prod venv was editable against the DEV checkout;
#      run-devpost.sh failed for weeks (fixed 2026-08-21).
#   3. this one — and it watches everything else.
#
# Deliberately mirrors kai-studio's scripts/promote-prod.sh rather than
# inventing a second pattern: separate clone, detached HEAD at an explicit
# pinned commit, promotion always deliberate, nothing here runs on a schedule.
#
#   scripts/promote-collector.sh <ref>        promote to <ref> (branch/tag/sha)
#   scripts/promote-collector.sh --status     what the collector is running
#   scripts/promote-collector.sh --rollback   return to the previous ref
#
# The install is NON-editable on purpose: the prod venv holds its own copy of
# the code, so no .pth can reach back into any working tree.

set -euo pipefail

PROD="${COLLECTOR_CHECKOUT:-$HOME/prod/deadman}"
STATE="${HOME}/.config/deadman/collector-previous-ref"
VENV="$PROD/.venv"

[ -d "$PROD/.git" ] || {
    echo "no collector checkout at $PROD" >&2
    echo "bootstrap: git clone <origin> $PROD && python3 -m venv $VENV" >&2
    exit 1
}
cd "$PROD"

reinstall() {
    # NON-editable, and --force-reinstall so a same-version rebuild still picks
    # up new code. An editable install here would recreate the exact bug this
    # script exists to prevent.
    "$VENV/bin/pip" install --quiet --force-reinstall --no-deps . >/dev/null
    # Fail closed: if an editable install somehow survives, stop rather than
    # leave the collector reading a working tree again.
    if ls "$VENV"/lib/python*/site-packages/__editable__* >/dev/null 2>&1; then
        echo "REFUSING: prod venv contains an editable install after reinstall" >&2
        exit 1
    fi
}

case "${1:-}" in
    --status)
        echo "collector checkout: $PROD"
        echo "pinned at:          $(git rev-parse --short HEAD)"
        git --no-pager log --oneline -1
        if ls "$VENV"/lib/python*/site-packages/__editable__* >/dev/null 2>&1; then
            echo "install:            ⚠ EDITABLE — the bug this script prevents"
        else
            echo "install:            non-editable (correct)"
        fi
        [ -f "$STATE" ] && echo "previous ref:       $(cat "$STATE")"
        exit 0
        ;;
    --rollback)
        [ -f "$STATE" ] || {
            echo "no previous ref recorded; nothing to roll back to" >&2
            exit 1
        }
        TARGET="$(cat "$STATE")"
        ;;
    "")
        echo "usage: promote-collector.sh <ref> | --status | --rollback" >&2
        exit 2
        ;;
    *)
        TARGET="$1"
        ;;
esac

BEFORE="$(git rev-parse HEAD)"

git fetch --quiet origin
RESOLVED="$(git rev-parse --verify --quiet "origin/${TARGET}^{commit}" ||
    git rev-parse --verify --quiet "${TARGET}^{commit}")" ||
    {
        echo "cannot resolve ref: $TARGET" >&2
        exit 1
    }

# Record where we came from BEFORE moving, so --rollback is always available.
mkdir -p "$(dirname "$STATE")"
echo "$BEFORE" > "$STATE"

git checkout --quiet --force --detach "$RESOLVED"
reinstall

echo "collector promoted: $(git rev-parse --short "$BEFORE") -> $(git rev-parse --short HEAD)"
git --no-pager log --oneline -1
echo
echo "if this was wrong: scripts/promote-collector.sh --rollback"
echo "the launchd job picks this up on its next run; no reload needed."
