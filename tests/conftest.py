import asyncio
import os
import shutil
from pathlib import Path
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from app.core.config import settings
from app.domain.entities import IssueData, TaskState, TaskStatus
from app.infrastructure.db.database import async_session_maker, init_db
from app.infrastructure.db.repository import StateRepository
from app.infrastructure.opencode.manager import OpenCodeProcessManager
from app.infrastructure.telegram.notifier import TelegramNotifier
from app.infrastructure.vcs.git_cli import GitCLIClient
from app.infrastructure.vcs.github_api import GitHubAPIClient


from app.core.config import settings

settings.IDLE_TIMEOUT = 1  # 1 second for tests


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[None, None]:
    await init_db()
    yield
    from app.infrastructure.db.database import engine

    await engine.dispose()


@pytest.fixture
def mock_github_client() -> MagicMock:
    client = MagicMock(spec=GitHubAPIClient)
    client.get_clone_url = MagicMock(return_value="git@github.com:test/repo.git")
    client.post_comment = AsyncMock()
    client.create_pull_request = AsyncMock()
    client.get_issue = AsyncMock()
    client.close = AsyncMock()
    return client


@pytest.fixture
def mock_git_client() -> MagicMock:
    client = MagicMock(spec=GitCLIClient)
    client.clone = AsyncMock()
    client.create_branch = AsyncMock()
    client.commit_and_push = AsyncMock()
    client.cleanup_workspace = AsyncMock()
    return client


@pytest.fixture
def mock_oc_manager() -> MagicMock:
    manager = MagicMock(spec=OpenCodeProcessManager)
    manager.spawn_server = AsyncMock()
    manager.kill_server = AsyncMock()
    manager.get_client = MagicMock()
    return manager


@pytest.fixture
def mock_telegram() -> MagicMock:
    telegram = MagicMock(spec=TelegramNotifier)
    telegram.send_message = AsyncMock()
    telegram.close = AsyncMock()
    return telegram


@pytest.fixture
def mock_db() -> MagicMock:
    db = MagicMock(spec=StateRepository)
    db.create_task = AsyncMock()
    db.set_active_instance = AsyncMock()
    db.get_task_state = AsyncMock()
    return db


@pytest.fixture
def sample_issue_data() -> IssueData:
    return IssueData(
        issue_number=123,
        repo_url="owner/test-repo",
        title="Test Issue",
        body="This is a test issue body",
        sender="test-user",
        owner="owner",
    )


@pytest.fixture
def sample_task_state(sample_issue_data: IssueData) -> TaskState:
    return TaskState(
        issue_number=sample_issue_data.issue_number,
        repo_url=sample_issue_data.repo_url,
        branch_name="feature/issue_123",
        status=TaskStatus.PENDING,
        workspace_path=str(settings.opencode_base_path / "issue_123"),
    )


@pytest.fixture
def temp_workspace() -> Generator[str, None, None]:
    workspace_path = str(settings.opencode_base_path / "test_issue")
    yield workspace_path
    if Path(workspace_path).exists():
        shutil.rmtree(workspace_path, ignore_errors=True)
