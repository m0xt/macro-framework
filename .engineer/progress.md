# Engineer progress — macro-framework

Append a structured entry at the bottom on every dispatch. Format:

```
## <UTC timestamp> — <short title>
- What: <1-2 line summary>
- Files touched: <list>
- Commit: <SHA or "none">
- Status: completed | partial | blocked
- Open thread for next dispatch: <if any, else "none">
```

Keep entries terse — this file is read by every stateless dispatch.

## 2026-05-18T08:29:14Z — LAN dashboard serve
- What: Added launchd-backed static HTTP serve for outputs/dashboard.html on 0.0.0.0:8001 and documented the LAN URL.
- Files touched: AGENTS.md; scripts/com.milkroad.macro-framework-serve.plist; .engineer/progress.md
- Commit: pending (this commit)
- Status: completed
- Open thread for next dispatch: Bob 13b webloc delivery after serve verification
