"""Minimal GitHub REST helpers: auth, pagination, recursive contents walk."""

import time

import requests

from config import GITHUB_TOKEN

API = "https://api.github.com"


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h


def gh_get(url: str, params: dict | None = None) -> requests.Response:
    """GET with auth and simple rate-limit backoff."""
    for attempt in range(5):
        resp = requests.get(url, headers=_headers(), params=params, timeout=30)
        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            reset = int(resp.headers.get("X-RateLimit-Reset", "0"))
            wait = max(reset - int(time.time()), 5)
            print(f"  rate limited, waiting {wait}s (set GITHUB_TOKEN to avoid)...")
            time.sleep(min(wait, 60))
            continue
        resp.raise_for_status()
        return resp
    resp.raise_for_status()
    return resp


def paginate(url: str, params: dict | None = None, max_items: int | None = None):
    """Yield items across paginated list endpoints (follows the Link header)."""
    params = dict(params or {})
    params.setdefault("per_page", 100)
    count = 0
    while url:
        resp = gh_get(url, params=params)
        params = None  # subsequent pages come fully-formed in the Link header
        for item in resp.json():
            yield item
            count += 1
            if max_items is not None and count >= max_items:
                return
        url = resp.links.get("next", {}).get("url", "")


def walk_contents(repo: str, path: str):
    """Recursively yield file entries (type == 'file') under a repo path."""
    resp = gh_get(f"{API}/repos/{repo}/contents/{path}")
    entries = resp.json()
    if isinstance(entries, dict):  # a single file
        entries = [entries]
    for entry in entries:
        if entry["type"] == "dir":
            yield from walk_contents(repo, entry["path"])
        elif entry["type"] == "file":
            yield entry


def download_raw(url: str) -> str:
    resp = requests.get(url, headers=_headers(), timeout=60)
    resp.raise_for_status()
    return resp.text
