#!/usr/bin/env python3
"""Update the Recent public activity section in the profile README.

Uses GitHub's public events endpoint and only Python's standard library.
No personal access token or third-party dependency is required.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

USERNAME = os.environ.get("GITHUB_USERNAME", "hvt299")
README_PATH = Path(os.environ.get("README_PATH", "README.md"))
START_MARKER = "<!-- recent-activity:start -->"
END_MARKER = "<!-- recent-activity:end -->"
MAX_ITEMS = 5


def clean_markdown(value: object) -> str:
    """Make API-provided text safe for a Markdown label or inline snippet."""
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    return re.sub(r"[\[\]`<>]", "", text)


def event_date(event: dict) -> str:
    raw = event.get("created_at", "")
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except (AttributeError, ValueError):
        return "recently"


def format_event(event: dict) -> str | None:
    event_type = event.get("type", "")
    repo = event.get("repo") or {}
    repo_name = clean_markdown(repo.get("name", ""))
    if not repo_name:
        return None

    repo_url = f"https://github.com/{repo_name}"
    payload = event.get("payload") or {}
    date = event_date(event)

    if event_type == "PushEvent":
        commits = payload.get("commits") or []
        count = payload.get("size") or len(commits) or 1
        label = "commit" if count == 1 else "commits"
        message = f"Pushed **{count} {label}** to [{repo_name}]({repo_url})"
    elif event_type == "PullRequestEvent":
        action = clean_markdown(payload.get("action", "updated"))
        pr = payload.get("pull_request") or {}
        number = pr.get("number") or payload.get("number")
        pr_url = pr.get("html_url") or repo_url
        target = f"{repo_name}#{number}" if number else repo_name
        message = f"Pull request {action}: [{clean_markdown(target)}]({pr_url})"
    elif event_type == "PullRequestReviewEvent":
        pr = payload.get("pull_request") or {}
        number = pr.get("number")
        pr_url = pr.get("html_url") or repo_url
        target = f"{repo_name}#{number}" if number else repo_name
        message = f"Reviewed a pull request in [{clean_markdown(target)}]({pr_url})"
    elif event_type == "IssuesEvent":
        action = clean_markdown(payload.get("action", "updated"))
        issue = payload.get("issue") or {}
        number = issue.get("number")
        issue_url = issue.get("html_url") or repo_url
        target = f"{repo_name}#{number}" if number else repo_name
        message = f"Issue {action}: [{clean_markdown(target)}]({issue_url})"
    elif event_type == "IssueCommentEvent":
        issue = payload.get("issue") or {}
        number = issue.get("number")
        issue_url = issue.get("html_url") or repo_url
        target = f"{repo_name}#{number}" if number else repo_name
        message = f"Commented on [{clean_markdown(target)}]({issue_url})"
    elif event_type == "CreateEvent":
        ref_type = clean_markdown(payload.get("ref_type", "resource"))
        ref = clean_markdown(payload.get("ref", ""))
        if ref_type == "repository":
            message = f"Created [{repo_name}]({repo_url})"
        elif ref:
            message = f"Created {ref_type} `{ref}` in [{repo_name}]({repo_url})"
        else:
            message = f"Created {ref_type} in [{repo_name}]({repo_url})"
    elif event_type == "ReleaseEvent":
        release = payload.get("release") or {}
        release_url = release.get("html_url") or repo_url
        release_name = clean_markdown(release.get("name") or release.get("tag_name") or "release")
        message = f"Published [{release_name}]({release_url}) in [{repo_name}]({repo_url})"
    else:
        return None

    return f"- {message} · `{date}`"


def fetch_recent_activity() -> list[str]:
    url = f"https://api.github.com/users/{USERNAME}/events/public?per_page=100"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{USERNAME}-profile-readme-updater",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=20) as response:
            data = json.load(response)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"GitHub API returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach GitHub API: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("GitHub API returned invalid JSON") from exc

    if not isinstance(data, list):
        raise RuntimeError("GitHub API response was not an event list")

    lines: list[str] = []
    for event in data:
        line = format_event(event)
        if line:
            lines.append(line)
        if len(lines) >= MAX_ITEMS:
            break

    if not lines:
        return ["_No recent public coding activity was found in the latest GitHub events._"]
    return lines


def update_readme(lines: list[str]) -> bool:
    if not README_PATH.exists():
        raise FileNotFoundError(f"README not found: {README_PATH}")

    content = README_PATH.read_text(encoding="utf-8")
    start = content.find(START_MARKER)
    end = content.find(END_MARKER)
    if start < 0 or end < 0 or end <= start:
        raise RuntimeError("Could not find recent-activity markers in README.md")

    start_content = start + len(START_MARKER)
    new_section = "\n" + "\n".join(lines) + "\n"
    updated = content[:start_content] + new_section + content[end:]
    if updated == content:
        print("Recent public activity is already up to date.")
        return False

    README_PATH.write_text(updated, encoding="utf-8")
    print(f"Updated recent public activity in {README_PATH}.")
    return True


def main() -> int:
    try:
        lines = fetch_recent_activity()
        update_readme(lines)
    except (RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
