# Monthly report tools

Supported manual workflow for the shareable monthly macro report. This is not part of `scripts/refresh.sh` and does not affect the daily dashboard cron path.

## Inputs

- `.cache/macro_update_*.md` — transient report markdown draft, gitignored.
- `.cache/charts/` — generated chart images, gitignored.
- Current cached/fetched macro data via the root pipeline modules.

## Commands

From repo root:

```bash
uv run python report/generate_report_charts.py
uv run python report/build_report.py
```

`generate_report_charts.py` writes chart PNGs under `.cache/charts/`.

`build_report.py` reads the newest `.cache/macro_update_*.md` and writes HTML under `reports/`, for example `reports/macro_update_2026_05.html`.

## Output policy

- `.cache/macro_update_*.md`, `.cache/macro_update_*.html`, and `.cache/charts/` are transient local inputs/working files.
- `reports/macro_update_*.html` is a tracked shareable artifact for now; see `DECISIONS.md`.
