#!/usr/bin/env python3
"""Render the neofetch-style profile card (dark_mode.svg / light_mode.svg).

Static profile facts live in PROFILE / SECTIONS below. Live numbers (uptime,
repos, stars, commits, followers, contributions) are pulled from the GitHub
GraphQL API when a token is available in $ACCESS_TOKEN or $GITHUB_TOKEN;
otherwise they render as "--" so the card can still be previewed locally.

Run from the repo root:  python3 profile/generate.py
"""

import datetime as dt
import json
import os
import urllib.request
from html import escape
from pathlib import Path

USER = "azzammasood"
ROOT = Path(__file__).resolve().parent.parent

WIDTH = 60  # characters in the right-hand info column

# Apache Iceberg, literally: the query is the tip above the waterline and the
# table format's metadata tree is everything underneath it.
ICEBERG = r"""
                  /\
                 /  \
                / .  \   /\
          /\   /      \_/  \
         /  \_/   .         \
~~~~~~~~/~~~~~~~~~~~~~~~~~~~~\~~~~~~~
  ~   ~/  SELECT * FROM lake  \ ~   ~
   ~  /           |            \   ~
     /      metadata.json       \
    |             |              \
    |       snap-0042.avro        |
    |        /    |    \          |
    |   m0.avro m1.avro m2.avro   |
     \     |      |      |       /
      |  00.parquet  01.parquet  |
      |  02.parquet  03.parquet  /
       \  04.parquet  05.parquet/
        \___                ___/
            \______________/
""".strip("\n").splitlines()

CAPTION = ["~90% of any lakehouse lives", "below the waterline."]

PROFILE = [
    ("Role", "Principal Data Engineer"),
    ("Host", "Nayatel"),
    ("Uptime", "{uptime}"),
    ("Kernel", "GCP + Apache Iceberg"),
    None,
    ("Languages.Programming", "Python, Go, SQL"),
    ("Languages.Frameworks", "FastAPI"),
    ("Stack.Streaming", "Kafka, Pub/Sub, Dataflow"),
    ("Stack.Storage", "BigQuery, Iceberg, ClickHouse, GCS"),
    ("Stack.Compute", "Spark (Serverless), Dataflow"),
    ("Stack.Orchestration", "Cloud Composer (Airflow)"),
    ("Stack.Infra", "Terraform, Docker, Cloud Build"),
    ("Stack.AI", "Vertex AI, RAG pipelines"),
]

SECTIONS = [
    ("Pipelines", [
        ("flight_intel", "Go → Kafka → ClickHouse"),
        ("lakehouse_migration", "Warehouse → GCS + Iceberg"),
        ("site_monitor", "2,500+ sites → Dataflow → alerts"),
        ("customer_360", "Serverless Spark + Composer"),
    ]),
    ("Certs", [
        ("GCP", "Batch & Streaming Pipelines, Smart"),
        ("", "Analytics, ML & AI on Google Cloud"),
        ("IBM", "Data Engineering"),
        ("Go", "Getting Started with Google Go"),
        ("Education", "BSc Computer Engineering, COMSATS"),
    ]),
    ("Contact", [
        ("Email", "ahmaduzzammasood@gmail.com"),
        ("LinkedIn", "in/ahmaduzzammasood"),
    ]),
    ("GitHub Stats", "stats"),
]

THEMES = {
    "dark": dict(bg="#161b22", fg="#c9d1d9", key="#ffa657", val="#a5d6ff",
                 dim="#616e7f", cap="#8b949e", ice="#e6edf3", water="#58a6ff", label="#7ee787",
                 add="#3fb950", border="#30363d"),
    "light": dict(bg="#f6f8fa", fg="#24292f", key="#953800", val="#0a3069",
                  dim="#c2cfde", cap="#6e7781", ice="#57606a", water="#0969da", label="#1a7f37",
                  add="#1a7f37", border="#d0d7de"),
}

FONT_SIZE = 15
LINE_H = 20
CHAR_W = 9.05  # approx advance of 15px monospace; only used for layout width
ART_X = 20
INFO_X = ART_X + 40 * CHAR_W + 30


# --------------------------------------------------------------- GitHub data

def graphql(token, query, variables=None):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Authorization": f"bearer {token}", "User-Agent": USER},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.load(resp)
    if "errors" in body:
        raise RuntimeError(body["errors"])
    return body["data"]


def fetch_stats():
    token = os.environ.get("ACCESS_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        return None

    data = graphql(token, """
    query($login: String!) {
      user(login: $login) {
        createdAt
        followers { totalCount }
        repositoriesContributedTo(contributionTypes: [COMMIT, PULL_REQUEST, REPOSITORY]) { totalCount }
        contributionsCollection { contributionCalendar { totalContributions } }
        repositories(ownerAffiliations: OWNER, first: 100, isFork: false) {
          totalCount
          nodes { stargazerCount }
        }
      }
    }""", {"login": USER})["user"]

    created = dt.datetime.fromisoformat(data["createdAt"].replace("Z", "+00:00"))
    now = dt.datetime.now(dt.timezone.utc)

    # contributionsCollection spans at most one year, so walk year by year.
    commits = 0
    start = created
    while start < now:
        end = min(start + dt.timedelta(days=365), now)
        year = graphql(token, """
        query($login: String!, $from: DateTime!, $to: DateTime!) {
          user(login: $login) {
            contributionsCollection(from: $from, to: $to) {
              totalCommitContributions
              restrictedContributionsCount
            }
          }
        }""", {"login": USER, "from": start.isoformat(), "to": end.isoformat()})
        cc = year["user"]["contributionsCollection"]
        commits += cc["totalCommitContributions"] + cc["restrictedContributionsCount"]
        start = end

    return {
        "created": created,
        "repos": data["repositories"]["totalCount"],
        "contributed": data["repositoriesContributedTo"]["totalCount"],
        "stars": sum(n["stargazerCount"] for n in data["repositories"]["nodes"]),
        "followers": data["followers"]["totalCount"],
        "commits": commits,
        "contribs": data["contributionsCollection"]["contributionCalendar"]["totalContributions"],
    }


def uptime(since, today):
    years = today.year - since.year
    months = today.month - since.month
    days = today.day - since.day
    if days < 0:
        months -= 1
        prev_month_end = today.replace(day=1) - dt.timedelta(days=1)
        days += prev_month_end.day
    if months < 0:
        years -= 1
        months += 12
    plural = lambda n, w: f"{n} {w}{'' if n == 1 else 's'}"
    return ", ".join([plural(years, "year"), plural(months, "month"), plural(days, "day")])


# ------------------------------------------------------------------ layout

def span(text, cls):
    return f'<tspan class="{cls}">{escape(text)}</tspan>'


def kv(key, value, width=WIDTH):
    """'. Key: ....... value' with the value right-aligned to `width`."""
    if not key:
        return span(" " * (width - len(value)), "dim") + span(value, "val")
    head = f"{key}:"
    dots = width - len(head) - len(value) - 4
    return (span(". ", "dim") + span(head, "key") + " "
            + span("." * max(dots, 1), "dim") + " " + span(value, "val"))


def rule(title, width=WIDTH):
    head = f"- {title} "
    return span(head, "fg") + span("─" * (width - len(head)), "dim")


def stat_pair(k1, v1, k2, v2, width=WIDTH):
    """Two key/value pairs on one line, split with a pipe at a fixed column."""
    left_w = 30
    left = f"{k1}: "
    right = f"{k2}: "
    ldots = left_w - len(left) - len(v1) - 3
    rdots = width - left_w - 3 - len(right) - len(v2) - 1
    return (span(". ", "dim") + span(left, "key") + span("." * ldots, "dim") + " "
            + span(v1, "val") + span(" | ", "dim") + span(right, "key")
            + span("." * rdots, "dim") + " " + span(v2, "val"))


def info_lines(stats, today):
    fmt = lambda n: f"{n:,}" if stats else "--"
    g = stats or {}
    up = uptime(g["created"], today) if stats else "-- years, -- months, -- days"

    lines = [span("ahmad", "key") + span("@", "fg") + span("lakehouse", "key")
             + " " + span("─" * (WIDTH - 16), "dim")]
    for row in PROFILE:
        lines.append("" if row is None else kv(row[0], row[1].format(uptime=up)))

    for title, rows in SECTIONS:
        lines.append("")
        lines.append(rule(title))
        if rows == "stats":
            lines.append(stat_pair("Repos", fmt(g.get("repos")), "Stars", fmt(g.get("stars"))))
            lines.append(stat_pair("Contributed", fmt(g.get("contributed")),
                                   "Followers", fmt(g.get("followers"))))
            lines.append(stat_pair("Commits", fmt(g.get("commits")),
                                   "Last 12mo", fmt(g.get("contribs"))))
        else:
            lines.extend(kv(k, v) for k, v in rows)

    stamp = today.strftime("%Y-%m-%d")
    lines.append("")
    lines.append(span("$ ", "add") + span(f"last_ingested={stamp} ", "fg")
                 + span("-- partition refreshed daily", "dim")
                 + '<tspan class="cursor">█</tspan>')
    return lines


def art_line(line):
    """Colour water, labels and ice separately within one row of the art."""
    out, buf, cls = [], "", None
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "~":
            c = "water"
        elif ch.isalnum() or (ch in ".-_*" and _in_word(line, i)):
            c = "label"
        else:
            c = "ice"
        if c != cls and buf:
            out.append(span(buf, cls))
            buf = ""
        cls = c
        buf += ch
        i += 1
    if buf:
        out.append(span(buf, cls))
    return "".join(out)


def _in_word(line, i):
    """True when a punctuation char sits between alphanumerics (e.g. m0.avro)."""
    left = line[:i].rstrip(".-_*")
    right = line[i + 1:].lstrip(".-_*")
    return bool(left) and bool(right) and left[-1].isalnum() and right[0].isalnum()


def render(theme, stats, today):
    c = THEMES[theme]
    info = info_lines(stats, today)
    rows = max(len(info), len(ICEBERG) + len(CAPTION) + 1)
    height = rows * LINE_H + 40
    width = int(INFO_X + WIDTH * CHAR_W + 25)

    art_top = 30 + (rows - len(ICEBERG) - len(CAPTION) - 1) * LINE_H // 2
    parts = []
    for n, line in enumerate(ICEBERG):
        parts.append(f'<tspan x="{ART_X}" y="{art_top + n * LINE_H}">{art_line(line)}</tspan>')
    for n, line in enumerate(CAPTION):
        y = art_top + (len(ICEBERG) + 1 + n) * LINE_H
        parts.append(f'<tspan x="{ART_X}" y="{y}" class="cap">{escape(line.center(37))}</tspan>')
    for n, line in enumerate(info):
        parts.append(f'<tspan x="{INFO_X:.0f}" y="{30 + n * LINE_H}">{line}</tspan>')

    body = "\n".join(parts)
    return f"""<?xml version='1.0' encoding='UTF-8'?>
<svg xmlns="http://www.w3.org/2000/svg" font-family="ConsolasFallback,Consolas,'DejaVu Sans Mono',monospace" width="{width}px" height="{height}px" font-size="{FONT_SIZE}px">
<style>
.fg {{fill: {c['fg']};}}
.key {{fill: {c['key']};}}
.val {{fill: {c['val']};}}
.dim {{fill: {c['dim']};}}
.cap {{fill: {c['cap']}; font-style: italic;}}
.ice {{fill: {c['ice']};}}
.water {{fill: {c['water']};}}
.label {{fill: {c['label']};}}
.add {{fill: {c['add']};}}
.cursor {{fill: {c['fg']}; animation: blink 1.1s step-end infinite;}}
@keyframes blink {{ 50% {{ opacity: 0; }} }}
text, tspan {{white-space: pre;}}
</style>
<rect width="{width}px" height="{height}px" fill="{c['bg']}" rx="15" stroke="{c['border']}"/>
<text x="{ART_X}" y="30" fill="{c['fg']}" xml:space="preserve">
{body}
</text>
</svg>
"""


def main():
    today = dt.datetime.now(dt.timezone.utc)
    stats = fetch_stats()
    for theme in THEMES:
        (ROOT / f"{theme}_mode.svg").write_text(render(theme, stats, today), encoding="utf-8")
    print("rendered", "with live stats" if stats else "without stats (no token)")


if __name__ == "__main__":
    main()
