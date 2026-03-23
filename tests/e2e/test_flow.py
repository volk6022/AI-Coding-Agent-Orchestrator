import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from app.application.use_cases.execute_task import execute_coding_task
from app.application.use_cases.handle_reply import handle_user_reply
from app.domain.entities import IssueData, OpenCodeProcess, TaskStatus


@pytest.mark.asyncio
async def test_execute_coding_task_full_flow(
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
                    "text": "Working on it...",
                }
            },
        }
        yield {
            "type": "session.idle",
            "properties": {},
        }
        yield {
            "type": "message.updated",
            "properties": {
                "info": {
                    "id": "msg_2",
                    "role": "assistant",
                    "time": {"completed": 12345},
                }
            },
        }
        yield {
            "type": "message.part.updated",
            "properties": {
                "part": {
                    "messageID": "msg_2",
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

    mock_git_client.clone.assert_called_once()
    mock_git_client.create_branch.assert_called_once()
    mock_oc_manager.spawn_server.assert_called_once()
    mock_db.create_task.assert_called_once()


@pytest.mark.asyncio
async def test_agent_asks_question_creates_github_comment(
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
                    "text": "Need clarification?",
                }
            },
        }
        yield {
            "type": "session.idle",
            "properties": {},
        }
        yield {
            "type": "message.updated",
            "properties": {
                "info": {
                    "id": "msg_2",
                    "role": "assistant",
                    "time": {"completed": 12345},
                }
            },
        }
        yield {
            "type": "message.part.updated",
            "properties": {
                "part": {
                    "messageID": "msg_2",
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

    mock_github_client.post_comment.assert_called_once()
    mock_telegram.send_message.assert_called()


@pytest.mark.asyncio
async def test_handle_user_reply_routes_to_active_session(
    mock_oc_manager: MagicMock,
    mock_db: MagicMock,
    mock_telegram: MagicMock,
):
    from app.infrastructure.db.repository import StateRepository
    from app.domain.entities import TaskState

    mock_task_state = TaskState(
        issue_number=123,
        repo_url="owner/repo",
        branch_name="feature/issue_123",
        status=TaskStatus.WAITING_REPLY,
        active_port=54321,
        session_id="session_abc",
    )
    mock_db.get_task_state = AsyncMock(return_value=mock_task_state)

    mock_oc_client = MagicMock()
    mock_oc_client.send_reply = AsyncMock()
    mock_oc_manager.get_client.return_value = mock_oc_client

    await handle_user_reply(
        issue_number=123,
        comment_body="Here's the clarification you needed",
        oc_manager=mock_oc_manager,
        db=mock_db,
        telegram=mock_telegram,
    )

    mock_oc_client.send_reply.assert_called_once_with(
        "session_abc", "Here's the clarification you needed"
    )


@pytest.mark.asyncio
async def test_timeout_triggers_cleanup(
    sample_issue_data: IssueData,
    mock_git_client: MagicMock,
    mock_github_client: MagicMock,
    mock_oc_manager: MagicMock,
    mock_db: MagicMock,
    mock_telegram: MagicMock,
):
    mock_oc_process = OpenCodeProcess(pid=12345, port=54321)
    mock_oc_manager.spawn_server.return_value = mock_oc_process

    async def mock_listen_events_timeout(session_id):
        await asyncio.sleep(100)
        yield {}

    mock_oc_client = MagicMock()
    mock_oc_client.create_session = AsyncMock(return_value="session_abc")
    mock_oc_client.send_message = AsyncMock()
    mock_oc_client.listen_events = mock_listen_events_timeout
    mock_oc_manager.get_client.return_value = mock_oc_client

    await execute_coding_task(
        issue_data=sample_issue_data,
        git=mock_git_client,
        github=mock_github_client,
        oc_manager=mock_oc_manager,
        db=mock_db,
        telegram=mock_telegram,
    )

    mock_git_client.cleanup_workspace.assert_called_once()
    mock_oc_manager.kill_server.assert_called_once_with(12345)
