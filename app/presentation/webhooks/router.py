import hmac
import hashlib
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.core.config import settings
from app.core.logger import get_logger
from app.infrastructure.vcs.github_api import GitHubAPIClient
from app.infrastructure.db.repository import StateRepository
from app.infrastructure.opencode.manager import OpenCodeProcessManager
from app.infrastructure.telegram.notifier import TelegramNotifier
from app.application.use_cases.handle_reply import handle_user_reply

logger = get_logger(component="webhooks")

router = APIRouter(prefix="/webhook", tags=["webhooks"])

_github_client: Optional[GitHubAPIClient] = None
_db: Optional[StateRepository] = None
_oc_manager: Optional[OpenCodeProcessManager] = None
_telegram: Optional[TelegramNotifier] = None


def get_github_client() -> GitHubAPIClient:
    global _github_client
    if _github_client is None:
        _github_client = GitHubAPIClient()
    return _github_client


def get_db() -> StateRepository:
    global _db
    if _db is None:
        _db = StateRepository()
    return _db


def get_oc_manager() -> OpenCodeProcessManager:
    global _oc_manager
    if _oc_manager is None:
        _oc_manager = OpenCodeProcessManager()
    return _oc_manager


def get_telegram() -> TelegramNotifier:
    global _telegram
    if _telegram is None:
        _telegram = TelegramNotifier()
    return _telegram


def verify_github_signature(payload: bytes, signature: str) -> bool:
    if not settings.GITHUB_WEBHOOK_SECRET:
        logger.warning("no_webhook_secret_configured")
        return True

    # Support multiple webhook secrets (comma-separated) for multi-repo deployments
    secrets = [s.strip() for s in settings.GITHUB_WEBHOOK_SECRET.split(",") if s.strip()]

    for secret in secrets:
        expected = hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        if hmac.compare_digest(f"sha256={expected}", signature):
            return True

    return False


class IssueEvent(BaseModel):
    action: str
    issue: dict
    repository: dict
    sender: dict


class CommentEvent(BaseModel):
    action: str
    issue: dict
    comment: dict
    repository: dict
    sender: dict


async def get_issue_data(event: IssueEvent) -> dict:
    repo_full_name = event.repository.get("full_name", "")
    return {
        "issue_number": event.issue.get("number"),
        "repo_url": repo_full_name,
        "title": event.issue.get("title", ""),
        "body": event.issue.get("body", ""),
        "sender": event.sender.get("login", ""),
        "owner": repo_full_name.split("/")[0] if repo_full_name else "",
    }


@router.post("/github")
async def github_webhook(
    request: Request,
    github: GitHubAPIClient = Depends(get_github_client),
    db: StateRepository = Depends(get_db),
    oc_manager: OpenCodeProcessManager = Depends(get_oc_manager),
    telegram: TelegramNotifier = Depends(get_telegram),
):
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    if not verify_github_signature(body, signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature",
        )

    event_type = request.headers.get("X-GitHub-Event", "")
    logger.info("github_webhook_received", event_type=event_type)

    if event_type == "issues":
        return await handle_issue_event(request, github, db, telegram)
    elif event_type == "issue_comment":
        return await handle_comment_event(request, github, db, oc_manager, telegram)

    return {"status": "ignored", "event": event_type}


async def handle_issue_event(
    request: Request,
    github: GitHubAPIClient,
    db: StateRepository,
    telegram: TelegramNotifier,
):
    try:
        event_data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    action = event_data.get("action")
    if action != "opened":
        return {"status": "ignored", "reason": f"action={action}"}

    issue = event_data.get("issue", {})
    issue_number = issue.get("number")
    repo = event_data.get("repository", {}).get("full_name", "")

    logger.info("new_issue_received", issue_number=issue_number, repo=repo)

    from app.domain.entities import IssueData

    issue_data = IssueData(
        issue_number=issue_number,
        repo_url=repo,
        title=issue.get("title", ""),
        body=issue.get("body", ""),
        sender=event_data.get("sender", {}).get("login", ""),
        owner=repo.split("/")[0] if repo else "",
    )

    from app.presentation.workers.broker import execute_task
    from dataclasses import asdict

    await execute_task.kiq(asdict(issue_data))

    return {"status": "queued", "issue_number": issue_number}


async def handle_comment_event(
    request: Request,
    github: GitHubAPIClient,
    db: StateRepository,
    oc_manager: OpenCodeProcessManager,
    telegram: TelegramNotifier,
):
    try:
        event_data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    action = event_data.get("action")
    if action != "created":
        return {"status": "ignored", "reason": f"action={action}"}

    issue = event_data.get("issue", {})
    comment = event_data.get("comment", {})
    repo = event_data.get("repository", {}).get("full_name", "")
    sender = event_data.get("sender", {}).get("login", "")

    issue_number = issue.get("number")
    comment_body = comment.get("body", "")

    task_state = await db.get_task_state(issue_number, repo)
    if not task_state:
        return {"status": "ignored", "reason": "no_active_task"}

    owner = repo.split("/")[0] if repo else ""
    if sender != owner:
        logger.info("comment_from_non_owner", sender=sender, owner=owner)
        return {"status": "ignored", "reason": "not_owner"}

    logger.info("reply_from_owner", issue_number=issue_number)

    await handle_user_reply(
        issue_number=issue_number,
        repo_url=repo,
        comment_body=comment_body,
        oc_manager=oc_manager,
        db=db,
        telegram=telegram,
    )

    return {"status": "processed", "issue_number": issue_number}
