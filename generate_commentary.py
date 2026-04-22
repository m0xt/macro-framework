"""Auto-generate daily brief commentary using Claude + web search.

Reads latest snapshots, builds a numbers summary, calls Claude with
web_search to get current macro context, and writes brief_commentary.md.
Requires ANTHROPIC_API_KEY env var. Fails soft — skips without crashing build.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

CACHE_DIR = Path(__file__).parent / ".cache"
SNAPSHOT_DIR = CACHE_DIR / "snapshots"
COMMENTARY_FILE = CACHE_DIR / "brief_commentary.md"

MODEL = "claude-sonnet-4-6"

SYSTEM = """\
You are a macro analyst for Milk Road, a crypto and macro publication.
Write a daily brief commentary connecting our proprietary framework signals to what is
actually happening in markets. Style: clear, direct, no fluff — 5 to 7 sentences.
Audience: sophisticated investor who follows macro daily.
Do not open with "In today's..." or similar. Lead with the most important observation.
Flowing prose only — no bullets. Include markdown links to sources inline where relevant.
Framework context: MRMI is our regime signal (risk-on/off). Macro Season is determined by
two axes — Growth (vertical) and Inflation (horizontal) — placing the economy in one of
four quadrants: Spring (growth up, inflation below target), Summer (growth up, inflation
above target), Fall (growth down, inflation above target), Winter (growth down, inflation
below target). Do not use the term "MRCI" — refer to the growth axis simply as "growth".\
"""


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


def _build_context(latest: dict, prior_1d: dict | None, prior_7d: dict | None) -> str:
    u = latest.get("underliers", {})
    u1 = prior_1d.get("underliers", {}) if prior_1d else {}

    def chg1(key: str) -> str:
        v, p = u.get(key), u1.get(key)
        if v is None or p is None or p == 0:
            return ""
        return f" (1d {((v/p - 1)*100):+.2f}%)"

    def diff1(a, b_snap, *keys) -> str:
        b = _g(b_snap, *keys) if b_snap else None
        if a is None or b is None:
            return ""
        return f" (1d {(a-b):+.3f})"

    def diff7(a, b_snap, *keys) -> str:
        b = _g(b_snap, *keys) if b_snap else None
        if a is None or b is None:
            return ""
        return f" (7d {(a-b):+.3f})"

    mrmi = _g(latest, "mrmi", "composite")
    state = (latest.get("mrmi") or {}).get("state", "?")
    gii = _g(latest, "components", "gii_fast")
    fincon = _g(latest, "components", "fincon")
    breadth = _g(latest, "components", "breadth")
    mrci = _g(latest, "mrci", "composite")
    infl = _g(latest, "inflation")

    lines = [
        f"Date: {latest.get('date', '?')}",
        "",
        "=== FRAMEWORK SIGNALS ===",
        f"MRMI {mrmi:+.3f} ({state})"
            + diff1(mrmi, prior_1d, "mrmi", "composite")
            + diff7(mrmi, prior_7d, "mrmi", "composite"),
        f"  GII (growth impulse): {gii:+.3f}" + diff1(gii, prior_1d, "components", "gii_fast"),
        f"  FinCon (financial conditions): {fincon:+.3f}" + diff1(fincon, prior_1d, "components", "fincon"),
        f"  Breadth (sector breadth): {breadth:+.3f}" + diff1(breadth, prior_1d, "components", "breadth"),
        f"Growth (vertical axis): {mrci:+.3f}" + diff1(mrci, prior_1d, "mrci", "composite"),
        f"  Real economy: {_g(latest, 'mrci', 'real_economy'):+.3f}",
        f"  Credit & money: {_g(latest, 'mrci', 'credit_money'):+.3f}",
        f"  Markets pillar: {_g(latest, 'mrci', 'markets'):+.3f}",
        f"  Labor: {_g(latest, 'mrci', 'labor'):+.3f}",
        f"Inflation context: {infl:+.3f}",
        "",
        "=== MARKET LEVELS ===",
    ]

    underliers = [
        ("SPX",                 "^GSPC"),
        ("IWM (Russell 2000)",  "IWM"),
        ("BTC",                 "BTC-USD"),
        ("VIX",                 "^VIX"),
        ("MOVE (rate vol)",     "^MOVE"),
        ("10Y yield",           "DGS10"),
        ("2Y yield",            "DGS2"),
        ("HY OAS (bp)",         "BAMLH0A0HYM2"),
        ("10Y real rate",       "DFII10"),
        ("5Y breakeven",        "T5YIE"),
        ("DXY",                 "DTWEXBGS"),
        ("Fed balance sheet $M","WALCL"),
    ]
    for label, key in underliers:
        v = u.get(key)
        if v is not None:
            lines.append(f"  {label}: {v:.2f}{chg1(key)}")

    return "\n".join(str(l) for l in lines)


def generate_commentary() -> bool:
    """Generate and save commentary. Returns True on success."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("  Commentary: ANTHROPIC_API_KEY not set — skipping.")
        return False

    snaps = _list_snapshots()
    if not snaps:
        print("  Commentary: no snapshots found — skipping.")
        return False

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

    context = _build_context(latest, prior_1d, prior_7d)
    today = latest.get("date", latest_d.isoformat())

    user_prompt = (
        f"Today is {today}. Here are the current readings from our macro framework:\n\n"
        f"{context}\n\n"
        f"Search the web for the most important macro market news today ({today}), "
        f"then write a 5–7 sentence commentary connecting our framework signals "
        f"to what is actually happening. Explain the 'why' behind the moves. "
        f"Write the commentary only — no preamble."
    )

    try:
        import anthropic
    except ImportError:
        print("  Commentary: anthropic package not installed — skipping.")
        return False

    client = anthropic.Anthropic(api_key=api_key)

    print("  Commentary: calling Claude + web search...", end="", flush=True)
    try:
        messages = [{"role": "user", "content": user_prompt}]
        tools = [{"type": "web_search_20260209", "name": "web_search"}]

        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM,
            tools=tools,
            messages=messages,
        )

        # Re-send up to 3 times if server-side tool loop hit its iteration limit
        for _ in range(3):
            if response.stop_reason != "pause_turn":
                break
            messages.append({"role": "assistant", "content": response.content})
            response = client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=SYSTEM,
                tools=tools,
                messages=messages,
            )

        body = next((b.text for b in response.content if b.type == "text"), "").strip()
        if not body:
            print(" no text in response — skipping.")
            return False

        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        COMMENTARY_FILE.write_text(f"date: {today}\n\n{body}\n")
        print(" done.")
        return True

    except Exception as e:
        print(f" failed: {e}")
        return False


if __name__ == "__main__":
    generate_commentary()
