
#!/usr/bin/env python3
"""Generate GitHub profile analytics as compact, responsive SVG cards and JSON."""

import html
import json
import os
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

USERNAME = "nikhilmurugan"
TOKEN = os.environ.get("GH_ANALYTICS_TOKEN", "").strip()
OUT = Path("assets/analytics")
API = "https://api.github.com/graphql"

BG = "#080F1D"
PANEL = "#101B30"
BORDER = "#263B60"
TEXT = "#F1F5FF"
MUTED = "#A6B5D0"
TRACK = "#263650"

COLORS = [
    "#38BDF8",
    "#A78BFA",
    "#E879F9",
    "#34D399",
    "#FBBF24",
    "#FB7185",
    "#60A5FA",
    "#2DD4BF",
]

REPOS_QUERY = """
query($login:String!, $cursor:String) {
  user(login:$login) {
    login
    followers { totalCount }
    repositories(
      first:100,
      after:$cursor,
      ownerAffiliations:OWNER,
      privacy:PUBLIC,
      isFork:false,
      orderBy:{field:UPDATED_AT,direction:DESC}
    ) {
      pageInfo { hasNextPage endCursor }
      nodes {
        name
        stargazerCount
        forkCount
        languages(first:20) {
          edges { size node { name } }
        }
      }
    }
  }
}
"""

CONTRIB_QUERY = """
query($login:String!, $from:DateTime!, $to:DateTime!) {
  user(login:$login) {
    contributionsCollection(from:$from,to:$to) {
      totalCommitContributions
      totalIssueContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays { date contributionCount }
        }
      }
    }
  }
}
"""


def esc(value):
    return html.escape(str(value), quote=True)


def gql(query, variables):
    if not TOKEN:
        raise RuntimeError(
            "GH_ANALYTICS_TOKEN is missing. Add it in "
            "Settings > Secrets and variables > Actions."
        )

    payload = json.dumps({
        "query": query,
        "variables": variables,
    }).encode()

    request = urllib.request.Request(
        API,
        data=payload,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "github-profile-analytics",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            result = json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")[:1200]
        raise RuntimeError(
            f"GitHub API HTTP {error.code}: {detail}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError(
            f"GitHub API connection failed: {error}"
        ) from error

    if result.get("errors"):
        messages = "; ".join(
            item.get("message", "Unknown GraphQL error")
            for item in result["errors"]
        )
        raise RuntimeError(f"GitHub GraphQL error: {messages}")

    if not result.get("data"):
        raise RuntimeError("GitHub API returned no data.")

    return result["data"]


def fetch_repos():
    repos = []
    cursor = None
    profile = None

    while True:
        user = gql(
            REPOS_QUERY,
            {"login": USERNAME, "cursor": cursor},
        ).get("user")

        if user is None:
            raise RuntimeError(f"GitHub user @{USERNAME} was not found.")

        profile = user
        connection = user["repositories"]
        repos.extend(connection["nodes"])

        page = connection["pageInfo"]
        if not page["hasNextPage"]:
            break

        cursor = page["endCursor"]
        if not cursor:
            raise RuntimeError("Repository pagination returned an empty cursor.")

    return profile, repos


def fetch_contributions():
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=364)

    data = gql(
        CONTRIB_QUERY,
        {
            "login": USERNAME,
            "from": f"{start}T00:00:00Z",
            "to": f"{today}T23:59:59Z",
        },
    )

    user = data.get("user")
    if user is None:
        raise RuntimeError(f"GitHub user @{USERNAME} was not found.")

    collection = user["contributionsCollection"]
    calendar = collection["contributionCalendar"]

    days = [
        day
        for week in calendar["weeks"]
        for day in week["contributionDays"]
    ]

    if not days:
        raise RuntimeError("GitHub returned an empty contribution calendar.")

    return collection, calendar, days


def streaks(days):
    counts = {
        date.fromisoformat(day["date"]): int(day["contributionCount"])
        for day in days
    }

    active_dates = sorted(
        day for day, count in counts.items() if count > 0
    )

    longest = 0
    run = 0
    previous = None

    for current_date in active_dates:
        if previous and current_date == previous + timedelta(days=1):
            run += 1
        else:
            run = 1

        longest = max(longest, run)
        previous = current_date

    today = datetime.now(timezone.utc).date()
    cursor = today if counts.get(today, 0) else today - timedelta(days=1)

    current = 0
    while counts.get(cursor, 0) > 0:
        current += 1
        cursor -= timedelta(days=1)

    return current, longest


def svg_start(width, height, title, subtitle):
    return f"""<svg xmlns="http://www.w3.org/2000/svg"
    width="{width}" height="{height}"
    viewBox="0 0 {width} {height}"
    role="img" aria-label="{esc(title)}">
    <defs>
      <linearGradient id="accent" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#38BDF8"/>
        <stop offset="52%" stop-color="#818CF8"/>
        <stop offset="100%" stop-color="#E879F9"/>
      </linearGradient>
      <linearGradient id="panel" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#142440"/>
        <stop offset="100%" stop-color="#0D172A"/>
      </linearGradient>
      <linearGradient id="bar" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0%" stop-color="#38BDF8"/>
        <stop offset="100%" stop-color="#A78BFA"/>
      </linearGradient>
    </defs>

    <rect width="100%" height="100%" rx="16" fill="{BG}"/>
    <rect x="1" y="1" width="{width - 2}" height="{height - 2}"
          rx="15" fill="none" stroke="{BORDER}" stroke-width="1"/>

    <text x="26" y="38" fill="{TEXT}"
          font-size="21" font-family="Arial,sans-serif"
          font-weight="700">{esc(title)}</text>

    <text x="26" y="61" fill="{MUTED}"
          font-size="11" font-family="Arial,sans-serif">
          {esc(subtitle)}
    </text>
    """


def svg_end(body):
    return body + "\n</svg>\n"


def save_svg(name, body):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    content = svg_end(body)

    path.write_text(content, encoding="utf-8")

    if (
        path.stat().st_size < 100
        or not content.lstrip().startswith("<svg")
        or not content.rstrip().endswith("</svg>")
    ):
        raise RuntimeError(f"Invalid or empty SVG: {path}")

    print(f"Generated {path}: {path.stat().st_size} bytes")


def stat_card(x, y, width, height, label, value, color):
    return f"""
    <rect x="{x}" y="{y}" width="{width}" height="{height}"
          rx="12" fill="url(#panel)" stroke="{BORDER}"/>

    <rect x="{x + 1}" y="{y + 1}" width="3" height="{height - 2}"
          rx="2" fill="{color}"/>

    <text x="{x + 17}" y="{y + 29}" fill="{MUTED}"
          font-size="12" font-family="Arial,sans-serif">
          {esc(label)}
    </text>

    <text x="{x + 17}" y="{y + 66}" fill="{color}"
          font-size="28" font-weight="700"
          font-family="Arial,sans-serif">
          {esc(value)}
    </text>
    """


def make_overview(repos, stars, forks, followers):
    width, height = 620, 180

    body = svg_start(
        width,
        height,
        "GitHub Overview",
        "Public repository statistics · Profile snapshot",
    )

    stats = [
        ("Repositories", len(repos), COLORS[0]),
        ("Stars Earned", stars, COLORS[1]),
        ("Forks", forks, COLORS[2]),
        ("Followers", followers, COLORS[3]),
    ]

    card_width = 133
    card_height = 82
    gap = 10
    start_x = 22

    for index, (label, value, color) in enumerate(stats):
        x = start_x + index * (card_width + gap)
        body += stat_card(
            x, 78, card_width, card_height, label, value, color
        )

    body += f"""
    <text x="24" y="174" fill="{MUTED}"
          font-size="10" font-family="Arial,sans-serif">
          @{esc(USERNAME)} · Owned public repositories
    </text>
    """

    save_svg("overview.svg", body)


def make_languages(languages):
    width, height = 620, 280

    body = svg_start(
        width,
        height,
        "Language Distribution",
        "Programming languages across owned public repositories",
    )

    total = sum(size for _, size in languages)

    if total <= 0:
        body += f"""
        <text x="28" y="125" fill="{MUTED}"
              font-size="14" font-family="Arial,sans-serif">
              No language data available.
        </text>
        """
    else:
        chart_x = 175
        chart_width = 355
        row_start = 98
        row_gap = 22

        for index, (name, size) in enumerate(languages[:8]):
            y = row_start + index * row_gap
            percentage = size / total * 100
            bar_width = chart_width * percentage / 100
            color = COLORS[index % len(COLORS)]

            body += f"""
            <text x="26" y="{y}" fill="{TEXT}"
                  font-size="12" font-family="Arial,sans-serif">
                  {esc(name)}
            </text>

            <rect x="{chart_x}" y="{y - 11}"
                  width="{chart_width}" height="9"
                  rx="5" fill="{TRACK}"/>

            <rect x="{chart_x}" y="{y - 11}"
                  width="{bar_width:.2f}" height="9"
                  rx="5" fill="{color}"/>

            <text x="585" y="{y}" text-anchor="end"
                  fill="{color}" font-size="11"
                  font-family="Arial,sans-serif">
                  {percentage:.1f}%
            </text>
            """

    save_svg("languages.svg", body)


def make_contribution_summary(calendar, current, longest, days):
    width, height = 620, 180

    active_days = sum(
        1 for day in days if int(day["contributionCount"]) > 0
    )

    body = svg_start(
        width,
        height,
        "Contribution Summary",
        "GitHub contribution calendar · Recent 365-day period",
    )

    stats = [
        ("Contributions", calendar["totalContributions"], COLORS[0]),
        ("Current Streak", current, COLORS[3]),
        ("Longest Streak", longest, COLORS[1]),
        ("Active Days", active_days, COLORS[2]),
    ]

    card_width = 133
    card_height = 82
    gap = 10

    for index, (label, value, color) in enumerate(stats):
        x = 22 + index * (card_width + gap)
        body += stat_card(
            x, 78, card_width, card_height, label, value, color
        )

    save_svg("contributions.svg", body)


def make_activity(days):
    width, height = 1240, 290

    body = svg_start(
        width,
        height,
        "Monthly Contribution Activity",
        "Contribution calendar counts grouped by month · Recent 12 months",
    )

    monthly = defaultdict(int)

    for day in days:
        monthly[day["date"][:7]] += int(day["contributionCount"])

    months = sorted(monthly)[-12:]
    maximum = max((monthly[month] for month in months), default=0)

    chart_left = 42
    chart_right = 1198
    chart_top = 91
    chart_bottom = 218
    chart_height = chart_bottom - chart_top

    body += f"""
    <line x1="{chart_left}" y1="{chart_bottom}"
          x2="{chart_right}" y2="{chart_bottom}"
          stroke="{BORDER}" stroke-width="1"/>
    """

    slot_width = (chart_right - chart_left) / max(len(months), 1)
    bar_width = 48

    for index, month in enumerate(months):
        value = monthly[month]
        bar_height = (
            value / maximum * chart_height if maximum else 0
        )

        x = chart_left + index * slot_width + (slot_width - bar_width) / 2
        y = chart_bottom - bar_height
        center = x + bar_width / 2

        body += f"""
        <rect x="{x:.1f}" y="{y:.1f}"
              width="{bar_width}" height="{max(bar_height, 2):.1f}"
              rx="7" fill="url(#accent)"/>

        <text x="{center:.1f}" y="{max(y - 10, 78):.1f}"
              text-anchor="middle" fill="{TEXT}"
              font-size="11" font-family="Arial,sans-serif">
              {value}
        </text>

        <text x="{center:.1f}" y="244"
              text-anchor="middle" fill="{MUTED}"
              font-size="11" font-family="Arial,sans-serif">
              {esc(date.fromisoformat(month + "-01").strftime("%b"))}
        </text>
        """

    total = sum(monthly.values())

    body += f"""
    <text x="1190" y="48" text-anchor="end"
          fill="{MUTED}" font-size="11"
          font-family="Arial,sans-serif">
          Total Contributions
    </text>

    <text x="1190" y="76" text-anchor="end"
          fill="#38BDF8" font-size="25"
          font-weight="700" font-family="Arial,sans-serif">
          {total}
    </text>
    """

    save_svg("activity.svg", body)


def main():
    print(f"Fetching public GitHub data for @{USERNAME}...")

    profile, repos = fetch_repos()
    collection, calendar, days = fetch_contributions()

    language_bytes = defaultdict(int)

    for repo in repos:
        for edge in repo["languages"]["edges"]:
            language_bytes[edge["node"]["name"]] += int(edge["size"])

    languages = sorted(
        language_bytes.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    current, longest = streaks(days)

    stars = sum(repo["stargazerCount"] for repo in repos)
    forks = sum(repo["forkCount"] for repo in repos)
    followers = profile["followers"]["totalCount"]

    metrics = {
        "username": USERNAME,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "public data",
        "repository_scope": "owned public non-fork repositories",
        "repository_count": len(repos),
        "stars": stars,
        "forks": forks,
        "followers": followers,
        "contributions_last_365_days": calendar["totalContributions"],
        "commits_last_365_days": collection["totalCommitContributions"],
        "issues_last_365_days": collection["totalIssueContributions"],
        "pull_requests_last_365_days": collection["totalPullRequestContributions"],
        "pull_request_reviews_last_365_days": collection[
            "totalPullRequestReviewContributions"
        ],
        "current_streak_days": current,
        "longest_streak_days": longest,
        "languages": [
            {"name": name, "bytes": size}
            for name, size in languages
        ],
    }

    OUT.mkdir(parents=True, exist_ok=True)

    (OUT / "metrics.json").write_text(
        json.dumps(metrics, indent=2) + "\n",
        encoding="utf-8",
    )

    make_overview(repos, stars, forks, followers)
    make_languages(languages)
    make_contribution_summary(calendar, current, longest, days)
    make_activity(days)

    expected = [
        "overview.svg",
        "languages.svg",
        "contributions.svg",
        "activity.svg",
        "metrics.json",
    ]

    for name in expected:
        path = OUT / name
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"Missing or empty output: {path}")

    json.loads(
        (OUT / "metrics.json").read_text(encoding="utf-8")
    )

    print("SUCCESS: all five analytics files generated and validated.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
