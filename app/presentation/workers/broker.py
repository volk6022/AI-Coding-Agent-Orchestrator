import json
from typing import Any, Dict

import taskiq
from taskiq import TaskiqEvents
from taskiq_redis import RedisBroker

from app.core.config import settings
from app.core.logger import get_logger
from app.domain.entities import IssueData
from app.infrastructure.db.repository import StateRepository
from app.infrastructure.opencode.manager import OpenCodeProcessManager
from app.infrastructure.telegram.notifier import TelegramNotifier
from app.infrastructure.vcs.git_cli import GitCLIClient
from app.infrastructure.vcs.github_api import GitHubAPIClient

logger = get_logger(component="broker")

broker = RedisBroker(settings.REDIS_URL)


@broker.on_event(TaskiqEvents.WORKER_START)
async def on_worker_start():
    logger.info("worker_started")


@broker.task()
async def execute_task(task_data: Dict[str, Any]):
    logger.info("executing_task", issue_number=task_data.get("issue_number"))

    issue_data = IssueData(**task_data)

    git = GitCLIClient()
    github = GitHubAPIClient()
    oc_manager = OpenCodeProcessManager()
    db = StateRepository()
    telegram = TelegramNotifier()

    try:
        from app.application.use_cases.execute_task import execute_coding_task

        await execute_coding_task(
            issue_data=issue_data,
            git=git,
            github=github,
            oc_manager=oc_manager,
            db=db,
            telegram=telegram,
        )
    finally:
        await github.close()
        await telegram.close()
