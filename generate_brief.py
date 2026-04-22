"""Daily brief generator — V1.

Reads snapshot JSONs from `.cache/snapshots/` and renders `.cache/brief.html`,
a self-contained card injected at the top of the dashboard. Purely mechanical:
no LLM, no web. Shows regime state + largest 1d/7d moves across our own series.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

CACHE_DIR = Path(__file__).parent / ".cache"
SNAPSHOT_DIR = CACHE_DIR / "snapshots"
BRIEF_FILE = CACHE_DIR / "brief.html"
COMMENTARY_FILE = CACHE_DIR / "brief_commentary.md"


# Fields we'll diff. (path-in-snapshot, display-name, format, direction)
# direction: +1 means "up = good/risk-on", -1 means "up = bad/risk-off",
# 0 means neutral (color by sign of change only, no good/bad).
FIELDS = [
    # MRMI + components — up = risk-on
    (("mrmi", "composite"),      "MRMI",          "{:+.2f}",  +1),
    (("components", "gii_fast"), "GII",           "{:+.2f}",  +1),
    (("components", "fincon"),   "FinCon",        "{:+.2f}",  +1),
    (("components", "breadth"),  "Breadth",       "{:+.2f}",  +1),
    # MRCI — context only, neutral color
    (("mrci", "composite"),      "MRCI",          "{:+.2f}",   0),
    (("mrci", "real_economy"),   "  Real econ",   "{:+.2f}",   0),
    (("mrci", "credit_money"),   "  Credit/$",    "{:+.2f}",   0),
    (("mrci", "markets"),        "  Markets",     "{:+.2f}",   0),
    (("mrci", "labor"),          "  Labor",       "{:+.2f}",   0),
    (("inflation",),             "Inflation",     "{:+.2f}",   0),
]

# Underliers we call out by name (label, key, format, pct?, direction)
# pct=True → report % change; False → absolute change in raw units.
UNDERLIERS = [
    ("SPX",      "^GSPC",        "{:+.2f}%", True,   +1),
    ("IWM",      "IWM",          "{:+.2f}%", True,   +1),
    ("BTC",      "BTC-USD",      "{:+.2f}%", True,   +1),
    ("VIX",      "^VIX",         "{:+.2f}",  False,  -1),
    ("MOVE",     "^MOVE",        "{:+.2f}",  False,  -1),
    ("10Y",      "DGS10",        "{:+.2f}bp", False, 0),  # x100 applied below
    ("HY OAS",   "BAMLH0A0HYM2", "{:+.2f}bp", False, -1),
    ("DXY",      "DTWEXBGS",     "{:+.2f}%", True,   -1),
]


def _list_snapshots() -> list[tuple[date, Path]]:
    """Return snapshots sorted oldest→newest as (date, path)."""
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


def _get(snap: dict, path: tuple[str, ...]):
    cur = snap
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    if isinstance(cur, (int, float)):
        return float(cur)
    return None


def _pick_prior(snaps: list[tuple[date, Path]], latest_d: date, target_days: int) -> dict | None:
    """Pick the snapshot closest to latest_d - target_days (not after).
    Falls back to the oldest snapshot if history is shorter than target."""
    if len(snaps) < 2:
        return None
    target = latest_d - timedelta(days=target_days)
    candidates = [s for s in snaps if s[0] <= target and s[0] < latest_d]
    if candidates:
        return _load(candidates[-1][1])
    # Fall back to oldest snapshot (still < latest)
    older = [s for s in snaps if s[0] < latest_d]
    if not older:
        return None
    return _load(older[0][1])


def _color_for(delta: float, direction: int) -> str:
    """Return 'pos' / 'neg' / 'neutral' class based on delta * direction."""
    if delta is None or abs(delta) < 1e-9:
        return "neutral"
    if direction == 0:
        return "pos" if delta > 0 else "neg"
    signed = delta * direction
    return "pos" if signed > 0 else "neg"


def _row(label: str, latest: float | None, prior: float | None,
         fmt: str, direction: int, pct: bool = False, scale: float = 1.0) -> dict | None:
    """Compute a single mover row. Returns None if either side missing."""
    if latest is None or prior is None:
        return None
    delta_raw = latest - prior
    if pct:
        if prior == 0:
            return None
        delta = (latest / prior - 1.0) * 100.0
    else:
        delta = delta_raw * scale
    return {
        "label": label,
        "latest": latest,
        "delta": delta,
        "delta_fmt": fmt.format(delta),
        "color": _color_for(delta, direction),
        "abs": abs(delta),
    }


def _rows_for(latest_snap: dict, prior_snap: dict | None) -> list[dict]:
    rows: list[dict] = []
    if prior_snap is None:
        return rows
    for path, label, fmt, direction in FIELDS:
        r = _row(label, _get(latest_snap, path), _get(prior_snap, path),
                 fmt, direction)
        if r is not None:
            rows.append(r)
    for label, key, fmt, pct, direction in UNDERLIERS:
        scale = 100.0 if "bp" in fmt else 1.0
        r = _row(label,
                 (latest_snap.get("underliers") or {}).get(key),
                 (prior_snap.get("underliers") or {}).get(key),
                 fmt, direction, pct=pct, scale=scale)
        if r is not None:
            rows.append(r)
    return rows


def _top_movers(rows: list[dict], n: int = 5) -> list[dict]:
    # Exclude the sub-indent MRCI pillars from "top movers" ranking so the
    # headline gets the category-level signals, not their children.
    ranked = [r for r in rows if not r["label"].startswith("  ")]
    ranked.sort(key=lambda r: r["abs"], reverse=True)
    return ranked[:n]


def _regime(latest_snap: dict) -> tuple[str, str]:
    """Return (label, css-class) for the regime."""
    state = (latest_snap.get("mrmi") or {}).get("state")
    if state == "green":
        return ("RISK-ON", "pos")
    if state == "red":
        return ("RISK-OFF", "neg")
    return ("—", "neutral")


def _fmt_row(r: dict) -> str:
    arrow = "▲" if r["delta"] > 0 else ("▼" if r["delta"] < 0 else "·")
    # Strip the leading sign from delta_fmt (we already show an arrow)
    dtxt = r["delta_fmt"].lstrip("+")
    return (
        f'<div class="brief-row">'
        f'  <span class="brief-row-label">{r["label"].strip()}</span>'
        f'  <span class="brief-row-delta {r["color"]}">'
        f'<span class="brief-arrow">{arrow}</span> {dtxt}</span>'
        f'</div>'
    )


def _render_movers_column(title: str, rows: list[dict], period_label: str) -> str:
    if not rows:
        return (
            f'<div class="brief-col">'
            f'  <div class="brief-col-title">{title}</div>'
            f'  <div class="brief-empty">No prior snapshot for {period_label}.</div>'
            f'</div>'
        )
    top = _top_movers(rows, n=3)
    body = "".join(_fmt_row(r) for r in top)
    return (
        f'<div class="brief-col">'
        f'  <div class="brief-col-title">{title}</div>'
        f'  <div class="brief-rows">{body}</div>'
        f'</div>'
    )


def _narrative(latest_snap: dict, rows_1d: list[dict], rows_7d: list[dict]) -> str:
    """Build a plain-English summary sentence from MRMI state + deltas."""
    label, _ = _regime(latest_snap)

    def find(rows, lbl):
        for r in rows:
            if r["label"] == lbl:
                return r
        return None

    m1 = find(rows_1d, "MRMI")
    m7 = find(rows_7d, "MRMI")

    def phrase(r, window):
        if r is None:
            return None
        if abs(r["delta"]) < 0.02:
            return f"flat {window}"
        verb_up = "strengthened" if r["delta"] > 0 else "softened"
        return f"{verb_up} {window} ({r['delta_fmt']})"

    parts = []
    if m7:
        parts.append(phrase(m7, "over the week"))
    if m1:
        parts.append(phrase(m1, "today"))
    parts = [p for p in parts if p]

    if label in ("RISK-ON", "RISK-OFF"):
        lead = f"Regime holds <span class='brief-regime-inline {_regime(latest_snap)[1]}'>{label}</span>"
    else:
        lead = "Regime indeterminate"

    if parts:
        return f'<div class="brief-narrative">{lead}. MRMI {"; ".join(parts)}.</div>'
    return f'<div class="brief-narrative">{lead}.</div>'


import re


def _md_to_html(text: str) -> str:
    """Minimal markdown renderer: [txt](url), **bold**, *italic*, paragraphs."""
    # Escape any raw HTML first, then re-inject our own tags.
    out = (text.replace("&", "&amp;")
               .replace("<", "&lt;")
               .replace(">", "&gt;"))
    out = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                 r'<a href="\2" target="_blank" rel="noopener">\1</a>', out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![*])\*([^*\n]+)\*(?![*])", r"<em>\1</em>", out)
    paragraphs = [p.strip() for p in out.split("\n\n") if p.strip()]
    return "".join(f"<p>{p}</p>" for p in paragraphs)


def _load_commentary() -> dict | None:
    """Read brief_commentary.md. First line: 'date: YYYY-MM-DD'. Rest: markdown body."""
    if not COMMENTARY_FILE.exists():
        return None
    raw = COMMENTARY_FILE.read_text().strip()
    if not raw:
        return None
    first, _, rest = raw.partition("\n")
    first = first.strip()
    if first.lower().startswith("date:"):
        d = first.split(":", 1)[1].strip()
        body = rest.strip()
    else:
        d = None
        body = raw
    return {"date": d, "body": body}


def _render_commentary(commentary: dict | None, latest_snap_date: str) -> str:
    if not commentary or not commentary.get("body"):
        return ""
    body_html = _md_to_html(commentary["body"])
    d = commentary.get("date")
    stale = d and latest_snap_date and d < latest_snap_date
    date_str = ""
    if d:
        tag = ' · <span class="brief-stale">stale</span>' if stale else ""
        date_str = f'<span class="brief-comm-date">{d}{tag}</span>'
    return (
        f'<div class="brief-commentary">'
        f'  <div class="brief-comm-head">'
        f'    <span class="brief-comm-title">Commentary</span>'
        f'    {date_str}'
        f'  </div>'
        f'  <div class="brief-comm-body">{body_html}</div>'
        f'</div>'
    )


def _render_headline(latest_snap: dict) -> str:
    """Compact chip-row: title + current MRMI value."""
    mrmi = _get(latest_snap, ("mrmi", "composite"))
    mrmi_str = f"{mrmi:+.2f}" if mrmi is not None else "—"
    return (
        f'<div class="brief-head">'
        f'  <span class="brief-title">Daily brief</span>'
        f'  <span class="brief-head-mrmi">MRMI <span class="brief-head-mrmi-val">{mrmi_str}</span></span>'
        f'</div>'
    )


STYLE = """
<style>
  .brief-card {
    margin: 8px 12px 0; padding: 16px 20px 14px; border-radius: 8px;
    background: #111; border: 1px solid #1a1a1a;
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', system-ui, sans-serif;
  }
  .brief-head {
    display: flex; align-items: baseline; justify-content: space-between;
    margin-bottom: 10px;
  }
  .brief-title {
    font-size: 10px; color: #555; text-transform: uppercase;
    letter-spacing: 0.8px; font-weight: 600;
  }
  .brief-head-mrmi {
    font-size: 11px; color: #666; text-transform: uppercase; letter-spacing: 0.5px;
  }
  .brief-head-mrmi-val {
    font-family: 'SF Mono', Menlo, monospace; color: #ccc; font-weight: 600;
    margin-left: 4px; font-size: 13px;
  }
  .brief-narrative {
    font-size: 14px; color: #ddd; line-height: 1.5;
    padding-bottom: 14px; margin-bottom: 14px;
    border-bottom: 1px solid #1a1a1a;
  }
  .brief-regime-inline { font-weight: 700; letter-spacing: 0.5px; }
  .brief-regime-inline.pos { color: #4CAF50; }
  .brief-regime-inline.neg { color: #E84B5A; }
  .brief-regime-inline.neutral { color: #888; }

  .brief-cols {
    display: grid; grid-template-columns: 1fr 1fr; gap: 28px;
  }
  .brief-col-title {
    font-size: 10px; color: #555; text-transform: uppercase;
    letter-spacing: 0.5px; margin-bottom: 8px; font-weight: 600;
  }
  .brief-rows { display: flex; flex-direction: column; gap: 4px; }
  .brief-row {
    display: flex; justify-content: space-between; align-items: baseline;
    padding: 6px 0; border-bottom: 1px solid #161616;
  }
  .brief-row:last-child { border-bottom: none; }
  .brief-row-label { font-size: 13px; color: #aaa; }
  .brief-row-delta {
    font-size: 13px; font-family: 'SF Mono', Menlo, monospace; font-weight: 600;
  }
  .brief-row-delta.pos { color: #4CAF50; }
  .brief-row-delta.neg { color: #E84B5A; }
  .brief-row-delta.neutral { color: #777; }
  .brief-arrow { margin-right: 4px; font-size: 11px; }

  .brief-empty { font-size: 12px; color: #555; font-style: italic; }

  .brief-commentary {
    margin-top: 16px; padding-top: 14px; border-top: 1px solid #1a1a1a;
  }
  .brief-comm-head {
    display: flex; align-items: baseline; justify-content: space-between;
    margin-bottom: 8px;
  }
  .brief-comm-title {
    font-size: 10px; color: #555; text-transform: uppercase;
    letter-spacing: 0.8px; font-weight: 600;
  }
  .brief-comm-date {
    font-size: 10px; color: #555; font-family: 'SF Mono', Menlo, monospace;
  }
  .brief-stale {
    color: #E84B5A; text-transform: uppercase; letter-spacing: 0.5px;
  }
  .brief-comm-body p {
    font-size: 13px; color: #bbb; line-height: 1.6; margin-bottom: 10px;
  }
  .brief-comm-body p:last-child { margin-bottom: 0; }
  .brief-comm-body strong { color: #eee; font-weight: 600; }
  .brief-comm-body em { color: #ccc; font-style: italic; }
  .brief-comm-body a { color: #4DA8DA; text-decoration: none; }
  .brief-comm-body a:hover { text-decoration: underline; }

  .brief-footer {
    margin-top: 12px; padding-top: 10px; border-top: 1px solid #1a1a1a;
    font-size: 10px; color: #444;
  }
</style>
"""


def generate_brief() -> Path | None:
    """Build brief.html from snapshots. Returns the written path, or None."""
    snaps = _list_snapshots()
    if not snaps:
        print("  No snapshots found — skipping brief.")
        return None

    latest_d, latest_path = snaps[-1]
    latest = _load(latest_path)
    prior_1d = _pick_prior(snaps, latest_d, 1)
    prior_7d = _pick_prior(snaps, latest_d, 7)

    rows_1d = _rows_for(latest, prior_1d)
    rows_7d = _rows_for(latest, prior_7d)

    headline = _render_headline(latest)
    narrative = _narrative(latest, rows_1d, rows_7d)
    col_1d = _render_movers_column("Last 24 hours", rows_1d, "1d")
    col_7d = _render_movers_column("Last 7 days", rows_7d, "7d")
    commentary = _render_commentary(_load_commentary(), latest_d.isoformat())

    # Footer: build time + history span
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    oldest_d = snaps[0][0]
    footer = (f'<div class="brief-footer">'
              f'Generated {now} · '
              f'Latest snapshot {latest_d.isoformat()}'
              + (f' · Prior {prior_1d["date"]}' if prior_1d and "date" in prior_1d else '')
              + (f' · 7d ref {prior_7d["date"]}' if prior_7d and "date" in prior_7d else '')
              + f' · {len(snaps)} snapshots in history'
              + '</div>')

    html = (STYLE
            + '<div class="brief-card">'
            + headline
            + narrative
            + '<div class="brief-cols">' + col_1d + col_7d + '</div>'
            + commentary
            + footer
            + '</div>')

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    BRIEF_FILE.write_text(html)
    print(f"  Brief written to {BRIEF_FILE}")
    return BRIEF_FILE


if __name__ == "__main__":
    generate_brief()
