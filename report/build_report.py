#!/usr/bin/env python3
"""
Convert the markdown macro update into a self-contained HTML report
with embedded base64 images. Open in browser to view.
"""

import base64
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / ".cache"
CHARTS_DIR = CACHE_DIR / "charts"
REPORTS_DIR = ROOT / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


def md_to_html_basic(md: str) -> str:
    """Minimal markdown → HTML converter for our report format."""
    lines = md.split("\n")
    html = []
    in_table = False
    in_list = False

    for i, line in enumerate(lines):
        # Headers
        if line.startswith("# "):
            html.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("## "):
            html.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("### "):
            html.append(f"<h3>{line[4:]}</h3>")
        # Horizontal rule
        elif line.strip() == "---":
            html.append("<hr>")
        # Image
        elif line.startswith("!["):
            m = re.match(r"!\[(.+?)\]\((.+?)\)", line)
            if m:
                alt, src = m.group(1), m.group(2)
                # Embed image as base64
                img_path = CACHE_DIR / src
                if img_path.exists():
                    with open(img_path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode()
                    html.append(f'<div class="chart-block"><img src="data:image/png;base64,{b64}" alt="{alt}"></div>')
                else:
                    html.append(f'<div class="chart-block missing">[Missing image: {src}]</div>')
        # Tables
        elif line.startswith("|") and not in_table:
            in_table = True
            html.append("<table>")
            cells = [c.strip() for c in line.strip("|").split("|")]
            html.append("<thead><tr>" + "".join(f"<th>{c}</th>" for c in cells) + "</tr></thead><tbody>")
        elif line.startswith("|---"):
            continue  # separator row
        elif line.startswith("|") and in_table:
            cells = [c.strip() for c in line.strip("|").split("|")]
            html.append("<tr>" + "".join(f"<td>{inline_md(c)}</td>" for c in cells) + "</tr>")
        elif in_table and not line.startswith("|"):
            html.append("</tbody></table>")
            in_table = False
            if line.strip():
                html.append(f"<p>{inline_md(line)}</p>")
        # Lists
        elif line.startswith("- "):
            if not in_list:
                html.append("<ul>")
                in_list = True
            html.append(f"<li>{inline_md(line[2:])}</li>")
        elif in_list and not line.startswith("- "):
            html.append("</ul>")
            in_list = False
            if line.strip():
                html.append(f"<p>{inline_md(line)}</p>")
        # Italic standalone (caption)
        elif line.startswith("*") and line.endswith("*") and len(line) > 2 and not line.startswith("**"):
            html.append(f'<p class="caption">{inline_md(line[1:-1])}</p>')
        # Empty line
        elif not line.strip():
            continue
        # Regular paragraph
        else:
            html.append(f"<p>{inline_md(line)}</p>")

    if in_table:
        html.append("</tbody></table>")
    if in_list:
        html.append("</ul>")

    return "\n".join(html)


def inline_md(text: str) -> str:
    """Inline markdown: bold, italic, code."""
    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # Italic (but not in middle of word)
    text = re.sub(r"(?<![\w*])\*([^*]+?)\*(?!\w)", r"<em>\1</em>", text)
    # Inline code
    text = re.sub(r"`([^`]+?)`", r"<code>\1</code>", text)
    return text


def build_html(content: str, title: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', system-ui, sans-serif;
    background: #0a0a0a;
    color: #d0d0d0;
    margin: 0;
    padding: 0;
    line-height: 1.6;
  }}
  .container {{
    max-width: 900px;
    margin: 0 auto;
    padding: 60px 40px 80px;
  }}
  h1 {{
    font-size: 36px;
    color: #fff;
    margin: 32px 0 8px;
    font-weight: 700;
    letter-spacing: -0.5px;
  }}
  h2 {{
    font-size: 24px;
    color: #fff;
    margin: 40px 0 16px;
    font-weight: 600;
    border-bottom: 1px solid #222;
    padding-bottom: 8px;
  }}
  h3 {{
    font-size: 17px;
    color: #ccc;
    margin: 24px 0 8px;
    font-weight: 600;
  }}
  p {{
    margin: 0 0 14px;
    color: #aaa;
    font-size: 15px;
  }}
  p.caption {{
    color: #666;
    font-size: 13px;
    margin: 8px 0 24px;
    line-height: 1.5;
    text-align: center;
    font-style: italic;
  }}
  strong {{ color: #e0e0e0; }}
  em {{ color: #bbb; }}
  hr {{
    border: none;
    border-top: 1px solid #222;
    margin: 32px 0;
  }}
  ul {{
    color: #aaa;
    margin: 0 0 14px;
    padding-left: 24px;
  }}
  li {{
    margin: 4px 0;
    font-size: 15px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 16px 0 24px;
    font-size: 14px;
  }}
  th {{
    text-align: left;
    padding: 10px 14px;
    background: #151515;
    color: #888;
    font-weight: 600;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    border-bottom: 1px solid #2a2a2a;
  }}
  td {{
    padding: 10px 14px;
    border-bottom: 1px solid #161616;
    color: #bbb;
  }}
  tr:hover td {{ background: #111; }}
  code {{
    font-family: 'SF Mono', Menlo, monospace;
    background: #1a1a1a;
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 13px;
    color: #f59e0b;
  }}
  .chart-block {{
    margin: 24px 0 8px;
    text-align: center;
  }}
  .chart-block img {{
    max-width: 100%;
    border: 1px solid #1a1a1a;
    border-radius: 4px;
  }}
  .chart-block.missing {{
    padding: 20px;
    background: #1a0a0a;
    color: #E84B5A;
    border-radius: 4px;
  }}

  /* Print-friendly */
  @media print {{
    body {{ background: white; color: #222; }}
    .container {{ padding: 20px; }}
    h1, h2, h3 {{ color: #000; }}
    p {{ color: #444; }}
    p.caption {{ color: #666; }}
    th {{ background: #eee; color: #444; }}
    td {{ color: #444; border-bottom-color: #eee; }}
    code {{ background: #eee; color: #c64; }}
    hr {{ border-top-color: #ddd; }}
    .chart-block img {{ border-color: #ccc; }}
  }}
</style>
</head>
<body>
<div class="container">
{content}
</div>
</body>
</html>
"""


def main():
    # Pick up the most recent macro_update_YYYY_MM.md in .cache/
    candidates = sorted(CACHE_DIR.glob("macro_update_*.md"))
    if not candidates:
        print(f"No macro_update_*.md found in {CACHE_DIR}")
        return
    md_file = candidates[-1]
    stem = md_file.stem  # e.g. macro_update_2026_05
    yyyy, mm = stem.split("_")[-2], stem.split("_")[-1]
    month_name = ["January","February","March","April","May","June","July","August","September","October","November","December"][int(mm)-1]
    title = f"Macro Update — {month_name} {yyyy}"

    with open(md_file) as f:
        md = f.read()

    print(f"Converting {md_file.name} to HTML...")
    content = md_to_html_basic(md)
    html = build_html(content, title)

    output = REPORTS_DIR / f"{stem}.html"
    with open(output, "w") as f:
        f.write(html)

    size_kb = output.stat().st_size / 1024
    print(f"Saved: {output} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
