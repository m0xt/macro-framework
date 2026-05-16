# Decisions

## 2026-05-15 — MRMI parameter reconciliation follows production code
Reason: `macro_pipeline.py` has used Sector Breadth `LOOKBACK = 90` since commit `9f124cf` with the inline provenance "optimized for drawdown: was 63 (originally 252)." README/CLAUDE/GUIDE still said 63, and no newer reproducible research result supported reverting production math. We kept the production value, updated docs only, and locked the documented parameters in tests.
