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

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

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
