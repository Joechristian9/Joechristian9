"""Generate a blue contribution heatmap SVG from the GitHub GraphQL API.

Usage: python3 scripts/gen_contrib.py [output_dir]   (needs GH_TOKEN and GH_USER)
       python3 scripts/gen_contrib.py [output_dir] --demo   (fake data, for previews)
"""
import json
import os
import random
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from xml.sax.saxutils import escape

OUT = next((a for a in sys.argv[1:] if not a.startswith("--")), "assets")
DEMO = "--demo" in sys.argv
USER = os.environ.get("GH_USER", "Joechristian9")
os.makedirs(OUT, exist_ok=True)

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount contributionLevel weekday } }
      }
    }
  }
}
"""
LEVELS = {"NONE": 0, "FIRST_QUARTER": 1, "SECOND_QUARTER": 2, "THIRD_QUARTER": 3, "FOURTH_QUARTER": 4}
COLORS = ["#13203F", "#0c2d6b", "#1d4ed8", "#3b82f6", "#93c5fd"]
MONO = "'JetBrains Mono','Fira Code','SF Mono',Menlo,Consolas,'DejaVu Sans Mono',monospace"


def fetch():
    token = os.environ["GH_TOKEN"]
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": USER}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json",
                 "User-Agent": "contrib-graph-generator"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    if data.get("errors"):
        raise SystemExit(f"GraphQL error: {data['errors']}")
    cal = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    return cal["totalContributions"], cal["weeks"]


def demo():
    random.seed(7)
    start = date.today() - timedelta(days=370)
    start -= timedelta(days=(start.weekday() + 1) % 7)
    weeks, d, total = [], start, 0
    while d <= date.today():
        days = []
        for _ in range(7):
            if d > date.today():
                break
            n = random.choice([0, 0, 0, 1, 2, 3, 5, 8, 12]) if random.random() < 0.45 else 0
            total += n
            lvl = 0 if n == 0 else 1 if n < 2 else 2 if n < 4 else 3 if n < 8 else 4
            days.append({"date": d.isoformat(), "contributionCount": n,
                         "contributionLevel": list(LEVELS)[lvl], "weekday": (d.weekday() + 1) % 7})
            d += timedelta(days=1)
        weeks.append({"contributionDays": days})
    return total, weeks


def level_fn(weeks):
    """Shade by quartiles of the non-zero daily counts (independent of the API's level field)."""
    counts = sorted(d["contributionCount"] for w in weeks for d in w["contributionDays"] if d["contributionCount"] > 0)
    if not counts:
        return lambda n: 0
    q = [counts[int(len(counts) * f)] if int(len(counts) * f) < len(counts) else counts[-1] for f in (0.25, 0.5, 0.75)]
    return lambda n: 0 if n <= 0 else 1 if n <= q[0] else 2 if n <= q[1] else 3 if n <= q[2] else 4


def render(total, weeks):
    lvl_of = level_fn(weeks)
    pitch, cell = 15, 12
    left, right, top = 44, 21, 62
    n = len(weeks)
    W = left + n * pitch + right
    H = top + 7 * pitch + 46

    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
         f'role="img" aria-label="{total} contributions in the last year">',
         '<style>.w{opacity:0;animation:in .5s ease-out forwards}@keyframes in{to{opacity:1}}</style>',
         f'<defs><clipPath id="grid"><rect x="{left - 2}" y="{top - 2}" width="{n * pitch + 2}" height="{7 * pitch + 2}"/></clipPath>'
         '<linearGradient id="scan" x1="0" x2="1" y1="0" y2="0">'
         '<stop offset="0" stop-color="#bfdbfe" stop-opacity="0"/>'
         '<stop offset="0.5" stop-color="#bfdbfe" stop-opacity="0.32"/>'
         '<stop offset="1" stop-color="#bfdbfe" stop-opacity="0"/></linearGradient></defs>',
         f'<rect width="{W}" height="{H}" rx="14" fill="#0A1224"/>',
         f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="14" fill="none" stroke="#1E3A6E"/>',
         f'<text x="22" y="30" font-family="{MONO}" font-size="14" font-weight="700" fill="#E6EDF3">'
         f'{total:,} contributions in the last year</text>',
         f'<text x="{W - 22}" y="30" text-anchor="end" font-family="{MONO}" font-size="12" fill="#60A5FA">'
         f'@{escape(USER)}</text>']

    s.append(f'<g font-family="{MONO}" font-size="10" fill="#7FA2D4">')
    for row, label in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        s.append(f'<text x="22" y="{top + row * pitch + 10}">{label}</text>')
    last_month, last_x = None, -100
    for i, wk in enumerate(weeks):
        days = wk["contributionDays"]
        if not days:
            continue
        month = date.fromisoformat(days[0]["date"]).strftime("%b")
        x = left + i * pitch
        if month != last_month and x - last_x >= 30:
            s.append(f'<text x="{x}" y="{top - 8}">{month}</text>')
            last_x = x
        last_month = month
    s.append('</g>')

    for i, wk in enumerate(weeks):
        s.append(f'<g class="w" style="animation-delay:{i * 0.025:.3f}s">')
        for d in wk["contributionDays"]:
            lvl = lvl_of(d["contributionCount"])
            x = left + i * pitch
            y = top + d["weekday"] * pitch
            twinkle = ""
            if lvl > 0:
                rnd = random.Random(i * 13 + d["weekday"])
                twinkle = (f'<animate attributeName="opacity" values="1;0.5;1" dur="{2.4 + rnd.random() * 2.6:.2f}s" '
                           f'begin="{2.0 + rnd.random() * 3:.2f}s" repeatCount="indefinite"/>')
            s.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2.5" fill="{COLORS[lvl]}">'
                     f'{twinkle}<title>{d["contributionCount"]} contributions on {d["date"]}</title></rect>')
        s.append('</g>')

    gw = n * pitch
    s.append(f'<g clip-path="url(#grid)"><rect x="{left}" y="{top - 2}" width="70" height="{7 * pitch + 2}" fill="url(#scan)">'
             f'<animateTransform attributeName="transform" type="translate" dur="7s" begin="2s" repeatCount="indefinite" '
             f'values="-70 0;{gw} 0;{gw} 0" keyTimes="0;0.55;1"/></rect></g>')
    last = weeks[-1]["contributionDays"][-1]
    rx_, ry_ = left + (n - 1) * pitch, top + last["weekday"] * pitch
    s.append(f'<rect x="{rx_ - 2}" y="{ry_ - 2}" width="{cell + 4}" height="{cell + 4}" rx="4" fill="none" '
             f'stroke="#93c5fd" stroke-width="1.5" opacity="0">'
             f'<animate attributeName="opacity" values="0;1;0" dur="2s" begin="2s" repeatCount="indefinite"/></rect>')

    ly = H - 22
    lx = W - 22 - 5 * pitch - 70
    s.append(f'<text x="{lx}" y="{ly + 10}" text-anchor="end" font-family="{MONO}" font-size="10" fill="#7FA2D4">Less</text>')
    for k, col in enumerate(COLORS):
        s.append(f'<rect x="{lx + 8 + k * pitch}" y="{ly}" width="{cell}" height="{cell}" rx="2.5" fill="{col}"/>')
    s.append(f'<text x="{lx + 8 + 5 * pitch + 4}" y="{ly + 10}" font-family="{MONO}" font-size="10" fill="#7FA2D4">More</text>')
    s.append('</svg>')
    return "\n".join(s)


total, weeks = demo() if DEMO else fetch()
svg = render(total, weeks)
ET.fromstring(svg)
name = "contributions-demo.svg" if DEMO else "contributions.svg"
with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
    f.write(svg)
print(f"{name}: {total} contributions, {len(weeks)} weeks, {len(svg)} bytes")
