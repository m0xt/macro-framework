"""Auto-generate weekly briefs (top + per-pillar) for the macro dashboard.

Uses the `claude` CLI (Claude Code subscription) with WebSearch enabled.
Three briefs in a tiered hierarchy, regenerated each week on Tuesday cadence:

    1. Market pillar brief    → briefs/YYYY-MM-DD/market.md
    2. Economy pillar brief   → briefs/YYYY-MM-DD/economy.md
    3. Top brief (synthesis)  → briefs/YYYY-MM-DD/top.md

The top brief is generated AFTER both pillar briefs and consumes them as
context, so it builds on fresh foundations rather than re-deriving the
underlying analysis. Each brief is regenerated only if the most recent
dated archive folder is older than the most recent Tuesday on or before
today (lazy weekly).

Past briefs are preserved in their dated folders forever (the `briefs/`
directory is git-tracked) so weekly research meetings can reference how
the read evolved over time.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent
CACHE_DIR = ROOT / ".cache"
SNAPSHOT_DIR = CACHE_DIR / "snapshots"
BRIEFS_DIR = ROOT / "briefs"

FILE_TOP     = "top.md"
FILE_MARKET  = "market.md"
FILE_ECONOMY = "economy.md"

MODEL = "sonnet"

SYSTEM_BASE = """\
You are a macro analyst for Milk Road, a crypto and macro publication.
Audience: sophisticated investor who follows macro daily.
Style: clear, direct, no fluff. Lead with the most important observation —
do not open with "In today's..." or similar. Flowing prose only — no bullets.
Include markdown links to sources inline where relevant.

Framework context: MRMI is the headline regime signal (LONG vs CASH). It
combines MMI (market momentum from credit / breadth / volatility) with a
macro stress buffer drawn from growth and inflation conditions. Discuss
growth, inflation, and stress in plain terms — do NOT use season metaphors
(no "Spring/Summer/Fall/Winter") and do NOT use the term "MRCI". Refer to
the growth axis simply as "growth".\
"""

SYSTEM_MARKET = SYSTEM_BASE + """

Your beat for this brief: the MARKET PILLAR (MMI). Three drivers — GII
(global growth impulse from credit spreads, sector rotation, copper, vol,
yield curve, shipping), Breadth (cyclical sector participation), and FinCon
(financial conditions: equity vol + bond vol + credit spreads). Discuss
divergences and what's driving the score. Length: 5–7 sentences."""

SYSTEM_ECONOMY = SYSTEM_BASE + """

Your beat for this brief: the ECONOMY PILLAR. The dashboard's headline view
for this pillar is the MACRO STRESS PRESSURE chart — a single continuous
score that smooths the AND-condition between weak growth and rising
inflation, then z-scores it against its own history. Reading guide:
  · 0     = typical historical macro reading
  · +1σ   = stress building above norm (top ~16% of history)
  · +2σ   = unusual stress building
  · −1σ   = unusually calm vs history
The two underlying axes feeding the pressure score are:
  · Real Economy Score (z) — equal-weighted PCE / Sahm / Real Income / GDPNow
  · Inflation Direction (Δ Core CPI YoY over 6m, in pp)
For the model's actual buffer / MRMI calculation, the framework still uses
a hard-clipped stress_intensity (rare, mostly 0). Don't conflate the two —
the pressure score is the read; the hard-clipped intensity is the trigger.

Lead with where the pressure z-score sits and what it implies, then
explain what each axis is doing to drive that reading, then call out what
would push it materially. Length: 5–7 sentences."""

SYSTEM_TOP = SYSTEM_BASE + """

This is the headline brief — a synthesis that connects both pillars to
where MRMI is and what it's signaling. You will receive the latest
framework snapshot AND the pillar briefs already written by your colleagues
this week. Use them as your foundation rather than re-deriving the
underlying analysis. Connect the cross-pillar story: where do market and
economy agree or diverge, what's the headline read, what to watch.
Length: 5–7 sentences."""


# ── snapshot helpers ───────────────────────────────────────────────────────

def _list_snapshots() -> list[tuple[date, Path]]:
    if not SNAPSHOT_DIR.exists():
        return []
    out = []
    for p in SNAPSHOT_DIR.glob("*.json"):
        try:
            d = datetime.strptime(p.stem, "%Y-%m-%d").date()
        except ValueError:
            continue
        out.append((d, p))
    out.sort()
    return out


def _load(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def _g(snap: dict, *keys) -> float | None:
    cur = snap
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return float(cur) if isinstance(cur, (int, float)) else None


def _fmt(v: float | None, spec: str = "+.3f") -> str:
    return format(v, spec) if isinstance(v, (int, float)) else "—"


# ── brief archive helpers ──────────────────────────────────────────────────

def _list_brief_dates() -> list[date]:
    if not BRIEFS_DIR.exists():
        return []
    out = []
    for p in BRIEFS_DIR.iterdir():
        if not p.is_dir():
            continue
        try:
            out.append(datetime.strptime(p.name, "%Y-%m-%d").date())
        except ValueError:
            continue
    out.sort()
    return out


def latest_brief_dir() -> Path | None:
    dates = _list_brief_dates()
    if not dates:
        return None
    return BRIEFS_DIR / dates[-1].isoformat()


def _read_brief(path: Path) -> str:
    return path.read_text().strip() if path.exists() else ""


# ── Tuesday-cadence freshness check ────────────────────────────────────────

def _most_recent_tuesday(today: date) -> date:
    """Tuesday on or before today. weekday(): Mon=0, Tue=1, ..., Sun=6."""
    days_back = (today.weekday() - 1) % 7
    return today - timedelta(days=days_back)


def _is_stale(filename: str, today: date) -> bool:
    """A brief is stale if no archive contains it, or the latest archive is
    older than the most recent Tuesday."""
    dates = _list_brief_dates()
    cutoff = _most_recent_tuesday(today)
    for d in reversed(dates):
        if (BRIEFS_DIR / d.isoformat() / filename).exists():
            return d < cutoff
    return True


# ── pillar-specific context builders ───────────────────────────────────────

def _market_context(latest: dict, prior_1d: dict | None, prior_7d: dict | None) -> str:
    def diff(a, snap, *k, days):
        if not snap:
            return ""
        b = _g(snap, *k)
        if a is None or b is None:
            return ""
        return f" ({days}d {(a-b):+.3f})"

    mmi = _g(latest, "mrmi", "composite")
    state = (latest.get("mrmi") or {}).get("state", "?")
    gii = _g(latest, "components", "gii_fast")
    fincon = _g(latest, "components", "fincon")
    breadth = _g(latest, "components", "breadth")
    u = latest.get("underliers", {})

    market_underliers = [
        ("VIX", "^VIX"), ("MOVE (rate vol)", "^MOVE"),
        ("HY OAS (bp)", "BAMLH0A0HYM2"),
        ("10Y yield", "DGS10"), ("2Y yield", "DGS2"),
        ("DXY", "DTWEXBGS"),
    ]

    lines = [
        f"Date: {latest.get('date', '?')}",
        "",
        "=== MMI (Momentum Index) ===",
        f"MMI {_fmt(mmi)} ({state})"
            + diff(mmi, prior_1d, "mrmi", "composite", days=1)
            + diff(mmi, prior_7d, "mrmi", "composite", days=7),
        f"  GII: {_fmt(gii)}"
            + diff(gii, prior_1d, "components", "gii_fast", days=1)
            + diff(gii, prior_7d, "components", "gii_fast", days=7),
        f"  Breadth: {_fmt(breadth)}"
            + diff(breadth, prior_1d, "components", "breadth", days=1)
            + diff(breadth, prior_7d, "components", "breadth", days=7),
        f"  FinCon: {_fmt(fincon)}"
            + diff(fincon, prior_1d, "components", "fincon", days=1)
            + diff(fincon, prior_7d, "components", "fincon", days=7),
        "",
        "=== MARKET LEVELS ===",
    ]
    for label, key in market_underliers:
        v = u.get(key)
        if v is not None:
            lines.append(f"  {label}: {v:.2f}")
    return "\n".join(lines)


def _smoothed_pressure(re: float | None, inf: float | None, k: float = 2.0) -> float | None:
    """Sigmoid-AND, mirrors the dashboard's chart-stress-strip (raw, not z-scored)."""
    import math
    if re is None or inf is None:
        return None
    sig = lambda x: 1.0 / (1.0 + math.exp(-x))
    return sig(-k * re) * sig(k * inf)


def _economy_context(latest: dict, prior_7d: dict | None) -> str:
    def diff7(a, *k):
        if not prior_7d:
            return ""
        b = _g(prior_7d, *k)
        if a is None or b is None:
            return ""
        return f" (7d {(a-b):+.3f})"

    # Fields driving the dashboard's economy pillar view
    re_score = _g(latest, "macro", "real_economy_score")
    inf_dir = _g(latest, "macro", "inflation_dir_pp")
    core_cpi = _g(latest, "macro", "core_cpi_yoy_pct")
    stress_intensity = _g(latest, "mrmi_combined", "stress_intensity")  # hard-clipped (model)
    macro_buffer = _g(latest, "mrmi_combined", "macro_buffer")
    pressure_raw = _smoothed_pressure(re_score, inf_dir)
    pressure_raw_7d = _smoothed_pressure(
        _g(prior_7d, "macro", "real_economy_score") if prior_7d else None,
        _g(prior_7d, "macro", "inflation_dir_pp") if prior_7d else None,
    )
    pressure_delta = (
        f" (7d {(pressure_raw - pressure_raw_7d):+.3f})"
        if (pressure_raw is not None and pressure_raw_7d is not None) else ""
    )

    # Real-economy sub-components (the four feeding the score)
    re_components = (latest.get("macro") or {}).get("real_economy_components") or {}

    u = latest.get("underliers", {})
    macro_underliers = [
        ("10Y real rate", "DFII10"),
        ("5Y breakeven", "T5YIE"),
        ("Fed balance sheet $M", "WALCL"),
    ]

    lines = [
        f"Date: {latest.get('date', '?')}",
        "",
        "=== MACRO STRESS PRESSURE (the dashboard headline chart) ===",
        f"Smoothed pressure (raw, pre-z-score): {_fmt(pressure_raw)}" + pressure_delta,
        "  · Range ~0.06 to ~1.00; ~0.25 = neutral baseline; rises when both axes are adverse.",
        "  · The dashboard z-scores this against full history before plotting.",
        "  · Hard-clipped stress_intensity (used by MRMI for buffer): " + _fmt(stress_intensity),
        "  · Macro buffer currently feeding MRMI: " + _fmt(macro_buffer)
            + "  (1.0 = full strength tailwind; 0.0 = fully eroded)",
        "",
        "=== UNDERLYING AXES (collapsible 'Underlying components' on dashboard) ===",
        f"Real Economy Score (z): {_fmt(re_score)}" + diff7(re_score, "macro", "real_economy_score"),
        "  · Above 0 = healthy growth; below 0 = weakening",
        f"Inflation Direction (Δ6m, pp): {_fmt(inf_dir)}" + diff7(inf_dir, "macro", "inflation_dir_pp"),
        "  · Above 0 = inflation accelerating; below 0 = decelerating",
        f"  · Latest Core CPI YoY level: {core_cpi:.2f}%" if isinstance(core_cpi, (int, float)) else "",
        "",
        "=== REAL ECONOMY SUB-COMPONENTS (drivers section, collapsed) ===",
    ]
    component_labels = {
        "real_pce_yoy": "Real PCE YoY",
        "sahm_rule": "Sahm Rule (raw, NOT inverted)",
        "income_yoy": "Real Personal Income YoY",
        "gdpnow": "Atlanta Fed GDPNow",
    }
    for key, label in component_labels.items():
        v = re_components.get(key)
        if isinstance(v, (int, float)):
            lines.append(f"  {label}: {v:+.3f}")

    lines.extend(["", "=== MACRO LEVELS ==="])
    for label, key in macro_underliers:
        v = u.get(key)
        if v is not None:
            lines.append(f"  {label}: {v:.2f}")
    return "\n".join(l for l in lines if l != "")


def _top_context(latest: dict) -> str:
    """Just the headline numbers — pillar briefs supply the analysis."""
    mrmi_combined = latest.get("mrmi_combined") or {}
    mrmi_value = mrmi_combined.get("value")
    mrmi_state = mrmi_combined.get("state", "?")
    momentum = mrmi_combined.get("momentum")
    macro_buffer = mrmi_combined.get("macro_buffer")
    stress = mrmi_combined.get("stress_intensity") or 0.0

    return (
        f"Date: {latest.get('date', '?')}\n\n"
        f"=== HEADLINE ===\n"
        f"MRMI {_fmt(mrmi_value)} ({mrmi_state})\n"
        f"  MMI (momentum): {_fmt(momentum)}\n"
        f"  Macro buffer: {_fmt(macro_buffer)}\n"
        f"  Stress intensity: {_fmt(stress)}\n"
    )


# ── claude CLI runner ──────────────────────────────────────────────────────

def _run_claude(system: str, prompt: str, label: str, timeout: int = 240) -> str | None:
    """Returns body string or None on failure."""
    print(f"  {label}: calling claude CLI + WebSearch...", end="", flush=True)
    try:
        result = subprocess.run(
            [
                "claude", "-p", prompt,
                "--model", MODEL,
                "--system-prompt", system,
                "--allowedTools", "WebSearch",
                "--no-session-persistence",
                "--disable-slash-commands",
                "--output-format", "text",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            print(f" failed (exit {result.returncode}): {result.stderr.strip()[:200]}")
            return None
        body = result.stdout.strip()
        if not body:
            print(" no text in response.")
            return None
        print(" done.")
        return body
    except subprocess.TimeoutExpired:
        print(f" timed out after {timeout}s.")
        return None
    except Exception as e:
        print(f" failed: {e}")
        return None


def _archive_dir_for(today_str: str) -> Path:
    d = BRIEFS_DIR / today_str
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── snapshot loader (shared) ───────────────────────────────────────────────

def _load_snapshots():
    """Returns (latest_dict, prior_1d_dict_or_None, prior_7d_dict_or_None, today_str) or None."""
    snaps = _list_snapshots()
    if not snaps:
        return None
    latest_d, latest_path = snaps[-1]
    latest = _load(latest_path)

    prior_1d = None
    for d, p in reversed(snaps[:-1]):
        if d < latest_d:
            prior_1d = _load(p)
            break

    prior_7d = None
    target7 = latest_d - timedelta(days=7)
    candidates = [(d, p) for d, p in snaps if d <= target7 and d < latest_d]
    if candidates:
        prior_7d = _load(candidates[-1][1])
    elif len(snaps) > 1:
        prior_7d = _load(snaps[0][1])

    today = latest.get("date", latest_d.isoformat())
    return latest, prior_1d, prior_7d, today


# ── individual brief generators ────────────────────────────────────────────

def generate_pillar_brief(pillar: str, force: bool = False) -> bool:
    if pillar == "market":
        filename, system = FILE_MARKET, SYSTEM_MARKET
    elif pillar == "economy":
        filename, system = FILE_ECONOMY, SYSTEM_ECONOMY
    else:
        raise ValueError(f"unknown pillar: {pillar}")

    today_dt = date.today()
    if not force and not _is_stale(filename, today_dt):
        print(f"  {pillar.capitalize()} brief: fresh (this week's Tuesday) — skipping.")
        return True

    if not shutil.which("claude"):
        print(f"  {pillar.capitalize()} brief: `claude` CLI not on PATH — skipping.")
        return False

    snap_data = _load_snapshots()
    if snap_data is None:
        print(f"  {pillar.capitalize()} brief: no snapshots — skipping.")
        return False
    latest, prior_1d, prior_7d, today = snap_data

    if pillar == "market":
        context = _market_context(latest, prior_1d, prior_7d)
        beat = "MMI (market momentum) over the last week"
    else:
        context = _economy_context(latest, prior_7d)
        beat = "the economy pillar (real-economy strength + inflation direction) over the last week"

    prompt = (
        f"This week's brief is dated {today}. Current readings:\n\n{context}\n\n"
        f"Search the web for the most material news from the last 5–7 days affecting "
        f"{beat}, then write the brief connecting our framework signals to what is "
        f"actually happening. Explain the 'why' behind the moves. "
        f"Write the brief only — no preamble."
    )

    body = _run_claude(system, prompt, label=f"{pillar.capitalize()} brief", timeout=240)
    if not body:
        return False
    (_archive_dir_for(today) / filename).write_text(body + "\n")
    return True


def generate_top_brief(force: bool = False) -> bool:
    today_dt = date.today()
    if not force and not _is_stale(FILE_TOP, today_dt):
        print("  Top brief: fresh (this week's Tuesday) — skipping.")
        return True

    if not shutil.which("claude"):
        print("  Top brief: `claude` CLI not on PATH — skipping.")
        return False

    snap_data = _load_snapshots()
    if snap_data is None:
        print("  Top brief: no snapshots — skipping.")
        return False
    latest, _, _, today = snap_data

    archive = _archive_dir_for(today)
    market_brief = _read_brief(archive / FILE_MARKET) or "(market pillar brief unavailable)"
    economy_brief = _read_brief(archive / FILE_ECONOMY) or "(economy pillar brief unavailable)"

    prompt = (
        f"Today is {today}. Headline framework readings:\n\n{_top_context(latest)}\n"
        f"=== THIS WEEK'S MARKET PILLAR BRIEF ===\n{market_brief}\n\n"
        f"=== THIS WEEK'S ECONOMY PILLAR BRIEF ===\n{economy_brief}\n\n"
        f"Synthesize a headline brief that connects both pillars to the MRMI read. "
        f"You may search the web for one or two pieces of cross-cutting context "
        f"(e.g. a major event tying the two stories together) but rely primarily on "
        f"the pillar briefs above — don't restate them, build on them. "
        f"Write the brief only — no preamble."
    )

    body = _run_claude(SYSTEM_TOP, prompt, label="Top brief", timeout=240)
    if not body:
        return False
    (archive / FILE_TOP).write_text(body + "\n")
    return True


# ── orchestrator ───────────────────────────────────────────────────────────

def generate_all_briefs(force: bool = False) -> bool:
    """Pillar briefs first (so the top brief can read them), then top brief."""
    ok_market = generate_pillar_brief("market", force=force)
    ok_economy = generate_pillar_brief("economy", force=force)
    ok_top = generate_top_brief(force=force)
    return ok_market and ok_economy and ok_top



if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    generate_all_briefs(force=force)
