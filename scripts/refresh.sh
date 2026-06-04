#!/usr/bin/env bash
# Refresh wrapper — LaunchAgent entry point.
#
# Production launchd jobs are ET-aware through scripts/refresh-if-et-time.sh:
#   · Mon–Fri 4:00pm ET — data/dashboard refresh, Supabase sync, Atlas rebuild.
#   · Mon–Fri 4:05pm ET — force brief regeneration from fresh data, dashboard
#     rerender, Supabase latest sync, Atlas rebuild.
#
# Delegates boilerplate to ~/ops/lib/cron-wrapper.sh:
#   - git pull, status.json emission, commit/push, operator/engineer handoff.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."   # repo root

REFRESH_MODE=data
case "${1:-}" in
    "") ;;
    --briefs-only) REFRESH_MODE=briefs ;;
    *) echo "usage: $0 [--briefs-only]" >&2; exit 64 ;;
esac

PROJECT_NAME=macro-framework
LAUNCHD_LOG="$PWD/.cache/launchd-refresh-daily.log"
COMMIT_AUTHOR_NAME="Mac mini refresh"
COMMIT_AUTHOR_EMAIL="refresh@macro-framework.local"
SUCCESS_SUMMARY="refresh ok (data/dashboard + supabase sync)"
PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
SYNC_LOG="${SYNC_LOG:-$PWD/.cache/supabase-sync.log}"

if [[ "$REFRESH_MODE" == "briefs" ]]; then
    LAUNCHD_LOG="$PWD/.cache/launchd-refresh.log"
    SUCCESS_SUMMARY="refresh ok (briefs + dashboard + supabase sync)"
fi

source "$HOME/ops/lib/cron-wrapper.sh"

cron_wrapper_pull

if [[ "$REFRESH_MODE" == "briefs" ]]; then
    "$PYTHON_BIN" -m macro_framework.weekly_briefs --force
    "$PYTHON_BIN" -m macro_framework.build --skip-briefs
else
    "$PYTHON_BIN" -m macro_framework.build --no-cache --skip-briefs
fi

SUPABASE_SYNC_STATUS=0
"$PYTHON_BIN" -m macro_framework.sync_to_supabase latest >"$SYNC_LOG" 2>&1 || SUPABASE_SYNC_STATUS=$?
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

# Write status.json before rendering the Atlas so its "Last run" pill reflects
# THIS run, not the previous one. The EXIT trap will rewrite the same content
# on success, or overwrite with a fail status if anything below aborts.
python3 "$HOME/ops/lib/write_status.py" \
    --project "$PROJECT_NAME" --out "$PWD/.cache/status.json" \
    --start-ts "$_CRON_WRAPPER_START_TS" \
    --duration-sec "$(( $(date +%s) - _CRON_WRAPPER_START_EPOCH ))" \
    --status ok --summary "$SUCCESS_SUMMARY"

"$PYTHON_BIN" -m macro_framework.build_index_page

cron_wrapper_commit_outputs \
    briefs/ \
    docs/index.html \
    outputs/dashboard.html \
    snapshots/ \
    -- "refresh $(date -u +%FT%TZ)"
