#!/usr/bin/env python3
"""Render docs/index.html for macro-framework's iteration surface.

The page is intentionally static and dependency-free. It imports the live
indicator constants, prompt text, and dashboard metadata from the production
modules so docs/index.html stays a view of the current system instead of a
second hand-maintained spec.
"""

from __future__ import annotations

import html
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from macro_framework import weekly_briefs
from macro_framework.build import build_library_indicators
from macro_framework.macro_pipeline import (
    FRED_SERIES,
    GROWTH_IMPULSE_CLIP_Z,
    GROWTH_IMPULSE_EMA_LEN,
    GROWTH_IMPULSE_FAST_ROC,
    GROWTH_IMPULSE_SLOW_ROC,
    GROWTH_IMPULSE_SPECS,
    GROWTH_IMPULSE_Z_LEN,
    MMI_DRIVER_SPECS,
    MMI_DRIVER_WEIGHTS,
    MRMI_POSTURE_BANDS,
    NON_FRED_SERIES,
    RELEASE_LAGS_DAYS,
    SECTOR_BREADTH_LOOKBACK,
    SECTOR_BREADTH_RECONCILIATION_NOTE,
    UNIFIED_STRESS_ALPHA,
    UNIFIED_STRESS_BETA,
    UNIFIED_STRESS_BUFFER_SIZE,
    UNIFIED_STRESS_LAMBDA,
    UNIFIED_STRESS_P99,
    UNIFIED_STRESS_THRESHOLD,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_FILE = REPO_ROOT / "docs" / "index.html"
STATUS_FILE = REPO_ROOT / ".cache" / "status.json"

SOURCE_MACRO_PIPELINE = "src/macro_framework/macro_pipeline.py"
SOURCE_BUILD = "src/macro_framework/build.py"
SOURCE_WEEKLY_BRIEFS = "src/macro_framework/weekly_briefs.py"
SOURCE_ARCHITECTURE = "docs/architecture.md"
SOURCE_TESTS = "tests/test_smoke.py"


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _run_git(args: list[str]) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return None


def github_repo_url() -> str:
    remote = _run_git(["remote", "get-url", "origin"]) or "git@github.com:m0xt/macro-framework.git"
    if remote.startswith("git@github.com:"):
        slug = remote.removeprefix("git@github.com:").removesuffix(".git")
        return f"https://github.com/{slug}"
    if remote.startswith("https://github.com/"):
        return remote.removesuffix(".git")
    return "https://github.com/m0xt/macro-framework"


def suggest_link(path: str) -> str:
    return f"{github_repo_url()}/edit/main/{path}"


def _load_status() -> dict[str, Any]:
    if not STATUS_FILE.exists():
        return {"last_run": "—", "status": "missing", "summary": "status.json not found", "error": "—"}
    try:
        status = json.loads(STATUS_FILE.read_text())
    except json.JSONDecodeError as exc:
        return {"last_run": "—", "status": "invalid", "summary": "status.json parse failed", "error": str(exc)}
    error = status.get("error")
    if isinstance(error, dict):
        error_text = error.get("message") or error.get("type") or json.dumps(error, sort_keys=True)
    else:
        error_text = error or "none"
    return {
        "last_run": status.get("last_run") or "—",
        "status": status.get("status") or "—",
        "summary": status.get("summary") or "—",
        "error": error_text,
    }


def _last_commit() -> str:
    return _run_git(["log", "-1", "--format=%h %s"]) or "—"


def pill(text: str) -> str:
    return f'<span class="pill">{esc(text)}</span>'


def source_link(path: str, label: str | None = None) -> str:
    label = label or Path(path).name
    return (
        f'<a class="suggest" href="{esc(suggest_link(path))}" target="_blank" '
        f'rel="noreferrer">Suggest edit → {esc(label)}</a>'
    )


def render_metric(label: str, value: str, note: str = "") -> str:
    return f"""
      <div class="metric">
        <div class="metric-label">{esc(label)}</div>
        <div class="metric-value">{esc(value)}</div>
        <div class="metric-note">{esc(note)}</div>
      </div>"""


def render_table(headers: list[str], rows: list[list[Any]]) -> str:
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def code_block(text: str) -> str:
    return f"<pre><code>{esc(text)}</code></pre>"


def render_mrmi_card() -> str:
    formula = "MRMI = MMI + buffer_size × (1 − stress_norm) − threshold"
    constants = [
        render_metric("buffer_size", f"{UNIFIED_STRESS_BUFFER_SIZE:.1f}", "Macro buffer when stress is zero."),
        render_metric("threshold", f"{UNIFIED_STRESS_THRESHOLD:.2f}", "Action threshold subtracted from raw MMI + buffer."),
        render_metric("stress_p99", f"{UNIFIED_STRESS_P99:.4f}", "Normalizes stress_raw before clipping to [0, 1]."),
        render_metric("stress α / β / λ", f"{UNIFIED_STRESS_ALPHA:.2f} / {UNIFIED_STRESS_BETA:.2f} / {UNIFIED_STRESS_LAMBDA:.1f}", "Growth weakness, inflation pressure, and interaction coefficients."),
    ]
    posture_rows = [
        [
            esc(band["label"]),
            f"<code>{esc(band['range'])}</code>",
            esc(f"{band['exposure']:.0%}"),
            esc(band["rationale"]),
        ]
        for band in MRMI_POSTURE_BANDS
    ]
    return f"""
      <article class="card" style="--accent: #38bdf8">
        <div class="card-top"><div><h2>MRMI formula <span>🧮</span></h2><p>Headline allocation posture math and constants imported from <code>{SOURCE_MACRO_PIPELINE}</code>.</p></div><div class="shortcut">M</div></div>
        {source_link(SOURCE_MACRO_PIPELINE, "macro_pipeline.py")}
        <div class="card-body">
          <div class="formula"><code>{esc(formula)}</code></div>
          <div class="metrics">{''.join(constants)}</div>
          <p class="hint">stress_raw = α·growth_weakness + β·inflation_pressure + λ·growth_weakness·inflation_pressure; stress_norm = clip(stress_raw / stress_p99, 0, 1).</p>
          <details open><summary>Posture thresholds</summary>{render_table(["Band", "Range", "Exposure", "Rationale"], posture_rows)}</details>
        </div>
      </article>"""


def render_mmi_card() -> str:
    total = sum(MMI_DRIVER_WEIGHTS.values()) or 1.0
    rows = []
    for _key, spec in MMI_DRIVER_SPECS.items():
        rows.append([
            esc(spec["label"]),
            esc(f"{spec['weight'] / total:.0%}"),
            esc(spec["source"]),
            esc(spec["rationale"]),
        ])
    return f"""
      <article class="card" style="--accent: #f59e0b">
        <div class="card-top"><div><h2>MMI drivers <span>📈</span></h2><p>Market Momentum Index inputs and equal-weight construction.</p></div><div class="shortcut">D</div></div>
        {source_link(SOURCE_MACRO_PIPELINE, "macro_pipeline.py")}
        <div class="card-body">
          {render_table(["Driver", "Weight", "Source", "Rationale"], rows)}
          <p class="hint">MMI = equal-weight average of Growth Impulses fast leg, Sector Breadth, and Financial Conditions. Sector Breadth lookback = <code>{SECTOR_BREADTH_LOOKBACK}</code>. {esc(SECTOR_BREADTH_RECONCILIATION_NOTE)}</p>
        </div>
      </article>"""


def render_growth_card() -> str:
    rows = []
    for key, spec in GROWTH_IMPULSE_SPECS.items():
        rows.append([
            f"<code>{esc(key)}</code>",
            esc(spec["label"]),
            esc(spec["group"]),
            esc(spec["source"]),
            esc(spec["explanation"]),
        ])
    return f"""
      <article class="card wide" style="--accent: #22c55e">
        <div class="card-top"><div><h2>Growth Impulses inputs <span>🌱</span></h2><p>The same tooltip/rationale specs used by the dashboard drill-down rows.</p></div><div class="shortcut">G</div></div>
        {source_link(SOURCE_MACRO_PIPELINE, "macro_pipeline.py")}
        <div class="card-body">
          <div class="meta compact">
            {pill(f"fast ROC {GROWTH_IMPULSE_FAST_ROC}d")}
            {pill(f"slow ROC {GROWTH_IMPULSE_SLOW_ROC}d")}
            {pill(f"z lookback {GROWTH_IMPULSE_Z_LEN}d")}
            {pill(f"clip ±{GROWTH_IMPULSE_CLIP_Z:.1f}z")}
            {pill(f"EMA {GROWTH_IMPULSE_EMA_LEN}")}
          </div>
          <details open><summary>Inputs and rationale</summary>{render_table(["Key", "Input", "Group", "Source", "Why it matters"], rows)}</details>
        </div>
      </article>"""


def reference_library_metadata() -> dict[str, dict[str, Any]]:
    idx = pd.date_range("2026-01-01", periods=2, freq="D")
    columns = sorted(set(FRED_SERIES) | set(NON_FRED_SERIES))
    fixture = pd.DataFrame({col: [float("nan"), float("nan")] for col in columns}, index=idx)
    return build_library_indicators(fixture, idx)


def render_reference_card() -> str:
    library = reference_library_metadata()
    rows = []
    for key, item in library.items():
        rows.append([
            f"<code>{esc(key)}</code>",
            esc(item["label"]),
            esc(item["category"]),
            esc(item.get("notes") or "—"),
            esc(item.get("desc") or "—"),
        ])
    return f"""
      <article class="card wide" style="--accent: #a78bfa">
        <div class="card-top"><div><h2>Reference Library <span>📚</span></h2><p>Supplementary dashboard series, including CPI, PPI, ISM/PMI, labor, activity, and liquidity context.</p></div><div class="shortcut">R</div></div>
        {source_link(SOURCE_BUILD, "build.py")}
        <div class="card-body">
          <details open><summary>Series shown on the dashboard</summary>{render_table(["Key", "Series", "Category", "Notes", "Description"], rows)}</details>
        </div>
      </article>"""


def render_lags_card() -> str:
    labels = {
        "PCEC96": "Real PCE",
        "UNRATE": "Unemployment rate",
        "RPI": "Real Personal Income",
        "GDPNOW": "Atlanta Fed GDPNow",
        "CPILFESL": "Core CPI",
    }
    rows = [
        [f"<code>{esc(key)}</code>", esc(labels.get(key, key)), esc(f"{days}d")]
        for key, days in RELEASE_LAGS_DAYS.items()
    ]
    return f"""
      <article class="card" style="--accent: #14b8a6">
        <div class="card-top"><div><h2>Release lags <span>⏱️</span></h2><p>Publication-lag guardrails applied before macro context feeds MRMI.</p></div><div class="shortcut">L</div></div>
        {source_link(SOURCE_MACRO_PIPELINE, "macro_pipeline.py")}
        <a class="suggest secondary" href="{esc(suggest_link(SOURCE_TESTS))}" target="_blank" rel="noreferrer">Suggest edit → test locks</a>
        <div class="card-body">{render_table(["Series", "Meaning", "Lag"], rows)}</div>
      </article>"""


def render_briefs_card() -> str:
    prompt_sections = [
        ("Market SYSTEM", weekly_briefs.SYSTEM_MARKET),
        ("Economy SYSTEM", weekly_briefs.SYSTEM_ECONOMY),
        ("Top SYSTEM", weekly_briefs.SYSTEM_TOP),
        ("Pillar USER template", weekly_briefs.PILLAR_BRIEF_USER_TEMPLATE),
        ("Top USER template", weekly_briefs.TOP_BRIEF_USER_TEMPLATE),
    ]
    blocks = "".join(
        f"<details class=\"prompt-details\"><summary>{esc(title)}</summary>{code_block(text)}</details>"
        for title, text in prompt_sections
    )
    return f"""
      <article class="card wide" style="--accent: #ec4899">
        <div class="card-top"><div><h2>Weekly briefs <span>✍️</span></h2><p>Tuesday lazy cadence, model, and the exact prompts used for market / economy / top briefs.</p></div><div class="shortcut">B</div></div>
        {source_link(SOURCE_WEEKLY_BRIEFS, "weekly_briefs.py")}
        <div class="card-body">
          <div class="meta compact">
            {pill(f"model: {weekly_briefs.MODEL}")}
            {pill("cadence: first successful build on/after Tuesday")}
            {pill("outputs: market.md / economy.md / top.md")}
          </div>
          {blocks}
        </div>
      </article>"""


def render_flow_card() -> str:
    steps = [
        ("Fetch", "Yahoo/FRED/DBnomics data, then cache aligned raw inputs."),
        ("Compute", "Growth Impulses + Sector Breadth + Financial Conditions → MMI."),
        ("Stress", "Release-lagged real economy + inflation direction → 0–10 macro stress."),
        ("Posture", "MRMI combines MMI and stress-eroded macro buffer → LONG / CAUTION / CASH."),
        ("Publish", "Snapshot, dashboard, briefs, docs/index.html, then Supabase latest sync."),
    ]
    nodes = "".join(
        f"<div class=\"node\"><div class=\"role\">{esc(title)}</div><div class=\"desc\">{esc(desc)}</div></div>"
        for title, desc in steps
    )
    return f"""
      <section class="flow-card">
        <div>
          <div class="eyebrow">architecture / flow</div>
          <h2>What feeds what.</h2>
          <p class="intro small">A compact map of the pipeline. The narrative source stays in <code>{SOURCE_ARCHITECTURE}</code>; this page links it rather than replacing it.</p>
        </div>
        <a class="suggest flow-suggest" href="{esc(suggest_link(SOURCE_ARCHITECTURE))}" target="_blank" rel="noreferrer">Suggest edit → architecture.md</a>
        <div class="arch-row">{nodes}</div>
      </section>"""


def build_html(build_time: str | None = None) -> str:
    build_time = build_time or datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    status = _load_status()
    last_commit = _last_commit()
    cards = "\n".join([
        render_mrmi_card(),
        render_mmi_card(),
        render_lags_card(),
        render_growth_card(),
        render_reference_card(),
        render_briefs_card(),
    ])
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Macro Framework Iteration Surface</title>
<style>
  * {{ box-sizing: border-box; }}
  :root {{
    color-scheme: dark;
    --bg: #09090b;
    --panel: #111113;
    --panel-2: #17171a;
    --border: #2a2a2e;
    --text: #e4e4e7;
    --muted: #a1a1aa;
    --dim: #71717a;
    --code: #050506;
  }}
  body {{
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", Inter, system-ui, sans-serif;
    background:
      radial-gradient(circle at 20% 0%, rgba(56, 189, 248, 0.11), transparent 28rem),
      radial-gradient(circle at 90% 10%, rgba(245, 158, 11, 0.11), transparent 26rem),
      var(--bg);
    color: var(--text);
    line-height: 1.55;
  }}
  main {{ max-width: 1180px; margin: 0 auto; padding: 40px 22px 64px; }}
  header {{ margin-bottom: 28px; }}
  .eyebrow {{
    font-family: "SF Mono", ui-monospace, Menlo, Consolas, monospace;
    color: var(--dim);
    font-size: 12px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
  }}
  h1 {{ font-size: clamp(32px, 5vw, 58px); line-height: 1; margin: 10px 0 14px; letter-spacing: -0.04em; }}
  h2 {{ margin: 0 0 8px; font-size: 23px; letter-spacing: -0.02em; }}
  h2 span {{ font-size: 22px; }}
  .intro {{ max-width: 820px; color: var(--muted); font-size: 16px; }}
  .intro.small {{ max-width: 620px; font-size: 14px; margin: 0; }}
  .meta {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; }}
  .meta.compact {{ margin: 0 0 16px; }}
  .pill {{
    border: 1px solid var(--border);
    background: rgba(255,255,255,0.03);
    color: var(--muted);
    border-radius: 999px;
    padding: 5px 10px;
    font-family: "SF Mono", ui-monospace, Menlo, Consolas, monospace;
    font-size: 12px;
  }}
  .status-strip {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 22px 0 28px; }}
  .status-cell {{ border: 1px solid var(--border); border-radius: 14px; background: rgba(255,255,255,0.03); padding: 10px 12px; min-width: 0; }}
  .status-label {{ color: var(--dim); font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em; }}
  .status-value {{ color: var(--text); font-family: "SF Mono", ui-monospace, Menlo, Consolas, monospace; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .cards {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; align-items: start; }}
  .card, .flow-card {{
    border: 1px solid color-mix(in srgb, var(--accent, #38bdf8), var(--border) 66%);
    border-radius: 18px;
    background: linear-gradient(180deg, color-mix(in srgb, var(--accent, #38bdf8), transparent 90%), rgba(17,17,19,0.96));
    box-shadow: 0 20px 60px rgba(0,0,0,0.24);
    overflow: hidden;
  }}
  .card.wide {{ grid-column: span 3; }}
  .card-top {{ display: flex; justify-content: space-between; gap: 16px; padding: 20px; border-bottom: 1px solid rgba(255,255,255,0.07); }}
  .card p {{ margin: 0; color: var(--muted); font-size: 14px; }}
  .shortcut {{
    flex: 0 0 auto;
    align-self: start;
    border: 1px solid color-mix(in srgb, var(--accent), white 10%);
    background: color-mix(in srgb, var(--accent), transparent 82%);
    color: var(--text);
    border-radius: 12px;
    padding: 8px 10px;
    font-family: "SF Mono", ui-monospace, Menlo, Consolas, monospace;
    font-weight: 800;
    font-size: 20px;
  }}
  .suggest {{ display: block; padding: 12px 20px; color: var(--accent); text-decoration: none; font-size: 13px; border-bottom: 1px solid rgba(255,255,255,0.07); }}
  .suggest.secondary {{ color: var(--muted); }}
  .suggest:hover {{ background: rgba(255,255,255,0.035); }}
  .card-body {{ padding: 18px 20px 20px; }}
  .formula {{ padding: 14px; background: var(--code); border: 1px solid var(--border); border-radius: 12px; margin-bottom: 14px; }}
  .metrics {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-bottom: 12px; }}
  .metric {{ border: 1px solid rgba(255,255,255,0.07); border-radius: 12px; background: rgba(0,0,0,0.18); padding: 12px; }}
  .metric-label {{ color: var(--dim); font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em; }}
  .metric-value {{ font-family: "SF Mono", ui-monospace, Menlo, Consolas, monospace; font-size: 18px; font-weight: 800; }}
  .metric-note, .hint {{ color: var(--dim); font-size: 13px; }}
  details summary {{ cursor: pointer; user-select: none; font-weight: 700; color: var(--text); }}
  details[open] > summary {{ color: var(--accent); }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 13px; }}
  th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid rgba(255,255,255,0.07); vertical-align: top; }}
  th {{ color: var(--dim); font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase; }}
  pre {{ margin: 12px 0 0; padding: 14px; background: var(--code); border: 1px solid var(--border); border-radius: 12px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; }}
  code {{ font-family: "SF Mono", ui-monospace, Menlo, Consolas, monospace; font-size: 12px; line-height: 1.55; color: #d4d4d8; }}
  .prompt-details {{ border: 1px solid rgba(255,255,255,0.07); border-radius: 12px; padding: 12px; margin-top: 10px; background: rgba(0,0,0,0.18); }}
  .flow-card {{ --accent: #94a3b8; margin-bottom: 16px; padding: 20px; }}
  .flow-suggest {{ margin: 14px -20px 16px; }}
  .arch-row {{ display: flex; flex-wrap: wrap; align-items: stretch; gap: 12px; }}
  .node {{ border: 1px solid var(--border); border-radius: 12px; padding: 12px; min-width: 180px; flex: 1; background: var(--panel-2); }}
  .node .role {{ font-weight: 700; }}
  .node .desc {{ color: var(--muted); font-size: 12px; margin-top: 4px; }}
  footer {{ margin-top: 24px; color: var(--dim); font-size: 12px; }}
  footer code {{ color: var(--muted); }}
  @media (max-width: 940px) {{
    .cards, .status-strip {{ grid-template-columns: 1fr; }}
    .card.wide {{ grid-column: span 1; }}
    .metrics {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>
<main>
  <header>
    <div class="eyebrow">macro-framework / iteration surface</div>
    <h1>Inputs Martin can challenge.</h1>
    <p class="intro">A static, regenerated view of the framework's iterable inputs: MRMI math, posture thresholds, MMI drivers, component rationales, release lags, Reference Library series, and weekly-brief prompts. Values below are imported from production code at build time.</p>
    <div class="meta">
      {pill("feedback: formula")}
      {pill("feedback: thresholds")}
      {pill("feedback: drivers")}
      {pill("feedback: prompts")}
      {pill(f"built {build_time}")}
    </div>
  </header>

  <section class="status-strip">
    <div class="status-cell"><div class="status-label">Last run</div><div class="status-value" title="{esc(status['last_run'])}">{esc(status['last_run'])}</div></div>
    <div class="status-cell"><div class="status-label">Status</div><div class="status-value" title="{esc(status['summary'])}">{esc(status['status'])} · {esc(status['summary'])}</div></div>
    <div class="status-cell"><div class="status-label">Last commit</div><div class="status-value" title="{esc(last_commit)}">{esc(last_commit)}</div></div>
    <div class="status-cell"><div class="status-label">Last error</div><div class="status-value" title="{esc(status['error'])}">{esc(status['error'])}</div></div>
  </section>

  {render_flow_card()}

  <section class="cards">
    {cards}
  </section>

  <footer>
    Regenerated by <code>uv run python -m macro_framework.build_index_page</code>. Cron calls this alongside <code>macro_framework.build</code>; suggest-edit links open the source artifact on GitHub.
  </footer>
</main>
</body>
</html>
"""


def main() -> None:
    build_time = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(build_html(build_time), encoding="utf-8")
    print(f"Index page saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
