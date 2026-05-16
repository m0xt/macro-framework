# Retention runbook

This project keeps `.cache/` local-only. Durable generated artifacts live outside cache:

- `outputs/dashboard.html` — latest deliverable, overwritten every build.
- `snapshots/YYYY-MM-DD.json` — daily point-in-time history for dashboard review and Supabase backfill.
- `snapshots-monthly/YYYY-MM.json` — future compacted month-end snapshots.
- `briefs/YYYY-MM-DD/*.md` — weekly Claude brief archive.
- `reports/` — tracked shareable report artifacts; final home deferred.

## Current policy

- Keep the last 90 days at daily granularity in `snapshots/`.
- Compact older daily snapshots to `snapshots-monthly/YYYY-MM.json` using the month-end value, or the latest available snapshot in that month if month-end is absent.
- Archive snapshots older than one year to a separate `archive` branch.
- Do not compact automatically in `scripts/refresh.sh` yet. The current snapshot set is well under 90 days.

## Manual compaction procedure

Only run this during a dedicated retention dispatch.

1. Confirm the repo is clean:
   ```bash
   cd ~/projects/macro-framework
   git status --short
   ```
2. List daily snapshots older than 90 days:
   ```bash
   python - <<'PY'
from datetime import date, timedelta
from pathlib import Path
cutoff = date.today() - timedelta(days=90)
for p in sorted(Path('snapshots').glob('*.json')):
    d = date.fromisoformat(p.stem)
    if d < cutoff:
        print(p)
PY
   ```
3. For each older month, copy the latest daily snapshot in that month to `snapshots-monthly/YYYY-MM.json`:
   ```bash
   mkdir -p snapshots-monthly
   python - <<'PY'
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
import shutil
cutoff = date.today() - timedelta(days=90)
by_month = defaultdict(list)
for p in sorted(Path('snapshots').glob('*.json')):
    d = date.fromisoformat(p.stem)
    if d < cutoff:
        by_month[p.stem[:7]].append(p)
for month, files in sorted(by_month.items()):
    src = files[-1]
    dst = Path('snapshots-monthly') / f'{month}.json'
    shutil.copy2(src, dst)
    print(f'{src} -> {dst}')
PY
   ```
4. Verify Supabase backfill still sees daily snapshots needed for any requested backfill window. Do not delete dailies if an operational backfill still depends on them.
5. Remove compacted daily files from `snapshots/` only after monthly copies exist:
   ```bash
   git status --short
   # use git rm snapshots/YYYY-MM-DD.json for the compacted daily files
   ```
6. Run:
   ```bash
   uv run pytest
   uv run ruff check .
   ```
7. Commit the compaction with a clear date range in the body.

## One-year archive branch procedure

Archive is intentionally manual until the retention compactor is implemented.

1. Create/update a local archive work branch from `main`:
   ```bash
   git fetch origin
   git switch -c archive/snapshots-$(date +%Y) origin/main
   ```
2. Keep the old snapshots that should leave `main` on that branch.
3. Push the branch:
   ```bash
   git push origin HEAD
   ```
4. Return to `main`, remove the archived files from `main`, and commit the removal.
5. Record the archive branch name in `DECISIONS.md` or the compaction commit body.

## Safety checks

- Never compact or delete the current 90-day window.
- Never compact during an unrelated math, Supabase, or docs dispatch.
- If `sync_to_supabase.py backfill` needs older daily granularity, postpone deletion and document the blocker.
