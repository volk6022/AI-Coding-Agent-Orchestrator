import asyncio
from contextlib import AsyncExitStack

from app.core.config import settings
from app.core.logger import get_logger
from app.domain.entities import IssueData, TaskState, TaskStatus
from app.domain.interfaces import (
    IGitHubClient,
    ILocalGitClient,
    IOpenCodeProcessManager,
    IStateRepository,
    ITelegramNotifier,
)

logger = get_logger(component="execute_task")

IDLE_TIMEOUT = settings.IDLE_TIMEOUT


async def execute_coding_task(
    issue_data: IssueData,
    git: ILocalGitClient,
    github: IGitHubClient,
    oc_manager: IOpenCodeProcessManager,
    db: IStateRepository,
    telegram: ITelegramNotifier,
) -> None:
    workspace_path = f"{settings.OPENCODE_BASE_DIR}/issue_{issue_data.issue_number}"
    branch_name = f"feature/issue_{issue_data.issue_number}"

    task_state = TaskState(
        issue_number=issue_data.issue_number,
        repo_url=issue_data.repo_url,
        branch_name=branch_name,
        status=TaskStatus.RUNNING,
        workspace_path=workspace_path,
    )
    await db.create_task(task_state)

    async with AsyncExitStack() as stack:
        stack.callback(git.cleanup_workspace, workspace_path)

        ssh_url = github.get_ssh_url(issue_data.repo_url)
        await git.clone_ssh(ssh_url, workspace_path)
        await git.create_branch(workspace_path, branch_name)

        oc_process = await oc_manager.spawn_server(workspace_path)
        stack.push_async_callback(lambda: oc_manager.kill_server(oc_process.pid))

        await db.set_active_instance(
            issue_data.issue_number,
            oc_process.port,
            status="RUNNING",
        )

        oc_client = oc_manager.get_client(oc_process.port)
        session_id = await oc_client.create_session(f"Issue #{issue_data.issue_number}")

        await db.set_active_instance(
            issue_data.issue_number,
            oc_process.port,
            session_id=session_id,
        )

        system_prompt = (
            f"Task: {issue_data.title}\n{issue_data.body}\n"
            "If you need help, ask a question. "
            "When done, output explicitly: [TASK_COMPLETED]."
        )
        await oc_client.send_message(session_id, system_prompt)

        task_completed = False

        try:
            async with asyncio.timeout(IDLE_TIMEOUT):
                async for event in oc_client.listen_events(session_id):
                    event_name = event.get("event_name", "")
                    data = event.get("data", {})

                    if event_name == "message_completed" and not data.get("has_commands"):
                        text = data.get("text", "")
                        if "[TASK_COMPLETED]" in text:
                            task_completed = True
                            break
                        else:
                            await github.post_comment(
                                issue_data.issue_number,
                                f"**Agent:**\n{text}",
                                issue_data.repo_url,
                            )
                            await db.set_active_instance(
                                issue_data.issue_number,
                                oc_process.port,
                                session_id=session_id,
                                status="WAITING_REPLY",
                            )
                            await telegram.send_message(
                                f"Agent asked a question in Issue #{issue_data.issue_number}"
                            )

                    elif event_name == "error":
                        error_msg = data.get("message", "Unknown error")
                        await telegram.send_message(f"OpenCode Error: {error_msg}")
                        break

        except TimeoutError:
            await github.post_comment(
                issue_data.issue_number,
                "Session aborted due to 12h idle timeout.",
                issue_data.repo_url,
            )
            await telegram.send_message(f"Task #{issue_data.issue_number} killed (Idle Timeout).")
            await db.set_active_instance(
                issue_data.issue_number,
                port=None,
                status="ABORTED",
            )
            return

        if task_completed:
            await git.commit_and_push_ssh(
                workspace_path,
                f"Fix #{issue_data.issue_number}",
                branch_name,
            )
            await github.create_pull_request(
                issue_data.issue_number,
                branch_name,
                issue_data.repo_url,
            )
            await db.set_active_instance(
                issue_data.issue_number,
                port=None,
                status="DONE",
            )
            await telegram.send_message(
                f"Success! PR created for Issue #{issue_data.issue_number}."
            )
