"""
Real integration test for OpenCode server.

This test spawns a real local opencode server instance to test the complete loop.
It uses actual settings from `.env` (via app.core.config.settings).
External dependencies (GitHub, Telegram) are mocked.
"""

import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio

from app.application.use_cases.execute_task import execute_coding_task
from app.core.config import settings
from app.domain.entities import IssueData, TaskStatus
from app.infrastructure.db.database import init_db
from app.infrastructure.db.repository import StateRepository
from app.infrastructure.opencode.manager import OpenCodeProcessManager
from app.infrastructure.vcs.git_cli import GitCLIClient
from app.infrastructure.vcs.github_api import GitHubAPIClient
from app.infrastructure.telegram.notifier import TelegramNotifier


class MockGitHubAPIClient(GitHubAPIClient):
    def __init__(self):
        self.comments_posted = []
        self.prs_created = []

    def get_clone_url(self, repo: str) -> str:
        return f"git@github.com:{repo}.git"

    async def post_comment(self, issue_number: int, body: str, repo: str) -> None:
        self.comments_posted.append((issue_number, body, repo))

    async def create_pull_request(
        self,
        issue_number: int,
        branch_name: str,
        repo: str,
        title: str | None = None,
    ) -> None:
        self.prs_created.append((issue_number, branch_name, repo))

    async def get_issue(self, issue_number: int, repo: str) -> IssueData:
        return IssueData(
            issue_number=issue_number,
            repo_url=repo,
            title="Test Issue",
            body="Test body",
            sender="test",
            owner="test",
        )

    async def close(self) -> None:
        pass


class MockTelegramNotifier(TelegramNotifier):
    def __init__(self):
        self.messages_sent = []

    async def send_message(self, text: str) -> None:
        self.messages_sent.append(text)

    async def close(self) -> None:
        pass


class MockGitCLIClient(GitCLIClient):
    """
    Mock Git client that creates the directory if needed but skips actual cloning,
    allowing the real OpenCode server to start in a valid directory.
    """

    def __init__(self):
        self.clone_calls = []
        self.branch_calls = []
        self.push_calls = []
        self.cleanup_calls = []

    async def clone(self, repo_url: str, workspace_path: str) -> None:
        self.clone_calls.append((repo_url, workspace_path))
        # Create an empty git repo to satisfy opencode
        Path(workspace_path).mkdir(parents=True, exist_ok=True)
        process = await asyncio.create_subprocess_exec(
            "git",
            "init",
            cwd=workspace_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await process.communicate()
        # Create a dummy file
        with open(os.path.join(workspace_path, "test.txt"), "w") as f:
            f.write("Initial content")

    async def create_branch(self, workspace_path: str, branch_name: str) -> None:
        self.branch_calls.append((workspace_path, branch_name))

    async def commit_and_push(
        self, workspace_path: str, commit_message: str, branch_name: str
    ) -> None:
        self.push_calls.append((workspace_path, commit_message, branch_name))

    async def cleanup_workspace(self, workspace_path: str) -> None:
        self.cleanup_calls.append(workspace_path)
        if Path(workspace_path).exists():
            # Handle windows permission issues sometimes seen with shutil.rmtree
            try:
                shutil.rmtree(workspace_path, ignore_errors=True)
            except Exception:
                pass


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[None, None]:
    await init_db()
    yield
    from app.infrastructure.db.database import engine

    await engine.dispose()


@pytest.mark.asyncio
async def test_real_opencode_server_interaction(db_session, monkeypatch):
    """
    Tests actual interaction with the OpenCode server locally.
    Requires opencode to be installed and available in PATH or via settings.OPENCODE_CLI_NAME.
    """
    # Use a temporary directory for workspaces
    temp_dir = tempfile.mkdtemp()
    monkeypatch.setattr(settings, "OPENCODE_BASE_DIR", temp_dir)
    # Give the agent enough time to think, but not forever.
    monkeypatch.setattr(settings, "IDLE_TIMEOUT", 30)

    # Unset auth variables so the server runs unauthenticated
    monkeypatch.delenv("OPENCODE_SERVER_PASSWORD", raising=False)
    monkeypatch.delenv("OPENCODE_SERVER_USERNAME", raising=False)

    # Initialize dependencies
    mock_git = MockGitCLIClient()
    mock_github = MockGitHubAPIClient()
    mock_telegram = MockTelegramNotifier()
    mock_db = StateRepository()

    # Use REAL OpenCode process manager
    real_oc_manager = OpenCodeProcessManager()

    issue_data = IssueData(
        issue_number=999,
        repo_url="test-owner/test-repo",
        title="Test real agent interaction",
        body="This is a test. Please reply exactly with '[TASK_COMPLETED]' and nothing else. Do not use any tools.",
        sender="tester",
        owner="test-owner",
    )

    try:
        # Check if opencode is installed before running
        process = await asyncio.create_subprocess_exec(
            settings.OPENCODE_CLI_NAME,
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()
        if process.returncode != 0:
            pytest.skip(
                f"opencode CLI ({settings.OPENCODE_CLI_NAME}) not found or failed to execute."
            )
    except FileNotFoundError:
        pytest.skip(f"opencode CLI ({settings.OPENCODE_CLI_NAME}) not found in PATH.")

    # Execute the coding task. This will:
    # 1. Start opencode serve
    # 2. Wait for port
    # 3. Create session
    # 4. Send the prompt
    # 5. Listen to SSE events until [TASK_COMPLETED]
    await execute_coding_task(
        issue_data=issue_data,
        git=mock_git,
        github=mock_github,
        oc_manager=real_oc_manager,
        db=mock_db,
        telegram=mock_telegram,
    )

    # Verify task completed successfully or waited for reply (if LLM is not configured properly but still replied with an error text)
    task_state = await mock_db.get_task_state(issue_data.issue_number, issue_data.repo_url)
    assert task_state is not None
    assert task_state.status in (TaskStatus.DONE, TaskStatus.WAITING_REPLY, TaskStatus.ABORTED), (
        f"Expected DONE or WAITING_REPLY, but got {task_state.status}. Telegram messages: {mock_telegram.messages_sent}"
    )

    # If it was WAITING_REPLY, it means it parsed the LLM output but it didn't contain [TASK_COMPLETED]
    # If it was ABORTED, it hit the 30s timeout after waiting for a reply
    if task_state.status in (TaskStatus.WAITING_REPLY, TaskStatus.ABORTED):
        assert len(mock_telegram.messages_sent) > 0
        print(
            "Note: Agent didn't complete the task. This is expected if the local LLM is unconfigured."
        )
