#!/usr/bin/env python3
"""Render GitHub repository JSON into a README template.

Usage: render_activity.py <activity.json> [README.md] [README.md.template]

Reads the GraphQL response from `gh api graphql ...`, formats the repo list
and weekly commit activity as a markdown table, and substitutes it into a
whole-document template.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from string import Template


USAGE = (
    "usage: render_activity.py <activity.json> [README.md] "
    "[README.md.template]"
)
TEMPLATE_FIELDS = {"repository_table", "updated_at"}
ACTIVITY_WEEKS = 12
ACTIVITY_LEVELS = "▂▃▄▅▆▇█"


def public_repos(nodes: list[dict | None]) -> list[dict]:
    return [
        n
        for n in nodes
        if isinstance(n, dict)
        and not n.get("isPrivate")
        and n.get("nameWithOwner")
        and n.get("url")
    ]


def format_pushed(pushed: str | None) -> str:
    if not pushed:
        return "No pushes yet"
    return pushed.replace("T", " ").rstrip("Z") + " UTC"


def contribution_activity(owner: dict) -> tuple[str | None, dict[str, list[dict]]]:
    collection = owner.get("contributionsCollection") or {}
    by_repository = {}
    for group in collection.get("commitContributionsByRepository") or []:
        repository = group.get("repository") or {}
        name = repository.get("nameWithOwner")
        if not name:
            continue
        contributions = group.get("contributions") or {}
        by_repository[name] = contributions.get("nodes") or []
    return collection.get("startedAt"), by_repository


def weekly_counts(contributions: list[dict], started_at: str | None) -> list[int]:
    counts = [0] * ACTIVITY_WEEKS
    if not started_at:
        return counts

    start = datetime.fromisoformat(started_at.replace("Z", "+00:00")).date()
    for contribution in contributions:
        occurred_at = contribution.get("occurredAt")
        if not occurred_at:
            continue
        occurred = datetime.fromisoformat(
            occurred_at.replace("Z", "+00:00")
        ).date()
        week = (occurred - start).days // 7
        if 0 <= week < ACTIVITY_WEEKS:
            counts[week] += int(contribution.get("commitCount") or 0)
    return counts


def render_histogram(counts: list[int], maximum: int) -> str:
    bars = []
    for count in counts:
        if count <= 0 or maximum <= 0:
            bars.append("▁")
            continue
        level = min(
            len(ACTIVITY_LEVELS) - 1,
            (count * len(ACTIVITY_LEVELS) - 1) // maximum,
        )
        bars.append(ACTIVITY_LEVELS[level])
    return "".join(bars)


def render_table(
    repos: list[dict],
    activity_started_at: str | None = None,
    activity_by_repository: dict[str, list[dict]] | None = None,
) -> str:
    if not repos:
        return "_No repositories._"

    activity_by_repository = activity_by_repository or {}
    repo_counts = {
        repo["nameWithOwner"]: weekly_counts(
            activity_by_repository.get(repo["nameWithOwner"], []),
            activity_started_at,
        )
        for repo in repos
    }
    maximum = max((max(counts) for counts in repo_counts.values()), default=0)

    lines = [
        "_Your commits by week, oldest → newest._",
        "",
        "| Repo | Language | Activity (12 weeks) | Last pushed |",
        "| --- | --- | --- | --- |",
    ]
    for repo in repos:
        name = repo["nameWithOwner"].replace("|", "\\|")
        url = repo["url"]
        language = ((repo.get("primaryLanguage") or {}).get("name") or "—").replace(
            "|", "\\|"
        )
        pushed = format_pushed(repo.get("pushedAt"))
        counts = repo_counts[repo["nameWithOwner"]]
        histogram = render_histogram(counts, maximum)
        lines.append(
            f"| [{name}]({url}) | {language} | `{histogram}` | {pushed} |"
        )
    return "\n".join(lines)


def render_readme(
    template_text: str,
    repos: list[dict],
    updated_at: str,
    activity_started_at: str | None = None,
    activity_by_repository: dict[str, list[dict]] | None = None,
) -> str:
    template = Template(template_text)
    if not template.is_valid():
        raise ValueError("invalid template placeholder; escape literal '$' as '$$'")

    fields = template.get_identifiers()
    missing = TEMPLATE_FIELDS - set(fields)
    unknown = set(fields) - TEMPLATE_FIELDS
    if missing:
        raise ValueError(f"missing template field(s): {', '.join(sorted(missing))}")
    if unknown:
        raise ValueError(f"unknown template field(s): {', '.join(sorted(unknown))}")

    return template.substitute(
        repository_table=render_table(
            repos,
            activity_started_at,
            activity_by_repository,
        ),
        updated_at=updated_at,
    )


def main() -> None:
    if len(sys.argv) not in (2, 3, 4):
        raise SystemExit(USAGE)

    activity_path = Path(sys.argv[1])
    readme_path = Path(sys.argv[2]) if len(sys.argv) >= 3 else Path("README.md")
    template_path = (
        Path(sys.argv[3])
        if len(sys.argv) == 4
        else readme_path.with_name(f"{readme_path.name}.template")
    )

    data = json.loads(activity_path.read_text())
    owner = data["data"].get("user") or data["data"].get("viewer")
    repos = owner.get("repositories") or owner.get("repositoriesContributedTo")
    nodes = repos["nodes"]
    activity_started_at, activity_by_repository = contribution_activity(owner)

    try:
        readme = render_readme(
            template_path.read_text(),
            public_repos(nodes),
            datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            activity_started_at,
            activity_by_repository,
        )
    except ValueError as error:
        raise SystemExit(f"{template_path}: {error}") from error
    readme_path.write_text(readme)


if __name__ == "__main__":
    main()
