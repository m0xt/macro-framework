#!/usr/bin/env bash
# Refresh wrapper — LaunchAgent entry point.
#
# Runs twice on weekdays — see scripts/com.milkroad.macro-refresh{,-daily}.plist:
#   · Tuesday 11:00 Prague — weekly run timed before the 15:00 macro meeting.
#     Triggers fresh AI brief generation (the freshness check in
#     weekly_briefs.py only regenerates on Tuesdays).
#   · Mon–Fri 22:30 Prague — daily end-of-US-close run. Refreshes data + snapshot
#     + Supabase row + dashboard; the brief freshness check skips regen on
#     non-Tuesdays, so this is purely data refresh.
#
# Delegates boilerplate to ~/ops/lib/cron-wrapper.sh:
#   - git pull, status.json emission, commit/push, operator/engineer handoff.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."   # repo root

PROJECT_NAME=macro-framework
LAUNCHD_LOG="$PWD/.cache/launchd-refresh-daily.log"   # matches both plists' StandardOutPath
COMMIT_AUTHOR_NAME="Mac mini refresh"
COMMIT_AUTHOR_EMAIL="refresh@macro-framework.local"
SUCCESS_SUMMARY="refresh ok (build + supabase sync)"
PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
SYNC_LOG="${SYNC_LOG:-$PWD/.cache/supabase-sync.log}"

source "$HOME/ops/lib/cron-wrapper.sh"

cron_wrapper_pull
"$PYTHON_BIN" build.py --no-cache

SUPABASE_SYNC_STATUS=0
"$PYTHON_BIN" sync_to_supabase.py latest >"$SYNC_LOG" 2>&1 || SUPABASE_SYNC_STATUS=$?
if [[ $SUPABASE_SYNC_STATUS -ne 0 ]]; then
    case "$SUPABASE_SYNC_STATUS" in
        20) SUPABASE_FAILURE_TYPE="supabase-auth" ;;
        21) SUPABASE_FAILURE_TYPE="supabase-network" ;;
        22) SUPABASE_FAILURE_TYPE="supabase-schema-drift" ;;
        *)  SUPABASE_FAILURE_TYPE="supabase-network" ;;
    esac
    echo "WARN: supabase sync failed ($SUPABASE_FAILURE_TYPE); local dashboard/snapshot commit will continue" >&2
    tail -50 "$SYNC_LOG" >&2 || true
    SUCCESS_SUMMARY="refresh ok, supabase sync failed ($SUPABASE_FAILURE_TYPE)"
else
    cat "$SYNC_LOG"
fi

cron_wrapper_commit_outputs \
    briefs/ \
    .cache/dashboard.html \
    .cache/snapshots/ \
    -- "refresh $(date -u +%FT%TZ)"
