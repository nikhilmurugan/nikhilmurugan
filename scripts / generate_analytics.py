#!/usr/bin/env python3
"""Generate validated GitHub analytics cards for the nikhilmurugan profile."""

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
API_URL = "https://api.github.com/graphql"
OUTPUT = Path("assets/analytics")
OUTPUT.mkdir(parents=True, exist_ok=True)

BG, PANEL, BORDER = "#0B1220", "#111B2E", "#253858"
TEXT, MUTED = "#E5EDFF", "#94A3B8"
BLUE, PURPLE, PINK, GREEN, ORANGE = "#38BDF8", "#A78BFA", "#E879F9", "#34D399", "#FB923C"


def graphql(query, variables=None):
    if not TOKEN:
        raise RuntimeError("GH_ANALYTICS_TOKEN is missing. Add it as a repository Actions secret.")
    payload = json.dumps({"query": query, "variables": variables or {}}).encode()
    request = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
            "User-Agent": "nikhilmurugan-github-analytics",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub GraphQL HTTP {exc.code}: {detail[:1200]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Cannot connect to GitHub GraphQL API: {exc}") from exc
    if result.get("errors"):
        raise RuntimeError("GitHub GraphQL returned errors: " + json.dumps(result["errors"])[:2000])
    if "data" not in result or result["data"] is None:
        raise RuntimeError("GitHub GraphQL returned no data. Check token permissions and API response.")
    return result["data"]


REPOSITORIES_QUERY = """
query($login: String!, $cursor: String) {
  viewer { login }
  user(login: $login) {
    login
    followers { totalCount }
    repositories(first: 100, after: $cursor, ownerAffiliations: OWNER,
      privacy: PUBLIC, isFork: false, orderBy: {field: UPDATED_AT, direction: DESC}) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        name
        stargazerCount
        forkCount
        languages(first: 20) { edges { size node { name } } }
      }
    }
  }
}
"""

CONTRIBUTIONS_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalIssueContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      restrictedContributionsCount
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


def fetch_repositories():
    repos, cursor, profile = [], None, None
    while True:
