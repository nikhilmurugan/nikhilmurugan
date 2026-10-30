
#!/usr/bin/env python3
"""Generate real GitHub profile analytics as SVG cards and JSON."""
import html, json, os, sys, urllib.error, urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

USERNAME = "nikhilmurugan"
TOKEN = os.environ.get("GH_ANALYTICS_TOKEN", "").strip()
OUT = Path("assets/analytics")
API = "https://api.github.com/graphql"
BG, PANEL, BORDER = "#0B1020", "#141D33", "#293754"
TEXT, MUTED = "#E8EEFF", "#9AAAC4"
COLORS = ["#55C2FF", "#A78BFA", "#F08BEA", "#53D6A5", "#FFB86B", "#FACC15"]

REPOS_QUERY = '''query($login:String!, $cursor:String){ user(login:$login){ login followers{totalCount} repositories(first:100,after:$cursor,ownerAffiliations:OWNER,privacy:PUBLIC,isFork:false,orderBy:{field:UPDATED_AT,direction:DESC}){ pageInfo{hasNextPage endCursor} nodes{name stargazerCount forkCount languages(first:20){edges{size node{name}}}} } } }'''
CONTRIB_QUERY = '''query($login:String!, $from:DateTime!, $to:DateTime!){ user(login:$login){ contributionsCollection(from:$from,to:$to){ totalCommitContributions totalIssueContributions totalPullRequestContributions totalPullRequestReviewContributions contributionCalendar{totalContributions weeks{contributionDays{date contributionCount}}} } } }'''

def esc(v): return html.escape(str(v), quote=True)

def gql(query, variables):
    if not TOKEN:
        raise RuntimeError("GH_ANALYTICS_TOKEN is missing. Add it in Settings > Secrets and variables > Actions.")
    payload = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(API, data=payload, headers={
        "Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json",
        "Content-Type": "application/json", "User-Agent": "github-profile-analytics"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            result = json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GitHub API HTTP {e.code}: {e.read().decode(errors='replace')[:1200]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"GitHub API connection failed: {e}") from e
    if result.get("errors"):
        messages = "; ".join(x.get("message", "Unknown GraphQL error") for x in result["errors"])
        raise RuntimeError(f"GitHub GraphQL error: {messages}. Check token validity and read:user access.")
    if not result.get("data"):
        raise RuntimeError("GitHub API returned no data.")
    return result["data"]

def fetch_repos():
    repos, cursor, profile = [], None, None
    while True:
        user = gql(REPOS_QUERY, {"login": USERNAME, "cursor": cursor}).get("user")
        if user is None: raise RuntimeError(f"GitHub user @{USERNAME} was not found.")
        profile = user
        conn = user["repositories"]
        repos.extend(conn["nodes"])
        page = conn["pageInfo"]
        if not page["hasNextPage"]: break
        cursor = page["endCursor"]
        if not cursor: raise RuntimeError("Repository pagination returned an empty cursor.")
    return profile, repos

def fetch_contributions():
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=364)
    data = gql(CONTRIB_QUERY, {"login": USERNAME, "from": f"{start}T00:00:00Z", "to": f"{today}T23:59:59Z"})
    user = data.get("user")
    if user is None: raise RuntimeError(f"GitHub user @{USERNAME} was not found.")
    collection = user["contributionsCollection"]
    calendar = collection["contributionCalendar"]
    days = [d for w in calendar["weeks"] for d in w["contributionDays"]]
    if not days: raise RuntimeError("GitHub returned an empty contribution calendar.")
    return collection, calendar, days

def streaks(days):
    counts = {date.fromisoformat(d["date"]): int(d["contributionCount"]) for d in days}
    active = sorted(d for d, n in counts.items() if n > 0)
    longest = run = 0; previous = None
    for d in active:
        run = run + 1 if previous and d == previous + timedelta(days=1) else 1
        longest = max(longest, run); previous = d
    today = datetime.now(timezone.utc).date()
    cursor = today if counts.get(today, 0) else today - timedelta(days=1)
    current = 0
    while counts.get(cursor, 0) > 0:
        current += 1; cursor -= timedelta(days=1)
    return current, longest

def svg_start(w, h, title, subtitle):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}"><defs><linearGradient id="accent" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="{COLORS[0]}"/><stop offset="55%" stop-color="{COLORS[1]}"/><stop offset="100%" stop-color="{COLORS[2]}"/></linearGradient><linearGradient id="panel"><stop offset="0%" stop-color="#1A2945"/><stop offset="100%" stop-color="{PANEL}"/></linearGradient></defs><rect width="100%" height="100%" rx="18" fill="{BG}"/><text x="26" y="38" fill="{TEXT}" font-size="19" font-family="Arial,sans-serif" font-weight="700">{esc(title)}</text><text x="26" y="60" fill="{MUTED}" font-size="11" font-family="Arial,sans-serif">{esc(subtitle)}</text>'''

def card(x, y, w, label, value, color):
    return f'''<rect x="{x}" y="{y}" width="{w}" height="94" rx="12" fill="url(#panel)" stroke="{BORDER}"/><text x="{x+14}" y="{y+27}" fill="{MUTED}" font-size="11" font-family="Arial,sans-serif">{esc(label)}</text><text x="{x+14}" y="{y+66}" fill="{color}" font-size="27" font-weight="700" font-family="Arial,sans-serif">{esc(value)}</text>'''

def save_svg(name, body):
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / name
    text = body + "\n</svg>\n"
    p.write_text(text, encoding="utf-8")
    if p.stat().st_size < 100 or not text.startswith("<svg") or not text.rstrip().endswith("</svg>"):
        raise RuntimeError(f"Invalid or empty SVG: {p}")
    print(f"Generated {p}: {p.stat().st_size} bytes")

def main():
    print(f"Fetching public GitHub data for @{USERNAME}...")
    profile, repos = fetch_repos()
    collection, calendar, days = fetch_contributions()
    lang_bytes = defaultdict(int)
    for repo in repos:
        for edge in repo["languages"]["edges"]:
            lang_bytes[edge["node"]["name"]] += int(edge["size"])
    languages = sorted(lang_bytes.items(), key=lambda x: x[1], reverse=True)
    current, longest = streaks(days)
    stars = sum(r["stargazerCount"] for r in repos)
    forks = sum(r["forkCount"] for r in repos)
    metrics = {
        "username": USERNAME, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "public data", "repository_scope": "owned public non-fork repositories",
        "repository_count": len(repos), "stars": stars, "forks": forks,
        "followers": profile["followers"]["totalCount"],
        "contributions_last_365_days": calendar["totalContributions"],
        "commits_last_365_days": collection["totalCommitContributions"],
        "issues_last_365_days": collection["totalIssueContributions"],
        "pull_requests_last_365_days": collection["totalPullRequestContributions"],
        "pull_request_reviews_last_365_days": collection["totalPullRequestReviewContributions"],
        "current_streak_days": current, "longest_streak_days": longest,
        "languages": [{"name": n, "bytes": b} for n, b in languages]}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    body = svg_start(760, 205, "GitHub Overview", "Owned public, non-fork repositories · Profile snapshot")
    for i, (label, value) in enumerate([("Repositories", len(repos)), ("Stars", stars), ("Forks", forks), ("Followers", metrics["followers"])]):
        body += card(24 + i*183, 82, 170, label, value, COLORS[i])
    body += f'<text x="26" y="195" fill="{MUTED}" font-size="10" font-family="Arial,sans-serif">@{esc(USERNAME)} · Public repositories only</text>'
    save_svg("overview.svg", body)
    body = svg_start(760, 360, "Language Distribution", "Language bytes across owned public, non-fork repositories")
    total = sum(b for _, b in languages)
    if total == 0:
        body += f'<text x="28" y="120" fill="{MUTED}" font-size="14">No language data returned for public repositories.</text>'
    else:
        for i, (name, size) in enumerate(languages[:8]):
            y, pct, color = 100 + i*31, size/total*100, COLORS[i % len(COLORS)]
            body += f'<text x="30" y="{y}" fill="{TEXT}" font-size="12">{esc(name)}</text><rect x="190" y="{y-13}" width="430" height="10" rx="5" fill="#26334A"/><rect x="190" y="{y-13}" width="{430*pct/100:.2f}" height="10" rx="5" fill="{color}"/><text x="710" y="{y}" text-anchor="end" fill="{color}" font-size="12">{pct:.1f}%</text>'
    save_svg("languages.svg", body)
    active = sum(1 for d in days if int(d["contributionCount"]) > 0)
    body = svg_start(760, 205, "Contribution Summary", "GitHub contribution calendar · Recent 365-day period")
    for i, (label, value, color) in enumerate([("Contributions", calendar["totalContributions"], COLORS[0]), ("Current streak", current, COLORS[3]), ("Longest streak", longest, COLORS[1]), ("Active days", active, COLORS[2])]):
        body += card(24 + i*183, 82, 170, label, value, color)
    save_svg("contributions.svg", body)
    monthly = defaultdict(int)
    for d in days: monthly[d["date"][:7]] += int(d["contributionCount"])
    months = sorted(monthly)[-12:]
    maximum = max((monthly[m] for m in months), default=0)
    body = svg_start(760, 270, "Monthly Contribution Activity", "Contribution calendar counts grouped by month")
    for i, month in enumerate(months):
        x, value = 30 + i*60, monthly[month]
        bh = value/maximum*118 if maximum else 0
        y = 195 - bh
        body += f'<rect x="{x}" y="{y:.1f}" width="34" height="{bh:.1f}" rx="5" fill="url(#accent)"/><text x="{x+17}" y="216" text-anchor="middle" fill="{MUTED}" font-size="9">{month[5:]}</text><text x="{x+17}" y="{max(83,y-8):.1f}" text-anchor="middle" fill="{TEXT}" font-size="9">{value}</text>'
    save_svg("activity.svg", body)
    expected = ["overview.svg", "languages.svg", "contributions.svg", "activity.svg", "metrics.json"]
    for name in expected:
        p = OUT / name
        if not p.is_file() or p.stat().st_size == 0: raise RuntimeError(f"Missing or empty output: {p}")
    json.loads((OUT / "metrics.json").read_text(encoding="utf-8"))
    print("SUCCESS: all five analytics files generated and validated.")

if __name__ == "__main__":
    try: main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
