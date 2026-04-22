#!/bin/zsh
# Daily macro dashboard refresh — runs build.py then asks Claude to write commentary.
# Add to cron: 0 18 * * 1-5 /Users/max/Projects/macro-framework/daily_refresh.sh

set -e
cd /Users/max/Projects/macro-framework

CLAUDE=/Users/max/.local/bin/claude
LOG=.cache/daily_refresh.log

mkdir -p .cache
echo "$(date): starting refresh" >> "$LOG"

# 1. Fetch fresh data + save snapshot
.venv/bin/python build.py >> "$LOG" 2>&1

# 2. Ask Claude to write commentary (uses subscription, no API key needed)
$CLAUDE --allowedTools "WebSearch,Read,Write" -p "
You are maintaining the daily brief for a macro dashboard at /Users/max/Projects/macro-framework.

Read the latest snapshot from .cache/snapshots/ (the most recent JSON file by date).
Also read the previous snapshot to compute 1-day changes.

Then search the web for today's most important macro market developments — Fed, rates,
credit spreads, equities, crypto, key economic releases.

Write a 5–7 sentence commentary in flowing prose (no bullets) that connects our
framework signal readings to what is actually happening in markets. Style: clear,
direct, no fluff. Lead with the most important observation. Include inline markdown
links to sources where relevant.

Save the result to .cache/brief_commentary.md in this exact format:
date: YYYY-MM-DD

[commentary text]

Sources: [Name](url) · [Name](url)

Use today's actual date for YYYY-MM-DD.
" >> "$LOG" 2>&1

# 3. Rebuild to inject the fresh commentary into the dashboard
.venv/bin/python build.py >> "$LOG" 2>&1

echo "$(date): done" >> "$LOG"
