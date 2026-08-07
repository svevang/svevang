#!/usr/bin/env bash
set -euo pipefail

commit=false
if [[ "${1:-}" == "--commit" ]]; then
  commit=true
elif [[ $# -gt 0 ]]; then
  echo "usage: scripts/refresh_activity.sh [--commit]" >&2
  exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if ! command -v gh >/dev/null 2>&1; then
  echo "error: GitHub CLI is required: https://cli.github.com/" >&2
  exit 1
fi

if [[ -n "${GITHUB_TOKEN:-}" && -z "${GH_TOKEN:-}" ]]; then
  export GH_TOKEN="$GITHUB_TOKEN"
fi

if [[ -z "${GH_TOKEN:-}" ]] && ! gh auth status >/dev/null 2>&1; then
  echo "error: run 'gh auth login' or export GH_TOKEN before refreshing activity locally" >&2
  exit 1
fi

activity_since=$(python3 -c 'from datetime import datetime, timedelta, timezone; now = datetime.now(timezone.utc); start = (now - timedelta(weeks=11, days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0); print(start.isoformat().replace("+00:00", "Z"))')

gh api graphql -F activitySince="$activity_since" -f query='
  query($activitySince: DateTime!) {
    user(login: "svevang") {
      repositories(
        first: 10,
        orderBy: {field: PUSHED_AT, direction: DESC},
        privacy: PUBLIC
      ) {
        nodes {
          nameWithOwner
          url
          pushedAt
          description
          primaryLanguage { name }
          isPrivate
        }
      }
      contributionsCollection(from: $activitySince) {
        startedAt
        endedAt
        commitContributionsByRepository(maxRepositories: 100) {
          repository { nameWithOwner }
          contributions(
            first: 100,
            orderBy: {field: OCCURRED_AT, direction: ASC}
          ) {
            nodes {
              occurredAt
              commitCount
            }
          }
        }
      }
    }
  }' > activity.json

python scripts/render_activity.py activity.json README.md

if git diff --quiet README.md; then
  echo "No README.md changes."
  exit 0
fi

echo "Updated README.md from GitHub repositories."

if [[ "$commit" == true ]]; then
  git add README.md
  git commit -m "chore: refresh activity"
else
  echo "Review with: git diff README.md"
  echo "Commit with: git add README.md && git commit -m 'chore: refresh activity'"
  echo "Or run: scripts/refresh_activity.sh --commit"
fi
