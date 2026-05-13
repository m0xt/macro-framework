#!/usr/bin/env bash
# Refresh wrapper for the Mac mini LaunchAgents.
#
# Runs twice on weekdays — see scripts/com.milkroad.macro-refresh{,-daily}.plist:
#   · Tuesday 11:00 Prague — weekly run timed before the 15:00 macro meeting.
#     Triggers fresh AI brief generation (the freshness check in
#     generate_commentary.py only regenerates on Tuesdays).
#   · Mon–Fri 22:30 Prague — daily end-of-US-close run. Refreshes data + snapshot
#     + Supabase row + dashboard; the brief freshness check skips regen on
#     non-Tuesdays, so this is purely data refresh.
#
# Steps:
#   1. git pull (incorporate edits the MacBook pushed)
#   2. build.py --no-cache (fresh Yahoo/FRED → snapshot + briefs-if-stale + legacy dashboard)
#   3. build_v2.py (renders the v2 dashboard from the fresh snapshot)
#   4. sync_to_supabase.py latest (push today's snapshot to the website DB)
#   5. git commit + push the new outputs (briefs/, dashboard_v2.html, snapshots/)
#   6. emit .cache/status.json and hand off to the Operator agent (~/ops)
#      via an EXIT trap so we always report, even when set -e aborts above.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

LAUNCHD_LOG="$REPO/.cache/launchd-refresh-daily.log"
STATUS_FILE="$REPO/.cache/status.json"

START_EPOCH=$(date +%s)
START_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

emit_status_and_handoff() {
    local exit_code=$?
    set +e
    local duration=$(( $(date +%s) - START_EPOCH ))
    local ws="$HOME/ops/lib/write_status.py"
    if [[ ! -x "$ws" ]]; then
        echo "WARN: $ws not found; skipping operator handoff"
        return
    fi
    mkdir -p "$(dirname "$STATUS_FILE")"
    if [[ $exit_code -eq 0 ]]; then
        python3 "$ws" \
            --project macro-framework --out "$STATUS_FILE" \
            --start-ts "$START_TS" --duration-sec "$duration" \
            --status ok \
            --summary "refresh ok (build + build_v2 + supabase sync)"
    else
        python3 "$ws" \
            --project macro-framework --out "$STATUS_FILE" \
            --start-ts "$START_TS" --duration-sec "$duration" \
            --status fail \
            --summary "refresh script exited $exit_code" \
            --error-type "script-nonzero-exit" \
            --error-message "scripts/refresh.sh exited with code $exit_code" \
            --error-tail-file "$LAUNCHD_LOG"
    fi
    "$HOME/ops/bin/operator-check" macro-framework || true
}
trap emit_status_and_handoff EXIT

echo "=== refresh: $(date -u +%FT%TZ) ==="

git pull --ff-only --quiet || echo "WARN: git pull failed — proceeding with local copy"

.venv/bin/python build.py --no-cache
.venv/bin/python build_v2.py

# Push today's snapshot to Supabase so the website can read it.
# Requires SUPABASE_URL + SUPABASE_SERVICE_KEY in .env (see README).
# Re-running same-day is idempotent — upsert overwrites the same row.
.venv/bin/python sync_to_supabase.py latest

# Stage only the persistent outputs (gitignore whitelists these).
git add briefs/ .cache/dashboard_v2.html .cache/snapshots/ 2>/dev/null || true

if git diff --cached --quiet; then
  echo "no output changes to commit"
else
  git -c user.name="Mac mini refresh" -c user.email="refresh@macro-framework.local" \
      commit -m "refresh $(date -u +%FT%TZ)"
  git push --quiet || echo "WARN: git push failed — outputs committed locally"
fi
