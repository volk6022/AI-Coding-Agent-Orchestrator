import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from app.application.use_cases.execute_task import execute_coding_task
from app.core.config import settings
from app.domain.entities import IssueData, OpenCodeProcess, TaskStatus


@pytest.mark.asyncio
async def test_workspace_cleanup_on_clone_failure(
    sample_issue_data: IssueData,
    mock_github_client: MagicMock,
    mock_oc_manager: MagicMock,
    mock_db: MagicMock,
    mock_telegram: MagicMock,
):
    from app.infrastructure.vcs.git_cli import GitCLIClient

    git_client = GitCLIClient()
    git_client.clone = AsyncMock(side_effect=RuntimeError("Clone failed"))

    workspace_path = f"{settings.OPENCODE_BASE_DIR}/issue_{sample_issue_data.issue_number}"
    Path(workspace_path).mkdir(parents=True, exist_ok=True)

    mock_oc_process = OpenCodeProcess(pid=12345, port=54321)
    mock_oc_manager.spawn_server.return_value = mock_oc_process

    with pytest.raises(RuntimeError, match="Clone failed"):
        await execute_coding_task(
            issue_data=sample_issue_data,
            git=git_client,
            github=mock_github_client,
            oc_manager=mock_oc_manager,
            db=mock_db,
            telegram=mock_telegram,
        )

    assert not Path(workspace_path).exists()


@pytest.mark.asyncio
async def test_process_killed_on_error_during_execution(
    sample_issue_data: IssueData,
    mock_git_client: MagicMock,
    mock_github_client: MagicMock,
    mock_oc_manager: MagicMock,
    mock_db: MagicMock,
    mock_telegram: MagicMock,
):
    mock_oc_process = OpenCodeProcess(pid=12345, port=54321)
    mock_oc_manager.spawn_server.return_value = mock_oc_process

    async def mock_listen_events(session_id):
        yield {
            "type": "session.error",
            "properties": {"error": {"message": "Agent crashed"}},
        }

    mock_oc_client = MagicMock()
    mock_oc_client.create_session = AsyncMock(return_value="session_abc")
    mock_oc_client.send_message = AsyncMock()
    mock_oc_client.listen_events = mock_listen_events
    mock_oc_manager.get_client.return_value = mock_oc_client

    await execute_coding_task(
        issue_data=sample_issue_data,
        git=mock_git_client,
        github=mock_github_client,
        oc_manager=mock_oc_manager,
        db=mock_db,
        telegram=mock_telegram,
    )

    mock_oc_manager.kill_server.assert_called_once_with(12345)
    mock_git_client.cleanup_workspace.assert_called_once()


@pytest.mark.asyncio
async def test_idle_timeout_triggers_abort(
    sample_issue_data: IssueData,
    mock_git_client: MagicMock,
    mock_github_client: MagicMock,
    mock_oc_manager: MagicMock,
    mock_db: MagicMock,
    mock_telegram: MagicMock,
):
    from app.core.config import settings

    idle_timeout = settings.IDLE_TIMEOUT

    mock_oc_process = OpenCodeProcess(pid=12345, port=54321)
    mock_oc_manager.spawn_server.return_value = mock_oc_process

    async def mock_listen_events_slow(session_id):
        await asyncio.sleep(idle_timeout + 1)
        yield {}

    mock_oc_client = MagicMock()
    mock_oc_client.create_session = AsyncMock(return_value="session_abc")
    mock_oc_client.send_message = AsyncMock()
    mock_oc_client.listen_events = mock_listen_events_slow
    mock_oc_manager.get_client.return_value = mock_oc_client

    await execute_coding_task(
        issue_data=sample_issue_data,
        git=mock_git_client,
        github=mock_github_client,
        oc_manager=mock_oc_manager,
        db=mock_db,
        telegram=mock_telegram,
    )

    mock_github_client.post_comment.assert_called()
    mock_telegram.send_message.assert_called()
    mock_db.set_active_instance.assert_any_call(
        sample_issue_data.issue_number, port=None, status=TaskStatus.ABORTED
    )


@pytest.mark.asyncio
async def test_pr_creation_after_task_completion(
    sample_issue_data: IssueData,
    mock_git_client: MagicMock,
    mock_github_client: MagicMock,
    mock_oc_manager: MagicMock,
    mock_db: MagicMock,
    mock_telegram: MagicMock,
):
    mock_oc_process = OpenCodeProcess(pid=12345, port=54321)
    mock_oc_manager.spawn_server.return_value = mock_oc_process

    async def mock_listen_events(session_id):
        yield {
            "type": "message.updated",
            "properties": {
                "info": {
                    "id": "msg_1",
                    "role": "assistant",
                    "time": {"completed": 12345},
                }
            },
        }
        yield {
            "type": "message.part.updated",
            "properties": {
                "part": {
                    "messageID": "msg_1",
                    "type": "text",
                    "text": "[TASK_COMPLETED]",
                }
            },
        }
        yield {
            "type": "session.idle",
            "properties": {},
        }

    mock_oc_client = MagicMock()
    mock_oc_client.create_session = AsyncMock(return_value="session_abc")
    mock_oc_client.send_message = AsyncMock()
    mock_oc_client.listen_events = mock_listen_events
    mock_oc_manager.get_client.return_value = mock_oc_client

    await execute_coding_task(
        issue_data=sample_issue_data,
        git=mock_git_client,
        github=mock_github_client,
        oc_manager=mock_oc_manager,
        db=mock_db,
        telegram=mock_telegram,
    )

    mock_git_client.commit_and_push.assert_called_once()
    mock_github_client.create_pull_request.assert_called_once()
    mock_telegram.send_message.assert_called()


@pytest.mark.asyncio
async def test_concurrent_tasks_respected(
    sample_issue_data: IssueData,
    mock_git_client: MagicMock,
    mock_github_client: MagicMock,
    mock_oc_manager: MagicMock,
    mock_db: MagicMock,
    mock_telegram: MagicMock,
):
    from app.presentation.workers.broker import _concurrency_semaphore

    mock_oc_process = OpenCodeProcess(pid=12345, port=54321)
    mock_oc_manager.spawn_server.return_value = mock_oc_process

    async def mock_listen_events(session_id):
        yield {
            "type": "message.updated",
            "properties": {
                "info": {
                    "id": "msg_1",
                    "role": "assistant",
                    "time": {"completed": 12345},
                }
            },
        }
        yield {
            "type": "message.part.updated",
            "properties": {
                "part": {
                    "messageID": "msg_1",
                    "type": "text",
                    "text": "[TASK_COMPLETED]",
                }
            },
        }
        yield {
            "type": "session.idle",
            "properties": {},
        }

    mock_oc_client = MagicMock()
    mock_oc_client.create_session = AsyncMock(return_value="session_abc")
    mock_oc_client.send_message = AsyncMock()
    mock_oc_client.listen_events = mock_listen_events
    mock_oc_manager.get_client.return_value = mock_oc_client

    assert _concurrency_semaphore._value == settings.MAX_CONCURRENT_INSTANCES
