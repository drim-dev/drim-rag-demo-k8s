"""Pile 3 (issue): issues + PRs labeled sig/scheduling, with comment threads.

This is the "why" pile #2 and the heart of the lecture spine: the rationale and the
*rejected* approaches live in the discussion comments, not in the issue body alone.
Requires GITHUB_TOKEN (the issues API is rate-limited hard without it).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import GITHUB_TOKEN, ISSUE_DIR, ISSUE_LABEL, ISSUES_MAX, K8S_REPO  # noqa: E402
from github import API, gh_get, paginate  # noqa: E402


def main() -> None:
    if not GITHUB_TOKEN:
        print("WARNING: GITHUB_TOKEN is empty — the issues API will rate-limit fast.")
    ISSUE_DIR.mkdir(parents=True, exist_ok=True)

    url = f"{API}/repos/{K8S_REPO}/issues"
    params = {"labels": ISSUE_LABEL, "state": "all", "sort": "updated", "direction": "desc"}

    saved = 0
    for issue in paginate(url, params=params, max_items=ISSUES_MAX):
        number = issue["number"]
        kind = "pr" if "pull_request" in issue else "issue"

        comments = []
        if issue.get("comments", 0):
            for c in paginate(issue["comments_url"]):
                comments.append({"author": c["user"]["login"], "body": c["body"] or ""})

        record = {
            "number": number,
            "kind": kind,
            "title": issue["title"],
            "state": issue["state"],
            "updated_at": issue["updated_at"],
            "author": issue["user"]["login"],
            "body": issue["body"] or "",
            "comments": comments,
        }
        (ISSUE_DIR / f"{number}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2))
        saved += 1
        print(f"  [{saved}] #{number} ({kind}, {len(comments)} comments) {issue['title'][:60]}")

    print(f"\nSaved {saved} issues/PRs to {ISSUE_DIR}")


if __name__ == "__main__":
    main()
