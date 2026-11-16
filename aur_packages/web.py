"""Requests to the web: GitHub's API with the token, NuGet, raw files."""

import json
import urllib.error
import urllib.request
from typing import Any

from aur_packages.updates import github_token


def request(url: str, attempts: int = 3) -> bytes | None:
    """The body of a URL, None if it fails; GitHub's API with the token of github_token, for its rate
    limit rather than the 60 requests an hour without one. Gives up on a stalled connection and tries
    again, instead of waiting forever."""
    req = urllib.request.Request(url, headers={"User-Agent": "aur-packages"})
    if url.startswith("https://api.github.com/") and (token := github_token()):
        req.add_header("Authorization", f"Bearer {token}")
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                body: bytes = response.read()
                return body
        except urllib.error.HTTPError:
            return None
        except OSError:
            if attempt == attempts - 1:
                return None
    return None


def request_json(url: str) -> Any:
    body = request(url)
    try:
        return json.loads(body) if body is not None else None
    except json.JSONDecodeError:
        return None
