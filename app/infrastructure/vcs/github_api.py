from typing import Optional

import httpx

from app.core.config import settings
from app.core.logger import get_logger
from app.domain.entities import IssueData
from app.domain.interfaces import IGitHubClient

logger = get_logger(component="github_api")


def _to_ssh_url(repo: str) -> str:
    """Convert 'owner/repo' to 'git@github.com:owner/repo.git'"""
    return f"git@github.com:{repo}.git"


class GitHubAPIClient(IGitHubClient):
    def __init__(self):
        self._client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {settings.GITHUB_TOKEN}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )

    async def post_comment(self, issue_number: int, body: str, repo: str) -> None:
        logger.info("posting_comment", issue_number=issue_number, repo=repo)

        url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"

        response = await self._client.post(url, json={"body": body})
        response.raise_for_status()

        logger.info("comment_posted", issue_number=issue_number)

    async def create_pull_request(
        self, issue_number: int, branch_name: str, repo: str, title: Optional[str] = None
    ) -> None:
        logger.info(
            "creating_pull_request", issue_number=issue_number, branch=branch_name, repo=repo
        )

        pr_title = title or f"Fix #{issue_number}"

        url = f"https://api.github.com/repos/{repo}/pulls"

        response = await self._client.post(
            url,
            json={
                "title": pr_title,
                "head": branch_name,
                "base": "main",
                "body": f"Closes #{issue_number}",
            },
        )
        response.raise_for_status()

        pr_url = response.json().get("html_url")
        logger.info("pull_request_created", issue_number=issue_number, pr_url=pr_url)

    async def get_issue(self, issue_number: int, repo: str) -> IssueData:
        logger.info("getting_issue", issue_number=issue_number, repo=repo)

        url = f"https://api.github.com/repos/{repo}/issues/{issue_number}"

        response = await self._client.get(url)
        response.raise_for_status()

        data = response.json()

        return IssueData(
            issue_number=issue_number,
            repo_url=repo,
            title=data.get("title", ""),
            body=data.get("body", ""),
            sender=data.get("user", {}).get("login", ""),
            owner=repo.split("/")[0],
        )

    def get_ssh_url(self, repo: str) -> str:
        return _to_ssh_url(repo)

    async def close(self) -> None:
        await self._client.aclose()
