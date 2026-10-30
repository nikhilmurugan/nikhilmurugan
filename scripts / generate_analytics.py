
#!/usr/bin/env python3
"""Generate real GitHub analytics SVG cards using GitHub GraphQL."""

import json
import os
import sys
import urllib.request
import urllib.error
import html
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from collections import defaultdict

USERNAME = "nikhilmurugan"
TOKEN = os.environ.get("GH_ANALYTICS_TOKEN")

OUTPUT = Path("assets/analytics")
OUTPUT.mkdir(parents=True, exist_ok=True)

API_URL = "https://api.github.com/graphql"

BG = "#0B1220"
PANEL = "#111B2E"
BORDER = "#253858"
TEXT = "#E5EDFF"
MUTED = "#94A3B8"
BLUE = "#38BDF8"
PURPLE = "#A78BFA"
PINK = "#E879F9"
GREEN = "#34D399"
ORANGE = "#FB923C"

if not TOKEN:
    sys.exit("ERROR: GH_ANALYTICS_TOKEN is not configured.")


def graphql(query, variables=None):
    payload = json.dumps({
        "query": query,
        "variables": variables or {}
    }).encode("utf-8")

    request = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "nikhilmurugan-github-analytics"
        }
    )

    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"GitHub API HTTP {error.code}: {detail[:1000]}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"GitHub API connection failed: {error}") from error

    if result.get("errors"):
        raise RuntimeError(
            "GitHub GraphQL error: " +
            json.dumps(result["errors"])[:1500]
        )

    return result["data"]


def fetch_repositories():
    query = """
    query($login: String!, $cursor: String) {
      user(login: $login) {
        login
        name
        followers { totalCount }
        repositories(
          first: 100
          after: $cursor
          ownerAffiliations: OWNER
          privacy: PUBLIC
          isFork: false
          orderBy: {field: UPDATED_AT, direction: DESC}
        ) {
          totalCount
          pageInfo {
            hasNextPage
            endCursor
          }
          nodes {
            name
            stargazerCount
            forkCount
            languages(first: 20) {
              edges {
                size
                node { name }
              }
            }
          }
        }
      }
    }
    """

    repositories = []
    cursor = None
    profile = None

    while True:
        data = graphql(query, {
            "login": USERNAME,
            "cursor": cursor
        })

        user = data.get("user")
        if not user:
            raise RuntimeError(f"GitHub user not found: {USERNAME}")

        profile = user
        connection = user["repositories"]
        repositories.extend(connection["nodes"])

        page = connection["pageInfo"]
        if not page["hasNextPage"]:
            break

        cursor = page["endCursor"]

    return profile, repositories


def fetch_contributions():
    today = date.today()
    start = today - timedelta(days=364)

    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          totalCommitContributions
          totalIssueContributions
          totalPullRequestContributions
          totalPullRequestReviewContributions
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                date
                contributionCount
              }
            }
          }
        }
      }
    }
    """

    data = graphql(query, {
        "login": USERNAME,
        "from": f"{start.isoformat()}T00:00:00Z",
        "to": f"{today.isoformat()}T23:59:59Z"
    })

    user = data.get("user")
    if not user:
        raise RuntimeError("Unable to retrieve contribution data.")

    collection = user["contributionsCollection"]
    calendar = collection["contributionCalendar"]

    days = [
        day
        for week in calendar["weeks"]
        for day in week["contributionDays"]
    ]

    return collection, calendar, days


def calculate_streaks(days):
    counts = {
        date.fromisoformat(item["date"]): item["contributionCount"]
        for item in days
    }

    active_dates = sorted(
        day for day, count in counts.items() if count > 0
    )

    longest = 0
    current_run = 0
    previous = None

    for day in active_dates:
        if previous and day == previous + timedelta(days=1):
            current_run += 1
        else:
            current_run = 1

        longest = max(longest, current_run)
        previous = day

    today = date.today()
    latest_possible = today if counts.get(today, 0) else today - timedelta(days=1)

    current = 0
    cursor = latest_possible

    while counts.get(cursor, 0) > 0:
        current += 1
        cursor -= timedelta(days=1)

    return current, longest


def calculate_languages(repositories):
    totals = defaultdict(int)

    for repo in repositories:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            totals[name] += edge["size"]

    return sorted(
        totals.items(),
        key=lambda item: item[1],
        reverse=True
    )


def esc(value):
    return html.escape(str(value))


def svg_start(width, height, title, subtitle):
    return f'''<svg xmlns="http://www.w3.org/2000/svg"
      width="{width}" height="{height}" viewBox="0 0 {width} {height}">
      <defs>
        <linearGradient id="accent" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="{BLUE}"/>
          <stop offset="55%" stop-color="{PURPLE}"/>
          <stop offset="100%" stop-color="{PINK}"/>
        </linearGradient>
        <linearGradient id="panel" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#15243C"/>
          <stop offset="100%" stop-color="{PANEL}"/>
        </linearGradient>
      </defs>
      <rect width="100%" height="100%" rx="18" fill="{BG}"/>
      <text x="26" y="39" fill="{TEXT}" font-size="19"
        font-family="Arial,sans-serif" font-weight="bold">{esc(title)}</text>
      <text x="26" y="62" fill="{MUTED}" font-size="11"
        font-family="Arial,sans-serif">{esc(subtitle)}</text>
    '''


def card(x, y, width, height, label, value, color=BLUE):
    return f'''
      <rect x="{x}" y="{y}" width="{width}" height="{height}"
        rx="12" fill="url(#panel)" stroke="{BORDER}"/>
      <text x="{x+16}" y="{y+27}" fill="{MUTED}"
        font-size="12" font-family="Arial,sans-serif">{esc(label)}</text>
      <text x="{x+16}" y="{y+67}" fill="{color}"
        font-size="27" font-weight="bold"
        font-family="Arial,sans-serif">{esc(value)}</text>
    '''


def save_svg(name, content):
    path = OUTPUT / name
    path.write_text(content + "\n</svg>\n", encoding="utf-8")
    print(f"Generated {path}")


def generate_overview(profile, repositories, collection, calendar):
    stars = sum(repo["stargazerCount"] for repo in repositories)
    forks = sum(repo["forkCount"] for repo in repositories)

    content = svg_start(
        760, 235,
        "GitHub Overview",
        "Public repositories · Owner repositories · Live API snapshot"
    )

    values = [
        ("Repositories", len(repositories), BLUE),
        ("Stars", stars, PURPLE),
        ("Forks", forks, PINK),
        ("Followers", profile["followers"]["totalCount"], GREEN),
    ]

    for index, (label, value, color) in enumerate(values):
        content += card(
            24 + index * 183, 88, 170, 105,
            label, value, color
        )

    content += f'''
      <text x="26" y="218" fill="{MUTED}" font-size="10"
        font-family="Arial,sans-serif">
        {esc(profile["login"])} · Public, non-fork repositories only
      </text>
    '''

    save_svg("overview.svg", content)


def generate_languages(languages):
    content = svg_start(
        760, 370,
        "Language Distribution",
        "Based on language bytes in owned public, non-fork repositories"
    )

    total = sum(size for _, size in languages)
    selected = languages[:8]

    palette = [
        BLUE, PURPLE, PINK, GREEN,
        ORANGE, "#FACC15", "#60A5FA", "#C084FC"
    ]

    if total == 0:
        content += f'''
          <text x="30" y="130" fill="{MUTED}" font-size="14"
            font-family="Arial,sans-serif">
            No language data available.
          </text>
        '''
    else:
        for index, (name, size) in enumerate(selected):
            y = 100 + index * 32
            percentage = size / total * 100
            color = palette[index % len(palette)]

            content += f'''
              <text x="30" y="{y}" fill="{TEXT}" font-size="12"
                font-family="Arial,sans-serif">{esc(name)}</text>
              <rect x="200" y="{y-13}" width="420" height="10"
                rx="5" fill="#25334A"/>
              <rect x="200" y="{y-13}"
                width="{420 * percentage / 100:.2f}" height="10"
                rx="5" fill="{color}"/>
              <text x="690" y="{y}" fill="{color}" font-size="12"
                text-anchor="end" font-family="Arial,sans-serif">
                {percentage:.1f}%
              </text>
            '''

    save_svg("languages.svg", content)


def generate_contributions(calendar, days, current, longest):
    total = calendar["totalContributions"]

    content = svg_start(
        760, 215,
        "Contribution Summary",
        "GitHub contribution calendar · Last 365 days"
    )

    content += card(25, 85, 165, 95, "Contributions", total, BLUE)
    content += card(210, 85, 165, 95, "Current streak", current, GREEN)
    content += card(395, 85, 165, 95, "Longest streak", longest, PURPLE)
    content += card(580, 85, 155, 95, "Active days",
                    sum(1 for d in days if d["contributionCount"] > 0),
                    PINK)

    save_svg("contributions.svg", content)


def generate_activity(days):
    counts = defaultdict(int)

    for item in days:
        month = item["date"][:7]
        counts[month] += item["contributionCount"]

    months = sorted(counts)[-12:]
    maximum = max((counts[m] for m in months), default=0)

    content = svg_start(
        760, 270,
        "Monthly Contribution Activity",
        "Actual daily contribution counts grouped by calendar month"
    )

    for index, month in enumerate(months):
        x = 32 + index * 59
        value = counts[month]
        bar_height = (value / maximum * 115) if maximum else 0
        y = 190 - bar_height

        content += f'''
          <rect x="{x}" y="{y:.2f}" width="32"
            height="{bar_height:.2f}" rx="5" fill="url(#accent)"/>
          <text x="{x+16}" y="211" fill="{MUTED}" font-size="9"
            text-anchor="middle" font-family="Arial,sans-serif">
            {esc(month[5:])}
          </text>
          <text x="{x+16}" y="{max(85, y-8):.2f}" fill="{TEXT}"
            font-size="9" text-anchor="middle"
            font-family="Arial,sans-serif">{value}</text>
        '''

    save_svg("activity.svg", content)


def main():
    print(f"Fetching public GitHub data for {USERNAME}...")

    profile, repositories = fetch_repositories()
    collection, calendar, days = fetch_contributions()

    languages = calculate_languages(repositories)
    current, longest = calculate_streaks(days)

    metrics = {
        "username": USERNAME,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "public",
        "repository_filter": "owned public non-fork repositories",
        "repository_count": len(repositories),
        "stars": sum(r["stargazerCount"] for r in repositories),
        "forks": sum(r["forkCount"] for r in repositories),
        "followers": profile["followers"]["totalCount"],
        "contributions": calendar["totalContributions"],
        "commits": collection["totalCommitContributions"],
        "issues": collection["totalIssueContributions"],
        "pull_requests": collection["totalPullRequestContributions"],
        "pull_request_reviews":
            collection["totalPullRequestReviewContributions"],
        "current_streak_days": current,
        "longest_streak_days": longest,
        "languages": [
            {"name": name, "bytes": size}
            for name, size in languages
        ],
    }

    (OUTPUT / "metrics.json").write_text(
        json.dumps(metrics, indent=2),
        encoding="utf-8"
    )

    generate_overview(profile, repositories, collection, calendar)
    generate_languages(languages)
    generate_contributions(calendar, days, current, longest)
    generate_activity(days)

    print("Analytics generation completed successfully.")


if __name__ == "__main__":
    main()
