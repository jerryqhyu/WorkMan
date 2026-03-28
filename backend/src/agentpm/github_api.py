from __future__ import annotations

import re
from typing import Any

import httpx


GITHUB_API = "https://api.github.com"


class GitHubError(RuntimeError):
    pass



def parse_github_remote(url: str | None) -> tuple[str, str] | None:
    if not url:
        return None
    ssh_match = re.match(r"git@github\.com:(?P<owner>[^/]+)/(?P<repo>.+?)(?:\.git)?$", url)
    if ssh_match:
        return ssh_match.group("owner"), ssh_match.group("repo")
    https_match = re.match(r"https://github\.com/(?P<owner>[^/]+)/(?P<repo>.+?)(?:\.git)?$", url)
    if https_match:
        return https_match.group("owner"), https_match.group("repo")
    return None


async def create_draft_pr(
    *,
    token: str,
    owner: str,
    repo: str,
    title: str,
    body: str,
    head: str,
    base: str,
) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {
        "title": title,
        "body": body,
        "head": head,
        "base": base,
        "draft": True,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(f"{GITHUB_API}/repos/{owner}/{repo}/pulls", json=payload, headers=headers)
    if response.status_code >= 400:
        raise GitHubError(response.text)
    return response.json()
