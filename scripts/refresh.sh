#!/usr/bin/env bash
# Refresh wrapper — LaunchAgent entry point.
#
# Runs twice on weekdays — see scripts/com.milkroad.macro-refresh{,-daily}.plist:
#   · Tuesday 11:00 Prague — weekly run timed before the 15:00 macro meeting.
#     Triggers fresh AI brief generation (the freshness check in
#     generate_commentary.py only regenerates on Tuesdays).
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
SUCCESS_SUMMARY="refresh ok (build + build_v2 + supabase sync)"

source "$HOME/ops/lib/cron-wrapper.sh"

cron_wrapper_pull
.venv/bin/python build.py --no-cache
.venv/bin/python build_v2.py
.venv/bin/python sync_to_supabase.py latest
cron_wrapper_commit_outputs \
    briefs/ \
    .cache/dashboard_v2.html \
    .cache/snapshots/ \
    -- "refresh $(date -u +%FT%TZ)"
