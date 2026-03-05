"""
Comprehensive E2E Integration Tests for AI Orchestrator.

This module tests the complete flow from GitHub webhook to task completion,
including failure scenarios and edge cases.
"""

import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.application.use_cases.execute_task import execute_coding_task
from app.application.use_cases.handle_reply import handle_user_reply
from app.core.config import settings
from app.domain.entities import IssueData, OpenCodeProcess, TaskState, TaskStatus
from app.infrastructure.db.database import async_session_maker, init_db
from app.infrastructure.db.repository import StateRepository
from app.infrastructure.opencode.client import OpenCodeClient
from app.infrastructure.opencode.manager import OpenCodeProcessManager
from app.infrastructure.vcs.git_cli import GitCLIClient
from app.infrastructure.vcs.github_api import GitHubAPIClient
from app.infrastructure.telegram.notifier import TelegramNotifier


@pytest.fixture(autouse=True)
def mock_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Override settings for testing with shorter timeouts."""
    monkeypatch.setattr(settings, "IDLE_TIMEOUT", 2)
    monkeypatch.setattr(settings, "MAX_CONCURRENT_INSTANCES", 2)
    monkeypatch.setattr(
        settings, "OPENCODE_BASE_DIR", tempfile.gettempdir() + "/test_workspaces"
    )


@pytest.fixture
def sample_issue() -> IssueData:
    """Create a sample issue for testing."""
    return IssueData(
        issue_number=42,
        repo_url="test-owner/test-repo",
        title="Add user authentication",
        body="Implement JWT-based authentication for the API endpoints",
        sender="contributor",
        owner="test-owner",
    )


class MockOpenCodeEventStream:
    """Simulates OpenCode SSE event stream with configurable behavior."""

    def __init__(
        self,
        events: List[Dict[str, Any]],
        delay: float = 0.01,
        should_timeout: bool = False,
    ):
        self.events = events
        self.delay = delay
        self.should_timeout = should_timeout
        self._consumed = False

    async def __aiter__(self) -> AsyncGenerator[Dict[str, Any], None]:
        if self._consumed:
            return
        self._consumed = True

        for event in self.events:
            if self.delay:
                await asyncio.sleep(self.delay)
            yield event

        if self.should_timeout:
            await asyncio.sleep(100)


class MockOpenCodeClient:
    """Mock OpenCode client for integration testing."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self._session_id: str | None = None
        self._events: List[Dict[str, Any]] = []
        self._messages_sent: List[str] = []
        self._replies_sent: List[str] = []

    def configure_events(self, events: List[Dict[str, Any]]) -> None:
        """Configure the events this client will emit."""
        self._events = events

    async def create_session(self, name: str) -> str:
        self._session_id = f"session_{name.replace(' ', '_').lower()}"
        return self._session_id

    async def send_message(self, session_id: str, message: str) -> None:
        self._messages_sent.append(message)

    async def send_reply(self, session_id: str, message: str) -> None:
        self._replies_sent.append(message)

    async def listen_events(
        self, session_id: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        async for event in MockOpenCodeEventStream(self._events):
            yield event

    async def close(self) -> None:
        pass

    @property
    def messages_sent(self) -> List[str]:
        return self._messages_sent

    @property
    def replies_received(self) -> List[str]:
        return self._replies_sent


class MockGitCLIClient:
    """Mock Git client that simulates git operations."""

    def __init__(self) -> None:
        self.clone_calls: List[tuple[str, str]] = []
        self.branch_calls: List[tuple[str, str]] = []
        self.push_calls: List[tuple[str, str, str]] = []
        self.cleanup_calls: List[str] = []
        self._should_fail_clone = False
        self._should_fail_push = False
        self._workspace_created: str | None = None

    def configure_fail_clone(self, should_fail: bool = True) -> None:
        self._should_fail_clone = should_fail

    def configure_fail_push(self, should_fail: bool = True) -> None:
        self._should_fail_push = should_fail

    async def clone_ssh(self, repo_url: str, workspace_path: str) -> None:
        self.clone_calls.append((repo_url, workspace_path))
        if self._should_fail_clone:
            raise RuntimeError("Git clone failed: Repository not found")

        Path(workspace_path).mkdir(parents=True, exist_ok=True)
        self._workspace_created = workspace_path

    async def create_branch(self, workspace_path: str, branch_name: str) -> None:
        self.branch_calls.append((workspace_path, branch_name))

    async def commit_and_push_ssh(
        self, workspace_path: str, commit_message: str, branch_name: str
    ) -> None:
        if self._should_fail_push:
            raise RuntimeError("Git push failed: Remote rejected")
        self.push_calls.append((workspace_path, commit_message, branch_name))

    async def cleanup_workspace(self, workspace_path: str) -> None:
        self.cleanup_calls.append(workspace_path)
        if Path(workspace_path).exists():
            shutil.rmtree(workspace_path, ignore_errors=True)


class MockGitHubAPIClient:
    """Mock GitHub API client for testing."""

    def __init__(self) -> None:
        self.comments_posted: List[tuple[int, str, str]] = []
        self.prs_created: List[tuple[int, str, str]] = []
        self._should_fail_comment = False
        self._should_fail_pr = False

    def configure_fail_comment(self, should_fail: bool = True) -> None:
        self._should_fail_comment = should_fail

    def configure_fail_pr(self, should_fail: bool = True) -> None:
        self._should_fail_pr = should_fail

    def get_ssh_url(self, repo: str) -> str:
        return f"git@github.com:{repo}.git"

    async def post_comment(self, issue_number: int, body: str, repo: str) -> None:
        if self._should_fail_comment:
            raise RuntimeError("GitHub API error: Rate limited")
        self.comments_posted.append((issue_number, body, repo))

    async def create_pull_request(
        self,
        issue_number: int,
        branch_name: str,
        repo: str,
        title: str | None = None,
    ) -> None:
        if self._should_fail_pr:
            raise RuntimeError("GitHub API error: Branch not found")
        self.prs_created.append((issue_number, branch_name, repo))

    async def get_issue(self, issue_number: int, repo: str) -> IssueData:
        return IssueData(
            issue_number=issue_number,
            repo_url=repo,
            title="Test Issue",
            body="Test body",
            sender="test",
            owner=repo.split("/")[0],
        )

    async def close(self) -> None:
        pass


class MockTelegramNotifier:
    """Mock Telegram notifier for testing."""

    def __init__(self) -> None:
        self.messages_sent: List[str] = []

    async def send_message(self, text: str) -> None:
        self.messages_sent.append(text)

    async def close(self) -> None:
        pass


class MockOpenCodeProcessManager:
    """Mock process manager for testing."""

    def __init__(self) -> None:
        self._mock_client = MockOpenCodeClient("127.0.0.1", 0)
        self.spawn_calls: List[str] = []
        self.kill_calls: List[int] = []

    def configure_client_events(self, events: List[Dict[str, Any]]) -> None:
        self._mock_client.configure_events(events)

    async def spawn_server(self, workspace_path: str) -> OpenCodeProcess:
        self.spawn_calls.append(workspace_path)
        return OpenCodeProcess(pid=12345, port=8765)

    async def kill_server(self, pid: int) -> None:
        self.kill_calls.append(pid)

    def get_client(self, port: int) -> MockOpenCodeClient:
        return self._mock_client


@pytest.fixture
def mock_git() -> MockGitCLIClient:
    return MockGitCLIClient()


@pytest.fixture
def mock_github() -> MockGitHubAPIClient:
    return MockGitHubAPIClient()


@pytest.fixture
def mock_telegram() -> MockTelegramNotifier:
    return MockTelegramNotifier()


@pytest.fixture
def mock_oc_manager() -> MockOpenCodeProcessManager:
    return MockOpenCodeProcessManager()


@pytest_asyncio.fixture
async def mock_db(db_session: None) -> StateRepository:
    return StateRepository()


@pytest.fixture(scope="session")
def event_loop() -> asyncio.AbstractEventLoop:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[None, None]:
    """Initialize and cleanup database for each test."""
    await init_db()
    yield
    from app.infrastructure.db.database import engine

    await engine.dispose()


def create_standard_success_events() -> List[Dict[str, Any]]:
    """Create a standard sequence of events for successful task completion."""
    return [
        {
            "event_name": "message_completed",
            "data": {
                "text": "I'll start working on this task.",
                "has_commands": False,
            },
        },
        {
            "event_name": "message_completed",
            "data": {
                "text": "I've implemented the feature. [TASK_COMPLETED]",
                "has_commands": False,
            },
        },
    ]


def create_question_then_complete_events() -> List[Dict[str, Any]]:
    """Create events where agent asks a question before completing."""
    return [
        {
            "event_name": "message_completed",
            "data": {
                "text": "I need clarification on the requirements.",
                "has_commands": False,
            },
        },
        {
            "event_name": "message_completed",
            "data": {
                "text": "Thanks for the clarification. [TASK_COMPLETED]",
                "has_commands": False,
            },
        },
    ]


def create_error_events() -> List[Dict[str, Any]]:
    """Create events that simulate an error."""
    return [
        {
            "event_name": "error",
            "data": {"message": "OpenCode server encountered an error"},
        },
    ]


class TestE2EFullFlow:
    """End-to-end tests for the complete task execution flow."""

    @pytest.mark.asyncio
    async def test_successful_task_execution(
        self,
        sample_issue: IssueData,
        mock_git: MockGitCLIClient,
        mock_github: MockGitHubAPIClient,
        mock_oc_manager: MockOpenCodeProcessManager,
        mock_db: StateRepository,
        mock_telegram: MockTelegramNotifier,
    ) -> None:
        """Test complete successful execution from issue to PR."""
        mock_oc_manager.configure_client_events(create_standard_success_events())

        await execute_coding_task(
            issue_data=sample_issue,
            git=mock_git,
            github=mock_github,
            oc_manager=mock_oc_manager,
            db=mock_db,
            telegram=mock_telegram,
        )

        assert len(mock_git.clone_calls) == 1
        assert len(mock_git.branch_calls) == 1
        assert len(mock_git.push_calls) == 1
        assert len(mock_github.prs_created) == 1
        assert len(mock_oc_manager.kill_calls) == 1
        assert len(mock_git.cleanup_calls) == 1

        task_state = await mock_db.get_task_state(sample_issue.issue_number)
        assert task_state is not None
        assert task_state.status == TaskStatus.DONE

    @pytest.mark.asyncio
    async def test_agent_asks_question_then_completes(
        self,
        sample_issue: IssueData,
        mock_git: MockGitCLIClient,
        mock_github: MockGitHubAPIClient,
        mock_oc_manager: MockOpenCodeProcessManager,
        mock_db: StateRepository,
        mock_telegram: MockTelegramNotifier,
    ) -> None:
        """Test flow where agent asks for clarification before completing."""
        mock_oc_manager.configure_client_events(create_question_then_complete_events())

        await execute_coding_task(
            issue_data=sample_issue,
            git=mock_git,
            github=mock_github,
            oc_manager=mock_oc_manager,
            db=mock_db,
            telegram=mock_telegram,
        )

        assert len(mock_github.comments_posted) == 1
        assert "clarification" in mock_github.comments_posted[0][1].lower()
        assert len(mock_telegram.messages_sent) >= 1
        assert "question" in mock_telegram.messages_sent[0].lower()

        task_state = await mock_db.get_task_state(sample_issue.issue_number)
        assert task_state is not None
        assert task_state.status == TaskStatus.DONE

    @pytest.mark.asyncio
    async def test_task_with_user_reply_injection(
        self,
        sample_issue: IssueData,
        mock_git: MockGitCLIClient,
        mock_github: MockGitHubAPIClient,
        mock_oc_manager: MockOpenCodeProcessManager,
        mock_db: StateRepository,
        mock_telegram: MockTelegramNotifier,
    ) -> None:
        """Test that user replies are properly routed to active session."""
        events = create_question_then_complete_events()
        mock_oc_manager.configure_client_events(events)

        await execute_coding_task(
            issue_data=sample_issue,
            git=mock_git,
            github=mock_github,
            oc_manager=mock_oc_manager,
            db=mock_db,
            telegram=mock_telegram,
        )

        task_state = await mock_db.get_task_state(sample_issue.issue_number)
        assert task_state is not None
        assert task_state.active_port == 8765
        assert task_state.session_id is not None

        await handle_user_reply(
            issue_number=sample_issue.issue_number,
            comment_body="Here's the clarification you need",
            oc_manager=mock_oc_manager,
            db=mock_db,
            telegram=mock_telegram,
        )

        client = mock_oc_manager.get_client(8765)
        assert len(client.replies_received) == 1
        assert "clarification" in client.replies_received[0].lower()


class TestE2EFailureModes:
    """Tests for failure scenarios and error handling."""

    @pytest.mark.asyncio
    async def test_clone_failure_triggers_cleanup(
        self,
        sample_issue: IssueData,
        mock_git: MockGitCLIClient,
        mock_github: MockGitHubAPIClient,
        mock_oc_manager: MockOpenCodeProcessManager,
        mock_db: StateRepository,
        mock_telegram: MockTelegramNotifier,
    ) -> None:
        """Test that workspace is cleaned up when git clone fails."""
        mock_git.configure_fail_clone()

        with pytest.raises(RuntimeError, match="Git clone failed"):
            await execute_coding_task(
                issue_data=sample_issue,
                git=mock_git,
                github=mock_github,
                oc_manager=mock_oc_manager,
                db=mock_db,
                telegram=mock_telegram,
            )

        assert len(mock_git.cleanup_calls) == 1

    @pytest.mark.asyncio
    async def test_error_event_triggers_cleanup(
        self,
        sample_issue: IssueData,
        mock_git: MockGitCLIClient,
        mock_github: MockGitHubAPIClient,
        mock_oc_manager: MockOpenCodeProcessManager,
        mock_db: StateRepository,
        mock_telegram: MockTelegramNotifier,
    ) -> None:
        """Test that OpenCode error triggers proper cleanup."""
        mock_oc_manager.configure_client_events(create_error_events())

        await execute_coding_task(
            issue_data=sample_issue,
            git=mock_git,
            github=mock_github,
            oc_manager=mock_oc_manager,
            db=mock_db,
            telegram=mock_telegram,
        )

        assert len(mock_oc_manager.kill_calls) == 1
        assert len(mock_git.cleanup_calls) == 1
        assert len(mock_telegram.messages_sent) >= 1
        assert "Error" in mock_telegram.messages_sent[0]

        task_state = await mock_db.get_task_state(sample_issue.issue_number)
        assert task_state is not None
        assert task_state.status == TaskStatus.FAILED

    @pytest.mark.asyncio
    async def test_idle_timeout_triggers_abort(
        self,
        sample_issue: IssueData,
        mock_git: MockGitCLIClient,
        mock_github: MockGitHubAPIClient,
        mock_oc_manager: MockOpenCodeProcessManager,
        mock_db: StateRepository,
        mock_telegram: MockTelegramNotifier,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that idle timeout properly aborts the task."""
        monkeypatch.setattr(settings, "IDLE_TIMEOUT", 1)

        async def slow_event_stream(
            session_id: str,
        ) -> AsyncGenerator[Dict[str, Any], None]:
            await asyncio.sleep(10)
            yield {}

        mock_client = MockOpenCodeClient("127.0.0.1", 8765)
        mock_client.listen_events = slow_event_stream
        mock_oc_manager._mock_client = mock_client

        await execute_coding_task(
            issue_data=sample_issue,
            git=mock_git,
            github=mock_github,
            oc_manager=mock_oc_manager,
            db=mock_db,
            telegram=mock_telegram,
        )

        assert len(mock_github.comments_posted) >= 1
        assert "timeout" in mock_github.comments_posted[0][1].lower()
        assert len(mock_telegram.messages_sent) >= 1
        assert "Timeout" in mock_telegram.messages_sent[0]

        task_state = await mock_db.get_task_state(sample_issue.issue_number)
        assert task_state is not None
        assert task_state.status == TaskStatus.ABORTED

    @pytest.mark.asyncio
    async def test_process_killed_on_exception(
        self,
        sample_issue: IssueData,
        mock_git: MockGitCLIClient,
        mock_github: MockGitHubAPIClient,
        mock_oc_manager: MockOpenCodeProcessManager,
        mock_db: StateRepository,
        mock_telegram: MockTelegramNotifier,
    ) -> None:
        """Test that OpenCode process is killed even when exception occurs."""
        mock_oc_manager.configure_client_events(create_error_events())

        await execute_coding_task(
            issue_data=sample_issue,
            git=mock_git,
            github=mock_github,
            oc_manager=mock_oc_manager,
            db=mock_db,
            telegram=mock_telegram,
        )

        assert 12345 in mock_oc_manager.kill_calls


class TestE2EConcurrency:
    """Tests for concurrency control and resource management."""

    @pytest.mark.asyncio
    async def test_concurrent_tasks_semaphore(
        self,
        sample_issue: IssueData,
        mock_git: MockGitCLIClient,
        mock_github: MockGitHubAPIClient,
        mock_oc_manager: MockOpenCodeProcessManager,
        mock_db: StateRepository,
        mock_telegram: MockTelegramNotifier,
    ) -> None:
        """Test that concurrent tasks respect the semaphore limit."""
        from app.presentation.workers.broker import _concurrency_semaphore

        mock_oc_manager.configure_client_events(create_standard_success_events())

        initial_value = _concurrency_semaphore._value

        tasks = []
        for i in range(3):
            issue = IssueData(
                issue_number=sample_issue.issue_number + i,
                repo_url=sample_issue.repo_url,
                title=f"Task {i}",
                body="Test",
                sender="test",
                owner="test-owner",
            )
            tasks.append(
                execute_coding_task(
                    issue_data=issue,
                    git=mock_git,
                    github=mock_github,
                    oc_manager=mock_oc_manager,
                    db=mock_db,
                    telegram=mock_telegram,
                )
            )

        await asyncio.gather(*tasks)

        assert _concurrency_semaphore._value == initial_value

    @pytest.mark.asyncio
    async def test_multiple_isolated_workspaces(
        self,
        mock_git: MockGitCLIClient,
        mock_github: MockGitHubAPIClient,
        mock_oc_manager: MockOpenCodeProcessManager,
        mock_db: StateRepository,
        mock_telegram: MockTelegramNotifier,
    ) -> None:
        """Test that multiple tasks create isolated workspaces."""
        issues = [
            IssueData(
                issue_number=i,
                repo_url="test-owner/test-repo",
                title=f"Issue {i}",
                body="Test",
                sender="test",
                owner="test-owner",
            )
            for i in range(1, 4)
        ]

        for issue in issues:
            mock_oc_manager.configure_client_events(create_standard_success_events())
            await execute_coding_task(
                issue_data=issue,
                git=mock_git,
                github=mock_github,
                oc_manager=mock_oc_manager,
                db=mock_db,
                telegram=mock_telegram,
            )

        workspace_paths = [call[1] for call in mock_git.clone_calls]
        assert len(set(workspace_paths)) == 3

        for path in workspace_paths:
            assert Path(path).parent == Path(settings.OPENCODE_BASE_DIR)


class TestE2EDatabasePersistence:
    """Tests for database state persistence and recovery."""

    @pytest.mark.asyncio
    async def test_task_state_persisted_throughout_lifecycle(
        self,
        sample_issue: IssueData,
        mock_git: MockGitCLIClient,
        mock_github: MockGitHubAPIClient,
        mock_oc_manager: MockOpenCodeProcessManager,
        mock_db: StateRepository,
        mock_telegram: MockTelegramNotifier,
    ) -> None:
        """Test that task state is properly persisted throughout execution."""
        events = [
            {
                "event_name": "message_completed",
                "data": {"text": "Starting...", "has_commands": False},
            },
        ]
        mock_oc_manager.configure_client_events(events)

        await execute_coding_task(
            issue_data=sample_issue,
            git=mock_git,
            github=mock_github,
            oc_manager=mock_oc_manager,
            db=mock_db,
            telegram=mock_telegram,
        )

        task_state = await mock_db.get_task_state(sample_issue.issue_number)
        assert task_state is not None
        assert task_state.issue_number == sample_issue.issue_number
        assert task_state.repo_url == sample_issue.repo_url
        assert task_state.branch_name == f"feature/issue_{sample_issue.issue_number}"
        assert task_state.active_port == 8765
        assert task_state.session_id is not None

    @pytest.mark.asyncio
    async def test_handle_reply_with_no_active_task(
        self,
        mock_oc_manager: MockOpenCodeProcessManager,
        mock_db: StateRepository,
        mock_telegram: MockTelegramNotifier,
    ) -> None:
        """Test that handle_reply gracefully handles non-existent tasks."""
        await handle_user_reply(
            issue_number=99999,
            comment_body="Test reply",
            oc_manager=mock_oc_manager,
            db=mock_db,
            telegram=mock_telegram,
        )

        client = mock_oc_manager.get_client(8765)
        assert len(client.replies_received) == 0

    @pytest.mark.asyncio
    async def test_handle_reply_with_completed_task(
        self,
        sample_issue: IssueData,
        mock_oc_manager: MockOpenCodeProcessManager,
        mock_db: StateRepository,
        mock_telegram: MockTelegramNotifier,
    ) -> None:
        """Test that handle_reply ignores completed tasks."""
        task_state = TaskState(
            issue_number=sample_issue.issue_number,
            repo_url=sample_issue.repo_url,
            branch_name="feature/issue_42",
            status=TaskStatus.DONE,
            active_port=8765,
            session_id="session_42",
        )
        await mock_db.create_task(task_state)

        await handle_user_reply(
            issue_number=sample_issue.issue_number,
            comment_body="Test reply",
            oc_manager=mock_oc_manager,
            db=mock_db,
            telegram=mock_telegram,
        )

        client = mock_oc_manager.get_client(8765)
        assert len(client.replies_received) == 0
