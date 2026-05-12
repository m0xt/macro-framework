#!/usr/bin/env bash
# Tuesday refresh wrapper for the Mac mini LaunchAgent.
#   1. git pull (so we incorporate any edits the MacBook pushed)
#   2. build.py --no-cache (fresh Yahoo/FRED → snapshot + briefs + legacy dashboard)
#   3. build_v2.py (renders the v2 dashboard from the fresh snapshot)
#   4. sync_to_supabase.py latest (push today's snapshot to the website DB)
#   5. git commit + push the new outputs (briefs/, dashboard_v2.html, snapshots/)

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

echo "=== tuesday refresh: $(date -u +%FT%TZ) ==="

git pull --ff-only --quiet || echo "WARN: git pull failed — proceeding with local copy"

.venv/bin/python build.py --no-cache
.venv/bin/python build_v2.py

# Push today's snapshot to Supabase so the website can read it.
# Requires SUPABASE_URL + SUPABASE_SERVICE_KEY in .env (see README).
.venv/bin/python sync_to_supabase.py latest

# Stage only the persistent outputs (gitignore whitelists these).
git add briefs/ .cache/dashboard_v2.html .cache/snapshots/ 2>/dev/null || true

if git diff --cached --quiet; then
  echo "no output changes to commit"
else
  git -c user.name="Mac mini tuesday" -c user.email="tuesday@macro-framework.local" \
      commit -m "tuesday refresh $(date -u +%F)"
  git push --quiet || echo "WARN: git push failed — outputs committed locally"
fi
